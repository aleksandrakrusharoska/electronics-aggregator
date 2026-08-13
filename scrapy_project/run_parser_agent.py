"""
Batch-processes ads in Supabase with the LLM parser agent.

Reads ads where:
  - description is not null/empty
  - llm_parsed_at is null (not yet processed), OR already processed but
    missing brand or is_electronics (legacy rows from before those fields
    were added)

Writes back: specs, condition, brand, model, seller_notes, phone,
             delivery_available, seller_type, is_electronics, llm_parsed_at

Usage:
    python run_parser_agent.py              # process all pending
    python run_parser_agent.py --limit 20  # test run with 20 ads
    python run_parser_agent.py --source pazar3  # only one source
    python run_parser_agent.py --reparse   # reparse already-processed ads
    python run_parser_agent.py --reparse --condition New  # reparse only New-condition ads (for reference prices)
    python run_parser_agent.py --fix-condition  # one-off: normalize non-canonical condition values
    python run_parser_agent.py --is-electronics-backlog  # one-off: backfill is_electronics on old ads
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client

from agents.parser_agent import AllProvidersExhausted, ParsedAdContent, build_parser, parse_ad

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
FETCH_BATCH = 50  # rows per Supabase page
MAX_RETRIES = 5

CANONICAL_CONDITIONS = {"New", "Used - Like New", "Used - Good", "Used - Fair", "Used", "For parts"}


def _execute_with_retry(query):
    """This table sees frequent transient statement timeouts under
    concurrent load from other scheduled jobs — retry a few times with
    backoff before giving up."""
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


def _fetch_pending_for_source(sb, source, reparse, condition, fix_condition, is_electronics_backlog):
    """Page through pending rows for a single source. Querying one source at
    a time keeps the (OR filter + ORDER BY) query fast — running it across
    both sources at once times out at this table size."""
    offset = 0
    while True:
        q = (
            sb.table("ads")
            .select("ad_url, title, description, condition, seller_type")
            .not_.is_("description", "null")
            .neq("description", "")
            .eq("source", source)
        )
        if is_electronics_backlog:
            # One-off backfill: legacy ads parsed before is_electronics
            # existed. Ordered by ad_url (not posted_date) below, since the
            # normal newest-first ordering means this backlog never gets a
            # turn — today's new ads always sort ahead of it.
            q = q.is_("is_electronics", "null")
        elif fix_condition:
            # One-off cleanup: rows with a non-null condition that isn't one
            # of our canonical categories (raw scraped free text, typos,
            # non-condition junk like a price note) — regardless of whether
            # they've already been parsed for brand/model.
            q = q.not_.is_("condition", "null").not_.in_("condition", sorted(CANONICAL_CONDITIONS))
        elif not reparse:
            # Only rows never attempted. Deliberately NOT "or brand is null":
            # a null brand is often a legitimate, permanent LLM result (ad
            # genuinely doesn't name a brand, or every provider failed on it
            # even after JSON-repair) — re-including those here would queue
            # the same doomed ad on every single run forever, burning a
            # request's worth of quota each time for no gain. Legacy rows
            # that predate the brand/is_electronics fields get backfilled
            # deliberately via --reparse or --is-electronics-backlog instead.
            q = q.is_("llm_parsed_at", "null")
        if condition:
            q = q.eq("condition", condition)
        if is_electronics_backlog:
            q = q.order("ad_url")
        elif not fix_condition:
            # Prioritize genuinely recent listings (posted_date) over rows
            # that were merely scraped/inserted recently — backfill inserts
            # old ads today, so scraped_at would wrongly jump them ahead of
            # the queue. scraped_at breaks ties (posted_date has no time
            # component). Skipped for --fix-condition: combined with the
            # NOT IN filter, ordering times out, and order doesn't matter
            # for a one-off cleanup pass anyway.
            q = q.order("posted_date", desc=True, nullsfirst=False).order("scraped_at", desc=True)
        result = _execute_with_retry(q.range(offset, offset + FETCH_BATCH - 1))
        rows = result.data
        if not rows:
            return
        yield from rows
        if len(rows) < FETCH_BATCH:
            return
        offset += FETCH_BATCH


def fetch_pending(sb, source=None, reparse=False, limit=None, condition=None, fix_condition=False,
                   is_electronics_backlog=False):
    """Yield rows that need LLM parsing, including existing condition/seller_type to avoid overwriting.

    Round-robins between sources (when source is not fixed) so one source's
    backlog can't starve the other."""
    sources = [source] if source else ["pazar3", "reklama5"]
    generators = [
        _fetch_pending_for_source(sb, s, reparse, condition, fix_condition, is_electronics_backlog)
        for s in sources
    ]
    fetched = 0
    while generators:
        for gen in list(generators):
            try:
                row = next(gen)
            except StopIteration:
                generators.remove(gen)
                continue
            except Exception as exc:
                # A persistent DB failure (retries exhausted) for this
                # source's query shouldn't kill the whole run — drop just
                # this source from the round-robin and keep going with
                # whatever else is still fetching. Whatever's already been
                # processed this run stays flushed either way.
                log.error("Fetching pending rows failed for this source, skipping it for the rest of this run: %s", exc)
                generators.remove(gen)
                continue
            yield row
            fetched += 1
            if limit is not None and fetched >= limit:
                return


def update_batch(sb, updates: list[dict]):
    try:
        _execute_with_retry(sb.table("ads").upsert(updates, on_conflict="ad_url"))
    except Exception as exc:
        log.error("Supabase upsert failed: %s", exc)


def main():
    parser = argparse.ArgumentParser(description="Run LLM parser agent on Supabase ads")
    parser.add_argument("--limit", type=int, default=None, help="Max ads to process")
    parser.add_argument("--source", default=None, choices=["reklama5", "pazar3"], help="Filter by source")
    parser.add_argument("--reparse", action="store_true", help="Re-run even on already-parsed ads")
    parser.add_argument("--condition", default=None, help="Only process ads with this condition (e.g. New)")
    parser.add_argument("--fix-condition", action="store_true",
                         help="One-off cleanup: reparse ads whose condition isn't one of the canonical categories")
    parser.add_argument("--is-electronics-backlog", action="store_true",
                         help="One-off backfill: process ads missing is_electronics, ordered by ad_url instead "
                              "of posted_date so the backlog isn't perpetually starved by newer ads")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("Missing SUPABASE_URL or SUPABASE_KEY in environment / .env")

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    llm_parser = build_parser()
    log.info("Connected to Supabase. LLM parser ready (%s).", os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"))

    processed = 0
    flush_every = 10
    pending_updates: list[dict] = []

    try:
        for row in fetch_pending(sb, source=args.source, reparse=args.reparse, limit=args.limit,
                                  condition=args.condition, fix_condition=args.fix_condition,
                                  is_electronics_backlog=args.is_electronics_backlog):
            ad_url = row["ad_url"]
            title = row.get("title") or ""
            description = row.get("description") or ""

            log.info("[%d] Parsing: %s", processed + 1, title[:60])
            try:
                parsed: ParsedAdContent = parse_ad(title, description, llm_parser)
            except AllProvidersExhausted:
                log.warning("All LLM providers exhausted for today — stopping early (processed %d).", processed)
                break
            time.sleep(4)  # stay under Groq free tier 30 req/min limit

            # Filter empty-string values from specs
            clean_specs = {k: v for k, v in (parsed.specs or {}).items() if v and v.strip()}

            update: dict = {
                "ad_url": ad_url,
                "specs": clean_specs,
                "brand": parsed.brand,
                "model": parsed.model,
                "seller_notes": parsed.seller_notes,
                "phone": parsed.phone,
                "delivery_available": bool(parsed.delivery_available),
                "is_electronics": bool(parsed.is_electronics),
                "llm_parsed_at": datetime.now(timezone.utc).isoformat(),
            }
            # condition: keep the existing value if it's already one of our
            # canonical categories (a seller-selected dropdown value is a
            # stronger signal than an LLM guess) — otherwise normalize/fill it.
            if row.get("condition") not in CANONICAL_CONDITIONS and parsed.condition:
                update["condition"] = parsed.condition
            # seller_type: only fill if the spider didn't already capture it
            if not row.get("seller_type") and parsed.seller_type:
                update["seller_type"] = parsed.seller_type

            pending_updates.append(update)
            processed += 1

            if len(pending_updates) >= flush_every:
                update_batch(sb, pending_updates)
                log.info("  -> flushed %d updates to Supabase", len(pending_updates))
                pending_updates.clear()
    except Exception:
        # Whatever happens, don't lose progress already made this run — the
        # rows accumulated in pending_updates below still get flushed after
        # this block, same as a clean finish.
        log.exception("Unexpected error — stopping early (processed %d so far). Flushing what's pending.", processed)

    if pending_updates:
        update_batch(sb, pending_updates)
        log.info("  -> flushed final %d updates to Supabase", len(pending_updates))

    log.info("Done. Processed %d ads.", processed)


if __name__ == "__main__":
    main()
