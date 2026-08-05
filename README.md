# Мулти-агентски систем за агрегирање огласи за техника

Дипломска работа — агрегатор на огласи за електроника од македонски портали ([pazar3.mk](https://www.pazar3.mk) и [reklama5.mk](https://www.reklama5.mk)) со мулти-агентска архитектура за обработка, кластеризација и детекција на аномалии во цени.

**Live demo:** [https://aggregator-aleksandras-team.vercel.app](https://aggregator-aleksandras-team.vercel.app)

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                        GitHub Actions                        │
│  daily_scrape · parse_ads · rescrape_details · backfill     │
└────────────────────┬────────────────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   Scrapy Spiders    │  pazar3 · reklama5 · rescrape
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │  Supabase (Postgres) │  65 000+ огласи
          └──────────┬──────────┘
                     │
     ┌───────────────┼───────────────┐
     │               │               │
┌────▼────┐   ┌──────▼──────┐  ┌────▼────────┐
│  Parser │   │  Clustering  │  │   Anomaly   │
│  Agent  │   │    Agent     │  │    Agent    │
│(Groq/   │   │ (TF-IDF +    │  │ (Z-score   │
│ Gemini) │   │  K-Means)    │  │  по кластер)│
└─────────┘   └─────────────┘  └─────────────┘
                     │
          ┌──────────▼──────────┐
          │   FastAPI Backend   │  Render
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │  React + Vite UI    │  Vercel
          └─────────────────────┘
```

## Агенти

| Агент | Опис | Тригер |
|---|---|---|
| **Scraper** | Scrapy spiders за pazar3 и reklama5 | GitHub Actions (дневно) |
| **Parser** | LLM екстракција на specs, состојба, категорија (Groq + Gemini) | GitHub Actions (2×/ден) |
| **Clustering** | TF-IDF + K-Means кластеризација на наслови | Рачно / по потреба |
| **Price Anomaly** | Z-score детекција на аномални цени по кластер | По кластеризација |
| **Dedup** | Детекција на дупликати | По scrape |
| **Rescrape** | Пополнување на недостасувачки полиња од detail страници | GitHub Actions (рачно) |

## Структура на проектот

```
├── frontend/               # React + Vite + Tailwind CSS
│   └── src/
│       ├── components/     # AdCard, AdModal, Sidebar, Header…
│       ├── pages/          # AnalyticsPage
│       └── api/            # client.js
│
├── backend/                # FastAPI
│   └── app/
│       ├── main.py         # CORS, app setup
│       └── api/ads.py      # /api/ads, /api/ads/similar, /api/stats
│
├── scrapy_project/         # Scrapy + агенти
│   ├── ads_scraper/
│   │   ├── spiders/        # pazar3, reklama5, rescrape, backfill
│   │   ├── pipelines.py    # Supabase pipeline
│   │   └── normalize.py    # Парсирање на цени и датуми
│   └── agents/
│       ├── parser_agent.py
│       ├── clustering_agent.py
│       ├── reference_price_agent.py
│       └── dedup_agent.py
│
└── .github/workflows/      # CI/CD
    ├── daily_scrape.yml
    ├── parse_ads.yml
    └── rescrape_details.yml
```

## Локално стартување

### Предуслови

- Python 3.12+
- Node.js 18+
- Supabase проект (или локален PostgreSQL)

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env         # пополни SUPABASE_URL и SUPABASE_KEY
uvicorn app.main:app --reload
```

API достапен на: `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
cp .env.example .env         # пополни VITE_API_URL (или остави празно за proxy)
npm run dev
```

UI достапен на: `http://localhost:5173`

### Scrapy / Агенти

```bash
cd scrapy_project
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env         # SUPABASE_URL, SUPABASE_KEY, GROQ_API_KEY, GEMINI_API_KEY

# Scrape
scrapy crawl pazar3
scrapy crawl reklama5

# LLM парсирање
python run_parser_agent.py --limit 500

# Кластеризација
python run_clustering_agent.py

# Референтни цени (споредба со нови цени)
python run_reference_price_agent.py
```

## Environment variables

### Backend (`.env`)

| Промeнлива | Опис |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon/service key |
| `ALLOWED_ORIGINS` | CORS origins (пр. `https://твојот-домен.vercel.app`) |

### Frontend (`.env`)

| Промeнлива | Опис |
|---|---|
| `VITE_API_URL` | URL до backend (пр. `https://aggregator-1n70.onrender.com`) |

### Scrapy (`.env`)

| Промeнлива | Опис |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon/service key |
| `GROQ_API_KEY` | Groq API клуч (LLM парсирање) |
| `GEMINI_API_KEY` | Google Gemini API клуч (LLM парсирање) |

## Deployment

| Сервис | Платформа | Конфигурација |
|---|---|---|
| Frontend | Vercel | Root dir: `frontend/`, auto-deploy on push |
| Backend | Render | Root dir: `backend/`, Python 3.12, auto-deploy on push |
| База | Supabase | Cloud PostgreSQL |
| CI/CD | GitHub Actions | Дневен scrape, 2× дневно парсирање |

## Функционалности на UI

- Пребарување и филтрирање по извор, состојба, цена, категорија
- Детектирани добри цени (Z-score аномалии под просекот на кластерот)
- Слични производи базирани на кластеризација
- Dark mode
- Wishlist (локален)
- Analytics страница со статистики по извор
