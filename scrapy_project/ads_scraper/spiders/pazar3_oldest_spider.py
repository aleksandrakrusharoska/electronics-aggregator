import os
import scrapy
from dotenv import load_dotenv
from ads_scraper.items import AdItem
from ads_scraper.spiders.pazar3_spider import Pazar3Spider

load_dotenv()

BASE = 'https://www.pazar3.mk/oglasi/elektronika/prodazba-kupuvanje-zamena'


class Pazar3OldestSpider(Pazar3Spider):
    """
    Crawls pazar3 from the oldest page backwards to the newest.

    Skips detail page visits for ads already in the DB so each run
    advances further toward the data gap instead of re-scraping the
    same oldest pages every time.

    Usage:
        scrapy crawl pazar3_oldest -s DOWNLOAD_DELAY=2 -s CONCURRENT_REQUESTS=1 -s LOG_LEVEL=INFO
    """
    name = 'pazar3_oldest'

    def start_requests(self):
        self._known = self._load_known_urls()
        yield scrapy.Request(BASE, callback=self._discover_pages)

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
                    .eq('source', 'pazar3')
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
            self.logger.info('Loaded %d known pazar3 URLs — will skip detail pages for these', len(known))
            return known
        except Exception as exc:
            self.logger.warning('Could not load known URLs: %s', exc)
            return set()

    def _discover_pages(self, response):
        page_nos = [
            int(p) for p in response.css('a.page-number::attr(page-no)').getall()
            if p.isdigit()
        ]
        last_page = max(page_nos) if page_nos else 1
        self.logger.info('Discovered %d pages — queuing from page %d down to 1', last_page, last_page)

        for page in range(last_page, 0, -1):
            yield scrapy.Request(
                f'{BASE}?Page={page}',
                callback=self._parse_listing_page,
                priority=page,
                errback=self._on_error,
                meta={'page': page},
            )

    def _on_error(self, failure):
        page = failure.request.meta.get('page', '?')
        self.logger.warning('Page %s failed (%s) — skipping', page, failure.value)

    def _parse_listing_page(self, response):
        if response.status == 404:
            self.logger.warning('Page %s returned 404 — skipping', response.meta.get('page', '?'))
            return

        listings = response.css('div.row-listing, div.row.row-listing')
        self.logger.info('Page %s: %d listings', response.meta.get('page', '?'), len(listings))

        for l in listings:
            item = AdItem()
            title  = l.css('h2 a::text').get()
            href   = l.css('h2 a::attr(href)').get()
            img    = l.css('img::attr(data-src)').get() or l.css('img::attr(src)').get()
            price  = l.css('p.list-price::text').get()
            posted = l.css('span.pull-right::text').get()
            crumbs = l.css('a.link-html.nobold::text').getall()

            item['title']       = title.strip() if title else None
            item['ad_url']      = response.urljoin(href) if href else None
            item['images']      = [response.urljoin(img)] if img else []
            item['price']       = price.strip() if price else None
            item['posted_date'] = posted.strip() if posted else None
            item['location']    = crumbs[-1].strip() if crumbs else None
            item['source']      = 'pazar3'

            if not href:
                yield item
                continue

            ad_url = response.urljoin(href)
            if ad_url in self._known:
                # Already in DB — no need to visit detail page
                continue

            yield response.follow(
                href,
                callback=self.parse_ad,
                meta={'listing': dict(item)},
                errback=self._on_error,
            )
        # No next-page following — all pages are already queued from _discover_pages
