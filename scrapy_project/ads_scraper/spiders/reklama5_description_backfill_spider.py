"""
Description backfill for reklama5.

The live spider's description selector (p.mt-3::text .get()) only ever
returned the FIRST text node — the <p> uses <br> tags between lines, which
splits it into multiple text nodes, so everything after the first line
(price, pickup location, contact number, etc.) was silently dropped for
every reklama5 ad ever scraped. Also flattened via the old clean_text()/
strip_emoji() pipeline on top of that. Fixed going forward in
reklama5_spider.py; this re-visits every existing ad's detail page to
recover the full original text.

Usage:
    scrapy crawl reklama5_description_backfill -s DOWNLOAD_DELAY=2 -s CONCURRENT_REQUESTS=2 -s LOG_LEVEL=INFO
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


class Reklama5DescriptionBackfillSpider(scrapy.Spider):
    name = 'reklama5_description_backfill'
    allowed_domains = ['reklama5.mk', 'www.reklama5.mk']
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
        last_url, batch = None, 1000
        try:
            while len(urls) < self._limit:
                time.sleep(1)
                q = (
                    self._client.table('ads')
                    .select('ad_url')
                    .eq('source', 'reklama5')
                    .not_.is_('description', 'null')
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
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse_ad, errback=self.errback)

    def parse(self, response):
        return self.parse_ad(response)

    def parse_ad(self, response):
        # Same fix as reklama5_spider.py: scope to the first p.mt-3 (a
        # "Категорија: ..." field elsewhere on the page reuses the class),
        # and pull every text node under it, not just the first.
        desc_els = response.css('p.mt-3')
        if not desc_els:
            return
        desc_parts = desc_els[0].css('::text').getall()
        raw = '\n'.join(t.strip() for t in desc_parts if t.strip())
        cleaned = clean_description(raw)
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
