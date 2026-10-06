"""
Store price agent: the reference "new" price of a brand+model, looked up in
Macedonian stores instead of estimated by an LLM.

For one model:
  1. Phones — phones.mk, a price-comparison site that already groups the
     offers of ~20 Macedonian shops under one product page. Its offers are
     used when at least two shops list it (refurbishers and the mobile
     operators, whose prices are tied to contracts, are left out).
  2. Everything else (and phones phones.mk doesn't cover) — the stores' own
     search: Neptun, Setec, Anhoch, Mobelix, Ledikom. Results whose title
     doesn't contain every distinctive word of the model are dropped without
     asking anyone; the LLM then picks, from what's left, the listings that
     are exactly this model sold new (not a case, not the Pro version, not an
     exhibition or used unit).
  3. Cheapest matching variant per store, a store far from the others
     (>1.5x off the median — e.g. one shop listing only the 1TB version) is
     dropped, and the reference price is the median of the rest. If the
     stores still disagree by more than 1.5x, the model name is too generic
     to be one product ("MacBook Air 13": an M1 at one shop, an M4 at
     another) and gets no price. So does a model that is just a category
     word ("Optoma projector", "Philips TV", "Apple Watch"), without
     searching at all.

The current price is used (with a discount or Setec's free club card), as
that is what a buyer pays for the same device new today.

The Macedonian shops (and phones.mk) don't answer requests from outside the
country — on GitHub's servers every one of them failed and only Setec, whose
search runs on a foreign service, came back. With PROXY_URL set (the same
Macedonian residential proxy reklama5 goes through) their requests use it.
A lookup in which any store failed raises StoreUnavailable instead of
returning "not found", so the model is retried rather than marked checked.
"""
import html
import json
import logging
import os
import re
import statistics
from concurrent.futures import ThreadPoolExecutor

from curl_cffi import requests

from agents.parser_agent import _extract_text

logger = logging.getLogger(__name__)

# public search key that setec.mk's own pages send to its search service
SETEC_SEARCH_KEY = 'c0424dab588b8cbbbe0a4809fc10b5f1c0c7d183b5b28ebe799f3fbf583ab358'
EXCLUDED_PHONESMK_VENDORS = {'mobitech', 'fixit', 'a1', 'mtel', 'telekom'}
MIN_PHONESMK_STORES = 2
MAX_OUTLIER_FACTOR = 1.5
MAX_SPREAD = 1.5   # the same model's cheapest variant differs by up to ~1.4x between shops
RESULTS_PER_STORE = 25

class StoreUnavailable(Exception):
    """A store didn't answer, so "not found" can't be trusted for this model."""


_session = requests.Session(impersonate='chrome', timeout=25)
# the Macedonian shops get the Macedonian proxy when there is one; Setec's
# search service is abroad and answers anyone, so it stays direct
_proxy = (os.getenv('PROXY_URL') or '').strip() or None
_mk_session = (requests.Session(impersonate='chrome', timeout=40, proxies={'http': _proxy, 'https': _proxy})
               if _proxy else _session)


def _num(s: str) -> float | None:
    """'39.980,00 ден.' / '129,000.00' / '33.190' -> 39980 / 129000 / 33190"""
    s = re.sub(r'[^\d.,]', '', s or '').strip('.,')
    s = re.sub(r'[.,]\d{2}$', '', s)
    return float(re.sub(r'[.,]', '', s)) if s else None


# ── store searches: each returns [{title, price, url}] ─────────────────────

def _neptun(q):
    d = _mk_session.post('https://www.neptun.mk/Product/SearchProductsAutocomplete',
                      json={'term': q, 'page': 1, 'itemsPerPage': 60},
                      headers={'x-requested-with': 'XMLHttpRequest', 'referer': 'https://www.neptun.mk/'}).json()
    items = next((v for v in d.values() if isinstance(v, list)), [])
    return [{'title': i['Title'], 'price': i['DiscountPrice'] if i.get('HasDiscount') else i['RegularPrice'],
             'url': 'https://www.neptun.mk' + i['Url']} for i in items if i.get('RegularPrice')]


def _setec(q):
    d = _session.post('https://search.sp.solslab.dev/indexes/products/search', json={'q': q, 'limit': 40},
                      headers={'authorization': f'Bearer {SETEC_SEARCH_KEY}', 'referer': 'https://setec.mk/'}).json()
    out = []
    for h in d.get('hits', []):
        cp = (h.get('variants') or [{}])[0].get('calculated_price') or {}
        # calculated_amount is the "Клуб цена" setec.mk shows as the price (the
        # club card is free); original_amount is a struck-through "regular" one
        price = cp.get('calculated_amount') or cp.get('original_amount')
        if price:
            out.append({'title': h['title'], 'price': float(price), 'url': f"https://setec.mk/products/{h['handle']}"})
    return out


def _anhoch(q):
    d = _mk_session.get('https://www.anhoch.com/products', params={'query': q},
                     headers={'accept': 'application/json', 'x-requested-with': 'XMLHttpRequest'}).json()
    out = []
    for p in (d.get('products') or {}).get('data', []):
        price = _num(p.get('formatted_price'))
        if price:
            out.append({'title': p['name'], 'price': price, 'url': f"https://www.anhoch.com/products/{p.get('slug', '')}"})
    return out


def _mobelix(q):
    t = _mk_session.get('https://mobelix.com.mk/mk/prebaruvanje', params={'product': q}).text
    out = []
    for block in t.split('product-wrapper')[1:]:
        url = re.search(r'href="(https://mobelix\.com\.mk/mk/proizvodi/[^"]+)"', block)
        alt = re.search(r'alt="([^"]+)"', block)
        price = re.search(r'class="h5 price">(.*?)</p>', block, re.S)
        if not (url and alt and price):
            continue
        amounts = re.findall(r'[\d,]+\.\d\d', re.sub(r'<del.*?</del>', '', price.group(1), flags=re.S))
        badges = [b.strip() for b in re.findall(r'class="badge[^"]*">([^<]+)<', block) if not b.strip().startswith('-')]
        if amounts:
            # slug and badges stay in the title: they mark used / exhibition
            # units ("Експонати", a "-2" slug) for the LLM to leave out
            title = f"{html.unescape(alt.group(1))} [{url.group(1).rsplit('/', 1)[1]}]"
            out.append({'title': title + (f" ({', '.join(badges)})" if badges else ''),
                        'price': _num(amounts[-1]), 'url': url.group(1)})
    return out


def _ledikom(q):
    t = _mk_session.get('https://ledikom.mk/search', params={'query': q}).text
    out = []
    for block in t.split('class="item-in-grid"')[1:]:
        name = re.search(r'class="item-name">\s*<a href="([^"]+)">([^<]+)</a>', block)
        price = (re.search(r'class="grid-new-price">\s*([\d.]+)', block)
                 or re.search(r'class="price"[^>]*>\s*([\d.]+)', block))
        if name and price:
            out.append({'title': html.unescape(name.group(2)).strip(), 'price': _num(price.group(1)),
                        'url': 'https://ledikom.mk' + name.group(1)})
    return out


STORES = {'Нептун': _neptun, 'Сетек': _setec, 'Анхоч': _anhoch, 'Mobelix': _mobelix, 'Ledikom': _ledikom}


def search_stores(q: str) -> dict[str, list[dict]]:
    """All five stores in parallel. Raises StoreUnavailable if any of them
    failed — a missing store could be the one that sells the model."""
    def one(item):
        name, fn = item
        try:
            return name, fn(q)
        except Exception as exc:
            return name, exc
    with ThreadPoolExecutor(len(STORES)) as ex:
        results = dict(ex.map(one, STORES.items()))
    failed = {name: r for name, r in results.items() if isinstance(r, Exception)}
    if failed:
        raise StoreUnavailable(', '.join(f'{n}: {str(e)[:80]}' for n, e in failed.items()))
    return results


# ── name matching ──────────────────────────────────────────────────────────

_STOP = {'apple', 'samsung', 'galaxy', 'xiaomi', 'redmi', '5g', '4g', 'lte', 'dual', 'sim', 'ds', 'the',
         'phone', 'smartphone', 'mobilen', 'telefon'}
_ORDINAL = ('st', 'nd', 'rd', 'th', 'gen')


def _tokens(s: str, brand: str = '') -> list[str]:
    s = html.unescape(s).lower().replace('+', ' plus ')
    b = set(re.findall(r'[a-z0-9]+', brand.lower()))
    return [t for t in re.findall(r'[a-z0-9]+', s) if t not in _STOP and t not in b]


def _has_token(want: str, title_tokens: list[str]) -> bool:
    """'2' also matches '2nd' / '2gen' ("AirPods Pro (2nd generation)")."""
    if want in title_tokens:
        return True
    return want.isdigit() and any(t.startswith(want) and t[len(want):] in _ORDINAL for t in title_tokens)


# ── phones.mk ──────────────────────────────────────────────────────────────

def phonesmk_offers(brand: str, model: str) -> dict | None:
    """{'page': url, 'stores': {shop: {price, title, url}}} for the phones.mk
    product whose name is exactly this model, or None."""
    want = _tokens(model, brand)
    if not want:
        return None
    t = _mk_session.get('https://www.phones.mk/', params={'search': f'{brand} {model}'}).text
    items = re.findall(r'class="product-link" href="([^"]+)" title="([^"]+)"', t)
    match = next((h for h, n in items if _tokens(n, brand) == want), None)
    if not match:
        return None
    t = re.sub(r'<svg.*?</svg>', '', _mk_session.get('https://www.phones.mk' + match).text, flags=re.S)
    a = t.find('offer-name-column offer-column')
    b = t.find('price-column offer-column', a)
    c = t.find('variants-column', b)
    if a < 0 or b < 0:
        return None
    # the offers are two parallel columns (names, prices) of the same rows
    stores = {}
    for nr, pr in zip(t[a:b].split('class="offer-row')[1:], t[b:c].split('class="offer-row')[1:]):
        vendor = re.search(r'vendor-mobile" title="([^"]+)"', nr)
        price = re.search(r'price-container">\s*([\d.]+)', pr)
        if not (vendor and price) or vendor.group(1).strip().lower() in EXCLUDED_PHONESMK_VENDORS:
            continue
        shop, value = vendor.group(1).strip(), _num(price.group(1))
        url = re.search(r'href="(http[^"]+)"', nr)
        title = re.search(r'<a class="trigger-offers-modal"[^>]*title="([^"]+)"', nr)
        if value and (shop not in stores or value < stores[shop]['price']):
            stores[shop] = {'price': value, 'title': html.unescape(title.group(1)) if title else '',
                            'url': url.group(1) if url else ''}
    return {'page': 'https://www.phones.mk' + match, 'stores': stores}


# ── store search + LLM pick ────────────────────────────────────────────────

_PICK = """You match store search results to one product. Product: "{product}".
Below are search results from Macedonian electronics stores, as "index | store | title | price MKD".
Return ONLY a JSON array of the indexes that are exactly this product, sold NEW:
- same model, not a different one (iPhone 15 is not iPhone 15 Pro / 15 Plus / 15e; Galaxy A54 is not A54s or A55; PS5 Slim is not PS5 Pro);
- any storage/colour variant of it is fine;
- NOT accessories, cases, glass, cables, chargers, straps, spare parts;
- NOT used, refurbished, open-box, display/exhibition units ("Exp.", "Експонати", "изложбен", "izlozben", "користен", "koristen", "polovni", "refurbished", "bez kutija", a slug ending in "-2"/"-3" when another listing of the same model exists at a much higher price).
- If the product name itself is too generic to be one product (e.g. just "Apple MacBook Pro", "Dell Latitude", "Samsung TV"), return [] — different generations differ hugely in price.
If none match, return []. No explanation.
{rows}"""


def _pick(parser, product: str, cands: list[dict]) -> list[int]:
    rows = '\n'.join(f"{i} | {c['store']} | {c['title']} | {c['price']:.0f}" for i, c in enumerate(cands))
    msg = [{'role': 'user', 'content': _PICK.format(product=product, rows=rows)}]
    last_exc = None
    for _ in range(len(parser._clients)):
        name, client = parser.next()
        try:
            raw = _extract_text(client.invoke(msg).content).strip()
            m = re.search(r'\[[\d,\s]*\]', raw)
            return [i for i in json.loads(m.group(0)) if 0 <= i < len(cands)] if m else []
        except Exception as exc:
            logger.debug('LLM provider %s failed: %s', name, exc)
            last_exc = exc
    raise RuntimeError(f'all LLM providers failed: {last_exc}')


def store_offers(parser, brand: str, model: str, product: str) -> dict:
    want = _tokens(model, brand)
    if not want:
        return {}
    found = search_stores(product)
    cands = [dict(c, store=s) for s, results in found.items() for c in results[:RESULTS_PER_STORE]]
    # keyword pre-filter: every distinctive word of the model must be in the title
    cands = [c for c in cands if all(_has_token(w, _tokens(c['title'])) for w in want)]
    if not cands:
        return {}
    stores = {}
    for i in _pick(parser, product, cands):
        c = cands[i]
        if c['store'] not in stores or c['price'] < stores[c['store']]['price']:
            stores[c['store']] = {'price': c['price'], 'title': c['title'], 'url': c['url']}
    return stores


def robust_prices(prices: list[float]) -> tuple[list[float], bool]:
    """Keep the prices within 1.5x of the median. Returns (kept, ambiguous):
    ambiguous when fewer than half survive, i.e. the stores really disagree."""
    if not prices:
        return [], False
    m = statistics.median(prices)
    kept = [p for p in prices if m / MAX_OUTLIER_FACTOR <= p <= m * MAX_OUTLIER_FACTOR]
    return kept, len(kept) * 2 < len(prices)


# a model name made only of these says what kind of device it is, not which one
_CATEGORY_WORDS = {
    'tv', 'televizor', 'televizija', 'smart', 'led', 'lcd', 'oled', 'monitor', 'projector', 'projektor',
    'laptop', 'notebook', 'computer', 'kompjuter', 'pc', 'tablet', 'phone', 'telefon', 'watch', 'smartwatch',
    'camera', 'kamera', 'printer', 'headphones', 'slusalki', 'speaker', 'zvucnik', 'mouse', 'keyboard',
    'tastatura', 'controller', 'dzojstik', 'joystick', 'console', 'konzola', 'router', 'charger', 'polnac',
}


def is_generic(brand: str, model: str) -> bool:
    """The model is only a category word ("projector", "TV") — not one product."""
    words = _tokens(model, brand)
    return not words or all(w in _CATEGORY_WORDS for w in words)


def find_store_price(parser, brand: str, model: str) -> dict:
    """{'price_mkd': median or None, 'status': found / ambiguous / not_found,
    'source': 'phones.mk' / 'stores', 'stores': {shop: {price, title, url}}}"""
    if is_generic(brand, model):
        return {'price_mkd': None, 'status': 'ambiguous', 'source': None, 'stores': {}}
    product = model if brand.lower() in model.lower() else f'{brand} {model}'.strip()
    try:
        pm = phonesmk_offers(brand, model)
    except Exception as exc:
        raise StoreUnavailable(f'phones.mk: {str(exc)[:80]}') from exc
    if pm and len(pm['stores']) >= MIN_PHONESMK_STORES:
        source, stores = 'phones.mk', pm['stores']
    else:
        source, stores = 'stores', store_offers(parser, brand, model, product)

    kept, ambiguous = robust_prices([s['price'] for s in stores.values()])
    if ambiguous or (kept and max(kept) / min(kept) > MAX_SPREAD):
        return {'price_mkd': None, 'status': 'ambiguous', 'source': source, 'stores': stores}
    if not kept:
        return {'price_mkd': None, 'status': 'not_found', 'source': source, 'stores': {}}
    # only the stores that made it into the median are kept as the sources
    used = {s: v for s, v in stores.items() if v['price'] in kept}
    return {'price_mkd': statistics.median(kept), 'status': 'found', 'source': source, 'stores': used}
