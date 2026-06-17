# Soccer IDSS — Data Layer

**Intelligent Decision Support System for Soccer Recruitment**

This repo currently covers **data ingestion and transformation**: scraping player stats and market values, storing them in PostgreSQL, and producing normalized per-position player profiles for the recruitment decision layer (not yet built).

**Sources:** SofaScore (performance stats), Transfermarkt (market values)  
**Coverage:** Premier League, La Liga, Bundesliga, Serie A, Ligue 1 — seasons `23/24`, `24/25`

---

## Setup

**Prerequisites:** [uv](https://docs.astral.sh/uv/), Python 3.11+, PostgreSQL 16.

### 1. Install uv

**macOS / Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Install and start PostgreSQL

**macOS (Homebrew):**

```bash
brew install postgresql@16
brew services start postgresql@16
createdb soccer_idss
```

**Windows:**

Download and run the installer from [postgresql.org](https://www.postgresql.org/download/windows/). The service starts automatically. Then open a terminal and run:

```bash
createdb soccer_idss
```

> If `createdb` is not found, add the Postgres `bin` folder to your PATH (e.g. `C:\Program Files\PostgreSQL\16\bin`).

### 3. Install deps and apply the schema

```bash
uv sync
uv run python main.py setup
```

---

## Running the pipeline

```bash
# First run (or full refresh): scrape → transform → build-features
uv run python main.py pipeline

# Rebuild from existing DB/cache (no network)
uv run python main.py pipeline --skip-scrape
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
