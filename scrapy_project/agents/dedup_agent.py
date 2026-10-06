"""
Deduplication agent: finds same product listed on multiple sites or multiple
times on the same site.

Strategy:
- TF-IDF with character n-grams (handles Cyrillic/Latin mix, typos, different
  capitalisation)
- Cosine similarity with batched matrix multiplication to keep memory low
- Price proximity filter (within 15%) and model-number check as gates
- Confirmation that it's the SAME SELLER, not just the same model: the same
  phone number, the same seller name (in either script), or a near-identical
  description (sellers paste the same text on both portals). A similar title
  and price alone matched different people selling the same phone — most of
  the old cross-site pairs were "iPhone 13 128GB" from two strangers.
- The parsed model must not conflict (iPhone 12 Pro vs iPhone 12).
"""
import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from agents.translit import fold_variants, to_latin

# Selling / condition phrases that add noise to title matching
_NOISE = [
    'se prodava', 'prodavam', 'prodava', 'za prodazba', 'prodazba',
    'itno', 'hitno',
    'kako nov', 'kako nova', 'kako novo',
    'zachuvan', 'zacuvan', 'zachuvana', 'zacuvana',
    'polovno', 'koristeno', 'koristena',
    'novo', 'nova', 'nov',
    'for sale', 'brand new', 'like new', 'used',
    # Cyrillic equivalents
    'се продава', 'продавам', 'итно', 'како ново', 'како нов', 'како нова',
    'зачуван', 'зачувана', 'користено', 'користена', 'ново', 'нова', 'нов',
]

CROSS_SITE_THRESHOLD = 0.75   # lower than before: a match now also needs seller confirmation
SAME_SITE_THRESHOLD = 0.95

_SERVICE_KEYWORDS = [
    'otkup', 'откуп', 'servis', 'сервис', 'remont', 'ремонт',
    'popravka', 'поправка', 'servisiranje', 'сервисирање',
]


def _is_service(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in _SERVICE_KEYWORDS)
PRICE_TOLERANCE = 0.15   # max fractional price difference
CHUNK_SIZE = 200         # rows of the similarity matrix computed at once
DESCRIPTION_MIN_SIM = 0.6  # measured: >= 0.6 was the same seller, < 0.4 different people
MIN_TITLE_WORDS = 3      # skip short generic titles like "desktop kompjuter"
LENGTH_RATIO_MIN = 0.55  # shorter title must be ≥55% the length of the longer one


def normalize_title(title: str) -> str:
    if not title:
        return ''
    t = title.lower()
    for phrase in _NOISE:
        t = t.replace(phrase, ' ')
    # one script and one spelling, so "Самсунг зачуван" and "Samsung zacuvan"
    # share character n-grams (the noise phrases above are matched first,
    # since they're listed in both scripts)
    t = fold_variants(t)
    # "256 gb" / "256GB" → "256gb",  "16 gb ram" → "16gb ram"
    t = re.sub(r'(\d+)\s*(gb|tb|mb)', r'\1\2', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _normalize_seller(name: str) -> str:
    """One script, letters and digits only: "Мартин" == "Martin",
    "Mobi Rekord" == "MobiRekord", "Купи Добар Мобилен.МК" ~ "...МК[Злате]"."""
    if not name:
        return ''
    return re.sub(r'[^a-z0-9]', '', fold_variants(to_latin(name.lower())))


def _seller_match(s1: str | None, s2: str | None) -> bool:
    """Return True if both seller names are known and similar enough."""
    n1, n2 = _normalize_seller(s1 or ''), _normalize_seller(s2 or '')
    if len(n1) < 3 or len(n2) < 3:   # "------", single letters
        return False
    if n1 == n2:
        return True
    # Accept if one name starts with the other (handles "Petar" vs "Petar Petrovski")
    return n1.startswith(n2) or n2.startswith(n1)


def _phone_match(p1: str | None, p2: str | None) -> bool:
    d1, d2 = re.sub(r'\D', '', p1 or '')[-8:], re.sub(r'\D', '', p2 or '')[-8:]
    return len(d1) == 8 and d1 == d2


def _models_conflict(a: dict, b: dict) -> bool:
    return bool(a.get('model_id') and b.get('model_id') and a['model_id'] != b['model_id'])


def _price_ok(p1, p2) -> bool:
    """Return True only when both prices are known and within tolerance."""
    if not p1 or not p2:
        return False
    hi, lo = max(p1, p2), min(p1, p2)
    return (hi - lo) / hi <= PRICE_TOLERANCE


def _extract_model_numbers(title: str) -> set:
    """Extract model identifiers (pure numbers and alphanumeric tokens like S3, A8, 2Pro)."""
    # Remove storage tokens like 64gb, 256gb, 16gb first, and percentages
    # ("батерија 100%"), which two different phones from one shop often share
    t = re.sub(r'\b\d+\s*(?:gb|tb|mb)\b', '', title, flags=re.IGNORECASE)
    t = re.sub(r'\d+\s*%', '', t)
    # Match pure numbers AND alphanumeric model tokens (S3, A8, 12Pro, etc.)
    return set(re.findall(r'\b[a-z]{0,2}\d+[a-z]{0,2}\b', t, flags=re.IGNORECASE))


def _titles_ok(t1: str, t2: str) -> bool:
    """Reject very short, mismatched-length, or different-model title pairs."""
    if len(t1.split()) < MIN_TITLE_WORDS or len(t2.split()) < MIN_TITLE_WORDS:
        return False
    hi, lo = max(len(t1), len(t2)), min(len(t1), len(t2))
    if hi == 0:
        return False
    if lo / hi < LENGTH_RATIO_MIN:
        return False
    # If both titles contain model numbers and they share none, they are different models
    nums1, nums2 = _extract_model_numbers(t1), _extract_model_numbers(t2)
    if nums1 and nums2 and nums1.isdisjoint(nums2):
        return False
    # one names a model number and the other none: "iPhone 12 Mini" vs "iPhone Xs Max"
    if bool(nums1) != bool(nums2):
        return False
    return True


def _build_vectorizer(titles_a: list[str], titles_b: list[str]) -> TfidfVectorizer:
    vect = TfidfVectorizer(
        analyzer='char_wb',
        ngram_range=(3, 4),
        min_df=1,
        sublinear_tf=True,
    )
    vect.fit(titles_a + titles_b)
    return vect


def _pairs_above_threshold(
    matrix_a,
    matrix_b,
    ads_a: list[dict],
    ads_b: list[dict],
    threshold: float,
    match_type: str,
    same_list: bool = False,
) -> list[dict]:
    """
    Batch-compute cosine similarity and return qualifying pairs.
    same_list=True skips self-matches and lower-triangular duplicates.
    """
    results = []
    for start in range(0, matrix_a.shape[0], CHUNK_SIZE):
        end = min(start + CHUNK_SIZE, matrix_a.shape[0])
        chunk_sims = cosine_similarity(matrix_a[start:end], matrix_b)

        rows, cols = np.where(chunk_sims >= threshold)
        for r, c in zip(rows, cols):
            global_r = start + r
            if same_list and global_r >= c:   # avoid self-match and (B,A) duplicate
                continue
            ad1 = ads_a[global_r]
            ad2 = ads_b[c]
            t1 = normalize_title(ad1.get('title', ''))
            t2 = normalize_title(ad2.get('title', ''))
            if not _titles_ok(t1, t2):
                continue
            if not _price_ok(ad1.get('price_eur'), ad2.get('price_eur')):
                continue
            if ad1['ad_url'] == ad2['ad_url'] or _models_conflict(ad1, ad2):
                continue
            results.append((ad1, ad2, round(float(chunk_sims[r, c]), 4)))
    return _confirmed(results, match_type)


def _confirmed(candidates: list[tuple], match_type: str) -> list[dict]:
    """Keep the candidate pairs that are the same seller's listing: same
    phone, same seller name, or near-identical descriptions."""
    descs = [d for a, b, _ in candidates for d in (a.get('description'), b.get('description')) if d]
    vect = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5), sublinear_tf=True).fit(descs) if descs else None
    results = []
    for ad1, ad2, score in candidates:
        same_seller = (_phone_match(ad1.get('phone'), ad2.get('phone'))
                       or _seller_match(ad1.get('seller_name'), ad2.get('seller_name')))
        if not same_seller and vect and ad1.get('description') and ad2.get('description'):
            m = vect.transform([ad1['description'], ad2['description']])
            same_seller = cosine_similarity(m[0], m[1])[0, 0] >= DESCRIPTION_MIN_SIM
        if not same_seller:
            continue
        # Canonical key order so UNIQUE(ad_url_1, ad_url_2) never collides
        url1, url2 = sorted([ad1['ad_url'], ad2['ad_url']])
        results.append({
            'ad_url_1': url1,
            'ad_url_2': url2,
            'similarity_score': score,
            'match_type': match_type,
            'same_seller': True,
            'is_service': _is_service(ad1.get('title', '')) or _is_service(ad2.get('title', '')),
        })
    return results


def find_cross_site_duplicates(
    r5_ads: list[dict],
    p3_ads: list[dict],
) -> list[dict]:
    """Return duplicate pairs between reklama5 and pazar3 ads."""
    if not r5_ads or not p3_ads:
        return []

    r5_titles = [normalize_title(a['title']) for a in r5_ads]
    p3_titles = [normalize_title(a['title']) for a in p3_ads]

    vect = _build_vectorizer(r5_titles, p3_titles)
    return _pairs_above_threshold(
        vect.transform(r5_titles),
        vect.transform(p3_titles),
        r5_ads,
        p3_ads,
        CROSS_SITE_THRESHOLD,
        'cross_site',
    )


def find_same_site_duplicates(ads: list[dict]) -> list[dict]:
    """Return duplicate pairs within the same source site."""
    if len(ads) < 2:
        return []

    titles = [normalize_title(a['title']) for a in ads]
    vect = TfidfVectorizer(
        analyzer='char_wb',
        ngram_range=(3, 4),
        min_df=1,
        sublinear_tf=True,
    )
    matrix = vect.fit_transform(titles)
    return _pairs_above_threshold(
        matrix, matrix,
        ads, ads,
        SAME_SITE_THRESHOLD,
        'same_site',
        same_list=True,
    )
