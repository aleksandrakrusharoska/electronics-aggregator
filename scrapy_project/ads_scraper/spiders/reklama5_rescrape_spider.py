"""
Detail-page re-scrape spider for reklama5.

Loads ads with missing category from Supabase and visits their detail
pages directly (no listing page traversal) to fill in:
  category, seller_name

Run in batches of --limit ads per GitHub Actions run.
Each run naturally picks up the next batch since filled ads are excluded.
"""
import logging
import os
import time

import scrapy
from ads_scraper.pipelines import to_db_row
from lookups import upsert_rows
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

BATCH_SIZE = 100


class Reklama5RescrapeSpider(scrapy.Spider):
    name = 'reklama5_rescrape'
    allowed_domains = ['reklama5.mk', 'www.reklama5.mk']
    start_urls = []  # populated in __init__
    custom_settings = {
        'DOWNLOAD_DELAY': 2,
        'CONCURRENT_REQUESTS': 2,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 1.5,
        'ITEM_PIPELINES': {},
        # Redirects are answered here instead of followed. reklama5 sends a
        # removed ad to /Search, and outside North Macedonia (a proxy IP it
        # doesn't place there) everything to reklama5.com. Following them
        # used to store the redirect target as a new "ad" (rows like
        # .../Search and reklama5.com/AdDetails?..., machine-translated) and
        # fetch a full search page for every removed ad.
        'REDIRECT_ENABLED': False,
        # 404 and redirects reach parse_ad instead of being dropped by
        # HttpErrorMiddleware. A 403 (bot block) or timeout still says
        # nothing about whether the ad exists, so those stay errors.
        'HTTPERROR_ALLOWED_CODES': [404, 301, 302],
    }

    def __init__(self, limit=5000, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._limit = int(limit)
        self._client = None
        self._batch: list[dict] = []
        self._updated = 0
        self._setup()

    def _setup(self, attempts=3):
        # A dropped Supabase connection here (2026-09-29: "Server disconnected"
        # while resolving the source_id) used to end the run with nothing
        # loaded, and Scrapy still exited clean. Retry the whole setup first.
        for attempt in range(1, attempts + 1):
            try:
                self._connect()
                self.start_urls = self._load_urls()
                logger.info('Loaded %d URLs to re-scrape.', len(self.start_urls))
                return
            except Exception as exc:
                if attempt == attempts:
                    logger.error('Setup failed: %s', exc)
                    self.start_urls = []
                    return
                wait = 5 * 3 ** (attempt - 1)
                logger.warning('Setup attempt %d/%d failed (%s), retrying in %ds.', attempt, attempts, exc, wait)
                time.sleep(wait)

    def _connect(self):
        from supabase import create_client
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        if not url or not key:
            raise RuntimeError('SUPABASE_URL and SUPABASE_KEY must be set.')
        self._client = create_client(url, key)
        from lookups import get_lookups
        self._lookups = get_lookups(self._client)
        self._source_id = self._lookups.source_id('reklama5', create=False)
        logger.info('Supabase connected.')

    def _load_urls(self) -> list[str]:
        urls = []
        last_url, batch = None, 1000
        try:
            while len(urls) < self._limit:
                time.sleep(1)
                q = (
                    self._client.table('ads')
                    .select('ad_url')
                    .eq('source_id', self._source_id)
                    .is_('category_id', 'null')
                    # only real reklama5.mk ad pages (not stray reklama5.com rows)
                    .gte('ad_url', 'https://reklama5.mk/AdDetails')
                    .lt('ad_url', 'https://reklama5.mk/AdDetailt')
                    # removed ads are marked inactive but keep category null;
                    # without this they would be re-checked on every run
                    .not_.is_('is_active', 'false')
                    .order('ad_url')
                )
                if last_url is not None:
                    q = q.gt('ad_url', last_url)
                rows = q.limit(batch).execute().data
                if not rows:
                    break
                for r in rows:
                    urls.append(r['ad_url'])
                logger.info('Loaded %d URLs so far...', len(urls))
                if len(rows) < batch:
                    break
                last_url = rows[-1]['ad_url']
        except Exception as exc:
            logger.error('Failed to load URLs (loaded %d so far): %s', len(urls), exc)
        return urls[:self._limit]

    async def start(self):
        # Scrapy >=2.13 drives crawling from start() rather than
        # start_requests(); self.start_urls is already populated by
        # _setup() in __init__, so the default implementation would work,
        # but we're explicit here for clarity.
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse_ad, errback=self.errback,
                                 meta={'original_url': url})

    def parse(self, response):
        return self.parse_ad(response)

    def _queue(self, row):
        self._batch.append(row)
        if len(self._batch) >= BATCH_SIZE:
            self._flush()

    def parse_ad(self, response):
        # Always update the row this request was made for, never the URL the
        # response came from (see REDIRECT_ENABLED above).
        ad_url = response.meta.get('original_url', response.request.url)

        if response.status == 404:
            self._queue({'ad_url': ad_url, 'is_active': False})
            return

        if response.status in (301, 302):
            location = response.headers.get('Location', b'').decode('latin-1')
            target = response.urljoin(location)
            if 'reklama5.com' in target:
                # Geo redirect (the proxy IP wasn't Macedonian): says nothing
                # about the ad, try it again on a later run.
                self.crawler.stats.inc_value('rescrape/geo_redirect')
            elif '/AdDetails' not in target:
                # Removed ads redirect to the search page.
                self.crawler.stats.inc_value('rescrape/removed')
                self._queue({'ad_url': ad_url, 'is_active': False})
            else:
                self.crawler.stats.inc_value('rescrape/other_redirect')
                logger.info('Unexpected redirect %s -> %s', ad_url, target)
            return

        update = {'ad_url': ad_url, 'is_active': True}

        # Category — deepest breadcrumb link in the #categoryDiv block
        cat_texts = [
            t.strip() for t in response.css('#categoryDiv a small::text').getall()
            if t.strip()
        ]
        if cat_texts:
            update['category'] = cat_texts[-1]

        # seller_name — missing for a minority of ads
        seller = response.css('div.row.mb-2.mt-2 div.col-9 h5.my-0::text').get()
        if seller:
            update['seller_name'] = seller.strip()

        self._queue(update)

    def errback(self, failure):
        logger.warning('Request failed: %s %s (url=%s)',
                       type(failure.value).__name__, failure.value, failure.request.url)

    def _flush(self):
        if not self._batch:
            return
        try:
            # Postgres rejects an upsert batch containing 2+ rows for the same
            # conflict key -- dedupe defensively, keeping the latest entry.
            deduped = list({row['ad_url']: row for row in self._batch}.values())
            rows = [to_db_row({**row, 'source': 'reklama5'}, self._lookups) for row in deduped]
            upsert_rows(self._client, 'ads', rows, on_conflict='ad_url')
            self._updated += len(deduped)
            logger.info('Flushed %d updates (total: %d)', len(deduped), self._updated)
        except Exception as exc:
            logger.error('Supabase flush failed: %s', exc)
        self._batch = []

    def closed(self, reason):
        self._flush()
        logger.info('Re-scrape done. Total updated: %d. Reason: %s', self._updated, reason)
