"""
Deduplication agent: finds same product listed on multiple sites or multiple
times on the same site.

Strategy:
- TF-IDF with character n-grams (handles Cyrillic/Latin mix, typos, different
  capitalisation)
- Cosine similarity with batched matrix multiplication to keep memory low
- Price proximity filter (within 35%) as a second gate
"""
import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from agents.translit import fold_variants

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

CROSS_SITE_THRESHOLD = 0.85
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
    if not name:
        return ''
    return re.sub(r'\s+', ' ', name.lower().strip())


def _seller_match(s1: str | None, s2: str | None) -> bool:
    """Return True if both seller names are known and similar enough."""
    n1, n2 = _normalize_seller(s1 or ''), _normalize_seller(s2 or '')
    if not n1 or not n2:
        return False
    if n1 == n2:
        return True
    # Accept if one name starts with the other (handles "Petar" vs "Petar Petrovski")
    return n1.startswith(n2) or n2.startswith(n1)


def _price_ok(p1, p2) -> bool:
    """Return True only when both prices are known and within tolerance."""
    if not p1 or not p2:
        return False
    hi, lo = max(p1, p2), min(p1, p2)
    return (hi - lo) / hi <= PRICE_TOLERANCE


def _extract_model_numbers(title: str) -> set:
    """Extract model identifiers (pure numbers and alphanumeric tokens like S3, A8, 2Pro)."""
    # Remove storage tokens like 64gb, 256gb, 16gb first
    t = re.sub(r'\b\d+\s*(?:gb|tb|mb)\b', '', title, flags=re.IGNORECASE)
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
            same_seller = _seller_match(ad1.get('seller_name'), ad2.get('seller_name'))
            if match_type == 'same_site' and not same_seller:
                continue
            # Canonical key order so UNIQUE(ad_url_1, ad_url_2) never collides
            url1, url2 = sorted([ad1['ad_url'], ad2['ad_url']])
            results.append({
                'ad_url_1': url1,
                'ad_url_2': url2,
                'similarity_score': round(float(chunk_sims[r, c]), 4),
                'match_type': match_type,
                'same_seller': same_seller,
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
