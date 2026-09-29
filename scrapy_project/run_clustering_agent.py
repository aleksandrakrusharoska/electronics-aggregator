"""
Run the product clustering agent against all ads in Supabase.

Usage:
    python run_clustering_agent.py
    python run_clustering_agent.py --source pazar3
"""
import argparse
import logging
import os
import sys

from dotenv import load_dotenv
from supabase import create_client

from agents.clustering_agent import cluster_ads, save_clusters
from lookups import get_lookups

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
        q = sb.table('ads_view').select('ad_url, title').eq('ad_type', 'product').order('ad_url')
        if source:
            q = q.eq('source_id', get_lookups(sb).source_id(source, create=False))
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default=None, choices=['reklama5', 'pazar3'])
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit('Missing SUPABASE_URL or SUPABASE_KEY in .env')

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    log.info('Fetching ads...')
    ads = fetch_ads(sb, source=args.source)
    log.info('Loaded %d ads', len(ads))

    results = cluster_ads(ads)
    log.info('Storing %d cluster assignments...', len(results))
    save_clusters(sb, ads, results, batch=STORE_BATCH)
    log.info('Done.')


if __name__ == '__main__':
    main()
