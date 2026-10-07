"""
Precomputes the analytics charts into analytics_snapshots (see
scrapy_project/sql/migrations/005_analytics_snapshots.sql), so the API serves
them with one small read instead of scanning every ad on a cold start.

Run by the daily workflow after the pipeline, when the data has changed:
    python precompute_analytics.py
"""
import logging
import sys
from datetime import datetime, timezone

from app.api import ads
from app.core.cache import snapshot_key
from app.core.supabase import get_supabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("precompute_analytics")

# every endpoint and every argument combination the frontend asks for
JOBS = [
    (ads.get_brand_analytics, {"source": None}),
    (ads.get_brand_analytics, {"source": "pazar3"}),
    (ads.get_brand_analytics, {"source": "reklama5"}),
    (ads.get_good_deal_analytics, {}),
    (ads.get_scrape_activity, {}),
    (ads.get_listing_trend, {}),
    (ads.get_depreciation_analytics, {}),
]


def main() -> int:
    sb = get_supabase()
    failed = 0
    for endpoint, kwargs in JOBS:
        key = snapshot_key(endpoint.snapshot_name, kwargs)
        try:
            data = endpoint.compute(**kwargs)
            sb.table("analytics_snapshots").upsert(
                {"name": key, "data": data, "computed_at": datetime.now(timezone.utc).isoformat()},
                on_conflict="name",
            ).execute()
            log.info("  %s: saved", key)
        except Exception as exc:
            failed += 1
            log.error("  %s: failed: %s", key, exc)
    log.info("Done, %d of %d snapshots saved.", len(JOBS) - failed, len(JOBS))
    return 1 if failed == len(JOBS) else 0


if __name__ == "__main__":
    sys.exit(main())
