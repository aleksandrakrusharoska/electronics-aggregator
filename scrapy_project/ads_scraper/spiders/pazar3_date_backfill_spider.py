"""
Date backfill spider for pazar3.

Crawls listing pages only (no detail page visits) and updates posted_date
for ads that currently have NULL posted_date in Supabase.

Reads the date from the listing card (span.pull-right) which gives accurate
dates for ads within the last ~12 months.
"""
import logging
import os
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import scrapy
from dotenv import load_dotenv

from ads_scraper.normalize import resolve_posted_date

load_dotenv()

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
START_URL = 'https://www.pazar3.mk/oglasi/elektronika/prodazba-kupuvanje-zamena'


class Pazar3DateBackfillSpider(scrapy.Spider):
    name = 'pazar3_date_backfill'
    allowed_domains = ['pazar3.mk']
    start_urls = [START_URL]
    custom_settings = {
        'DOWNLOAD_DELAY': 2,
        'CONCURRENT_REQUESTS': 1,
        'ITEM_PIPELINES': {},  # bypass all pipelines — we write directly to Supabase
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._client = None
        self._null_urls: set[str] = set()
        self._batch: list[dict] = []
        self._updated = 0

    def start_requests(self):
        self._connect()
        self._load_null_urls()
        if not self._null_urls:
            logger.info('No ads with null posted_date — nothing to do.')
            return
        logger.info('Found %d ads with null posted_date.', len(self._null_urls))
        yield scrapy.Request(START_URL, callback=self.parse)

    async def start(self):
        # Scrapy >=2.13 drives crawling from start() rather than
        # start_requests() — bridge to the sync generator above so the
        # Supabase setup it does actually runs.
        for request in self.start_requests():
            yield request

    def _connect(self):
        from supabase import create_client
        url = self.settings.get('SUPABASE_URL') or os.getenv('SUPABASE_URL')
        key = self.settings.get('SUPABASE_KEY') or os.getenv('SUPABASE_KEY')
        if not url or not key:
            raise RuntimeError('SUPABASE_URL and SUPABASE_KEY must be set.')
        self._client = create_client(url, key)
        logger.info('Supabase connected.')

    def _load_null_urls(self):
        import time
        offset, batch = 0, 1000
        try:
            while True:
                time.sleep(1)
                rows = (
                    self._client.table('ads')
                    .select('ad_url')
                    .eq('source', 'pazar3')
                    .is_('posted_date', 'null')
                    .order('ad_url')
                    .range(offset, offset + batch - 1)
                    .execute()
                    .data
                )
                if not rows:
                    break
                for r in rows:
                    self._null_urls.add(r['ad_url'])
                logger.info('Loaded %d null-date URLs so far...', len(self._null_urls))
                if len(rows) < batch:
                    break
                offset += batch
        except Exception as exc:
            logger.error('Failed to load null URLs from Supabase (loaded %d so far): %s',
                         len(self._null_urls), exc)

    def parse(self, response):
        now = datetime.now(timezone.utc).isoformat()
        found_on_page = 0

        listings = response.css('div.row-listing, div.row.row-listing')
        logger.info('DEBUG requested=%s status=%s final_url=%s listings=%d',
                     response.request.url, response.status, response.url, len(listings))

        for listing in listings:
            href = listing.css('h2 a::attr(href)').get()
            if not href:
                continue
            ad_url = response.urljoin(href)
            if ad_url not in self._null_urls:
                continue

            posted_raw = listing.css('span.pull-right::text').get()
            if not posted_raw:
                continue

            resolved = resolve_posted_date(posted_raw.strip(), now)
            if not resolved:
                continue

            self._null_urls.discard(ad_url)
            self._batch.append({'ad_url': ad_url, 'posted_date': resolved})
            found_on_page += 1

            if len(self._batch) >= BATCH_SIZE:
                self._flush()

        if found_on_page:
            logger.info('Page %s — updated %d dates (remaining: %d)',
                        response.url[-60:], found_on_page, len(self._null_urls))

        if not self._null_urls and self._updated > 0:
            logger.info('All null posted_dates filled. Total updated: %d', self._updated)
            return

        # Follow next page
        next_btn = response.css('a.next.page-number:not(.disabled)::attr(href)').get()
        used_fallback = False
        if not next_btn:
            used_fallback = True
            parsed = urlparse(response.url)
            params = parse_qs(parsed.query)
            current = int(params.get('Page', ['1'])[0])
            next_btn = response.css(f'a.page-number[page-no="{current + 1}"]::attr(href)').get()
        logger.info('DEBUG pagination: primary_selector=%s used_fallback=%s next_btn=%r',
                     'no match' if used_fallback else 'matched', used_fallback, next_btn)
        if next_btn:
            yield response.follow(next_btn, callback=self.parse)
        else:
            logger.warning('DEBUG no next_btn found — stopping. page_number_hrefs=%r',
                            response.css('a.page-number::attr(href)').getall())

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
