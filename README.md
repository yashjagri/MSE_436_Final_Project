# Soccer IDSS — Data Layer

**Intelligent Decision Support System for Soccer Recruitment**

This repo currently covers **data ingestion and transformation**: scraping player stats and market values, storing them in PostgreSQL, and producing normalized per-position player profiles for the recruitment decision layer (not yet built).

**Sources:** SofaScore (performance stats), Transfermarkt (market values)  
**Coverage:** Premier League, La Liga, Bundesliga, Serie A, Ligue 1 — seasons `23/24`, `24/25`

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # set DATABASE_URL if needed

createdb soccer_idss          # one-time, if the DB doesn't exist yet
python main.py db-init        # applies migrations/001_initial_schema.sql via psql
```

`db-init` applies the schema only — it does not create the database. Requires PostgreSQL with `psql` on your PATH.

---

## Running the pipeline

```bash
# First run (or full refresh): scrape → transform → build-features
python main.py pipeline

# Rebuild from existing DB/cache (no network)
python main.py pipeline --skip-scrape
```

Or programmatically:

```python
from pipeline.transform import run_transform
from pipeline.build_features import run_build_features

run_transform()        # raw season stats → per-90 player profiles in DB
run_build_features()   # normalize profiles → parquet export + DB vectors
```

---

## Outputs (for the recruitment decision layer)

| Artifact | Path / location | Purpose |
|---|---|---|
| Player profiles | `data/processed/player_features.parquet` | Exportable player pool with stats, metadata, and normalized profile vectors |
| Normalization bounds | `data/processed/scalers.json` | Min/max per position × stat (for comparing profiles on a common scale) |
| Position stat schema | `config.POSITION_FEATURES` | Which stats matter per position group (`GK`, `DEF`, `MID`, `FWD`) and their order |
| Profile vectors | `player_features.feature_vector` (JSONB) | Same normalized vectors, queryable from Postgres |
| Query log (schema only) | `recommendation_logs` table | Reserved for logging recruitment searches once the decision layer exists |

Each parquet row includes per-90 stats, recruitment metadata (`position_group`, `age`, `market_value_eur`, `league_name`, `club_name`, `minutes_played`), a `feature_vector` (normalized `[0,1]` profile), and `feature_names` (column order).

**Relevant config** (`config.py`):

| Setting | Default | Purpose |
|---|---|---|
| `MIN_MINUTES` | `450` | Minimum playing time for a player to enter the pool |
| `POSITION_FEATURES` | per position group | Stat dimensions used to build comparable profiles |
