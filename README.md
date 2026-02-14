# News App

Contextual news data retrieval system with LLM-powered query parsing.

> **Design document**: See [`docs/DESIGN.md`](docs/DESIGN.md) for architecture, assumptions, tradeoffs, and alternative approaches for scaling.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Python 3.13+
- Docker & Docker Compose

## Setup

```bash
uv sync
```

## Environment

```bash
cp .env.example .env
```

Then edit `.env` and set your values:

- `MONGODB_URL` – Full MongoDB URL (optional; when empty, built from below)
- `MONGO_DB` – Database name (default: news)
- `MONGO_HOST` – Host (default: localhost; use `mongodb` when app runs in Docker)
- `MONGO_PORT` – Port (default: 27017)
- `MONGO_USER` / `MONGO_PASSWORD` – Auth (required when MongoDB has auth)
- `OPENAI_API_KEY` – Required for unified query and summaries
- `OPENAI_MODEL` – LLM model (default: gpt-4o-mini)
- `VALKEY_URL` – Valkey/Redis URL for geocode cache (optional; use `CACHE_BACKEND=memory` when unset)
- `CACHE_BACKEND` – `valkey` or `memory` (default: memory when `VALKEY_URL` unset)
- `MAX_RADIUS_KM` – Max radius for nearby search in km (default: 1500)

## Docker Compose

Start MongoDB and Valkey:

```bash
docker compose up -d
```

Mongo Express: `http://localhost:8081` (if `MONGO_EXPRESS_PORT=8081`).

With the app running on the host, set `VALKEY_URL=redis://localhost:6379` for geocode cache, or leave `CACHE_BACKEND=memory`.

## MongoDB

Load data:

```bash
uv run python -m app.cli load news_data.json
```

Or load data and summarize:

Options:
- `--summarize` / `-s` – Summarize articles via LLM (default: false)
- `--n-summarize` / `-n` – Number of articles to summarize, 1–n (default: 10)

```bash
uv run python -m app.cli load news_data.json --summarize -n 20
```

## Run

```bash
uv run uvicorn app.main:app --reload
```

## API Endpoints

Deterministic:
- `GET /api/v1/news/category?category=...` – By category
- `GET /api/v1/news/search?query=...` – Text search
- `GET /api/v1/news/nearby?lat=...&lon=...&radius_km=10` – Nearby articles
- `GET /api/v1/news/source?source=...` – By source
- `GET /api/v1/news/score?threshold=...` – By relevance threshold (0–1)


Non-deterministic:
- `GET /api/v1/news?query=...` – Unified; LLM routes to category/search/nearby
- `GET /api/v1/news/trending?lat=...&lon=...&radius_km=10&limit=5&offset=0` – Location-based trending (cached 5 min, supports pagination)

Docs: `http://localhost:8000/docs`

## Trending

After loading articles, generate simulated events for trending testing:

```bash
uv run python -m app.cli generate-events
```

Options: `--count` / `-n` (default 10000), `--users` / `-u` (default 500), `--lat` and `--lon` to cluster events at a location for focused trending tests.

```bash
uv run python -m app.cli generate-events --lat 18.02 --lon 72.70 -n 1000
```
