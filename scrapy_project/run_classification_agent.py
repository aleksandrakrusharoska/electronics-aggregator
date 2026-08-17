"""
Run the ad classification agent against all ads in Supabase.

Labels each ad as 'product', 'service', or 'wanted'.

Usage:
    python run_classification_agent.py
    python run_classification_agent.py --source pazar3
    python run_classification_agent.py --dry-run        # print samples, no writes
"""
import argparse
import logging
import os
import sys

from dotenv import load_dotenv
from supabase import create_client

from agents.classification_agent import classify_ads

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


def fetch_ads(sb, source=None) -> list[dict]:
    ads, last_url = [], None
    while True:
        q = sb.table('ads').select('ad_url, title, description, source').order('ad_url')
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


def store_results(sb, results: list[dict]):
    for i in range(0, len(results), STORE_BATCH):
        batch = results[i:i + STORE_BATCH]
        try:
            sb.table('ads').upsert(batch, on_conflict='ad_url').execute()
            log.info('  stored %d / %d', i + len(batch), len(results))
        except Exception as exc:
            log.error('Store failed: %s', exc)


def print_samples(results: list[dict], ads_by_url: dict, n: int = 5):
    for ad_type in ('service', 'wanted', 'product'):
        samples = [r for r in results if r['ad_type'] == ad_type][:n]
        if not samples:
            continue
        log.info('── %s samples ──', ad_type.upper())
        for r in samples:
            ad = ads_by_url.get(r['ad_url'], {})
            log.info('  [%s] %s', ad_type, ad.get('title', r['ad_url'])[:80])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default=None, choices=['reklama5', 'pazar3'])
    parser.add_argument('--dry-run', action='store_true', help='Classify but do not write to DB')
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit('Missing SUPABASE_URL or SUPABASE_KEY in .env')

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    log.info('Fetching ads...')
    ads = fetch_ads(sb, source=args.source)
    log.info('Loaded %d ads', len(ads))

    results = classify_ads(ads)

    ads_by_url = {a['ad_url']: a for a in ads}
    print_samples(results, ads_by_url)

    if args.dry_run:
        log.info('Dry-run mode — skipping writes.')
        return

    log.info('Storing %d classifications...', len(results))
    store_results(sb, results)
    log.info('Done.')


if __name__ == '__main__':
    main()
