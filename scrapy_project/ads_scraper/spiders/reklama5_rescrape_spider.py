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
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

BATCH_SIZE = 100


class Reklama5RescrapeSpider(scrapy.Spider):
    name = 'reklama5_rescrape'
    # allowed_domains intentionally omitted (temporary, for diagnosis): the
    # last production run got a 302 on all 5000 requests and scraped zero
    # items — if the redirect target is off-domain, OffsiteMiddleware would
    # silently drop the follow-up request before parse_ad ever sees it.
    # Leaving domains unrestricted here so we can see where these ads
    # actually redirect to, via the DEBUG logging below.
    start_urls = []  # populated in __init__
    custom_settings = {
        'DOWNLOAD_DELAY': 2,
        'CONCURRENT_REQUESTS': 2,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 1.5,
        'ITEM_PIPELINES': {},
        # Let 404s reach parse_ad instead of being silently dropped by
        # HttpErrorMiddleware — it's the one reliable "this listing is gone"
        # signal, unlike a 403 (bot block) or timeout, which say nothing
        # about whether the ad still exists.
        'HTTPERROR_ALLOWED_CODES': [404],
    }

    def __init__(self, limit=5000, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._limit = int(limit)
        self._client = None
        self._batch: list[dict] = []
        self._updated = 0
        self._debug_logged = 0
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
                    .is_('category', 'null')
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
        for i, url in enumerate(self.start_urls):
            if i < 5:
                logger.info('DEBUG requesting: %s', url)
            yield scrapy.Request(url, callback=self.parse_ad, errback=self.errback)

    def parse(self, response):
        return self.parse_ad(response)

    def parse_ad(self, response):
        ad_url = response.url

        if response.status == 404:
            self._batch.append({'ad_url': ad_url, 'is_active': False})
            if len(self._batch) >= BATCH_SIZE:
                self._flush()
            return

        update = {'ad_url': ad_url, 'is_active': True}

        if self._debug_logged < 5:
            self._debug_logged += 1
            logger.info(
                'DEBUG parse_ad: requested=%s status=%s final_url=%s redirected=%s categoryDiv_count=%d',
                response.request.url, response.status, response.url,
                response.request.url != response.url, len(response.css('#categoryDiv')),
            )

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

        if len(update) > 1:
            self._batch.append(update)
            if len(self._batch) >= BATCH_SIZE:
                self._flush()

    def errback(self, failure):
        logger.warning('DEBUG errback: %s %s (url=%s)',
                        type(failure.value).__name__, failure.value, failure.request.url)

    def _flush(self):
        if not self._batch:
            return
        try:
            # Postgres rejects an upsert batch containing 2+ rows for the same
            # conflict key -- dedupe defensively, keeping the latest entry.
            deduped = list({row['ad_url']: row for row in self._batch}.values())
            self._client.table('ads').upsert(deduped, on_conflict='ad_url').execute()
            self._updated += len(deduped)
            logger.info('Flushed %d updates (total: %d)', len(deduped), self._updated)
        except Exception as exc:
            logger.error('Supabase flush failed: %s', exc)
        self._batch = []

    def closed(self, reason):
        self._flush()
        logger.info('Re-scrape done. Total updated: %d. Reason: %s', self._updated, reason)
