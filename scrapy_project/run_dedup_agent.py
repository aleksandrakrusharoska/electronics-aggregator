"""
Run the deduplication agent against all ads in Supabase.

Usage:
    python run_dedup_agent.py                # cross-site only (reklama5 vs pazar3)
    python run_dedup_agent.py --same-site    # also within each site
    python run_dedup_agent.py --clear        # wipe existing results first, then re-run
"""
import argparse
import logging
import os
import sys

from dotenv import load_dotenv
from supabase import create_client

from agents.dedup_agent import find_cross_site_duplicates, find_same_site_duplicates

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
FETCH_PAGE = 1000
STORE_BATCH = 500


def fetch_ads(sb, source: str | None = None) -> list[dict]:
    """Load ad_url, title, price_eur, source for all (or one source) ads."""
    ads, last_url = [], None
    while True:
        q = (
            sb.table('ads')
            .select('ad_url, title, price_eur, source, seller_name')
            .not_.is_('title', 'null')
            .order('ad_url')
        )
        if source:
            q = q.eq('source', source)
        if last_url is not None:
            q = q.gt('ad_url', last_url)
        batch = q.limit(FETCH_PAGE).execute().data
        if not batch:
            break
        ads.extend(batch)
        if len(batch) < FETCH_PAGE:
            break
        last_url = batch[-1]['ad_url']
    return ads


def store(sb, pairs: list[dict]) -> None:
    # Deduplicate by (ad_url_1, ad_url_2), keeping highest similarity score
    seen: dict[tuple, dict] = {}
    for p in pairs:
        key = (p['ad_url_1'], p['ad_url_2'])
        if key not in seen or p['similarity_score'] > seen[key]['similarity_score']:
            seen[key] = p
    unique = list(seen.values())

    for i in range(0, len(unique), STORE_BATCH):
        batch = unique[i:i + STORE_BATCH]
        try:
            sb.table('duplicates').upsert(
                batch, on_conflict='ad_url_1,ad_url_2'
            ).execute()
            log.info('  stored %d / %d pairs', i + len(batch), len(unique))
        except Exception as exc:
            log.error('Store failed: %s', exc)


def run_and_store(sb, label: str, pairs: list[dict]) -> None:
    log.info('%s → %d pairs found', label, len(pairs))
    if pairs:
        store(sb, pairs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--same-site', action='store_true',
                        help='Also detect duplicates within each site')
    parser.add_argument('--clear', action='store_true',
                        help='Delete all existing duplicate records before running')
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit('Missing SUPABASE_URL or SUPABASE_KEY in .env')

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    if args.clear:
        log.info('Clearing existing duplicates table...')
        sb.table('duplicates').delete().neq('id', 0).execute()

    # ── Cross-site ────────────────────────────────────────────────
    log.info('Fetching reklama5 ads...')
    r5 = fetch_ads(sb, 'reklama5')
    log.info('  %d ads loaded', len(r5))

    log.info('Fetching pazar3 ads...')
    p3 = fetch_ads(sb, 'pazar3')
    log.info('  %d ads loaded', len(p3))

    log.info('Computing cross-site similarity (reklama5 × pazar3)...')
    run_and_store(sb, 'cross_site', find_cross_site_duplicates(r5, p3))

    # ── Same-site (optional) ──────────────────────────────────────
    if args.same_site:
        log.info('Computing same-site duplicates for reklama5...')
        run_and_store(sb, 'reklama5 same_site', find_same_site_duplicates(r5))

        log.info('Computing same-site duplicates for pazar3...')
        run_and_store(sb, 'pazar3 same_site', find_same_site_duplicates(p3))

    log.info('Done.')


if __name__ == '__main__':
    main()
