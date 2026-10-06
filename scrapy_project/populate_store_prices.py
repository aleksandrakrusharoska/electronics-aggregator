"""
Looks up the price of a NEW unit in Macedonian stores (store_price_agent)
for every model used by a product ad that was never checked or was last
checked more than STALE_DAYS ago, and stores it on `models`
(store_new_price_mkd, store_count, store_sources, store_checked_at).

Models with no store price still get store_checked_at, so they're retried
only once the check goes stale — prices and assortments change, so stale
checks are redone (about a seventh of the models per day at STALE_DAYS=7).

Run this before run_reference_price_agent.py (see reference_price.yml).

Usage:
    python populate_store_prices.py              # unchecked + stale models
    python populate_store_prices.py --limit 200  # at most 200 models this run
"""
import argparse
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from supabase import create_client

from agents.parser_agent import build_parser
from agents.store_price_agent import find_store_price

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
FETCH_BATCH = 1000
MAX_RETRIES = 3
STALE_DAYS = 7
WORKERS = 4      # models looked up in parallel (each one already queries 5 stores at once)
SAVE_EVERY = 50


def _execute_with_retry(query):
    """Same retry pattern as populate_price_estimates.py: the ads tables see
    transient statement timeouts under load from other scheduled jobs."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return query.execute()
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = 2 ** attempt
            log.warning("Query failed (attempt %d/%d): %s — retrying in %ds", attempt, MAX_RETRIES, exc, wait)
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


def fetch_models_to_check(sb) -> list[dict]:
    """Never checked first, then the stalest."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)).isoformat()
    models, offset = [], 0
    while True:
        batch = _execute_with_retry(
            sb.table("models")
            .select("model_id, brand_id, name, store_checked_at, brands(name)")
            .or_(f"store_checked_at.is.null,store_checked_at.lt.{cutoff}")
            .order("store_checked_at", desc=False, nullsfirst=True)
            .order("model_id")
            .range(offset, offset + FETCH_BATCH - 1)
        ).data
        models.extend(batch)
        if len(batch) < FETCH_BATCH:
            return models
        offset += FETCH_BATCH


def save(sb, rows: list[dict]):
    if not rows:
        return
    try:
        _execute_with_retry(sb.table("models").upsert(rows, on_conflict="model_id"))
    except Exception as exc:
        log.error("Saving store prices failed for a batch of %d: %s", len(rows), exc)


def main(limit: int | None = None):
    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("Missing SUPABASE_URL or SUPABASE_KEY in environment / .env")

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    log.info("Connected to Supabase.")

    in_use = fetch_models_in_use(sb)
    todo = [m for m in fetch_models_to_check(sb) if m["model_id"] in in_use]
    if limit:
        todo = todo[:limit]
    log.info("Models used by product ads: %d, to check in stores now: %d", len(in_use), len(todo))
    if not todo:
        log.info("Nothing to do.")
        return

    parser = build_parser()
    lock = threading.Lock()
    pending, counts = [], {"found": 0, "not_found": 0, "ambiguous": 0, "failed": 0}

    def work(m):
        brand = (m.get("brands") or {}).get("name") or ""
        try:
            r = find_store_price(parser, brand, m["name"])
        except Exception as exc:
            # a network/LLM failure leaves the model unchecked, so the next run retries it
            log.warning("  %s %s: %s", brand, m["name"], exc)
            with lock:
                counts["failed"] += 1
            return
        row = {
            "model_id": m["model_id"], "brand_id": m["brand_id"], "name": m["name"],
            "store_new_price_mkd": r["price_mkd"],
            "store_count": len(r["stores"]) if r["price_mkd"] else None,
            "store_sources": r["stores"] or None,
            "store_checked_at": datetime.now(timezone.utc).isoformat(),
        }
        with lock:
            counts[r["status"]] += 1
            pending.append(row)
            if len(pending) >= SAVE_EVERY:
                save(sb, pending[:])
                pending.clear()
                log.info("  -> checked %d/%d (found %d)", sum(counts.values()), len(todo), counts["found"])

    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(work, todo))
    save(sb, pending)

    log.info("Done. %s", ", ".join(f"{k}: {v}" for k, v in counts.items()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None, help="Check at most this many models in this run")
    main(ap.parse_args().limit)
