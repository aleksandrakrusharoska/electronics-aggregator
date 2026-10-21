"""IncrementalCheckPipeline: loading the known URLs and stopping the crawl (no network)."""
from types import SimpleNamespace

import pytest
from scrapy.exceptions import DropItem

import lookups
import supabase
from ads_scraper import pipelines
from ads_scraper.pipelines import IncrementalCheckPipeline


class FakeQuery:
    """Just enough of the supabase query builder: eq/gt/order/limit/execute."""

    def __init__(self, urls, fail):
        self.urls, self.fail, self.after, self.n = urls, fail, '', None

    def select(self, _cols):
        return self

    def eq(self, _col, _val):
        return self

    def gt(self, _col, val):
        self.after = val
        return self

    def order(self, _col):
        return self

    def limit(self, n):
        self.n = n
        return self

    def execute(self):
        if self.fail:
            raise RuntimeError('canceling statement due to statement timeout')
        page = [u for u in sorted(self.urls) if u > self.after][:self.n]
        return SimpleNamespace(data=[{'ad_url': u} for u in page])


def _spider(monkeypatch, urls, fail=False):
    client = SimpleNamespace(table=lambda _name: FakeQuery(urls, fail))
    monkeypatch.setattr(supabase, 'create_client', lambda _url, _key: client)
    monkeypatch.setattr(lookups, 'get_lookups', lambda _client: SimpleNamespace(source_id=lambda *_a, **_k: 1))
    monkeypatch.setattr(pipelines.time, 'sleep', lambda _s: None)
    closed = []
    settings = {'INCREMENTAL': True, 'SUPABASE_URL': 'u', 'SUPABASE_KEY': 'k'}
    crawler = SimpleNamespace(
        settings=SimpleNamespace(getbool=lambda k, d=False: bool(settings.get(k, d)), get=settings.get),
        engine=SimpleNamespace(close_spider=lambda _spider, reason: closed.append(reason)))
    return SimpleNamespace(name='pazar3', crawler=crawler), closed


def test_known_urls_are_read_page_by_page(monkeypatch):
    urls = [f'https://pazar3.mk/oglas/{i:05d}' for i in range(2500)]   # three pages of 1000
    spider, _ = _spider(monkeypatch, urls)
    p = IncrementalCheckPipeline()
    p.open_spider(spider)
    assert p._known == set(urls)
    with pytest.raises(DropItem):
        p.process_item({'ad_url': urls[0]}, spider)
    assert p.process_item({'ad_url': 'https://pazar3.mk/oglas/new'}, spider)


def test_failed_load_stops_the_crawl_after_the_cap(monkeypatch):
    spider, closed = _spider(monkeypatch, [], fail=True)
    p = IncrementalCheckPipeline()
    p.open_spider(spider)
    for i in range(IncrementalCheckPipeline.MAX_ITEMS_WITHOUT_KNOWN - 1):
        p.process_item({'ad_url': f'https://pazar3.mk/oglas/{i}'}, spider)
    assert closed == []
    p.process_item({'ad_url': 'https://pazar3.mk/oglas/last'}, spider)
    assert closed == ['incremental_unknown_cap']
