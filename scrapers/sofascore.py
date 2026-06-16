"""
SofaScore unofficial JSON API scraper.

Endpoints used:
  GET /tournament/{tournament_id}/seasons
      → lists all seasons for a league with their SofaScore IDs

  GET /season/{season_id}/statistics/player
      ?page=0&limit=100&sortField=rating&sortDirection=desc
      &position=T&minMinutesPlayed=0
      → paginated player stats for one season

  GET /player/{player_id}
      → player profile (dob, nationality, position, transfermarkt link)

All responses are cached to data/raw/sofascore/ so subsequent runs
read from disk and don't hammer the API.

NOTE: These endpoints are unofficial and may change. If you get 404s,
inspect requests on sofascore.com with browser DevTools and update the
URL patterns here.
"""

from __future__ import annotations

from loguru import logger
from tqdm import tqdm

from config import SOFASCORE_BASE, LEAGUES, TARGET_SEASONS
from scrapers.base import RateLimitedSession


class SofaScoreScraper(RateLimitedSession):
    SOURCE = "sofascore"

    EXTRA_HEADERS = {
        "Referer": "https://www.sofascore.com/",
        "Origin": "https://www.sofascore.com",
        "Accept": "application/json",
    }

    def __init__(self):
        super().__init__()
        self._session.headers.update(self.EXTRA_HEADERS)

    # ──────────────────────────────────────────────────────────────
    # Season discovery
    # ──────────────────────────────────────────────────────────────

    def get_seasons(self, tournament_id: int) -> list[dict]:
        """
        Returns all season records for a tournament, e.g.
          [{"id": 61627, "name": "24/25", "year": "24/25"}, ...]
        """
        url = f"{SOFASCORE_BASE}/tournament/{tournament_id}/seasons"
        key = f"tournament_{tournament_id}_seasons"
        data = self.get_json(url, cache_key=key)
        return data.get("seasons", [])

    def resolve_season_id(self, tournament_id: int, year: str) -> int | None:
        """
        Map a human year string like "23/24" → SofaScore season ID.
        SofaScore stores year as "23/24" or "2023/2024" — we try both.
        """
        seasons = self.get_seasons(tournament_id)
        # Normalise target: "23/24" → also try "2023/2024"
        parts = year.split("/")
        full_year = f"20{parts[0]}/20{parts[1]}" if len(parts[0]) == 2 else year

        for s in seasons:
            if s.get("year") in (year, full_year) or s.get("name") in (year, full_year):
                return s["id"]

        logger.warning(f"Season '{year}' not found for tournament {tournament_id}. "
                       f"Available: {[s.get('year') for s in seasons[:5]]}")
        return None

    # ──────────────────────────────────────────────────────────────
    # Season statistics (all players, paginated)
    # ──────────────────────────────────────────────────────────────

    def get_season_stats(
        self,
        season_id: int,
        position: str = "T",   # T=all, G=GK, D=def, M=mid, F=fwd
        min_minutes: int = 0,
        page_limit: int = 100,
    ) -> list[dict]:
        """
        Fetches all pages of player statistics for a season.
        Returns a flat list of result dicts, each containing:
          { "player": {...}, "team": {...}, "statistics": {...} }
        """
        all_results: list[dict] = []
        page = 0

        while True:
            key = f"season_{season_id}_stats_pos{position}_page{page}"
            url = (
                f"{SOFASCORE_BASE}/season/{season_id}/statistics/player"
                f"?page={page}&limit={page_limit}"
                f"&sortField=rating&sortDirection=desc"
                f"&position={position}&minMinutesPlayed={min_minutes}"
            )
            data = self.get_json(url, cache_key=key)
            results = data.get("results", [])
            if not results:
                break
            all_results.extend(results)
            total_pages = data.get("pages", 1)
            page += 1
            if page >= total_pages:
                break

        return all_results

    # ──────────────────────────────────────────────────────────────
    # Player profile
    # ──────────────────────────────────────────────────────────────

    def get_player_profile(self, player_id: int) -> dict:
        """
        Returns the full player profile dict from SofaScore, e.g.
          { "id", "name", "slug", "position", "dateOfBirthTimestamp",
            "country": {"name", "alpha2"}, "transfermarktUrl", ... }
        """
        url = f"{SOFASCORE_BASE}/player/{player_id}"
        key = f"player_{player_id}"
        data = self.get_json(url, cache_key=key)
        return data.get("player", data)

    # ──────────────────────────────────────────────────────────────
    # High-level: scrape everything for configured leagues/seasons
    # ──────────────────────────────────────────────────────────────

    def scrape_all(self) -> list[dict]:
        """
        Main entry point. Iterates every (league, season) combination in
        config and returns a flat list of enriched player-season records:

          {
            "league_key": str,
            "league_name": str,
            "season_year": str,
            "sofascore_season_id": int,
            "player": { sofascore player dict },
            "team": { sofascore team dict },
            "statistics": { raw stat dict },
          }
        """
        records: list[dict] = []

        for league_key, league_cfg in LEAGUES.items():
            tournament_id = league_cfg["sofascore_tournament_id"]

            for year in TARGET_SEASONS:
                season_id = self.resolve_season_id(tournament_id, year)
                if season_id is None:
                    logger.warning(f"Skipping {league_cfg['name']} {year} — season not found")
                    continue

                logger.info(f"Fetching {league_cfg['name']} {year} (season_id={season_id})")
                results = self.get_season_stats(season_id)
                logger.info(f"  → {len(results)} player-season rows")

                for r in tqdm(results, desc=f"{league_cfg['name']} {year}", leave=False):
                    records.append({
                        "league_key": league_key,
                        "league_name": league_cfg["name"],
                        "season_year": year,
                        "sofascore_season_id": season_id,
                        "player": r.get("player", {}),
                        "team": r.get("team", {}),
                        "statistics": r.get("statistics", {}),
                    })

        return records


# ──────────────────────────────────────────────────────────────────
# Stat field mapping
# SofaScore API field → our DB column name
# ──────────────────────────────────────────────────────────────────

STAT_MAP: dict[str, str] = {
    "appearances": "appearances",
    "minutesPlayed": "minutes_played",
    "goals": "goals",
    "assists": "assists",
    "shotsTotal": "shots_total",
    "shotsOnTarget": "shots_on_target",
    "expectedGoals": "expected_goals",
    "expectedAssists": "expected_assists",
    "keyPasses": "key_passes",
    "totalPasses": "passes_total",
    "accuratePasses": "passes_accurate",
    "totalLongBalls": "long_balls_total",
    "accurateLongBalls": "long_balls_accurate",
    "totalCrosses": "crosses_total",
    "accurateCrosses": "crosses_accurate",
    "dribbleAttempts": "dribbles_attempted",
    "successfulDribbles": "dribbles_successful",
    "totalTackle": "tackles_total",
    "wonTackle": "tackles_won",
    "interceptions": "interceptions",
    "clearances": "clearances",
    "blockedShots": "blocks",
    "totalGroundDuels": "ground_duels_total",
    "groundDuelsWon": "ground_duels_won",
    "totalAerialDuels": "aerial_duels_total",
    "aerialDuelsWon": "aerial_duels_won",
    "saves": "saves",
    "goalsConceded": "goals_conceded",
    "cleanSheets": "clean_sheets",
    "yellowCards": "yellow_cards",
    "redCards": "red_cards",
    "rating": "avg_rating",
}


def map_stats(raw: dict) -> dict:
    """Translate a SofaScore statistics dict to DB column names."""
    out: dict = {}
    for api_key, db_col in STAT_MAP.items():
        val = raw.get(api_key)
        if val is not None:
            out[db_col] = val
    return out
