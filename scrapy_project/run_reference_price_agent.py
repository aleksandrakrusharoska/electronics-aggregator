"""
Batch-computes reference "New" prices and good-deal flags for ads in Supabase.

Reads every product-type ad with a matched brand+model+price_mkd (across
both sources) — service/wanted posts (e.g. phone buyback ads) are excluded
even if the LLM parser happened to fill in a brand+model on one, since
they're not a "this exact item at this price" listing a reference price
comparison would make sense for. Also reads the full Setec retail catalog,
computes reference prices, and writes back: reference_new_price_mkd,
reference_sample_size, reference_source, price_vs_new_ratio, good_price_deal

Usage:
    python run_reference_price_agent.py
"""
import logging
import os
import sys
import time

from dotenv import load_dotenv
from supabase import create_client

from agents.reference_price_agent import compute_reference_prices

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
UPDATE_BATCH = 200
MAX_RETRIES = 3


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


def fetch_priced_ads(sb) -> list[dict]:
    """Fetch ad_url, brand, model, condition, price_mkd, title for every matched ad,
    one source at a time (querying both at once times out at this table size)."""
    rows = []
    for source in ("pazar3", "reklama5"):
        last_url = None
        while True:
            q = (
                sb.table("ads")
                .select("ad_url, brand, model, condition, price_mkd, title")
                .eq("source", source)
                .eq("ad_type", "product")
                .not_.is_("brand", "null")
                .not_.is_("model", "null")
                .not_.is_("price_mkd", "null")
                .order("ad_url")
            )
            if last_url is not None:
                q = q.gt("ad_url", last_url)
            batch = _execute_with_retry(q.limit(FETCH_BATCH)).data
            if not batch:
                break
            rows.extend(batch)
            log.info("Loaded %d %s ads so far...", len(rows), source)
            if len(batch) < FETCH_BATCH:
                break
            last_url = batch[-1]["ad_url"]
    return rows


def fetch_retail_prices(sb) -> list[dict]:
    rows = []
    last_url = None
    while True:
        q = sb.table("retail_prices").select("url, brand, title, price_mkd").order("url")
        if last_url is not None:
            q = q.gt("url", last_url)
        batch = _execute_with_retry(q.limit(FETCH_BATCH)).data
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < FETCH_BATCH:
            break
        last_url = batch[-1]["url"]
    return rows


def update_batch(sb, updates: list[dict]):
    try:
        _execute_with_retry(sb.table("ads").upsert(updates, on_conflict="ad_url"))
    except Exception as exc:
        log.error("Supabase upsert failed: %s", exc)


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("Missing SUPABASE_URL or SUPABASE_KEY in environment / .env")

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    log.info("Connected to Supabase.")

    ads = fetch_priced_ads(sb)
    log.info("Total ads with brand+model+price_mkd: %d", len(ads))

    retail_prices = fetch_retail_prices(sb)
    log.info("Total retail_prices rows: %d", len(retail_prices))

    results = compute_reference_prices(ads, retail_prices)

    updated = 0
    for i in range(0, len(results), UPDATE_BATCH):
        batch = results[i:i + UPDATE_BATCH]
        update_batch(sb, batch)
        updated += len(batch)
        log.info("  -> flushed %d/%d updates to Supabase", updated, len(results))

    log.info("Done. Updated %d ads.", updated)


if __name__ == "__main__":
    main()
