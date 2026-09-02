import scrapy
from ads_scraper.items import AdItem


class Pazar3Spider(scrapy.Spider):
    name = 'pazar3'
    allowed_domains = ['pazar3.mk']
    start_urls = ['https://www.pazar3.mk/oglasi/elektronika/prodazba-kupuvanje-zamena']
    custom_settings = {
        'DOWNLOAD_DELAY': 3,
        'CONCURRENT_REQUESTS': 1,
    }

    def __init__(self, start_url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if start_url:
            self.start_urls = [u.strip() for u in start_url.split('|') if u.strip()]

    # pazar3.mk serves inconsistent results for the exact same listing-page
    # URL — repeat requests moments apart can return 0, a handful, or a
    # full page of listings, seemingly load-balanced across backends that
    # aren't in sync. An empty page is never legitimate mid-crawl (only a
    # real end-of-pagination, signaled separately by the missing next-page
    # link, ends it), so retry a few times before accepting it.
    EMPTY_PAGE_RETRIES = 3

    def parse(self, response):
        from urllib.parse import urlparse, parse_qs

        listings = response.css('div.row-listing, div.row.row-listing')
        if not listings:
            retries = response.meta.get('empty_retries', 0)
            if retries < self.EMPTY_PAGE_RETRIES:
                self.logger.warning(
                    'Empty listing page at %s (retry %d/%d) — pazar3.mk inconsistency, not end of results',
                    response.url, retries + 1, self.EMPTY_PAGE_RETRIES)
                yield scrapy.Request(
                    response.url,
                    callback=self.parse,
                    dont_filter=True,
                    meta={**response.meta, 'empty_retries': retries + 1},
                )
                return
            self.logger.warning('Empty listing page at %s after %d retries — giving up on this page',
                                 response.url, self.EMPTY_PAGE_RETRIES)

        for l in listings:
            item = AdItem()
            title = l.css('h2 a::text').get()
            href = l.css('h2 a::attr(href)').get()
            img = l.css('img::attr(data-src)').get() or l.css('img::attr(src)').get()
            price = l.css('p.list-price::text').get()
            posted = l.css('span.pull-right::text').get()
            crumbs = l.css('a.link-html.nobold::text').getall()
            location = crumbs[-1].strip() if crumbs else None

            item['title'] = title.strip() if title else None
            item['ad_url'] = response.urljoin(href) if href else None
            item['images'] = [response.urljoin(img)] if img else []
            item['price'] = price.strip() if price else None
            item['posted_date'] = posted.strip() if posted else None
            item['location'] = location
            item['source'] = 'pazar3'

            if href:
                yield response.follow(
                    href,
                    callback=self.parse_ad,
                    meta={'listing': dict(item)},
                )
            else:
                yield item

        next_btn = response.css('a.next.page-number:not(.disabled)::attr(href)').get()
        if not next_btn:
            parsed = urlparse(response.url)
            from urllib.parse import parse_qs
            params = parse_qs(parsed.query)
            current = int(params.get('Page', ['1'])[0])
            next_btn = response.css(f'a.page-number[page-no="{current+1}"]::attr(href)').get()
        if next_btn:
            # Lower priority than the item-detail requests above, so Scrapy's
            # default LIFO scheduler finishes this page's ads before moving
            # on — otherwise it dives through pagination depth-first, which
            # breaks IncrementalCheckPipeline's "stop after N consecutive
            # known ads" assumption that items arrive newest-first.
            yield response.follow(next_btn, callback=self.parse, priority=-1)

    def parse_ad(self, response):
        listing = response.meta.get('listing') or {}
        item = AdItem()
        for k, v in listing.items():
            item[k] = v

        item['ad_url'] = response.url
        item['source'] = 'pazar3'

        title = response.css('h1.ci-text-base::text').get()
        if title:
            item['title'] = title.strip()

        # Description is in the <meta name="description"> tag (server-rendered, reliable)
        desc = response.css('meta[name="description"]::attr(content)').get()
        if desc:
            item['description'] = desc.strip()

        # Price value attribute on the bdi element
        price_val = response.css('bdi.format-money-int::attr(value)').get()
        if price_val:
            item['price'] = price_val.strip() + ' МКД'

        # Published date
        pub_date = response.css('bdi.published-date::text').get()
        pub_time = response.css('bdi.published-time::text').get()
        if pub_date:
            item['posted_date'] = (pub_date.strip() + ' ' + pub_time.strip()).strip() if pub_time else pub_date.strip()

        # Gallery images (main photo slider only, not related-ads thumbnails)
        images = [
            src.strip() for src in
            response.css('img.custom-photo-zoom::attr(data-src)').getall()
            if src.strip()
        ]
        if images:
            item['images'] = images

        # Seller name
        seller = response.css('div.user-name.ci-text-base::text').get()
        if seller:
            item['seller_name'] = seller.strip()

        # Structured tag-items: Condition, category, seller type, etc.
        tag_map = {}
        for tag in response.css('a.tag-item'):
            label = tag.css('span::text').get('').strip().rstrip(':').strip()
            value = tag.css('bdi::text').get('').strip()
            if label and value:
                tag_map[label] = value

        if not item.get('location'):
            item['location'] = tag_map.get('Локација')

        condition = tag_map.get('Condition') or tag_map.get('Состојба')
        if condition:
            item['condition'] = condition

        category = tag_map.get('Производи')
        if category:
            item['category'] = category

        advertiser = tag_map.get('Огласено од', '')
        if 'Физичко' in advertiser:
            item['seller_type'] = 'private'
        elif 'Правно' in advertiser or 'Компанија' in advertiser:
            item['seller_type'] = 'business'

        yield item
