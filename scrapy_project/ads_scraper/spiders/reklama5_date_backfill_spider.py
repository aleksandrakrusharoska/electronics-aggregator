"""
Date backfill spider for reklama5.

Crawls listing pages only (no detail page visits) and updates posted_date
for ads that currently have NULL posted_date in Supabase.

reklama5 never surfaces the posted date on the ad detail page itself —
it's only shown on listing/search cards (div.ad-date-div-1), so unlike
pazar3 this field can't be filled in by a detail-page rescrape.
"""
import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy
from dotenv import load_dotenv

from ads_scraper.normalize import resolve_posted_date

load_dotenv()
logger = logging.getLogger(__name__)

BATCH_SIZE = 100
START_URLS = [
    'https://reklama5.mk/Search?city=&cat=580&q=&sell=0&sell=1&buy=0&buy=1&trade=0&trade=1&includeOld=0&includeOld=1&includeNew=0&includeNew=1&cargoReady=0&DDVIncluded=0&private=0&company=0&page=1&SortByPrice=0&zz=1&pageView=',
    'https://reklama5.mk/Search?city=&cat=558&q=&sell=0&sell=1&buy=0&buy=1&trade=0&trade=1&includeOld=0&includeOld=1&includeNew=0&includeNew=1&cargoReady=0&DDVIncluded=0&private=0&company=0&page=1&SortByPrice=0&zz=1&pageView=',
]


class Reklama5DateBackfillSpider(scrapy.Spider):
    name = 'reklama5_date_backfill'
    # allowed_domains intentionally omitted (temporary, for diagnosis): the
    # last production run got a 302 on both start URLs and OffsiteMiddleware
    # filtered the redirect targets before parse() ever ran (confirmed via
    # 'offsite/filtered': 2 in the run's stats). Leaving domains unrestricted
    # so we can see the real destination in the DEBUG logging below.
    start_urls = START_URLS
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
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse)

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
        last_url, batch = None, 1000
        try:
            while True:
                time.sleep(1)
                q = (
                    self._client.table('ads')
                    .select('ad_url')
                    .eq('source', 'reklama5')
                    .is_('posted_date', 'null')
                    .order('ad_url')
                )
                if last_url is not None:
                    q = q.gt('ad_url', last_url)
                rows = q.limit(batch).execute().data
                if not rows:
                    break
                for r in rows:
                    self._null_urls.add(r['ad_url'])
                logger.info('Loaded %d null-date URLs so far...', len(self._null_urls))
                if len(rows) < batch:
                    break
                last_url = rows[-1]['ad_url']
        except Exception as exc:
            logger.error('Failed to load null URLs from Supabase (loaded %d so far): %s',
                         len(self._null_urls), exc)

    def _next_page_url(self, url):
        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        current = int(qs.get('page', ['1'])[0])
        qs['page'] = [str(current + 1)]
        return urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))

    def _page_info(self, response):
        """Return (current_page, total_pages) from 'Страна N од M' span, or (None, None)."""
        text = response.css('span.number-of-pages::text').get('')
        m = re.search(r'(\d+)\s+од\s+(\d+)', text)
        if m:
            return int(m.group(1)), int(m.group(2))
        return None, None

    def parse(self, response):
        now = datetime.now(timezone.utc).isoformat()
        found_on_page = 0

        blocks = response.css('div.row.ad-top-div')
        logger.info('DEBUG requested=%s status=%s final_url=%s blocks=%d',
                     response.request.url, response.status, response.url, len(blocks))

        for block in blocks:
            href = block.css('a.SearchAdTitle::attr(href)').get()
            if not href:
                continue
            ad_url = response.urljoin(href)
            if ad_url not in self._null_urls:
                continue

            # Date sits either as bare text in the div (regular ads) or
            # inside a <span> child (promoted ads) — collect both forms.
            parts = [
                t.strip() for t in
                block.css('div.ad-date-div-1::text, div.ad-date-div-1 span::text').getall()
                if t.strip()
            ]
            if not parts:
                continue
            posted_raw = re.sub(r'\s+', ' ', ' '.join(parts)).strip()

            resolved = resolve_posted_date(posted_raw, now)
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

        if not self._null_urls:
            logger.info('All null posted_dates filled. Total updated: %d', self._updated)
            return

        current_page, total_pages = self._page_info(response)
        logger.info('DEBUG page_info: current_page=%r total_pages=%r number_of_pages_text=%r',
                     current_page, total_pages, response.css('span.number-of-pages::text').get())
        if current_page is not None and total_pages is not None:
            if current_page >= total_pages:
                logger.info('Reached last page (%d/%d) for %s — stopping this category.',
                            current_page, total_pages, response.url)
                return
        elif not blocks:
            logger.info('No items and no page-info on %s — stopping.', response.url)
            return

        next_url = self._next_page_url(response.url)
        logger.info('DEBUG following next_url=%s', next_url)
        yield scrapy.Request(next_url, callback=self.parse)

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
