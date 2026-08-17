import os
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy
from ads_scraper.items import AdItem
from ads_scraper.spiders.reklama5_spider import Reklama5Spider, _IMG_URL_RE


class Reklama5OldestSpider(Reklama5Spider):
    """
    Crawls reklama5 from the oldest page backwards to the newest, across
    both tracked categories (cat=580, cat=558).

    Skips detail page visits for ads already in the DB so each run
    advances further toward the data gap instead of re-scraping the
    same oldest pages every time.

    Usage:
        scrapy crawl reklama5_oldest -s DOWNLOAD_DELAY=2 -s CONCURRENT_REQUESTS=1 -s LOG_LEVEL=INFO
    """
    name = 'reklama5_oldest'

    def start_requests(self):
        self._known = self._load_known_urls()
        for url in self.start_urls:
            first_page_url = self._set_page(url, 1)
            self.logger.info('DEBUG requesting first page: %s', first_page_url)
            yield scrapy.Request(
                first_page_url,
                callback=self._discover_pages,
                errback=self._on_discover_error,
                meta={'base_url': url},
            )

    def _on_discover_error(self, failure):
        self.logger.warning('DEBUG discover request failed: %s (url=%s)',
                             failure.value, failure.request.url)

    async def start(self):
        # Scrapy >=2.13 drives crawling from start() rather than
        # start_requests() — bridge to the sync generator above so the
        # known-URL loading and _discover_pages callback actually run.
        for request in self.start_requests():
            yield request

    def _load_known_urls(self):
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        if not url or not key:
            self.logger.warning('No Supabase credentials — known-URL skip disabled')
            return set()
        try:
            from supabase import create_client
            client = create_client(url, key)
            known = set()
            last_url, batch = None, 1000
            while True:
                q = (
                    client.table('ads')
                    .select('ad_url')
                    .eq('source', 'reklama5')
                    .order('ad_url')
                )
                if last_url is not None:
                    q = q.gt('ad_url', last_url)
                rows = q.limit(batch).execute().data
                if not rows:
                    break
                for r in rows:
                    known.add(r['ad_url'])
                if len(rows) < batch:
                    break
                last_url = rows[-1]['ad_url']
            self.logger.info('Loaded %d known reklama5 URLs — will skip detail pages for these', len(known))
            return known
        except Exception as exc:
            self.logger.warning('Could not load known URLs: %s', exc)
            return set()

    def _set_page(self, url, page):
        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        qs['page'] = [str(page)]
        return urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))

    def _discover_pages(self, response):
        base_url = response.meta['base_url']
        self.logger.info('DEBUG _discover_pages: requested=%s status=%s final_url=%s',
                          response.request.url, response.status, response.url)
        _, stated_total = self._page_info(response)
        stated_total = stated_total or 1
        self.logger.info(
            'Stated page count for %s is %d — probing for the real reachable ceiling',
            base_url, stated_total,
        )
        # reklama5's search UI caps browsable results well below the stated
        # "Страна N од M" total (observed: ~110 pages reachable out of 386
        # stated) — anything past the cap 404s. Binary-search for the real
        # last page instead of queuing (and mostly wasting) the full stated
        # range every run.
        yield scrapy.Request(
            self._set_page(base_url, stated_total),
            callback=self._probe_ok,
            errback=self._probe_bad,
            dont_filter=True,
            meta={'base_url': base_url, 'low': 1, 'high': stated_total, 'probe_page': stated_total},
        )

    def _probe_ok(self, response):
        base_url = response.meta['base_url']
        low, high, probe_page = response.meta['low'], response.meta['high'], response.meta['probe_page']
        self.logger.info('DEBUG _probe_ok: page=%d status=%s final_url=%s low=%d high=%d',
                          probe_page, response.status, response.url, low, high)
        if high - probe_page <= 1:
            self.logger.info('%s: last reachable page is %d', base_url, probe_page)
            yield from self._queue_pages(base_url, probe_page)
            return
        mid = (probe_page + high) // 2
        yield scrapy.Request(
            self._set_page(base_url, mid),
            callback=self._probe_ok,
            errback=self._probe_bad,
            dont_filter=True,
            meta={'base_url': base_url, 'low': probe_page, 'high': high, 'probe_page': mid},
        )

    def _probe_bad(self, failure):
        base_url = failure.request.meta['base_url']
        low, high, probe_page = failure.request.meta['low'], failure.request.meta['high'], failure.request.meta['probe_page']
        self.logger.info('DEBUG _probe_bad: page=%d failure=%s low=%d high=%d',
                          probe_page, failure.value, low, high)
        if probe_page - low <= 1:
            self.logger.info('%s: last reachable page is %d', base_url, low)
            yield from self._queue_pages(base_url, low)
            return
        mid = (low + probe_page) // 2
        yield scrapy.Request(
            self._set_page(base_url, mid),
            callback=self._probe_ok,
            errback=self._probe_bad,
            dont_filter=True,
            meta={'base_url': base_url, 'low': low, 'high': probe_page, 'probe_page': mid},
        )

    def _queue_pages(self, base_url, last_valid_page):
        self.logger.info('Queuing %s from page %d down to 1', base_url, last_valid_page)
        for page in range(last_valid_page, 0, -1):
            yield scrapy.Request(
                self._set_page(base_url, page),
                callback=self._parse_listing_page,
                priority=page,
                errback=self._on_error,
                meta={'page': page, 'base_url': base_url},
            )

    def _on_error(self, failure):
        page = failure.request.meta.get('page', '?')
        self.logger.warning('Page %s failed (%s) — skipping', page, failure.value)

    def _parse_listing_page(self, response):
        blocks = response.css('div.row.ad-top-div')
        self.logger.info('DEBUG _parse_listing_page: page=%s status=%s final_url=%s listings=%d',
                          response.meta.get('page', '?'), response.status, response.url, len(blocks))

        for block in blocks:
            item = AdItem()
            item['source'] = 'reklama5'
            link = block.css('a.SearchAdTitle::attr(href)').get()
            item['ad_url'] = response.urljoin(link) if link else response.url
            item['title'] = block.css('a.SearchAdTitle::text').get()
            item['description'] = block.css('p.searchAdDesc::text').get()

            price = block.css('span.search-ad-price::text').get()
            if price:
                item['price'] = price.strip()

            city = block.css('span.city-span::text').get()
            if city:
                item['location'] = city.strip()

            img_style = block.css('.ad-image::attr(style)').get()
            images = []
            if img_style:
                m = _IMG_URL_RE.search(img_style)
                if m:
                    src = m.group(1).strip().strip('"\'')
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = response.urljoin(src)
                    images.append(src)
            item['images'] = images
            item['specs'] = {}

            if not link:
                yield item
                continue

            ad_url = response.urljoin(link)
            if ad_url in self._known:
                # Already in DB — no need to visit detail page
                continue

            yield response.follow(
                link,
                callback=self.parse_ad,
                meta={'listing': dict(item)},
                errback=self._on_error,
            )
        # No next-page following — all pages are already queued from _discover_pages
