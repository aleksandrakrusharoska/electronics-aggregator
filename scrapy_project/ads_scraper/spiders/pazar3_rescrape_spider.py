"""
Detail-page re-scrape spider for pazar3.

Loads ads with missing key fields from Supabase and visits their detail
pages directly (no listing page traversal) to fill in:
  listing_type, condition, category, seller_name, description

Selection is keyed on listing_type IS NULL rather than category or
posted_date: listing_type is present on ~100% of detail pages (verified
against a live sample) so the pool actually drains, whereas category is
only present on a small minority of pages and would otherwise get
re-selected forever without making progress.

Run in batches of --limit ads per GitHub Actions run (~3-4 hours per 20000 ads).
Each run naturally picks up the next batch since filled ads are excluded.
"""
import logging
import os
import time
from datetime import datetime, timezone

import scrapy
from dotenv import load_dotenv

from ads_scraper.normalize import parse_price, resolve_posted_date

load_dotenv()
logger = logging.getLogger(__name__)

BATCH_SIZE = 100


class Pazar3RescrapeSpider(scrapy.Spider):
    name = 'pazar3_rescrape'
    allowed_domains = ['pazar3.mk']
    start_urls = []  # populated in __init__
    custom_settings = {
        'DOWNLOAD_DELAY': 2,
        'CONCURRENT_REQUESTS': 2,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 1.5,
        'ITEM_PIPELINES': {},
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
                    .is_('listing_type', 'null')
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

    def parse(self, response):
        return self.parse_ad(response)

    def parse_ad(self, response):
        ad_url = response.url
        update = {'ad_url': ad_url}

        # posted_date
        pub_date = response.css('bdi.published-date::text').get()
        pub_time = response.css('bdi.published-time::text').get()
        if pub_date:
            raw = (pub_date.strip() + ' ' + pub_time.strip()).strip() if pub_time else pub_date.strip()
            resolved = resolve_posted_date(raw, datetime.now(timezone.utc).isoformat())
            if resolved:
                update['posted_date'] = resolved

        # Tag-based fields: condition, category
        tag_map = {}
        for tag in response.css('a.tag-item'):
            label = tag.css('span::text').get('').strip().rstrip(':').strip()
            value = tag.css('bdi::text').get('').strip()
            if label and value:
                tag_map[label] = value

        condition = tag_map.get('Condition') or tag_map.get('Состојба')
        if condition:
            update['condition'] = condition

        category = tag_map.get('Производи')
        if category:
            update['category'] = category

        listing_type_raw = (
            tag_map.get('Вид на оглас') or
            tag_map.get('Тип на оглас') or
            tag_map.get('Вид') or
            tag_map.get('Тип')
        )
        if listing_type_raw:
            lt = listing_type_raw.strip().lower()
            if 'продав' in lt:
                update['listing_type'] = 'sale'
            elif 'купув' in lt:
                update['listing_type'] = 'buy'
            elif 'разменув' in lt or 'замена' in lt:
                update['listing_type'] = 'trade'
            else:
                update['listing_type'] = listing_type_raw.strip()

        # seller_name
        seller = response.css('div.user-name.ci-text-base::text').get()
        if seller:
            update['seller_name'] = seller.strip()

        # description
        desc = response.css('meta[name="description"]::attr(content)').get()
        if desc:
            update['description'] = desc.strip()

        # price_note — only if no numeric price found
        price_val = response.css('bdi.format-money-int::attr(value)').get()
        if not price_val:
            price_text = response.css('p.list-price::text, .ad-price::text').get()
            if price_text:
                parsed = parse_price(price_text.strip())
                if parsed.get('price_note'):
                    update['price_note'] = parsed['price_note']

        if len(update) > 1:
            self._batch.append(update)
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
        logger.info('Re-scrape done. Total updated: %d. Reason: %s', self._updated, reason)
