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

        price_fields = parse_price(item.get('price'))
        item['price'] = price_fields['price_amount']
        item['currency'] = item.get('currency') or price_fields['currency']
        item['price_eur'] = price_fields['price_eur']
        item['price_mkd'] = price_fields['price_mkd']
        item['price_note'] = price_fields['price_note']

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

    def open_spider(self, spider):
        self._known = set()
        self._consecutive = 0
        if not spider.crawler.settings.getbool('INCREMENTAL', False):
            return
        url = spider.crawler.settings.get('SUPABASE_URL')
        key = spider.crawler.settings.get('SUPABASE_KEY')
        if not url or not key:
            return
        from datetime import datetime, timezone, timedelta
        from supabase import create_client
        client = create_client(url, key)
        # Only load URLs scraped in the last 30 days — enough for incremental
        # check without fetching the entire table (which causes statement timeout).
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        logger.info('IncrementalCheckPipeline: loading recent URLs for %s (since %s)...', spider.name, cutoff[:10])
        offset, batch = 0, 1000
        try:
            while True:
                rows = _execute_with_retry(
                    client.table('ads')
                    .select('ad_url')
                    .eq('source', spider.name)
                    .gte('scraped_at', cutoff)
                    .order('ad_url')
                    .range(offset, offset + batch - 1)
                ).data
                if not rows:
                    break
                for r in rows:
                    self._known.add(r['ad_url'])
                if len(rows) < batch:
                    break
                offset += batch
        except Exception as exc:
            # Even after retries the DB is still timing out — don't crash the
            # whole spider over a skip-known-ads optimization. Continue with
            # whatever was loaded so far (possibly empty); worst case is a
            # few re-scraped ads, not a failed run.
            logger.error('IncrementalCheckPipeline: failed to load known URLs (loaded %d so far): %s',
                         len(self._known), exc)
        logger.info('IncrementalCheckPipeline: %d recent URLs loaded.', len(self._known))

    def process_item(self, item, spider):
        if not spider.crawler.settings.getbool('INCREMENTAL', False):
            return item
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
        self.client = create_client(self.url, self.key)
        logger.info('Supabase pipeline connected.')

    def close_spider(self, spider):
        self._flush()

    def process_item(self, item, spider):
        d = dict(item)
        # images and specs arrive as Python objects from NormalizePipeline
        self._batch.append(d)
        if len(self._batch) >= self.BATCH_SIZE:
            self._flush()
        return item

    def _flush(self):
        if not self._batch:
            return
        try:
            self.client.table('ads').upsert(self._batch, on_conflict='ad_url').execute()
            logger.debug('Upserted %d items to Supabase.', len(self._batch))
        except Exception as e:
            logger.error('Supabase upsert failed (%d items): %s', len(self._batch), e)
        self._batch = []
