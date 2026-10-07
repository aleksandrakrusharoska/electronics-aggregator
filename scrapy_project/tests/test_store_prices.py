from agents.reference_price_agent import compute_reference_prices
from agents.store_price_agent import _has_token, _num, _tokens, is_generic, robust_prices


def test_store_price_formats():
    assert _num('39.980,00 ден.') == 39980      # Anhoch
    assert _num('129,000.00') == 129000         # Mobelix
    assert _num('33.190') == 33190              # Ledikom / phones.mk
    assert _num('') is None


def test_model_words_ignore_brand_and_filler():
    assert _tokens('Apple iPhone 15 128GB', 'Apple') == ['iphone', '15', '128gb']
    assert _tokens('Samsung Galaxy A54 5G', 'Samsung') == ['a54']


def test_ordinal_generations_match_plain_numbers():
    assert _has_token('2', _tokens('AirPods Pro (2nd generation)'))
    assert not _has_token('2', _tokens('AirPods Pro 3'))


def test_one_far_off_store_is_dropped():
    # Setec listing only the 1TB iPhone 16 Pro Max next to five stores at 61-84k
    kept, ambiguous = robust_prices([61500, 66390, 69990, 79990, 83990, 131290])
    assert 131290 not in kept and not ambiguous


def test_stores_that_really_disagree_are_ambiguous():
    _, ambiguous = robust_prices([20000, 21000, 90000, 95000])  # two cheap vs two expensive
    assert ambiguous


def _ad(**kw):
    return {'ad_url': 'u', 'brand': 'Apple', 'model': 'iPhone 15', 'condition': 'Used - Good',
            'price_mkd': 20000, 'title': 'iPhone 15', **kw}


def test_store_price_comes_before_marketplace():
    new_listings = [_ad(ad_url=f'n{i}', condition='New', price_mkd=30000) for i in range(3)]
    r = compute_reference_prices([_ad()] + new_listings, {'apple|iphone 15': (40000.0, 6)})[0]
    assert r['reference_source'] == 'store' and r['reference_new_price_mkd'] == 40000


def test_no_store_and_no_marketplace_means_no_reference():
    r = compute_reference_prices([_ad()], {})[0]
    assert r['reference_source'] is None and r['good_price_deal'] is False


def test_category_words_alone_are_too_generic():
    assert is_generic('Optoma', 'projector')
    assert is_generic('Philips', 'TV')
    assert is_generic('Apple', 'Apple Watch')            # which series?
    assert not is_generic('Apple', 'AirTag')             # one word, but one product
    assert not is_generic('Sony', 'PS5 controller')


def test_optional_store_failure_is_left_out_but_required_one_raises(monkeypatch):
    import pytest
    import agents.store_price_agent as a

    def boom(q):
        raise RuntimeError('HTTP 403')
    ok = lambda q: [{'title': 'x', 'price': 1.0, 'url': 'u'}]
    monkeypatch.setattr(a, 'STORES', {'Нептун': boom, 'Анхоч': boom, 'Mobelix': ok})
    assert a.search_stores('q') == {'Нептун': [], 'Анхоч': [], 'Mobelix': ok('q')}
    monkeypatch.setattr(a, 'STORES', {'Mobelix': boom, 'Ledikom': ok})
    with pytest.raises(a.StoreUnavailable):
        a.search_stores('q')
