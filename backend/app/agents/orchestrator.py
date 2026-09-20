"""Оркестратор — го поврзува pipeline-от од агенти во синџир (chain).

Ова е местото каде LangChain координацијата може да се прошири;
за почеток, детерминистички Celery chain е доволен и робустен:

    Scraper → De-duplicator → Price Analyst → Recommender → Alerts
"""
from celery import chain

from app.core.celery_app import celery_app
from app.core.agent_log import log_activity


@celery_app.task(name="agents.orchestrator.run_pipeline")
def run_pipeline() -> str:
    log_activity("Orchestrator", "Стартувам нов pipeline циклус", target="System")

    pipeline = chain(
        celery_app.signature("agents.scraper.scrape_all"),
        celery_app.signature("agents.deduplicator.deduplicate"),
        celery_app.signature("agents.price_analyst.analyze"),
        celery_app.signature("agents.recommender.generate"),
        celery_app.signature("agents.alerts.notify"),
    )
    pipeline.apply_async()
    return "pipeline started"
