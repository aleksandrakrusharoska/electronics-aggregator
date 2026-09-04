"""
Detail-page re-scrape spider for pazar3.

Loads ads with missing key fields from Supabase and visits their detail
pages directly (no listing page traversal) to fill in:
  listing_type, condition, category, seller_name, description

Selection is keyed on listing_type IS NULL rather than category or
posted_date: listing_type is present on essentially every detail page —
verified directly against several live pages that still came back
listing_type IS NULL in our own data, and every one of them had the
"Вид на оглас" tag right there. Those rows are legacy: the ordinary
scrape's parse_ad never attempted this field until it was added there
(now it does, so freshly-discovered ads no longer feed this backlog —
see pazar3_spider.parse_ad), so a large share of the pre-existing pool
already has a real listing_type sitting unread on the page, not a
missing one.

The one real gap this spider closes on its own: a page that truly has
no "Вид на оглас" tag at all (a small minority — some categories/ad
types don't carry it) used to leave listing_type null even after being
visited, indistinguishable from "not visited yet" and so re-selected
forever with no way to finish draining. It's now written as the literal
string 'none' in that case instead, so a real visit always leaves this
column non-null and the pool actually empties. Ads confirmed older than
3 years are excluded (see _load_urls) — low analytics value, and a
meaningful chunk of the backlog.

Run in batches of --limit ads per GitHub Actions run (~3-4 hours per 20000 ads).
Each run naturally picks up the next batch since filled ads are excluded.
"""
import logging
import os
import time
from datetime import datetime, timedelta, timezone

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
        # Skip ads confirmed older than 3 years — old, likely-expired
        # listings have little analytics value, and this cuts the backlog
        # by roughly 40%, letting effort concentrate on ads worth having
        # up to date. Ads with no posted_date yet (unknown age, ~8% of the
        # backlog) stay in scope rather than being excluded by default —
        # their age isn't confirmed old.
        cutoff = (datetime.now(timezone.utc) - timedelta(days=3 * 365)).date().isoformat()
        try:
            while len(urls) < self._limit:
                time.sleep(1)
                q = (
                    self._client.table('ads')
                    .select('ad_url')
                    .eq('source', 'pazar3')
                    .is_('listing_type', 'null')
                    .or_(f'posted_date.gte.{cutoff},posted_date.is.null')
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
        else:
            # Explicit sentinel, not left null — see pazar3_spider.parse_ad
            # for why (null vs "checked, genuinely absent" ambiguity).
            update['listing_type'] = 'none'

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
            # Postgres rejects an upsert batch containing 2+ rows for the same
            # conflict key ("ON CONFLICT DO UPDATE command cannot affect row a
            # second time") -- dedupe defensively, keeping the latest entry.
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
