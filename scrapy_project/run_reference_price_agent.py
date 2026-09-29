"""
Batch-computes reference "New" prices and good-deal flags for ads in Supabase.

Reads every product-type ad with a matched model and a price (across both
sources) — service/wanted posts (e.g. phone buyback ads) are excluded even
if the LLM parser happened to fill in a brand+model on one, since they're
not a "this exact item at this price" listing a reference price comparison
would make sense for.

Writes back:
  models  market_new_price_mkd, market_sample_size  (per model)
  ad_analysis  reference_source, price_vs_new_ratio, good_price_deal  (per ad)

Usage:
    python run_reference_price_agent.py
"""
import logging
import os
import sys
import time

from dotenv import load_dotenv
from supabase import create_client

from agents.reference_price_agent import _build_marketplace_index, _norm, compute_reference_prices
from lookups import get_lookups

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
    """Every priced product ad with a matched model, with brand/model names
    from ads_view, one source at a time (querying both at once times out at
    this table size)."""
    lookups = get_lookups(sb)
    rows = []
    for source in ("pazar3", "reklama5"):
        source_id = lookups.source_id(source, create=False)
        if source_id is None:
            continue
        last_url = None
        while True:
            q = (
                sb.table("ads_view")
                .select("ad_url, source_id, brand_id, model_id, brand, model, condition, price_mkd, title")
                .eq("source_id", source_id)
                .eq("ad_type", "product")
                .not_.is_("model_id", "null")
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


def fetch_llm_estimates(sb) -> dict[str, float]:
    """{'brand|model' (normalized): estimated new price}, skipping models the
    LLM couldn't estimate (NULL) — see populate_price_estimates.py."""
    estimates, offset = {}, 0
    while True:
        batch = _execute_with_retry(
            sb.table("models")
            .select("name, estimated_new_price_mkd, brands(name)")
            .not_.is_("estimated_new_price_mkd", "null")
            .order("model_id")
            .range(offset, offset + FETCH_BATCH - 1)
        ).data
        for row in batch:
            estimates[f'{_norm(row["brands"]["name"])}|{_norm(row["name"])}'] = float(row["estimated_new_price_mkd"])
        if len(batch) < FETCH_BATCH:
            return estimates
        offset += FETCH_BATCH


def market_prices_per_model(ads: list[dict]) -> list[dict]:
    """models rows with the marketplace median for every model seen in `ads`
    (None where there aren't enough New listings, so stale values get
    cleared too)."""
    index = _build_marketplace_index(ads)
    models = {}
    for ad in ads:
        key = f'{_norm(ad["brand"])}|{_norm(ad["model"])}'
        median, size = index.get(key, (None, None))
        models[ad["model_id"]] = {
            "model_id": ad["model_id"], "brand_id": ad["brand_id"], "name": ad["model"],
            "market_new_price_mkd": median, "market_sample_size": size,
        }
    return list(models.values())


def update_models(sb, rows: list[dict]):
    try:
        _execute_with_retry(sb.table("models").upsert(rows, on_conflict="model_id"))
    except Exception as exc:
        log.error("Saving market prices failed: %s", exc)


def update_batch(sb, updates: list[dict]):
    try:
        _execute_with_retry(sb.table("ad_analysis").upsert(updates, on_conflict="ad_url"))
    except Exception as exc:
        log.error("Supabase upsert failed: %s", exc)


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("Missing SUPABASE_URL or SUPABASE_KEY in environment / .env")

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    log.info("Connected to Supabase.")

    ads = fetch_priced_ads(sb)
    log.info("Total priced product ads with a model: %d", len(ads))

    llm_estimates = fetch_llm_estimates(sb)
    log.info("Total cached LLM price estimates: %d", len(llm_estimates))

    model_rows = market_prices_per_model(ads)
    for i in range(0, len(model_rows), UPDATE_BATCH):
        update_models(sb, model_rows[i:i + UPDATE_BATCH])
    log.info("Updated market prices for %d models.", len(model_rows))

    results = [
        {
            "ad_url": r["ad_url"],
            "reference_source": r["reference_source"],
            "price_vs_new_ratio": r["price_vs_new_ratio"],
            "good_price_deal": r["good_price_deal"],
        }
        for r in compute_reference_prices(ads, llm_estimates)
    ]

    updated = 0
    for i in range(0, len(results), UPDATE_BATCH):
        batch = results[i:i + UPDATE_BATCH]
        update_batch(sb, batch)
        updated += len(batch)
        log.info("  -> flushed %d/%d updates to Supabase", updated, len(results))

    log.info("Done. Updated %d ads.", updated)


if __name__ == "__main__":
    main()
