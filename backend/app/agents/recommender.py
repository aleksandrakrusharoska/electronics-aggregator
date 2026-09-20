"""Recommendation Agent — кластеризација и препораки.

Ги кластерира огласите по embedding (HDBSCAN/KMeans) и генерира
препораки од тип: „сличен производ, подобра цена во истиот кластер".
"""
from app.core.agent_log import log_activity
from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.ml.clustering import cluster_listings


@celery_app.task(name="agents.recommender.generate")
def generate(prev: dict | None = None) -> dict:
    db = SessionLocal()
    try:
        n_clusters = cluster_listings(db)
        log_activity("Recommender", f"Кластеризација завршена: {n_clusters} кластери", target="System")
    finally:
        db.close()
    return {**(prev or {}), "clusters": n_clusters}
