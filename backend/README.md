# Ad Aggregator — Backend

Мулти-агентски систем за агрегирање огласи за техника.
FastAPI + Celery + SQLAlchemy + pgvector + LangChain.

## Стартување (development)

```bash
# 1. Инфраструктура (PostgreSQL + Redis)
docker compose up -d

# 2. Python околина
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Конфигурација
cp .env.example .env

# 4. Иницијализација на базата (dev; подоцна Alembic миграции)
python -m app.core.init_db

# 5. API сервер
uvicorn app.main:app --reload

# 6. Celery worker (агентите) — во посебен терминал
celery -A app.core.celery_app worker --loglevel=info

# 7. Celery beat (периодично тригерирање на Scraper Agent) — трет терминал
celery -A app.core.celery_app beat --loglevel=info
```

API документација: http://localhost:8000/docs

## Структура

```
app/
├── main.py            # FastAPI апликација + WebSocket live feed
├── api/               # REST endpoints (listings, agents)
├── agents/            # Celery tasks = агентите
├── models/            # SQLAlchemy модели
├── ml/                # embeddings, кластеризација, аномалии
└── core/              # config, database, celery, логирање на агенти
```

## Агенти

| Агент | Задача | Тригер |
|---|---|---|
| Scraper | Собира огласи од Pazar3 и Reklama5 | Celery beat (периодично) |
| De-duplicator | Embeddings + cosine similarity | По секој scrape |
| Price Analyst | Z-score аномалии по кластер | По дедупликација |
| Recommendation | Кластеризација + препораки | По анализа |
| Alert | Нотификации за нови релевантни огласи | По анализа |

## Тестирање на scraper (без база/Celery)

```bash
python scripts/test_scraper.py reklama5
python scripts/test_scraper.py pazar3
# Setec адаптерот е историски и не е дел од активниот pipeline.
```

Unit тестови за екстракцијата (offline, со HTML fixture):

```bash
pytest tests/test_extraction.py -v
```

**Пред прв тест:** отвори ги порталите во прелистувач и потврди ги
URL шаблоните во `app/agents/scrapers/{reklama5,pazar3}.py`
(означени со TODO). Екстракцијата е хеуристичка и отпорна на
разлики во HTML; URL-ата мора да се точни.
