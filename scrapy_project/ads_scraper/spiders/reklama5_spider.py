import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import scrapy
from ads_scraper.items import AdItem

_IMG_URL_RE = re.compile(r"url\(([^)]+)\)")


class Reklama5Spider(scrapy.Spider):
    name = 'reklama5'
    allowed_domains = ['reklama5.mk', 'www.reklama5.mk']
    start_urls = [
        'https://reklama5.mk/Search?city=&cat=580&q=&sell=0&sell=1&buy=0&buy=1&trade=0&trade=1&includeOld=0&includeOld=1&includeNew=0&includeNew=1&cargoReady=0&DDVIncluded=0&private=0&company=0&page=1&SortByPrice=0&zz=1&pageView=',
        'https://reklama5.mk/Search?city=&cat=558&q=&sell=0&sell=1&buy=0&buy=1&trade=0&trade=1&includeOld=0&includeOld=1&includeNew=0&includeNew=1&cargoReady=0&DDVIncluded=0&private=0&company=0&page=1&SortByPrice=0&zz=1&pageView=',
    ]

    def __init__(self, start_url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if start_url:
            self.start_urls = [u.strip() for u in start_url.split('|') if u.strip()]

    def _next_page_url(self, url):
        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        current = int(qs.get('page', ['1'])[0])
        qs['page'] = [str(current + 1)]
        return urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))

    def _page_info(self, response):
        """Return (current_page, total_pages) from 'Страна N од M' span, or (None, None)."""
        text = response.css('span.number-of-pages::text').get('')
        m = re.search(r'(\d+)\s+од\s+(\d+)', text)
        if m:
            return int(m.group(1)), int(m.group(2))
        return None, None

    def parse(self, response):
        blocks = response.css('div.row.ad-top-div')
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

            if link:
                yield response.follow(
                    link,
                    callback=self.parse_ad,
                    meta={'listing': dict(item)},
                )
            else:
                yield item

        current_page, total_pages = self._page_info(response)
        if current_page is not None and total_pages is not None:
            self.logger.debug('Page %d/%d — %s', current_page, total_pages, response.url)
            if current_page >= total_pages:
                self.logger.info('Reached last page (%d/%d), stopping.', current_page, total_pages)
                return
        elif not blocks:
            self.logger.info('No items and no page-info on %s — stopping.', response.url)
            return

        next_url = self._next_page_url(response.url)
        # Lower priority than the item-detail requests above — see
        # pazar3_spider.py for why this matters for the incremental stop logic.
        yield scrapy.Request(next_url, callback=self.parse, priority=-1)

    def parse_ad(self, response):
        listing = response.meta.get('listing') or {}
        item = AdItem()
        for k, v in listing.items():
            item[k] = v

        item['ad_url'] = response.url

        title = response.css('h5.card-title::text').get()
        if title:
            item['title'] = title.strip()

        # Price h5 contains two text nodes: amount and currency
        price_parts = [t.strip() for t in response.css('h5.mb-0.defaultBlue::text').getall() if t.strip()]
        if price_parts:
            item['price'] = ' '.join(price_parts)

        desc = response.css('p.mt-3::text').get()
        if desc:
            item['description'] = desc.strip()

        seller = response.css('div.row.mb-2.mt-2 div.col-9 h5.my-0::text').get()
        if seller:
            item['seller_name'] = seller.strip()

        # Images use src2 attribute (lazy-loaded by the galleria plugin)
        images = []
        for src in response.css('div.adDetails.galleria img::attr(src2)').getall():
            src = src.split('?')[0].strip()
            if src.startswith('//'):
                src = 'https:' + src
            if src:
                images.append(src)
        if not images:
            # Fallback: visible slider image
            src = response.css('div.r5-slider img::attr(src)').get('')
            src = src.split('?')[0].strip()
            if src.startswith('//'):
                src = 'https:' + src
            if src:
                images = [src]
        if images:
            item['images'] = images

        # Specs: look for two-column table rows anywhere on the page
        specs = {}
        for row in response.css('table tr'):
            tds = row.css('td')
            if len(tds) >= 2:
                k = tds[0].css('::text').get('').strip()
                v = tds[1].css('::text').get('').strip()
                if k and v and k != v:
                    specs[k.lower()] = v
        if specs:
            item['specs'] = specs

        yield item
