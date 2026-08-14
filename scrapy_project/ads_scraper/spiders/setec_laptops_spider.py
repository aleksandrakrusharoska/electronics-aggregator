"""
Setec.mk laptop catalog spider.

Fetches Setec's live "Преносни Компјутери" (Laptops) catalog via their
Meilisearch-backed search API — same mechanism as setec_phones_spider, just
a different category (~250 products). Used to compute reference "new"
prices for the used-ad price comparison feature and brand price analytics,
which previously had near-zero coverage for laptop brands (Setec's phone
catalog obviously never matched them).

The category ID below was found by querying the site's own
`category_filters` search index for all category name/ID pairs (POST an
empty query to https://search.sp.solslab.dev/indexes/category_filters/search
with the same bearer token) and looking up "Преносни Компјутери" — the same
approach to use if another category is ever added.

Writes to the same `retail_prices` table as setec_phones_spider (not
`ads`), since this is catalog/retail data, not a classified listing.
"""
import json
import logging
import os
from datetime import datetime, timezone

import scrapy
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SEARCH_URL = 'https://search.sp.solslab.dev/indexes/products/search'
SEARCH_TOKEN = 'c0424dab588b8cbbbe0a4809fc10b5f1c0c7d183b5b28ebe799f3fbf583ab358'
LAPTOPS_CATEGORY_ID = 'pcat_01JFZ1W5Q38VHNF746YGVYZ0PM'
PAGE_SIZE = 50
BATCH_SIZE = 50


class SetecLaptopsSpider(scrapy.Spider):
    name = 'setec_laptops'
    allowed_domains = ['setec.mk', 'sp.solslab.dev']
    custom_settings = {
        'DOWNLOAD_DELAY': 1,
        'ITEM_PIPELINES': {},  # bypass ads-specific pipelines — we write directly to Supabase
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._client = None
        self._batch: list[dict] = []
        self._written = 0
        self._connect()

    def _connect(self):
        from supabase import create_client
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        if not url or not key:
            raise RuntimeError('SUPABASE_URL and SUPABASE_KEY must be set.')
        self._client = create_client(url, key)
        logger.info('Supabase connected.')

    def start_requests(self):
        yield self._page_request(offset=0)

    async def start(self):
        for request in self.start_requests():
            yield request

    def _page_request(self, offset):
        body = {
            'q': '',
            'limit': PAGE_SIZE,
            'offset': offset,
            'filter': (
                "status = 'published' AND is_web_active = 'true' "
                f"AND product_categories.id = '{LAPTOPS_CATEGORY_ID}'"
            ),
        }
        return scrapy.Request(
            SEARCH_URL,
            method='POST',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {SEARCH_TOKEN}',
            },
            body=json.dumps(body),
            callback=self.parse,
            meta={'offset': offset},
        )

    def parse(self, response):
        data = json.loads(response.text)
        hits = data.get('hits', [])
        offset = response.meta['offset']
        self.logger.info('Offset %d: %d hits (estimatedTotalHits=%s)',
                          offset, len(hits), data.get('estimatedTotalHits'))

        now = datetime.now(timezone.utc).isoformat()
        for hit in hits:
            variants = hit.get('variants') or []
            if not variants:
                continue
            price = variants[0].get('calculated_price') or {}
            amount = price.get('calculated_amount')
            original = price.get('original_amount')
            handle = hit.get('handle')
            if not amount or not handle:
                continue

            self._batch.append({
                'url': f'https://setec.mk/products/{handle}',
                'source': 'setec',
                'brand': hit.get('brand_name'),
                'title': hit.get('title'),
                'price_mkd': amount,
                'original_price_mkd': original,
                'scraped_at': now,
            })
            if len(self._batch) >= BATCH_SIZE:
                self._flush()

        if len(hits) == PAGE_SIZE:
            yield self._page_request(offset + PAGE_SIZE)

    def _flush(self):
        if not self._batch:
            return
        try:
            self._client.table('retail_prices').upsert(self._batch, on_conflict='url').execute()
            self._written += len(self._batch)
            logger.info('Flushed %d rows (total: %d)', len(self._batch), self._written)
        except Exception as exc:
            logger.error('Supabase flush failed: %s', exc)
        self._batch = []

    def closed(self, reason):
        self._flush()
        logger.info('Setec laptops catalog done. Total written: %d. Reason: %s', self._written, reason)
