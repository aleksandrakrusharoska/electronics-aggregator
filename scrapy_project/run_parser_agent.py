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
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from supabase import create_client

from agents.parser_agent import AllProvidersExhausted, ParsedAdContent, build_parser, parse_ads_batch
from ads_scraper.normalize import MKD_PER_EUR

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


def _fetch_pending_for_source(sb, source, reparse, condition, fix_condition, is_electronics_backlog,
                               null_brand_backlog=False):
    """Page through pending rows for a single source. Querying one source at
    a time keeps the (OR filter + ORDER BY) query fast — running it across
    both sources at once times out at this table size.

    Offset pagination is what used to live here, and it silently rotted:
    past a few thousand rows deep it exceeds Supabase's statement timeout,
    the same failure found in the pazar3/reklama5 backfill spiders. Keyset
    (cursor) pagination replaces it below, except for --fix-condition, which
    deliberately has no ORDER BY (see that branch) so there's no column to
    build a cursor from — it keeps plain offset paging."""
    def base_query():
        # 6-year cutoff (looser than the pazar3 rescrape spider's 3-year
        # skip, not absent entirely): brand/model extraction on older ads
        # feeds the DepreciationChart and reference-price analytics, which
        # benefit from a longer historical range than 3 years — but the
        # pazar3 archive goes back to ~2015, and opening that whole pool to
        # LLM parsing at once would compete for the same daily quota as
        # parsing today's actual new arrivals, the higher-priority backlog
        # right now. 6 years is a temporary middle ground while that
        # backlog is being actively cleared unattended; revisit once it's
        # caught up. Ads without a description yet (stuck behind the
        # rescrape spider's own age skip) still won't reach here either
        # way, since that's filtered on next.
        old_cutoff = (datetime.now(timezone.utc) - timedelta(days=6 * 365)).date().isoformat()
        q = (
            sb.table("ads")
            .select("ad_url, title, description, condition, seller_type, price_mkd, posted_date, scraped_at")
            .not_.is_("description", "null")
            .neq("description", "")
            .or_(f"posted_date.gte.{old_cutoff},posted_date.is.null")
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
        elif null_brand_backlog:
            # One-off backfill: already-parsed rows that came out brand=null,
            # including ones stuck there by the JSON-truncation bug fixed
            # alongside this flag (see _parse_json_response) — worth a single
            # retry now that the repair can recover them. Not part of normal
            # runs since a null brand is often a legitimate, permanent result
            # and retrying it every run would burn quota for nothing.
            q = q.not_.is_("llm_parsed_at", "null").is_("brand", "null")
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
        return q

    if fix_condition:
        # No ORDER BY on purpose: combined with the NOT IN filter above,
        # adding one times out, and row order doesn't matter for a one-off
        # cleanup pass anyway. Without a sort column there's nothing to
        # build a keyset cursor from.
        #
        # This used to page through with an incrementing OFFSET, which is
        # broken here specifically: each fixed row's condition becomes
        # canonical and drops out of this same NOT IN filter, shrinking the
        # matching set while the loop is still consuming it. An offset page
        # fetched after earlier rows were removed silently skips whatever
        # shifted into the range already "consumed" by a prior page —
        # verified in production: a run reported done after 534 fixes, but
        # ~468 non-canonical rows this exact query should have covered were
        # still sitting there untouched. Fetching everything in one shot
        # sidesteps that: there's no offset to drift, since the query never
        # runs a second time against a set the same run's own writes have
        # since shrunk. One-off cleanup at this table's scale (low
        # thousands at most) comfortably fits a single page.
        rows = _execute_with_retry(base_query().limit(20000)).data
        yield from rows
        return
        return

    if is_electronics_backlog or null_brand_backlog:
        # ad_url ordering, not posted_date — same reasoning as the
        # is_electronics backlog above: newest-first would let today's
        # new ads perpetually cut in line ahead of this backlog. ad_url is
        # unique, so a plain single-column cursor is enough.
        last_url = None
        while True:
            q = base_query().order("ad_url")
            if last_url is not None:
                q = q.gt("ad_url", last_url)
            rows = _execute_with_retry(q.limit(FETCH_BATCH)).data
            if not rows:
                return
            yield from rows
            if len(rows) < FETCH_BATCH:
                return
            last_url = rows[-1]["ad_url"]
        return

    # Prioritize genuinely recent listings (posted_date) over rows that were
    # merely scraped/inserted recently — backfill inserts old ads today, so
    # scraped_at would wrongly jump them ahead of the queue. scraped_at
    # breaks ties (posted_date has no time component). Neither column is
    # unique alone, so the cursor is the pair: strictly "older" than the
    # last row's (posted_date, scraped_at).
    last_posted, last_scraped, started = None, None, False
    while True:
        q = base_query().order("posted_date", desc=True, nullsfirst=False).order("scraped_at", desc=True)
        if started:
            if last_posted is not None:
                q = q.or_(
                    f"posted_date.lt.{last_posted},"
                    f"and(posted_date.eq.{last_posted},scraped_at.lt.{last_scraped})"
                )
            else:
                # NULLS LAST means a null last_posted means every non-null
                # posted_date row has already been consumed — everything
                # left has posted_date IS NULL, so just tie-break on scraped_at.
                q = q.is_("posted_date", "null").lt("scraped_at", last_scraped)
        rows = _execute_with_retry(q.limit(FETCH_BATCH)).data
        if not rows:
            return
        yield from rows
        if len(rows) < FETCH_BATCH:
            return
        last_row = rows[-1]
        last_posted, last_scraped, started = last_row["posted_date"], last_row["scraped_at"], True


def fetch_pending(sb, source=None, reparse=False, limit=None, condition=None, fix_condition=False,
                   is_electronics_backlog=False, null_brand_backlog=False):
    """Yield rows that need LLM parsing, including existing condition/seller_type to avoid overwriting.

    Round-robins between sources (when source is not fixed) so one source's
    backlog can't starve the other."""
    sources = [source] if source else ["pazar3", "reklama5"]
    generators = [
        _fetch_pending_for_source(sb, s, reparse, condition, fix_condition, is_electronics_backlog,
                                   null_brand_backlog)
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


def _build_update(row: dict, parsed: ParsedAdContent) -> dict:
    clean_specs = {k: v for k, v in (parsed.specs or {}).items() if v and v.strip()}
    update: dict = {
        "ad_url": row["ad_url"],
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

    # Sellers sometimes retype the price inside the description, and it
    # can disagree with the ad's own structured price field (a currency
    # mix-up, a typo, an installment amount mistakenly used as the listed
    # price). Trust the explicit statement over the structured field once
    # they disagree by more than 2x either way — small gaps are normal, a
    # >2x/<0.5x gap is the signature of exactly the bogus-price patterns
    # this exists to catch.
    if parsed.stated_price_amount and parsed.stated_price_currency:
        stated_mkd = (
            parsed.stated_price_amount * MKD_PER_EUR
            if parsed.stated_price_currency == "EUR"
            else parsed.stated_price_amount
        )
        current_mkd = row.get("price_mkd")
        if not current_mkd or current_mkd <= 0:
            update["price_mkd"] = round(stated_mkd, 2)
            update["price_eur"] = round(stated_mkd / MKD_PER_EUR, 2)
            log.info("  price filled in from description: %.2f MKD (stated %s %s)",
                     stated_mkd, parsed.stated_price_amount, parsed.stated_price_currency)
        else:
            ratio = stated_mkd / current_mkd
            if ratio < 0.5 or ratio > 2.0:
                update["price_mkd"] = round(stated_mkd, 2)
                update["price_eur"] = round(stated_mkd / MKD_PER_EUR, 2)
                log.info("  price corrected from description: %.2f -> %.2f MKD (stated %s %s)",
                         current_mkd, stated_mkd, parsed.stated_price_amount, parsed.stated_price_currency)
    return update


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
    parser.add_argument("--null-brand-backlog", action="store_true",
                         help="One-off backfill: retry already-parsed ads with brand=null (worth another shot "
                              "after a parser fix that could recover some of them)")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("Missing SUPABASE_URL or SUPABASE_KEY in environment / .env")

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    llm_parser = build_parser()
    log.info("Connected to Supabase. LLM parser ready (%s).", os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"))

    processed = 0
    flush_every = 10
    pending_updates: list[dict] = []
    # Batching N ads into one LLM call amortizes the system prompt's fixed
    # token cost across all N instead of paying it per ad — measured at
    # ~55% fewer total tokens for a batch of 5 vs 5 separate calls.
    batch_size = int(os.getenv("PARSE_BATCH_SIZE", "5"))
    batch_rows: list[dict] = []
    exhausted = False

    def process_batch(rows: list[dict]) -> bool:
        """Parse one batch and queue its updates. Returns False if every
        provider is exhausted for the day (caller should stop)."""
        nonlocal processed
        items = [(r.get("title") or "", r.get("description") or "") for r in rows]
        log.info("[%d-%d] Parsing batch of %d", processed + 1, processed + len(rows), len(rows))
        try:
            results = parse_ads_batch(items, llm_parser)
        except AllProvidersExhausted:
            log.warning("All LLM providers exhausted for today — stopping early (processed %d).", processed)
            return False
        # 30 req/min free-tier cap applies per provider, not to this loop as
        # a whole — round-robin across N providers means any single one is
        # only reused every N calls, so the wait needed to stay under its
        # own limit shrinks as N grows. 1.5s clears that even at just 2
        # providers; with 13 (11 Groq + 2 Gemini) there's a wide margin.
        time.sleep(1.5)
        for row, parsed in zip(rows, results):
            pending_updates.append(_build_update(row, parsed))
            processed += 1
        return True

    try:
        for row in fetch_pending(sb, source=args.source, reparse=args.reparse, limit=args.limit,
                                  condition=args.condition, fix_condition=args.fix_condition,
                                  is_electronics_backlog=args.is_electronics_backlog,
                                  null_brand_backlog=args.null_brand_backlog):
            batch_rows.append(row)
            if len(batch_rows) < batch_size:
                continue

            if not process_batch(batch_rows):
                exhausted = True
                batch_rows = []
                break
            batch_rows = []

            if len(pending_updates) >= flush_every:
                update_batch(sb, pending_updates)
                log.info("  -> flushed %d updates to Supabase", len(pending_updates))
                pending_updates.clear()

        if batch_rows and not exhausted:
            # Trailing partial batch (fewer than batch_size ads left once
            # fetch_pending ran out, e.g. --limit not a multiple of it).
            process_batch(batch_rows)
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
