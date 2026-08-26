# Мулти-агентски систем за агрегирање огласи за техника

Дипломска работа — агрегатор на огласи за електроника од македонски портали ([pazar3.mk](https://www.pazar3.mk) и [reklama5.mk](https://www.reklama5.mk)).

**Live demo:** [https://electronics-aggregator.vercel.app](https://electronics-aggregator.vercel.app)

---

## Како работи

Секој ден, автоматизирани скрипти (агенти) го собираат следново:

1. **Scraper** — секој ден собира нови огласи од pazar3.mk и reklama5.mk.
2. **Parser** (AI) — од описот на огласот извлекува бренд, модел, состојба и спецификации.
3. **Reference Price** — за секој половен уред, го споредува со цена на нов истиот модел (од Setec.mk или друг оглас за нов уред) и означува дали е добра цена.
4. **Clustering** — групира слични производи, за да се прикажат „слични огласи".
5. **Dedup** — открива дупликат огласи од двата извора.

Сите податоци се чуваат во Supabase (PostgreSQL база), а веб-апликацијата ги прикажува преку FastAPI бекенд и React фронтенд.

## Структура на проектот

- **`frontend/`** — React + Vite + Tailwind CSS апликација
- **`backend/`** — FastAPI сервер кој ги сервира податоците (`/api/ads`)
- **`scrapy_project/`** — Scrapy spiders + агентите (parser, clustering, reference price, dedup)
- **`.github/workflows/`** — автоматско (закажано) стартување на агентите

## Локално стартување

### Предуслови

- Python 3.12+
- Node.js 18+
- Supabase проект

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

scrapy crawl pazar3                        # scrape
python run_parser_agent.py --limit 500     # AI парсирање
python run_clustering_agent.py             # кластеризација
python run_reference_price_agent.py        # споредба со нови цени
```

## Environment variables

| Промeнлива | Каде | Опис |
|---|---|---|
| `SUPABASE_URL`, `SUPABASE_KEY` | backend, scrapy | Supabase проект |
| `ALLOWED_ORIGINS` | backend | Дозволени CORS домени (фронтенд URL) |
| `GROQ_API_KEY` | scrapy | LLM за парсирање на огласи |
| `CHAT_GROQ_API_KEY` | backend | LLM за AI chat асистентот (одделен клуч од scraping-от, за да не се дели дневниот лимит) |
| `GEMINI_API_KEY` | scrapy | Резервен LLM за парсирање |
| `VITE_API_URL` | frontend | URL до backend |

## Deployment

Фронтендот е на Vercel, бекендот на Render, базата на Supabase, а GitHub Actions ги стартува агентите на распоред (дневен scrape, парсирање, споредба на цени...).

## Функционалности на UI

- Пребарување и филтрирање по извор, состојба, цена, категорија
- Детекција на добри цени (споредба со реална цена на нов уред)
- AI chat асистент за прашања за конкретен оглас
- Слични производи базирани на кластеризација
- Dark mode
- Wishlist (локален)
- Analytics страница со статистики по извор
