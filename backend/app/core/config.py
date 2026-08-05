"""Централна конфигурација — сè се чита од .env преку pydantic-settings."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg2://aggregator:aggregator@localhost:5432/ad_aggregator"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Scraping
    scrape_interval_minutes: int = 30
    scrape_user_agent: str = "AdAggregatorBot/1.0"

    # ML
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    dedup_similarity_threshold: float = 0.92
    price_anomaly_zscore: float = 2.5

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # LLM (опционално)
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"


@lru_cache
def get_settings() -> Settings:
    return Settings()
