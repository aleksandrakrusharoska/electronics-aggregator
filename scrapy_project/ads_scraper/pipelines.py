import json
import logging
import time
from datetime import datetime, timezone

from ads_scraper.normalize import clean_description, clean_text, parse_price, resolve_posted_date, strip_emoji

logger = logging.getLogger(__name__)

MAX_QUERY_RETRIES = 3


def _execute_with_retry(query):
    """The ads table sees frequent transient statement timeouts under
    concurrent load from scheduled scraping/parsing jobs — retry a few
    times with backoff before giving up."""
    for attempt in range(1, MAX_QUERY_RETRIES + 1):
        try:
            return query.execute()
        except Exception as exc:
            if attempt == MAX_QUERY_RETRIES:
                raise
            wait = 2 ** attempt
            logger.warning('Supabase query failed (attempt %d/%d): %s — retrying in %ds',
                           attempt, MAX_QUERY_RETRIES, exc, wait)
            time.sleep(wait)


def to_db_row(d: dict, lookups) -> dict:
    """Replace the name fields spiders produce (source, category, location)
    with the lookup-table foreign keys the normalized `ads` table stores.
    Keys absent from `d` stay absent, so partial upserts (backfill spiders
    updating a single column) don't blank out other columns."""
    d = dict(d)
    source_id = None
    if 'source' in d:
        source_id = lookups.source_id(d.pop('source'))
        d['source_id'] = source_id
    if 'category' in d:
        category = d.pop('category')
        if source_id is None:
            raise ValueError(f"category without source for {d.get('ad_url')}")
        d['category_id'] = lookups.category_id(source_id, category)
    if 'location' in d:
        d['location_id'] = lookups.location_id(d.pop('location'))
    return d


class NormalizePipeline:
    """Clean and normalise every item before it reaches the writer."""

    def process_item(self, item, spider):
        now_utc = datetime.now(timezone.utc).isoformat()
        item['scraped_at'] = now_utc

        item['title'] = strip_emoji(clean_text(item.get('title')))
        # description keeps its line breaks and emojis — sellers use both
        # (bullet lists, section breaks) and the frontend already renders
        # them (whitespace-pre-line); only the title needs to stay flat.
        item['description'] = clean_description(item.get('description'))
        item['location'] = clean_text(item.get('location')) or None

        # The raw scraped `price` text becomes amount + currency; price_mkd is
        # a generated column in the DB. An amount without a recognised
        # currency is dropped rather than silently treated as MKD — no price
        # means "по договор" to the frontend, same as a missing one.
        price_fields = parse_price(item.pop('price', None))
        currency = item.get('currency') or price_fields['currency']
        if currency in ('MKD', 'EUR') and price_fields['price_amount'] is not None:
            item['price_amount'] = float(price_fields['price_amount'])
            item['currency'] = currency
        else:
            item['price_amount'] = None
            item['currency'] = None

        item['posted_date'] = resolve_posted_date(item.get('posted_date'), now_utc)

        return item


class JsonWriterPipeline:
    """Write items to a JSON Lines file named <spider.name>_items.jl"""

    file = None

    def open_spider(self, spider):
        self.file = open(f"{spider.name}_items.jl", "w", encoding="utf-8")

    def close_spider(self, spider):
        if self.file is not None:
            self.file.close()

    def process_item(self, item, spider):
        line = json.dumps(dict(item), ensure_ascii=False) + "\n"
        self.file.write(line)
        return item


class IncrementalCheckPipeline:
    """
    In incremental mode, drops items whose ad_url already exists in Supabase.
    Closes the spider after INCREMENTAL_STOP_AFTER consecutive known items,
    since listing pages are sorted newest-first.
    """

    STOP_AFTER = 50
    # Without the known URLs the spider can't tell where the new ads end. A
    # normal day brings ~150 new ads per portal, so this many means it is
    # re-scraping old ones: stop rather than crawl until the step times out
    # (and, for pazar3 behind the proxy, spend paid traffic on it).
    MAX_ITEMS_WITHOUT_KNOWN = 400

    def open_spider(self, spider):
        self._known = set()
        self._consecutive = 0
        self._new = 0
        self._load_failed = False
        if not spider.crawler.settings.getbool('INCREMENTAL', False):
            return
        url = spider.crawler.settings.get('SUPABASE_URL')
        key = spider.crawler.settings.get('SUPABASE_KEY')
        if not url or not key:
            return
        from supabase import create_client
        from lookups import get_lookups
        client = create_client(url, key)
        source_id = get_lookups(client).source_id(spider.name, create=False)
        if source_id is None:
            logger.warning('IncrementalCheckPipeline: unknown source %r, nothing to skip.', spider.name)
            return
        # Every URL of the source, a page at a time after the last URL seen
        # (keyset on the (source_id, ad_url) index). The earlier query, only
        # URLs scraped in the last 30 days with offset paging, had to read the
        # table rows for scraped_at and hit the statement timeout on its
        # first page for pazar3 every day from 2026-10-13: the crawl then knew
        # no ads and re-scraped until the 75-minute step timeout.
        logger.info('IncrementalCheckPipeline: loading known URLs for %s...', spider.name)
        last, batch = '', 1000
        try:
            while True:
                rows = _execute_with_retry(
                    client.table('ads')
                    .select('ad_url')
                    .eq('source_id', source_id)
                    .gt('ad_url', last)
                    .order('ad_url')
                    .limit(batch)
                ).data
                self._known.update(r['ad_url'] for r in rows)
                if len(rows) < batch:
                    break
                last = rows[-1]['ad_url']
        except Exception as exc:
            # Even after retries the DB is still timing out — don't crash the
            # whole spider over a skip-known-ads optimization. Continue with
            # whatever was loaded so far, capped by MAX_ITEMS_WITHOUT_KNOWN.
            self._load_failed = True
            logger.error('IncrementalCheckPipeline: failed to load known URLs (loaded %d so far): %s',
                         len(self._known), exc)
        logger.info('IncrementalCheckPipeline: %d known URLs loaded.', len(self._known))

    def process_item(self, item, spider):
        if not spider.crawler.settings.getbool('INCREMENTAL', False):
            return item
        if self._load_failed:
            self._new += 1
            if self._new == self.MAX_ITEMS_WITHOUT_KNOWN:
                logger.warning('Known URLs failed to load and %d ads were scraped — stopping spider.', self._new)
                spider.crawler.engine.close_spider(spider, 'incremental_unknown_cap')
        url = item.get('ad_url')
        if url and url in self._known:
            self._consecutive += 1
            logger.debug('Known ad (%d consecutive): %s', self._consecutive, url)
            if self._consecutive >= self.STOP_AFTER:
                logger.info('Reached %d consecutive known ads — stopping spider.', self.STOP_AFTER)
                spider.crawler.engine.close_spider(spider, 'incremental_done')
            from scrapy.exceptions import DropItem
            raise DropItem(f'Already in DB: {url}')
        self._consecutive = 0
        return item


class SupabasePipeline:
    """Upsert items to Supabase in batches as the spider runs."""

    BATCH_SIZE = 100

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            url=crawler.settings.get('SUPABASE_URL'),
            key=crawler.settings.get('SUPABASE_KEY'),
        )

    def __init__(self, url, key):
        self.url = url
        self.key = key
        self.client = None
        self._batch = []

    def open_spider(self, spider):
        if not self.url or not self.key:
            raise RuntimeError('SUPABASE_URL and SUPABASE_KEY must be set in .env')
        from supabase import create_client
        from lookups import get_lookups
        self.client = create_client(self.url, self.key)
        self.lookups = get_lookups(self.client)
        logger.info('Supabase pipeline connected.')

    def close_spider(self, spider):
        self._flush()

    def process_item(self, item, spider):
        d = to_db_row(dict(item), self.lookups)
        # images and specs arrive as Python objects from NormalizePipeline
        self._batch.append(d)
        if len(self._batch) >= self.BATCH_SIZE:
            self._flush()
        return item

    def _flush(self):
        if not self._batch:
            return
        try:
            from lookups import upsert_rows
            upsert_rows(self.client, 'ads', self._batch, on_conflict='ad_url')
            logger.debug('Upserted %d items to Supabase.', len(self._batch))
        except Exception as e:
            logger.error('Supabase upsert failed (%d items): %s', len(self._batch), e)
        self._batch = []
