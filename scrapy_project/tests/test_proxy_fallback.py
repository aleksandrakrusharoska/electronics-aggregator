"""ProxyMiddleware: reklama5 always through the proxy, pazar3 only after it
answers 403 (then for the rest of the run)."""
from types import SimpleNamespace

from scrapy.http import HtmlResponse, Request

from ads_scraper.middlewares import ProxyMiddleware

PROXY = 'http://user:pass@proxy.example:8000'
P3 = 'https://www.pazar3.mk/oglasi/elektronika/prodazba-kupuvanje-zamena'


class _Stats:
    def __init__(self):
        self.values = {}

    def inc_value(self, key):
        self.values[key] = self.values.get(key, 0) + 1


def _spider():
    return SimpleNamespace(logger=SimpleNamespace(warning=lambda *a, **k: None),
                           crawler=SimpleNamespace(stats=_Stats()))


def test_reklama5_always_proxied_pazar3_direct():
    mw, spider = ProxyMiddleware(PROXY), _spider()
    r5 = Request('https://reklama5.mk/Search?city=&cat=0')
    p3 = Request(P3)
    mw.process_request(r5, spider)
    mw.process_request(p3, spider)
    assert r5.meta['proxy'] == PROXY
    assert 'proxy' not in p3.meta


def test_pazar3_403_is_retried_through_the_proxy_for_the_rest_of_the_run():
    mw, spider = ProxyMiddleware(PROXY), _spider()
    first = Request(P3)
    mw.process_request(first, spider)
    retry = mw.process_response(first, HtmlResponse(P3, status=403, request=first), spider)
    assert isinstance(retry, Request) and retry.dont_filter
    assert spider.crawler.stats.values['proxy_fallback/403'] == 1

    mw.process_request(retry, spider)
    assert retry.meta['proxy'] == PROXY
    later = Request(P3 + '?Page=2')
    mw.process_request(later, spider)
    assert later.meta['proxy'] == PROXY


def test_no_proxy_configured_keeps_the_403():
    mw, spider = ProxyMiddleware(None), _spider()
    req = Request(P3)
    resp = HtmlResponse(P3, status=403, request=req)
    assert mw.process_response(req, resp, spider) is resp


def test_403_through_the_proxy_is_not_retried_again():
    mw, spider = ProxyMiddleware(PROXY), _spider()
    req = Request(P3, meta={'proxy': PROXY})
    resp = HtmlResponse(P3, status=403, request=req)
    assert mw.process_response(req, resp, spider) is resp
