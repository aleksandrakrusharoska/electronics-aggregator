"""
One-off price check: restores prices the LLM parser overwrote by mistake.

From 2026-08-13 to 2026-10-03 the parser replaced an ad's price whenever its
description restated a number more than 2x different, and sellers write
thousands as shorthand ("18" for 18.000 ден), so correct prices became
18 MKD and the like. The damaged rows aren't marked, but the seller's own
price is still on the ad page. This spider revisits the candidates (parsed
since 2026-08-13, price now under 1000 MKD), reads the price with the daily
spiders' own parse_ad + NormalizePipeline, and:

  * page price differs  -> restores it (our bug)
  * page price matches  -> leaves it (genuinely cheap, or the seller's typo)
  * page has no price   -> leaves it, counted separately
  * ad removed          -> marks it inactive, as the rescrape spiders do

Dry run by default: nothing is written until -a dry_run=0. Every decision
goes to price_check_report.csv.

    scrapy crawl price_check -a source=reklama5 -a limit=40          # dry run
    scrapy crawl price_check -a source=pazar3 -a part=1 -a parts=2 -a dry_run=0
"""
import csv
import logging
import os
import time

import scrapy
from dotenv import load_dotenv

from ads_scraper.pipelines import NormalizePipeline
from ads_scraper.spiders.pazar3_spider import Pazar3Spider
from ads_scraper.spiders.reklama5_spider import Reklama5Spider
from ads_scraper.normalize import MKD_PER_EUR

load_dotenv()
logger = logging.getLogger(__name__)

PARSED_SINCE = '2026-08-13'   # the day the overwriting started
MAX_PRICE_MKD = 1000          # shorthand amounts end up below this
REPORT = 'price_check_report.csv'


def _to_mkd(amount, currency):
    if amount is None or currency not in ('MKD', 'EUR'):
        return None
    return float(amount) * (MKD_PER_EUR if currency == 'EUR' else 1)


class PriceCheckSpider(scrapy.Spider):
    name = 'price_check'
    allowed_domains = ['pazar3.mk', 'reklama5.mk', 'www.reklama5.mk']
    custom_settings = {
        'DOWNLOAD_DELAY': 2,
        'CONCURRENT_REQUESTS': 2,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 1.5,
        'ITEM_PIPELINES': {},
        'HTTPERROR_ALLOWED_CODES': [404, 301, 302],
    }

    def __init__(self, source='all', limit=0, part=1, parts=1, dry_run='1', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._source = source
        self._limit = int(limit)
        self._part, self._parts = int(part), int(parts)
        self._dry_run = str(dry_run) not in ('0', 'false', 'False', 'no')
        self._parsers = {'pazar3': Pazar3Spider(), 'reklama5': Reklama5Spider()}
        self._normalize = NormalizePipeline()
        self._report = open(REPORT, 'w', newline='', encoding='utf-8')
        self._csv = csv.writer(self._report)
        self._csv.writerow(['action', 'ad_url', 'db_amount', 'db_currency', 'page_amount', 'page_currency'])
        self._candidates = {}
        self._connect_and_load()

    # ---------------------------------------------------------------- setup
    def _retry(self, fn, what):
        for attempt in range(1, 4):
            try:
                return fn()
            except Exception as exc:
                if attempt == 3:
                    raise
                logger.warning('%s failed (%s), retrying.', what, exc)
                time.sleep(5 * attempt)

    def _page_through(self, make_query):
        rows, last = [], None
        while True:
            q = make_query().order('ad_url').limit(1000)
            if last is not None:
                q = q.gt('ad_url', last)
            batch = self._retry(lambda: q.execute().data, 'Supabase page')
            rows += batch
            if len(batch) < 1000:
                return rows
            last = batch[-1]['ad_url']

    def _connect_and_load(self):
        from supabase import create_client
        self._client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
        sources = {r['name']: r['source_id'] for r in
                   self._client.table('sources').select('source_id,name').execute().data}
        names = {v: k for k, v in sources.items()}

        parsed = {r['ad_url'] for r in self._page_through(
            lambda: self._client.table('ad_analysis').select('ad_url').gte('llm_parsed_at', PARSED_SINCE))}
        cheap = self._page_through(
            lambda: self._client.table('ads').select('ad_url,source_id,price_amount,currency,price_mkd')
            .lt('price_mkd', MAX_PRICE_MKD))

        cands = [r for r in cheap if r['ad_url'] in parsed
                 and (self._source == 'all' or names.get(r['source_id']) == self._source)]
        # split into parts so each GitHub run stays under its 6-hour limit
        cands = [r for i, r in enumerate(cands) if i % self._parts == self._part - 1]
        if self._limit:
            cands = cands[:self._limit]
        for r in cands:
            r['source'] = names[r['source_id']]
            self._candidates[r['ad_url']] = r
        logger.info('Price check: %d candidates (source=%s, part %d/%d, dry_run=%s)',
                    len(self._candidates), self._source, self._part, self._parts, self._dry_run)

    async def start(self):
        for url, row in self._candidates.items():
            meta = {'listing': {'ad_url': url}, 'original_url': url}
            if row['source'] == 'reklama5':
                # reklama5 redirects removed ads to /Search (and non-Macedonian
                # IPs to reklama5.com); answer those instead of following them.
                # pazar3 301s live ads to a canonical path, so follow there.
                meta['dont_redirect'] = True
            yield scrapy.Request(url, callback=self.parse_ad, errback=self.errback, meta=meta)

    # ---------------------------------------------------------------- checking
    def parse_ad(self, response):
        url = response.meta['original_url']
        row = self._candidates[url]
        db = (row['price_amount'], row['currency'])

        if response.status == 404 or (
                response.status in (301, 302)
                and '/AdDetails' not in response.headers.get('Location', b'').decode('latin-1')
                and 'reklama5.com' not in response.headers.get('Location', b'').decode('latin-1')):
            return self._decide('removed', url, db, (None, None), {'is_active': False})
        if response.status in (301, 302):
            return self._decide('skipped_geo_redirect', url, db, (None, None), None)

        item = next((x for x in self._parsers[row['source']].parse_ad(response)
                     if not isinstance(x, scrapy.Request)), None)
        if item is None:
            return self._decide('skipped_unparsed', url, db, (None, None), None)
        item = self._normalize.process_item(dict(item), self)
        page = (item.get('price_amount'), item.get('currency'))

        page_mkd, db_mkd = _to_mkd(*page), _to_mkd(*db)
        if page_mkd is None:
            return self._decide('page_has_no_price', url, db, page, None)
        if db_mkd is not None and abs(page_mkd - db_mkd) <= 0.02 * max(page_mkd, db_mkd):
            return self._decide('unchanged', url, db, page, None)
        return self._decide('restored', url, db, page,
                            {'price_amount': page[0], 'currency': page[1]})

    def _decide(self, action, url, db, page, update):
        self.crawler.stats.inc_value(f'price_check/{action}')
        self._csv.writerow([action, url, *db, *page])
        if update and not self._dry_run:
            self._retry(lambda: self._client.table('ads').update(update).eq('ad_url', url).execute(),
                        'Supabase update')
        if action == 'restored':
            logger.info('%s %s: %s %s -> %s %s', 'Would restore' if self._dry_run else 'Restored',
                        url, *db, *page)

    def errback(self, failure):
        self.crawler.stats.inc_value('price_check/request_failed')
        logger.warning('Request failed: %s (url=%s)', failure.value, failure.request.url)

    def closed(self, reason):
        self._report.close()
        stats = {k.split('/', 1)[1]: v for k, v in self.crawler.stats.get_stats().items()
                 if k.startswith('price_check/')}
        logger.info('Price check done (%s, dry_run=%s): %s', reason, self._dry_run, stats)
