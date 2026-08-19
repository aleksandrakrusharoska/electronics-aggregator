"""
Regression test for the keyset-pagination bug that silently broke run_dedup_agent.py
(and ~10 other files with the same copy-pasted OFFSET-pagination pattern) once the
ads table grew large enough for deep OFFSET queries to exceed Supabase's statement
timeout. Fixed by paginating on a `.gt('ad_url', cursor)` cursor instead of `.range()`.

Exercises the real fetch_ads() from run_dedup_agent.py against an in-memory fake
Supabase client, so it doesn't need a live database.
"""
from run_dedup_agent import FETCH_PAGE, fetch_ads


class FakeResult:
    def __init__(self, data):
        self.data = data


class _Not:
    def __init__(self, query):
        self._query = query

    def is_(self, col, _val):
        self._query._filters.append(('not_null', col, None))
        return self._query


class FakeQuery:
    """Minimal stand-in for a supabase-py query builder — only the chain
    methods fetch_ads() actually calls."""

    def __init__(self, rows):
        self._rows = rows
        self._filters = []
        self._order_col = None
        self._limit_n = None

    def select(self, *_args, **_kwargs):
        return self

    @property
    def not_(self):
        return _Not(self)

    def eq(self, col, val):
        self._filters.append(('eq', col, val))
        return self

    def gt(self, col, val):
        self._filters.append(('gt', col, val))
        return self

    def order(self, col):
        self._order_col = col
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def execute(self):
        rows = list(self._rows)
        for op, col, val in self._filters:
            if op == 'eq':
                rows = [r for r in rows if r.get(col) == val]
            elif op == 'gt':
                rows = [r for r in rows if r.get(col) is not None and r[col] > val]
            elif op == 'not_null':
                rows = [r for r in rows if r.get(col) is not None]
        if self._order_col:
            rows = sorted(rows, key=lambda r: r[self._order_col])
        if self._limit_n is not None:
            rows = rows[: self._limit_n]
        return FakeResult(rows)


class FakeClient:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return FakeQuery(self._rows)


def _make_rows(n, source='pazar3', domain='example.mk'):
    return [
        {
            'ad_url': f'https://{domain}/ad/{i:05d}',
            'title': f'Ad {i}',
            'price_eur': 10.0,
            'source': source,
            'seller_name': 'seller',
        }
        for i in range(n)
    ]


def test_fetch_ads_paginates_past_a_single_page():
    # More rows than FETCH_PAGE, so the cursor loop is forced to actually
    # advance across multiple pages — the exact code path that silently
    # broke once a table grew past ~9000 rows under OFFSET pagination.
    rows = _make_rows(FETCH_PAGE * 2 + 137)
    client = FakeClient(rows)

    result = fetch_ads(client)

    got = sorted(r['ad_url'] for r in result)
    want = sorted(r['ad_url'] for r in rows)
    assert got == want, 'pagination must return every row exactly once, with no gaps or duplicates'


def test_fetch_ads_filters_by_source():
    rows = (
        _make_rows(50, source='pazar3', domain='pazar3.mk')
        + _make_rows(50, source='reklama5', domain='reklama5.mk')
    )
    client = FakeClient(rows)

    result = fetch_ads(client, source='pazar3')

    assert len(result) == 50
    assert all(r['source'] == 'pazar3' for r in result)


def test_fetch_ads_excludes_null_title():
    rows = _make_rows(20)
    rows[5]['title'] = None
    client = FakeClient(rows)

    result = fetch_ads(client)

    assert len(result) == 19
    assert all(r['title'] is not None for r in result)
