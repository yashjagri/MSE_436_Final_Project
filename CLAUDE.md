# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A football transfer recruitment IDSS (Intelligent Decision Support System) for MSE 436. A sporting
director enters a position, budget, age range, and attribute priorities; a position-aware KNN model
scores every eligible player in Europe's top-five leagues and returns a ranked shortlist with fit
scores, attribute breakdowns, and Transfermarkt market values.

## Two independent data layers (read this first)

The repo contains **two separate stacks** that share only the Transfermarkt scraper. Confusing them
is the most common mistake:

1. **Current IDSS (active)** — API-Football + Transfermarkt → **Supabase (PostgreSQL)** → `model/knn.py`
   → `backend/main.py` (FastAPI) → `frontend/` (React + Vite). Files: `pipeline/fetch_api_football.py`,
   `pipeline/scrape_transfermarkt_values.py`, `pipeline/build_player_table.py`, `model/`, `backend/`,
   `frontend/`. Data lives in the Supabase `players` table.

2. **Legacy scraper layer (original data pipeline)** — SofaScore + Transfermarkt → **local Postgres**
   → parquet. Files: `main.py` (Click CLI), `config.py`, `scrapers/`, `db/`, `migrations/`,
   `pipeline/ingest.py`, `pipeline/transform.py`, `pipeline/build_features.py`. Driven by
   `uv run python main.py <command>`.

The IDSS reuses only `pipeline/scrape_transfermarkt_values.py` from the legacy world. If
`data/processed/player_features.parquet` (a legacy artifact) exists, `build_player_table.py` uses it
as the market-value source instead of Supabase.

**`POSITION_FEATURES` is defined twice with different schemas** — do not cross-reference them:
- `model/knn.py`: six detailed positions (`Goalkeeper`, `Fullback`, `Centre Back`, `Midfielder`,
  `Winger`, `Striker`), feature names suffixed `_per90` / `_pct`. **This is what the running app uses.**
- `config.py`: four broad groups (`FWD`/`MID`/`DEF`/`GK`), feature names suffixed `_p90`. Legacy only.

## Commands

Python env is managed with `uv` (matches the committed `uv.lock`). Prefix Python commands with `uv run`.

```bash
uv sync                                        # install deps from pyproject.toml/uv.lock

# Current IDSS data pipeline (run in order; see README for API quota details)
uv run python pipeline/scrape_transfermarkt_values.py   # squads + market values → Supabase (~10 min, cached)
uv run python pipeline/fetch_api_football.py            # stats → cache (100 req/day free tier; multi-day)
uv run python pipeline/build_player_table.py            # join + upsert into Supabase `players` (no API calls)

# Backend (run from repo root)
uv run uvicorn backend.main:app --reload               # FastAPI on :8000, docs at /docs

# Frontend
cd frontend && npm install && npm run dev              # Vite dev server on :3000 (strict port)

# Legacy pipeline (local Postgres)
uv run python main.py setup                            # copy .env, apply migrations/001_initial_schema.sql
uv run python main.py pipeline [--skip-scrape]         # scrape → transform → build-features → parquet
```

There is **no test suite** and no linter configured.

## Architecture notes

**KNN recommender (`model/knn.py`)** — the core algorithm, called by `backend/main.py`:
1. `filter_players` prunes to position + budget + age + `min_minutes` (default 450, to kill small-sample
   per-90 noise). Players with a null `market_value_eur` are dropped so the model only suggests
   signable players.
2. Raise `InsufficientPlayersError` if fewer than `TOP_N` (15) survive — the API turns this into a 422
   with a readable message, never a 500.
3. Per-position features are `StandardScaler`-scaled, then user weights (0–3) are applied **after**
   scaling so a weight expresses importance rather than unit magnitude.
4. `build_ideal_vector` constructs an "ideal player" query point: the midpoint of each feature's range,
   shifted toward that feature's max in proportion to `weight / MAX_WEIGHT`.
5. `NearestNeighbors` (Euclidean) returns the 15 closest; distance → fit score via
   `max(0, 100 - distance * 25)`. Each result carries plain-language `reasons` (percentile-based, within
   the filtered pool) and a per-feature `breakdown` used by the UI's radar chart.

**Backend (`backend/main.py`)** — thin FastAPI wrapper. Loads the entire Supabase `players` table into
a module-level DataFrame cache (`_players_cache`) once per process (paginated at 1000 rows). CORS is
locked to `http://localhost:3000` — this is why the frontend uses `strictPort` on 3000. Endpoints:
`POST /recommend`, `GET /players`, `GET /health`, `GET /monitoring`. Every `/recommend` call is
best-effort logged to the Supabase `recommendation_logs` table (`log_search`, failures swallowed);
`/monitoring` aggregates those logs into response-time, fit-distribution, per-league fairness, and
coverage metrics for the dashboard. (The README lists only three endpoints — `/monitoring` and the
logging are undocumented there.)

**Frontend (`frontend/`)** — React 18 + Tailwind v4 via Vite, no router. `src/App.jsx` orchestrates
`Sidebar` (brief input), `PlayerCard` + `FeatureBar` (results/radar), `ComparePanel`, and
`MonitoringPanel`.

**Config & credentials** — all secrets load from `.env` via `python-dotenv` (`config.py` for legacy,
inline `load_dotenv()` for IDSS). `.env` is gitignored; copy `.env.example`. Keys: `API_FOOTBALL_KEY`,
`SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_DB_PASSWORD`, `DATABASE_URL` (legacy Postgres only).

## Data caveats (baked into the pipeline, don't "fix")

- Stats are **2024/25 season** (newest the API-Football free tier serves); market values/squads are
  current 2025/26 from Transfermarkt. The join key is `lower(name) + '_' + date_of_birth`; unmatched
  players are kept with a null market value and logged to `unmatched_players.log`.
- Free `/players` endpoint limitations: aerial-duel win rate falls back to overall duel win rate,
  per-player clean sheets are null, pass completion uses the API's `passes.accuracy`.
- `fetch_api_football.py` self-throttles to the free tier (100 req/day, ~9 req/min, resumes from JSON
  cache in `pipeline/cache/`). A full fetch spans 2–3 days of runs.
