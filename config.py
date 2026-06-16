import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

for _d in (DATA_DIR, RAW_DIR / "sofascore", RAW_DIR / "transfermarkt", PROCESSED_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://localhost/soccer_idss"
)

SOFASCORE_BASE = "https://api.sofascore.com/api/v1"
TRANSFERMARKT_BASE = "https://www.transfermarkt.com"

FORCE_RESCRAPE = os.environ.get("FORCE_RESCRAPE", "0") == "1"
SCRAPE_DELAY = float(os.environ.get("SCRAPE_DELAY_SECONDS", "2.0"))

# Minimum minutes for a player to be included in features
MIN_MINUTES = 450

# Top 5 European leagues
LEAGUES = {
    "premier_league": {
        "name": "Premier League",
        "country": "England",
        "sofascore_tournament_id": 17,
        "transfermarkt_code": "GB1",
        "transfermarkt_slug": "premier-league",
    },
    "la_liga": {
        "name": "La Liga",
        "country": "Spain",
        "sofascore_tournament_id": 8,
        "transfermarkt_code": "ES1",
        "transfermarkt_slug": "laliga",
    },
    "bundesliga": {
        "name": "Bundesliga",
        "country": "Germany",
        "sofascore_tournament_id": 35,
        "transfermarkt_code": "L1",
        "transfermarkt_slug": "bundesliga",
    },
    "serie_a": {
        "name": "Serie A",
        "country": "Italy",
        "sofascore_tournament_id": 23,
        "transfermarkt_code": "IT1",
        "transfermarkt_slug": "serie-a",
    },
    "ligue_1": {
        "name": "Ligue 1",
        "country": "France",
        "sofascore_tournament_id": 34,
        "transfermarkt_code": "FR1",
        "transfermarkt_slug": "ligue-1",
    },
}

TARGET_SEASONS = ["23/24", "24/25"]

# SofaScore position code -> position group
SOFASCORE_POSITION_MAP = {
    "G": "GK",
    "D": "DEF",
    "M": "MID",
    "F": "FWD",
}

# Features used in the KNN vector, keyed by position group.
# Order matters: it defines the vector index layout.
POSITION_FEATURES: dict[str, list[str]] = {
    "FWD": [
        "goals_p90",
        "xg_p90",
        "shots_on_target_p90",
        "assists_p90",
        "xa_p90",
        "key_passes_p90",
        "dribbles_successful_p90",
        "aerial_duels_won_pct",
    ],
    "MID": [
        "key_passes_p90",
        "pass_completion_pct",
        "passes_p90",
        "xa_p90",
        "assists_p90",
        "goals_p90",
        "tackles_won_p90",
        "interceptions_p90",
        "dribbles_successful_p90",
    ],
    "DEF": [
        "tackles_won_p90",
        "interceptions_p90",
        "clearances_p90",
        "aerial_duels_won_pct",
        "pass_completion_pct",
        "blocks_p90",
        "dribbles_successful_p90",
    ],
    "GK": [
        "saves_p90",
        "save_pct",
        "pass_completion_pct",
    ],
}
