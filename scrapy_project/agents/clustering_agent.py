"""
Product clustering agent.

Groups ads into product clusters using TF-IDF + SVD + MiniBatchKMeans.
Each cluster gets a human-readable label from its top terms.

Pipeline:
  normalised titles → TF-IDF (char+word n-grams) → SVD (100 dims) → KMeans
"""
import logging
import re

import numpy as np
from sklearn.cluster import MiniBatchKMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import Normalizer

from agents.translit import to_latin

logger = logging.getLogger(__name__)

N_CLUSTERS = 150          # number of product groups
SVD_COMPONENTS = 100      # latent dimensions after SVD
TOP_TERMS = 4             # words used to label each cluster
MIN_TITLE_LEN = 3         # skip very short titles

_NOISE = [
    'se prodava', 'prodavam', 'itno', 'hitno', 'kako nov', 'kako nova',
    'zachuvan', 'zacuvan', 'polovno', 'koristeno', 'novo', 'nov', 'nova',
    'for sale', 'like new', 'used', 'brand new',
    'се продава', 'продавам', 'итно', 'како нов', 'како ново',
    'зачуван', 'користено', 'ново', 'нов',
]


def _normalise(title: str) -> str:
    if not title:
        return ''
    t = title.lower()
    for phrase in _NOISE:
        t = t.replace(phrase, ' ')
    # one script, so Cyrillic and Latin titles of the same product share words;
    # standard spelling (not folded) keeps the cluster labels readable
    t = to_latin(t)
    t = re.sub(r'(\d+)\s*(gb|tb|mb)', r'\1\2', t)
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _cluster_label(cluster_id: int, tfidf: TfidfVectorizer, svd: TruncatedSVD, kmeans: MiniBatchKMeans) -> str:
    """Reconstruct top TF-IDF terms for a cluster centroid."""
    centroid_svd = kmeans.cluster_centers_[cluster_id]
    centroid_tfidf = svd.inverse_transform(centroid_svd.reshape(1, -1))[0]
    feature_names = tfidf.get_feature_names_out()
    top_idx = centroid_tfidf.argsort()[::-1][:TOP_TERMS]
    terms = [feature_names[i] for i in top_idx if len(feature_names[i]) > 2]
    return ' · '.join(terms)


def cluster_ads(ads: list[dict]) -> list[dict]:
    """
    Cluster ads by title similarity.
    Returns list of dicts: {ad_url, cluster_id, cluster_label}
    """
    valid = [a for a in ads if _normalise(a.get('title', '')) and
             len(_normalise(a.get('title', '')).split()) >= MIN_TITLE_LEN]
    logger.info('Ads eligible for clustering: %d / %d', len(valid), len(ads))

    titles = [_normalise(a['title']) for a in valid]

    # TF-IDF with both word and character n-grams for Cyrillic/Latin mix
    tfidf = TfidfVectorizer(
        analyzer='word',
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.9,
        sublinear_tf=True,
    )

    logger.info('Fitting TF-IDF...')
    X = tfidf.fit_transform(titles)
    logger.info('TF-IDF matrix: %s', X.shape)

    # Dimensionality reduction (LSA)
    svd = TruncatedSVD(n_components=SVD_COMPONENTS, random_state=42)
    normalizer = Normalizer(copy=False)

    logger.info('Applying SVD + normalisation...')
    X_reduced = normalizer.fit_transform(svd.fit_transform(X))
    logger.info('Explained variance: %.1f%%', svd.explained_variance_ratio_.sum() * 100)

    # Clustering
    n_clusters = min(N_CLUSTERS, len(valid) // 3)
    logger.info('Running MiniBatchKMeans with k=%d...', n_clusters)
    kmeans = MiniBatchKMeans(
        n_clusters=n_clusters,
        random_state=42,
        batch_size=2000,
        n_init=5,
        max_iter=100,
    )
    labels = kmeans.fit_predict(X_reduced)
    logger.info('Clustering done.')

    # Generate human-readable label per cluster
    cluster_labels: dict[int, str] = {}
    for cid in range(n_clusters):
        cluster_labels[cid] = _cluster_label(cid, tfidf, svd, kmeans)

    results = []
    for ad, cid in zip(valid, labels):
        results.append({
            'ad_url': ad['ad_url'],
            'cluster_id': int(cid),
            'cluster_label': cluster_labels[int(cid)],
        })

    # Log cluster size distribution
    sizes = np.bincount(labels)
    logger.info(
        'Cluster sizes — min: %d, max: %d, mean: %.1f, median: %.1f',
        sizes.min(), sizes.max(), sizes.mean(), np.median(sizes)
    )

    return results


def save_clusters(sb, ads: list[dict], results: list[dict], batch: int = 500) -> set[int]:
    """Write one clustering run to the normalized schema: labels into
    `clusters`, the assignment into ads.cluster_id. KMeans renumbers
    clusters every run, so clusters no longer in use are deleted afterwards
    (ads.cluster_id is ON DELETE SET NULL), and ads that stopped being
    products lose their old cluster."""
    labels = {r['cluster_id']: r['cluster_label'] for r in results}
    cluster_ids = set(labels)
    if cluster_ids:
        sb.table('clusters').upsert(
            [{'cluster_id': cid, 'label': label} for cid, label in labels.items()],
            on_conflict='cluster_id',
        ).execute()

    rows = list({r['ad_url']: {'ad_url': r['ad_url'], 'cluster_id': r['cluster_id']} for r in results}.values())
    for i in range(0, len(rows), batch):
        sb.table('ad_analysis').upsert(rows[i:i + batch], on_conflict='ad_url').execute()

    if cluster_ids:
        sb.table('clusters').delete().not_.in_('cluster_id', sorted(cluster_ids)).execute()
    sb.table('ad_analysis').update({'cluster_id': None}).neq('ad_type', 'product').not_.is_('cluster_id', 'null').execute()
    return cluster_ids
