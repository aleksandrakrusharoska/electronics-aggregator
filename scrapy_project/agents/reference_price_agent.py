"""
Reference price agent.

Computes, for every ad with a matched brand+model, how its price compares
to a reference "New" price — so the frontend can show "this used phone
costs X% of a new one" instead of the old cluster/z-score anomaly badge.

Reference price comes from two tiers, in priority order:
  1. The median of our own marketplace's condition="New" listings of the
     same model (pooled across pazar3 + reklama5). Skipped for New ads
     themselves, so an ad is never compared against its own price.
  2. A cached LLM price estimate (models.estimated_new_price_mkd, populated
     by populate_price_estimates.py) — covers everything tier 1 doesn't,
     including categories without enough marketplace listings. A model's
     estimate, not an observed price, so it only kicks in once marketplace
     matching has failed.

Both prices belong to the model (stored on `models`); which one applies to
a given ad depends on the ad (its condition), so the ad stores only
reference_source, plus its own ratio and good-deal flag.

Fields computed per ad:
  reference_new_price_mkd  the reference price
  reference_sample_size    how many matching listings contributed (tier
                            2 has no real sample — always 1)
  reference_source         "marketplace" or "llm_estimate"
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
# financing ads), not the item's real cost — even the cheapest new phones
# cost several thousand MKD, so anything under this is implausible for real
# "New" electronics. Excluded from the marketplace reference pool entirely,
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


# Tier/variant keywords that continue a model name ("Pro", "Max", ...) —
# used to recognise titles listing several variants of one model at once.
_VARIANT_KEYWORDS = {'pro', 'pro+', 'max', 'plus', 'ultra', 'mini', 'lite', 'fe', 'se', 'note', 'air', '5g', '4g'}


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


def compute_reference_prices(ads: list[dict],
                              llm_estimates: dict[str, float] | None = None) -> list[dict]:
    """
    ads: list of dicts with ad_url, brand, model, condition, price_mkd, title.
    llm_estimates: optional {'brand|model' (normalized): price_mkd} cache —
        see models.estimated_new_price_mkd / populate_price_estimates.py. Tried only
        once marketplace matching fails; missing or None entries
        are treated as no estimate available.
    Returns list of dicts: ad_url, reference_new_price_mkd,
    reference_sample_size, reference_source, price_vs_new_ratio, good_price_deal.
    """
    marketplace_index = _build_marketplace_index(ads)
    llm_estimates = llm_estimates or {}
    logger.info('Marketplace New-condition brand+model groups: %d', len(marketplace_index))
    logger.info('Cached LLM price estimates: %d', len(llm_estimates))

    results = []
    matched_marketplace = matched_llm = skipped_multi_variant = 0

    for ad in ads:
        brand, model = ad.get('brand'), ad.get('model')
        price = ad.get('price_mkd')

        ref_price = ref_size = ref_source = None
        if brand and model and _is_multi_variant_listing(_norm(model).split(), ad.get('title')):
            skipped_multi_variant += 1
        elif brand and model:
            key = f'{_norm(brand)}|{_norm(model)}'
            if ad.get('condition') != 'New':
                # Marketplace fallback is a pool of other New-condition ads —
                # skip it for New-condition ads themselves, otherwise an ad
                # that's the only "New" listing for its model ends up being
                # compared against its own price (ratio trivially = 1.0).
                mp_match = marketplace_index.get(key)
                if mp_match:
                    ref_price, ref_size = mp_match
                    ref_source = 'marketplace'
                    matched_marketplace += 1

            if not ref_price:
                llm_price = llm_estimates.get(key)
                if llm_price:
                    ref_price, ref_size, ref_source = float(llm_price), 1, 'llm_estimate'
                    matched_llm += 1

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

    logger.info('Ads matched: %d via marketplace, %d via LLM estimate, '
                '%d skipped (multi-variant listing), %d unmatched',
                matched_marketplace, matched_llm, skipped_multi_variant,
                len(ads) - matched_marketplace - matched_llm - skipped_multi_variant)
    return results
