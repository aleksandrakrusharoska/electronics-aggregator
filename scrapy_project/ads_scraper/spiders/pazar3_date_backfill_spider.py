"""
Date backfill spider for pazar3.

Visits each null-posted_date ad's own detail page directly (mirrors
pazar3_rescrape_spider) rather than crawling listing pages. Listing pages
show recent ads only, so old backlog ads that have aged off the visible
listings were essentially unreachable that way regardless of how many
pages got crawled. The detail page reliably has the date via
bdi.published-date / bdi.published-time.
"""
import logging
import os
import time
from datetime import datetime, timezone

import scrapy
from dotenv import load_dotenv

from ads_scraper.normalize import resolve_posted_date

load_dotenv()
logger = logging.getLogger(__name__)

BATCH_SIZE = 100


class Pazar3DateBackfillSpider(scrapy.Spider):
    name = 'pazar3_date_backfill'
    allowed_domains = ['pazar3.mk']
    start_urls = []  # populated in __init__
    custom_settings = {
        'DOWNLOAD_DELAY': 2,
        'CONCURRENT_REQUESTS': 2,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 1.5,
        'ITEM_PIPELINES': {},  # bypass all pipelines — we write directly to Supabase
        # Let 404s reach parse_ad instead of being silently dropped by
        # HttpErrorMiddleware — a dead listing just means no date to set.
        'HTTPERROR_ALLOWED_CODES': [404],
    }

    def __init__(self, limit=5000, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._limit = int(limit)
        self._client = None
        self._batch: list[dict] = []
        self._updated = 0
        self._setup()

    def _setup(self):
        try:
            self._connect()
            self.start_urls = self._load_null_urls()
            logger.info('Found %d ads with null posted_date.', len(self.start_urls))
        except Exception as exc:
            logger.error('Failed to load null URLs from Supabase: %s', exc)
            self.start_urls = []

    def _connect(self):
        from supabase import create_client
        url = self.settings.get('SUPABASE_URL') or os.getenv('SUPABASE_URL')
        key = self.settings.get('SUPABASE_KEY') or os.getenv('SUPABASE_KEY')
        if not url or not key:
            raise RuntimeError('SUPABASE_URL and SUPABASE_KEY must be set.')
        self._client = create_client(url, key)
        logger.info('Supabase connected.')

    def _load_null_urls(self) -> list[str]:
        urls = []
        last_url, batch = None, 1000
        while len(urls) < self._limit:
            time.sleep(1)
            q = (
                self._client.table('ads')
                .select('ad_url')
                .eq('source', 'pazar3')
                .is_('posted_date', 'null')
                .order('ad_url')
            )
            if last_url is not None:
                q = q.gt('ad_url', last_url)
            rows = q.limit(batch).execute().data
            if not rows:
                break
            for r in rows:
                urls.append(r['ad_url'])
            logger.info('Loaded %d null-date URLs so far...', len(urls))
            if len(rows) < batch:
                break
            last_url = rows[-1]['ad_url']
        return urls[:self._limit]

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse_ad, errback=self.errback)

    def parse(self, response):
        return self.parse_ad(response)

    def parse_ad(self, response):
        if response.status == 404:
            return  # ad no longer live — leave stored state as-is

        pub_date = response.css('bdi.published-date::text').get()
        pub_time = response.css('bdi.published-time::text').get()
        if not pub_date:
            return

        raw = (pub_date.strip() + ' ' + pub_time.strip()).strip() if pub_time else pub_date.strip()
        resolved = resolve_posted_date(raw, datetime.now(timezone.utc).isoformat())
        if not resolved:
            return

        self._batch.append({'ad_url': response.url, 'posted_date': resolved})
        if len(self._batch) >= BATCH_SIZE:
            self._flush()

    def errback(self, failure):
        logger.warning('Failed to fetch %s: %s', failure.request.url, failure.value)

    def _flush(self):
        if not self._batch:
            return
        try:
            self._client.table('ads').upsert(self._batch, on_conflict='ad_url').execute()
            self._updated += len(self._batch)
            logger.info('Flushed %d updates (total: %d)', len(self._batch), self._updated)
        except Exception as exc:
            logger.error('Supabase flush failed: %s', exc)
        self._batch = []

    def closed(self, reason):
        self._flush()
        logger.info('Date backfill done. Total updated: %d. Reason: %s', self._updated, reason)
