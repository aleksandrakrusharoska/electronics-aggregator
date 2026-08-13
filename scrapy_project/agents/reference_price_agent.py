"""
Reference price agent.

Computes, for every ad with a matched brand+model, how its price compares
to a reference "New" price — so the frontend can show "this used phone
costs X% of a new one" instead of the old cluster/z-score anomaly badge.

Reference price comes from two tiers, in priority order:
  1. Setec's live retail catalog (retail_prices table) — real retailer
     pricing, but only covers currently-sold models.
  2. Our own marketplace's condition="New" listings (pooled across
     pazar3 + reklama5) — broader coverage, used as a fallback for older
     or discontinued models Setec doesn't carry, but less authoritative
     (a seller's asking price, not a retailer's).

Fields computed per ad:
  reference_new_price_mkd  the reference price
  reference_sample_size    how many matching listings contributed
  reference_source         "setec" or "marketplace"
  price_vs_new_ratio       price_mkd / reference_new_price_mkd
  good_price_deal          heuristic: is the ratio low enough for its
                            condition tier to call it a good deal?

Ads without a matched brand+model, or with no reference available at all,
get all fields set to None/False rather than a guess.
"""
import logging
import re
import statistics

logger = logging.getLogger(__name__)

MIN_REFERENCE_SAMPLES = 2  # a lone marketplace listing can't be trusted as a reference — see MIN_PLAUSIBLE_PRICE_MKD

# Ratios below this are almost certainly a broken/garbage price_mkd value
# upstream (e.g. a placeholder or a scraping error), not a genuine deal —
# don't confidently label those "good deals".
MIN_PLAUSIBLE_RATIO = 0.10

# "New"-condition marketplace ads below this are almost always a monthly
# installment amount advertised as "the price" (e.g. "24 Meseci Garancija"
# financing ads), not the item's real cost — Setec's own cheapest phone
# is ~4,600 MKD, so anything under this is implausible for real "New"
# electronics. Excluded from the marketplace reference pool entirely,
# since with few samples per model a single one of these can otherwise
# become the whole reference price for other ads of that model.
MIN_PLAUSIBLE_PRICE_MKD = 1500

# Heuristic: how far below the reference "New" price a used ad in a given
# condition tier should be to count as a good deal. Not statistically
# fitted — a starting point, easy to tune once real data comes in.
CONDITION_MAX_RATIO = {
    'New': 0.95,
    'Used - Like New': 0.80,
    'Used - Good': 0.68,
    'Used - Fair': 0.55,
    'Used': 0.65,
    'For parts': 0.35,
}
DEFAULT_MAX_RATIO = 0.65  # condition unknown/other


def _norm(s):
    return s.strip().lower() if s else ''


# Network-generation suffix ("5G"/"4G") is inconsistently present on both
# sides: the LLM sometimes keeps it in an ad's model ("Galaxy A26 5G"), and
# Setec's own retail titles include it for some phones but not others (e.g.
# "Redmi Note 14 Pro+ 5G" but plain "Galaxy A26"). It's a network descriptor,
# not a distinguishing/pricier variant like "Pro"/"Max" — strip it from both
# sides before matching so its presence/absence on either side never blocks
# an otherwise-correct match.
_NETWORK_GEN_RE = re.compile(r'^[345]g$')


def _strip_network_gen(tokens: list[str]) -> list[str]:
    return [t for t in tokens if not _NETWORK_GEN_RE.match(t)]


def _build_retail_index(retail_prices: list[dict]) -> dict[str, list[tuple[list[str], float]]]:
    """Group retail listings by normalized brand -> [(tokenized title, price_mkd), ...]."""
    index: dict[str, list[tuple[list[str], float]]] = {}
    for r in retail_prices:
        brand = _norm(r.get('brand'))
        title = _norm(r.get('title'))
        price = r.get('price_mkd')
        if not brand or not title or not price or float(price) <= 0:
            continue
        index.setdefault(brand, []).append((_strip_network_gen(title.split()), float(price)))
    return index


# Setec titles follow "<Brand> <Model tokens...> <storage spec> <color...>"
# (e.g. "Apple iPhone 16 Pro Max 256GB Natural Titanium"). A storage-spec
# token marks where the model name ends and variant descriptors (color,
# marketing color-family name like Samsung's "Awesome") begin.
_STORAGE_RE = re.compile(r'^\d+(/\d+)?(gb|tb)$')

# Tier/variant keywords that continue a model name rather than describe
# color/storage — if one of these sits between the matched model tokens and
# the next storage-spec token, the title is a pricier/different variant the
# ad's (shorter) model string shouldn't be credited against — e.g. an ad
# with model "iPhone 16" must not match "iPhone 16 Pro Max", and "X6" must
# not match "X6c" or "X6 Pro".
_VARIANT_KEYWORDS = {'pro', 'pro+', 'max', 'plus', 'ultra', 'mini', 'lite', 'fe', 'se', 'note', 'air', '5g', '4g'}


def _title_matches_model(model_tokens: list[str], title_tokens: list[str]) -> bool:
    """True if model_tokens appear as a contiguous run in title_tokens and
    aren't immediately followed by a tier keyword before the storage spec."""
    n, m = len(model_tokens), len(title_tokens)
    for start in range(m - n + 1):
        if title_tokens[start:start + n] != model_tokens:
            continue
        for tok in title_tokens[start + n:]:
            if tok in _VARIANT_KEYWORDS:
                break  # different/pricier variant (e.g. "Pro Max") — reject this position
            if _STORAGE_RE.match(tok):
                return True  # model name ends here, rest is storage/color — accept
        else:
            return True  # ran off the end without hitting a variant keyword — accept
    return False


def _is_multi_variant_listing(model_tokens: list[str], title: str) -> bool:
    """True if the ad's title mentions its own model number together with
    2+ different tier-keyword combinations, e.g. "iPhone 16, 16 Pro i 16
    Pro Max" — a shop/price-list post covering several variants at once
    rather than one specific item, so its price can't be attributed to a
    single model with any confidence.

    Anchored on the ad's own model number (not just any number in the
    title) to avoid false positives from unrelated numbers like "24
    Meseci Garancija" (24-month warranty).
    """
    anchors = [t for t in model_tokens if re.fullmatch(r'\d{1,3}', t)]
    if not anchors:
        return False
    anchor = anchors[-1]

    title_tokens = re.sub(r'[^\w+]+', ' ', _norm(title)).split()
    mentions = set()
    i = 0
    while i < len(title_tokens):
        if title_tokens[i] != anchor:
            i += 1
            continue
        j = i + 1
        suffix = []
        while j < len(title_tokens) and title_tokens[j] in _VARIANT_KEYWORDS:
            suffix.append(title_tokens[j])
            j += 1
        mentions.add(tuple(suffix))
        i = j
    return len(mentions) >= 2


def _match_retail(brand: str, model: str, retail_index: dict) -> tuple[float, int] | None:
    """Find retail listings whose title's model portion exactly matches the
    ad's model (see _title_matches_model), for this brand.
    Returns (min_price, sample_size) or None if no match."""
    candidates = retail_index.get(_norm(brand))
    if not candidates:
        return None
    model_tokens = _strip_network_gen(_norm(model).split())
    if not model_tokens:
        return None
    matches = [price for title_tokens, price in candidates if _title_matches_model(model_tokens, title_tokens)]
    if not matches:
        return None
    return min(matches), len(matches)


def _build_marketplace_index(ads: list[dict]) -> dict[str, tuple[float, int]]:
    """Group New-condition marketplace ads by (brand|model) -> (median_price, sample_size)."""
    groups: dict[str, list[float]] = {}
    for ad in ads:
        if ad.get('condition') != 'New':
            continue
        brand, model = ad.get('brand'), ad.get('model')
        price = ad.get('price_mkd')
        if not brand or not model or not price or float(price) < MIN_PLAUSIBLE_PRICE_MKD:
            continue
        key = f'{_norm(brand)}|{_norm(model)}'
        groups.setdefault(key, []).append(float(price))

    index = {}
    for key, prices in groups.items():
        if len(prices) < MIN_REFERENCE_SAMPLES:
            continue
        index[key] = (statistics.median(prices), len(prices))
    return index


def compute_reference_prices(ads: list[dict], retail_prices: list[dict]) -> list[dict]:
    """
    ads: list of dicts with ad_url, brand, model, condition, price_mkd, title.
    retail_prices: list of dicts with brand, title, price_mkd.
    Returns list of dicts: ad_url, reference_new_price_mkd,
    reference_sample_size, reference_source, price_vs_new_ratio, good_price_deal.
    """
    retail_index = _build_retail_index(retail_prices)
    marketplace_index = _build_marketplace_index(ads)
    logger.info('Retail brands indexed: %d (%d listings)', len(retail_index),
                sum(len(v) for v in retail_index.values()))
    logger.info('Marketplace New-condition brand+model groups: %d', len(marketplace_index))

    results = []
    matched_setec = matched_marketplace = skipped_multi_variant = 0

    for ad in ads:
        brand, model = ad.get('brand'), ad.get('model')
        price = ad.get('price_mkd')

        ref_price = ref_size = ref_source = None
        if brand and model and _is_multi_variant_listing(_norm(model).split(), ad.get('title')):
            skipped_multi_variant += 1
        elif brand and model:
            setec_match = _match_retail(brand, model, retail_index)
            if setec_match:
                ref_price, ref_size = setec_match
                ref_source = 'setec'
                matched_setec += 1
            elif ad.get('condition') != 'New':
                # Marketplace fallback is a pool of other New-condition ads —
                # skip it for New-condition ads themselves, otherwise an ad
                # that's the only "New" listing for its model ends up being
                # compared against its own price (ratio trivially = 1.0).
                key = f'{_norm(brand)}|{_norm(model)}'
                mp_match = marketplace_index.get(key)
                if mp_match:
                    ref_price, ref_size = mp_match
                    ref_source = 'marketplace'
                    matched_marketplace += 1

        if not ref_price or not price or float(price) <= 0:
            results.append({
                'ad_url': ad['ad_url'],
                'reference_new_price_mkd': None,
                'reference_sample_size': None,
                'reference_source': None,
                'price_vs_new_ratio': None,
                'good_price_deal': False,
            })
            continue

        ratio = round(float(price) / ref_price, 4)
        max_ratio = CONDITION_MAX_RATIO.get(ad.get('condition'), DEFAULT_MAX_RATIO)

        results.append({
            'ad_url': ad['ad_url'],
            'reference_new_price_mkd': round(ref_price, 2),
            'reference_sample_size': ref_size,
            'reference_source': ref_source,
            'price_vs_new_ratio': ratio,
            'good_price_deal': MIN_PLAUSIBLE_RATIO <= ratio <= max_ratio,
        })

    logger.info('Ads matched: %d via setec, %d via marketplace fallback, %d skipped (multi-variant listing), %d unmatched',
                matched_setec, matched_marketplace, skipped_multi_variant,
                len(ads) - matched_setec - matched_marketplace - skipped_multi_variant)
    return results
