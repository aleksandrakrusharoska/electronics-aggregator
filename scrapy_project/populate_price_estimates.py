"""
Finds unique (brand, model) pairs among ads that don't yet have a cached
LLM price estimate in model_price_estimates, and fills the gap via
price_estimate_agent's estimate_prices_batch() — one LLM call per batch of
unique pairs, not per ad, since many ads share the same model.

Run this before run_reference_price_agent.py (see reference_price.yml) so
its tier-3 lookup has fresh cache entries for anything new since the last
run. Pairs the LLM can't confidently estimate are cached as NULL too, so
they aren't retried every single run — same "checked, genuinely absent"
sentinel pattern as pazar3_spider's listing_type='none'.

Usage:
    python populate_price_estimates.py
"""
import logging
import os
import sys
import time

from dotenv import load_dotenv
from supabase import create_client

from agents.parser_agent import AllProvidersExhausted
from agents.price_estimate_agent import build_price_estimate_parser, estimate_prices_batch

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
FETCH_BATCH = 1000
MAX_RETRIES = 3
# Pairs per LLM call — keeps prompt+response comfortably within
# reasoning_effort='low' output limits (same batching rationale as
# run_parser_agent.py's PARSE_BATCH_SIZE, just a bigger batch since each
# item here is two short strings, not a full title+description).
ESTIMATE_BATCH = 25


def _norm(s):
    return s.strip().lower() if s else ''


def _execute_with_retry(query):
    """The ads table sees frequent transient statement timeouts under
    concurrent load from other scheduled jobs — same retry pattern as
    run_reference_price_agent.py's _execute_with_retry."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return query.execute()
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = 2 ** attempt
            log.warning("Query failed (attempt %d/%d): %s — retrying in %ds",
                        attempt, MAX_RETRIES, exc, wait)
            time.sleep(wait)


def fetch_distinct_pairs(sb) -> set[tuple[str, str]]:
    """Every (brand, model) pair currently in use across product ads,
    lowercased — matches reference_price_agent.py's own key normalization."""
    pairs = set()
    for source in ("pazar3", "reklama5"):
        last_url = None
        while True:
            q = (
                sb.table("ads")
                .select("ad_url, brand, model")
                .eq("source", source)
                .eq("ad_type", "product")
                .not_.is_("brand", "null")
                .not_.is_("model", "null")
                .order("ad_url")
            )
            if last_url is not None:
                q = q.gt("ad_url", last_url)
            batch = _execute_with_retry(q.limit(FETCH_BATCH)).data
            if not batch:
                break
            for row in batch:
                b, m = _norm(row["brand"]), _norm(row["model"])
                if b and m:
                    pairs.add((b, m))
            if len(batch) < FETCH_BATCH:
                break
            last_url = batch[-1]["ad_url"]
        log.info("Distinct pairs so far after %s: %d", source, len(pairs))
    return pairs


def fetch_cached_pairs(sb) -> set[tuple[str, str]]:
    """Pairs already in model_price_estimates, including ones cached as
    NULL (LLM couldn't estimate) — those don't need retrying either."""
    cached = set()
    while True:
        # Plain offset pagination is safe here: this is a read-only pass
        # over a table nothing else is concurrently deleting from mid-loop
        # (contrast pazar3_rescrape_spider's --fix-condition bug, where rows
        # dropped out of the same filter as they were fixed).
        batch = _execute_with_retry(
            sb.table("model_price_estimates")
            .select("brand, model")
            .range(len(cached), len(cached) + FETCH_BATCH - 1)
        ).data
        if not batch:
            break
        for row in batch:
            cached.add((_norm(row["brand"]), _norm(row["model"])))
        if len(batch) < FETCH_BATCH:
            break
    return cached


def upsert_estimates(sb, rows: list[dict]):
    try:
        _execute_with_retry(sb.table("model_price_estimates").upsert(rows, on_conflict="brand,model"))
    except Exception as exc:
        log.error("Upsert failed for batch of %d: %s", len(rows), exc)


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("Missing SUPABASE_URL or SUPABASE_KEY in environment / .env")

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    log.info("Connected to Supabase.")

    all_pairs = fetch_distinct_pairs(sb)
    log.info("Total distinct brand+model pairs in ads: %d", len(all_pairs))

    cached = fetch_cached_pairs(sb)
    log.info("Already cached (including known-unrecognized): %d", len(cached))

    missing = sorted(all_pairs - cached)
    log.info("Missing estimates to fetch: %d", len(missing))
    if not missing:
        log.info("Nothing to do.")
        return

    parser = build_price_estimate_parser()
    written = 0
    for i in range(0, len(missing), ESTIMATE_BATCH):
        chunk = missing[i:i + ESTIMATE_BATCH]
        try:
            prices = estimate_prices_batch(chunk, parser=parser)
        except AllProvidersExhausted:
            log.warning("All providers exhausted/failing — stopping early (wrote %d/%d).",
                        written, len(missing))
            break
        rows = [
            {"brand": b, "model": m, "estimated_new_price_mkd": p}
            for (b, m), p in zip(chunk, prices)
        ]
        upsert_estimates(sb, rows)
        written += len(rows)
        log.info("  -> estimated %d/%d pairs", written, len(missing))
        time.sleep(1.5)

    log.info("Done. Wrote %d estimate rows (nulls included, for pairs the LLM couldn't recognize).", written)


if __name__ == "__main__":
    main()
