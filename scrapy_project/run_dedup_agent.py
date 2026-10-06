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

from lookups import get_lookups

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
URL_CHUNK = 40   # ad URLs per .in_() filter — pazar3 URLs are long and the request line has a size limit


def fetch_ads(sb, source: str | None = None) -> list[dict]:
    """Active ads with what the matching needs (title, price, seller, phone,
    description, parsed model), one row per URL."""
    ads, last_url = [], None
    while True:
        q = (
            sb.table('ads_view')
            .select('ad_url, title, price_eur, source, seller_name, phone, description, model_id')
            .not_.is_('title', 'null')
            .not_.is_('is_active', 'false')
            .order('ad_url')
        )
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
    return list({a['ad_url']: a for a in ads}.values())


def replace_pairs(sb, match_type: str, pairs: list[dict]) -> None:
    """Each run recomputes the full set over all active ads, so it replaces
    the previous pairs of that type — only adding (as before) kept every
    wrong pair from older matching rules forever."""
    sb.table('duplicates').delete().eq('match_type', match_type).execute()
    store(sb, pairs)


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


def group_pairs(pairs: list[tuple[str, str]]) -> list[set[str]]:
    """Connected components: if A=B and B=C, then A, B and C are one listing."""
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        parent[find(a)] = find(b)
    groups: dict[str, set[str]] = {}
    for x in list(parent):
        groups.setdefault(find(x), set()).add(x)
    return list(groups.values())


def update_groups(sb) -> int:
    """Turn all stored pairs into groups and mark each ad's group on
    ad_analysis (dup_group_id, dup_primary — see 004_duplicate_groups.sql).
    The cheapest ad of a group (newest on a tie) is the one the list shows."""
    pairs, last_id = [], 0
    while True:
        batch = (sb.table('duplicates').select('id, ad_url_1, ad_url_2')
                 .gt('id', last_id).order('id').limit(FETCH_PAGE).execute().data)
        pairs += [(p['ad_url_1'], p['ad_url_2']) for p in batch]
        if len(batch) < FETCH_PAGE:
            break
        last_id = batch[-1]['id']
    groups = [g for g in group_pairs(pairs) if len(g) > 1]

    members = sorted({u for g in groups for u in g})
    info = {}
    for i in range(0, len(members), URL_CHUNK):
        for a in (sb.table('ads_view').select('ad_url, price_eur, posted_date, scraped_at')
                  .in_('ad_url', members[i:i + URL_CHUNK]).execute().data):
            info[a['ad_url']] = a

    def primary_of(g):   # cheapest; on a tie, the newest
        price = lambda u: (info.get(u) or {}).get('price_eur') or float('inf')
        date = lambda u: str((info.get(u) or {}).get('posted_date') or (info.get(u) or {}).get('scraped_at') or '')
        cheapest = min(price(u) for u in g)
        return max((u for u in g if price(u) == cheapest), key=lambda u: (date(u), u))

    rows = {}
    for gid, g in enumerate(sorted(groups, key=lambda g: min(g)), start=1):
        primary = primary_of(g)
        for u in g:
            rows[u] = {'ad_url': u, 'dup_group_id': gid, 'dup_primary': u == primary}

    # ads that were in a group last time but aren't any more — paged by
    # dup_group_id, which the partial index covers (paging by ad_url made
    # Postgres walk the whole table and hit the statement timeout)
    offset = 0
    while True:
        batch = (sb.table('ad_analysis').select('ad_url, dup_group_id').not_.is_('dup_group_id', 'null')
                 .order('dup_group_id').order('ad_url').range(offset, offset + FETCH_PAGE - 1).execute().data)
        for a in batch:
            rows.setdefault(a['ad_url'], {'ad_url': a['ad_url'], 'dup_group_id': None, 'dup_primary': None})
        if len(batch) < FETCH_PAGE:
            break
        offset += FETCH_PAGE

    # only ads that already have an analysis row (upsert must not create bare rows)
    have = set()
    urls = list(rows)
    for i in range(0, len(urls), URL_CHUNK):
        have.update(a['ad_url'] for a in sb.table('ad_analysis').select('ad_url').in_('ad_url', urls[i:i + URL_CHUNK]).execute().data)
    out = [r for u, r in rows.items() if u in have]
    for i in range(0, len(out), STORE_BATCH):
        sb.table('ad_analysis').upsert(out[i:i + STORE_BATCH], on_conflict='ad_url').execute()
    log.info('Duplicate groups: %d (covering %d ads)', len(groups), sum(len(g) for g in groups))
    return len(groups)


def run_and_store(sb, label: str, match_type: str, pairs: list[dict]) -> None:
    log.info('%s → %d pairs found', label, len(pairs))
    replace_pairs(sb, match_type, pairs)


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
    run_and_store(sb, 'cross_site', 'cross_site', find_cross_site_duplicates(r5, p3))

    # ── Same-site (optional) ──────────────────────────────────────
    if args.same_site:
        log.info('Computing same-site duplicates for both sites...')
        run_and_store(sb, 'same_site', 'same_site', find_same_site_duplicates(r5) + find_same_site_duplicates(p3))

    update_groups(sb)
    log.info('Done.')


if __name__ == '__main__':
    main()
