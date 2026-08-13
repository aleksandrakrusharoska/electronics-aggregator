"""
Description formatting backfill for pazar3.

Ads scraped before the clean_description() fix (2026-08-12T13:41:09Z) have
their descriptions flattened to one line — line breaks and emojis stripped
by the old clean_text()/strip_emoji() pipeline. Re-visits each such ad's
detail page, re-extracts the description from the same source the regular
spider uses (meta[name="description"], which reliably keeps the seller's
original line breaks), and re-applies the corrected cleaning.

Usage:
    scrapy crawl pazar3_description_backfill -s DOWNLOAD_DELAY=2 -s CONCURRENT_REQUESTS=2 -s LOG_LEVEL=INFO
"""
import logging
import os
import time

import scrapy
from dotenv import load_dotenv

from ads_scraper.normalize import clean_description

load_dotenv()
logger = logging.getLogger(__name__)

BATCH_SIZE = 100
# Fix commit timestamp (UTC) — ads scraped at/after this already have
# correctly-formatted descriptions from the source.
FIX_CUTOFF = '2026-08-12T13:41:09+00:00'


class Pazar3DescriptionBackfillSpider(scrapy.Spider):
    name = 'pazar3_description_backfill'
    allowed_domains = ['pazar3.mk']
    start_urls = []  # populated in __init__
    custom_settings = {
        'DOWNLOAD_DELAY': 2,
        'CONCURRENT_REQUESTS': 2,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 1.5,
        'ITEM_PIPELINES': {},  # bypass all pipelines — we write directly to Supabase
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
            self.start_urls = self._load_urls()
            logger.info('Loaded %d URLs to re-scrape.', len(self.start_urls))
        except Exception as exc:
            logger.error('Setup failed: %s', exc)
            self.start_urls = []

    def _connect(self):
        from supabase import create_client
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        if not url or not key:
            raise RuntimeError('SUPABASE_URL and SUPABASE_KEY must be set.')
        self._client = create_client(url, key)
        logger.info('Supabase connected.')

    def _load_urls(self) -> list[str]:
        urls = []
        offset, batch = 0, 1000
        try:
            while len(urls) < self._limit:
                time.sleep(1)
                rows = (
                    self._client.table('ads')
                    .select('ad_url')
                    .eq('source', 'pazar3')
                    .not_.is_('description', 'null')
                    .lt('scraped_at', FIX_CUTOFF)
                    .order('ad_url')
                    .range(offset, offset + batch - 1)
                    .execute()
                    .data
                )
                if not rows:
                    break
                for r in rows:
                    urls.append(r['ad_url'])
                logger.info('Loaded %d URLs so far...', len(urls))
                if len(rows) < batch:
                    break
                offset += batch
        except Exception as exc:
            logger.error('Failed to load URLs (loaded %d so far): %s', len(urls), exc)
        return urls[:self._limit]

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse_ad, errback=self.errback)

    def parse(self, response):
        return self.parse_ad(response)

    def parse_ad(self, response):
        if response.status == 404:
            return  # ad no longer live — leave the stored description as-is

        raw = response.css('meta[name="description"]::attr(content)').get()
        if not raw:
            return
        cleaned = clean_description(raw.strip())
        if not cleaned:
            return

        self._batch.append({'ad_url': response.url, 'description': cleaned})
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
        logger.info('Description backfill done. Total updated: %d. Reason: %s', self._updated, reason)
