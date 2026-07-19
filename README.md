# Transfer Recruitment IDSS

An Intelligent Decision Support System for football transfer recruitment,
built for MSE 436. A sporting director enters a position, budget, age range,
and attribute priorities; a position-aware KNN model scores every eligible
player in Europe's top five leagues and returns a ranked shortlist with fit
scores, attribute breakdowns, and Transfermarkt market values.

Performance stats are from the **2024/25 season** (the newest the
API-Football free tier serves — 2025/26 needs a paid plan); market values
and squads are **current (2025/26)** from Transfermarkt.

**Stack:** API-Football (performance stats) + Transfermarkt (market values)
→ Supabase (PostgreSQL) → scikit-learn KNN → FastAPI → React + Tailwind.

This repo also contains the original data layer (SofaScore + Transfermarkt →
local Postgres → parquet) in `scrapers/`, `db/`, `migrations/`, and
`main.py`; the IDSS reuses its Transfermarkt scraper via
`pipeline/scrape_transfermarkt_values.py`.

```
/
├── .env                        # credentials (never committed)
├── requirements.txt / pyproject.toml
├── pipeline/
│   ├── fetch_api_football.py         # pulls and caches API-Football data
│   ├── scrape_transfermarkt_values.py# squads + market values → Supabase
│   ├── build_player_table.py         # joins sources, computes per90s, upserts
│   └── cache/                        # raw API-Football responses (JSON)
├── scrapers/                   # original scraper layer (Transfermarkt reused)
├── model/
│   └── knn.py                  # KNN logic
├── backend/
│   └── main.py                 # FastAPI app
├── frontend/                   # React + Tailwind UI (Vite)
└── README.md
```

## Prerequisites

- Python 3.11+ (or `uv`, which manages the venv from `pyproject.toml`)
- Node.js 18+
- An [API-Football](https://dashboard.api-football.com/) key (free tier —
  sign up on the api-sports dashboard, not RapidAPI)
- A Supabase project

## 1. Environment setup

With uv (recommended, matches the committed lockfile workflow):

```bash
uv sync
```

or with plain pip:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your credentials:

```
API_FOOTBALL_KEY=your_api_football_key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_api_key
SUPABASE_DB_PASSWORD=your_database_password   # for direct-SQL table creation
DATABASE_URL=postgresql://localhost/soccer_idss  # only for the old scraper layer
```

Credentials are loaded with python-dotenv; nothing is hardcoded and `.env`
is gitignored.

## 2. Run the data pipeline

**Step 1 — Transfermarkt market values (~10 min, cached):**

```bash
uv run python pipeline/scrape_transfermarkt_values.py
```

Walks every 2025/26 squad in the five leagues using the rate-limited,
disk-cached scraper (2 s between requests), then creates/upserts the
`transfermarkt_players` table in Supabase with `name`, `date_of_birth`,
`club`, `market_value_eur`, and detailed `position`.

**Step 2 — API-Football stats (respects the 100 requests/day limit):**

```bash
uv run python pipeline/fetch_api_football.py
```

Free-tier constraints, all handled automatically:

- **100 requests/day** — the script prints used/remaining after every call,
  stops cleanly at the quota, and resumes from its JSON cache next run.
  A full fetch (~210 requests) takes **2–3 days of runs**.
- **10 requests/minute** — calls are throttled to ~9/min; a mid-run 429
  waits a minute instead of aborting.
- **Season cap** — free plans only serve seasons 2022–2024, so the app uses
  **2024/25** (2025/26 needs a paid plan).
- **Page cap (3)** — players are fetched per *team* (a squad fits in ≤3
  pages) rather than per league.

**Step 3 — build and upsert (no API requests):**

```bash
uv run python pipeline/build_player_table.py
```

Flattens the cached responses, keeps only the five league competitions
(team queries also return cup games), computes per-90 and percentage
metrics with division-by-zero guards, joins against `transfermarkt_players`
on `lower(name) + '_' + date_of_birth`, refines broad API positions with
Transfermarkt's detailed roles (so Fullback/Winger exist), and upserts into
the `players` table keyed on `join_key` — re-running is always safe.
Unmatched players are kept with a null market value and listed in
`unmatched_players.log`. (If the original pipeline's
`data/processed/player_features.parquet` exists, it is used as the
market-value source instead of Supabase.)

Data caveats from the free `/players` endpoint: aerial-duel win rate falls
back to overall duel win rate, per-player clean sheets are unavailable
(null), and pass completion uses the API's `passes.accuracy` field.

## 3. Start the backend

```bash
uv run uvicorn backend.main:app --reload
```

Endpoints (docs at http://localhost:8000/docs):

- `POST /recommend` — position, max_budget_eur, min_age, max_age, weights → top-15 shortlist
- `GET /players` — raw player list, optional `position` / `max_budget_eur` filters
- `GET /health` — API status and player count

## 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 (the backend's CORS allowlist expects this port).

## How the KNN model works (plain English)

Think of every striker (or keeper, or midfielder…) as a point in space,
where each axis is one stat that matters for that position — for strikers:
goals per 90, shots per 90, shot accuracy, and aerial duels won.

1. **Filter first.** Only players in the chosen position, within budget
   (players without a known market value are skipped), and inside the age
   range are considered — the model never wastes a recommendation on someone
   you can't sign.
2. **Put every stat on the same scale.** Passes per 90 can be ~50 while
   goals per 90 is ~0.5, so each stat is standardised (StandardScaler) so no
   stat dominates just because its numbers are bigger.
3. **Apply your priorities.** Each scaled stat is multiplied by your 0–3
   weight *after* scaling — a weight of 3 makes differences in that stat
   count three times as much, and 0 removes it entirely.
4. **Build the "ideal player".** The target starts at the midpoint of each
   stat's range among the filtered players, then shifts toward the top of
   the range for stats you weighted highly — the more you care, the more
   elite the target.
5. **Find the nearest neighbours.** The 15 players closest to that ideal
   point (Euclidean distance) are returned, with distance converted to a
   0–100 fit score: `fit = max(0, 100 − distance × 25)`.

Each card in the UI shows, per stat, the player's actual value against the
ideal value so you can see *why* a player scored the way they did.

If fewer than 15 players satisfy the filters, the API returns a readable
error suggesting a bigger budget or wider age range instead of a 500.
