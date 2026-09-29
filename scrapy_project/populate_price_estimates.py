"""
Finds models (brand + model) used by product ads that don't have an LLM
new-price estimate yet (models.estimated_at is null) and fills the gap via
price_estimate_agent's estimate_prices_batch() — one LLM call per batch of
models, not per ad, since many ads share the same model.

Run this before run_reference_price_agent.py (see reference_price.yml) so
its LLM tier has fresh estimates for anything new since the last run.
Models the LLM can't confidently estimate still get estimated_at set (with
a NULL price), so they aren't retried every single run.

Usage:
    python populate_price_estimates.py
"""
import logging
import os
import sys
import time
from datetime import datetime, timezone

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


def fetch_models_in_use(sb) -> set[int]:
    """model_id of every model currently used by a product ad."""
    in_use, last_url = set(), None
    while True:
        q = (
            sb.table("ad_analysis")
            .select("ad_url, model_id")
            .eq("ad_type", "product")
            .not_.is_("model_id", "null")
            .order("ad_url")
        )
        if last_url is not None:
            q = q.gt("ad_url", last_url)
        batch = _execute_with_retry(q.limit(FETCH_BATCH)).data
        if not batch:
            return in_use
        in_use.update(row["model_id"] for row in batch)
        if len(batch) < FETCH_BATCH:
            return in_use
        last_url = batch[-1]["ad_url"]


def fetch_unestimated_models(sb) -> list[dict]:
    """Models never sent to the LLM yet, with their brand name."""
    models, offset = [], 0
    while True:
        batch = _execute_with_retry(
            sb.table("models")
            .select("model_id, brand_id, name, brands(name)")
            .is_("estimated_at", "null")
            .order("model_id")
            .range(offset, offset + FETCH_BATCH - 1)
        ).data
        models.extend(batch)
        if len(batch) < FETCH_BATCH:
            return models
        offset += FETCH_BATCH


def save_estimates(sb, rows: list[dict]):
    try:
        _execute_with_retry(sb.table("models").upsert(rows, on_conflict="model_id"))
    except Exception as exc:
        log.error("Saving estimates failed for batch of %d: %s", len(rows), exc)


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("Missing SUPABASE_URL or SUPABASE_KEY in environment / .env")

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    log.info("Connected to Supabase.")

    in_use = fetch_models_in_use(sb)
    missing = [m for m in fetch_unestimated_models(sb) if m["model_id"] in in_use]
    log.info("Models used by product ads: %d, still without an estimate: %d", len(in_use), len(missing))
    if not missing:
        log.info("Nothing to do.")
        return

    parser = build_price_estimate_parser()
    written = 0
    for i in range(0, len(missing), ESTIMATE_BATCH):
        chunk = missing[i:i + ESTIMATE_BATCH]
        try:
            prices = estimate_prices_batch([(m["brands"]["name"], m["name"]) for m in chunk], parser=parser)
        except AllProvidersExhausted:
            log.warning("All providers exhausted/failing — stopping early (wrote %d/%d).",
                        written, len(missing))
            break
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            {"model_id": m["model_id"], "brand_id": m["brand_id"], "name": m["name"],
             "estimated_new_price_mkd": p, "estimated_at": now}
            for m, p in zip(chunk, prices)
        ]
        save_estimates(sb, rows)
        written += len(rows)
        log.info("  -> estimated %d/%d pairs", written, len(missing))
        time.sleep(1.5)

    log.info("Done. Estimated %d models (nulls included, for models the LLM couldn't recognize).", written)


if __name__ == "__main__":
    main()
