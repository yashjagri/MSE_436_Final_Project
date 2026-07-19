"""Fetch player statistics from API-Football and cache them to disk.

Pulls every player for the five target leagues (Premier League, La Liga,
Bundesliga, Serie A, Ligue 1) for the 2024/25 season.

Free-tier constraints shape the design:
  * 100 requests/day — a daily counter is persisted to
    ``pipeline/cache/request_log.json`` and the script hard-stops before
    exceeding it, resuming from the cache on the next run.
  * seasons limited to 2022-2024 — so the 2024/25 season is fetched
    (2025/26 needs a paid plan).
  * the ``page`` parameter is capped at 3 — so players are fetched per
    *team* (a squad fits in <=3 pages of 20) instead of per league.

Flow: 1 request per league for its team list, then up to 3 pages of
``/players`` per team. Every response is cached as JSON in
``pipeline/cache`` so no request is ever spent twice; interrupting and
re-running is always safe.

Run with:  python pipeline/fetch_api_football.py
"""

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = "https://v3.football.api-sports.io"
# 2024/25 season — the newest the API-Football free plan allows (free plans
# cover seasons 2022-2024 only; 2025/26 requires a paid plan).
SEASON = 2024
DAILY_REQUEST_LIMIT = 100
PER_MINUTE_LIMIT = 10        # free tier also caps requests per minute
REQUEST_INTERVAL = 60 / PER_MINUTE_LIMIT + 0.5
MAX_RETRIES = 3
MAX_RATE_LIMIT_WAITS = 5
MAX_FREE_PAGE = 3  # free plans reject page > 3

LEAGUES = {
    39: "Premier League",
    140: "La Liga",
    78: "Bundesliga",
    135: "Serie A",
    61: "Ligue 1",
}

CACHE_DIR = Path(__file__).parent / "cache"
REQUEST_LOG_FILE = CACHE_DIR / "request_log.json"


class DailyQuotaExhausted(Exception):
    """Raised when the 100 requests/day API-Football quota is used up."""


def load_request_log():
    """Return today's request count, resetting the counter on a new day."""
    today = date.today().isoformat()
    if REQUEST_LOG_FILE.exists():
        with open(REQUEST_LOG_FILE) as f:
            log = json.load(f)
        if log.get("date") == today:
            return log
    return {"date": today, "count": 0}


def save_request_log(log):
    """Persist the daily request counter to disk."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(REQUEST_LOG_FILE, "w") as f:
        json.dump(log, f)


def print_quota(log):
    """Print how many API requests have been used today and how many remain."""
    remaining = DAILY_REQUEST_LIMIT - log["count"]
    print(f"  API requests used today: {log['count']}/{DAILY_REQUEST_LIMIT} "
          f"({remaining} remaining)")


def teams_cache_path(league_id):
    """Return the cache file path for a league's team list."""
    return CACHE_DIR / f"teams_league{league_id}_season{SEASON}.json"


def players_cache_path(team_id, page):
    """Return the cache file path for one page of one team's players."""
    return CACHE_DIR / f"players_team{team_id}_season{SEASON}_page{page}.json"


_last_request_at = {"t": 0.0}


def throttle():
    """Space requests out to stay under the free tier's per-minute limit."""
    elapsed = time.time() - _last_request_at["t"]
    if elapsed < REQUEST_INTERVAL:
        time.sleep(REQUEST_INTERVAL - elapsed)
    _last_request_at["t"] = time.time()


def api_get(endpoint, params, request_log):
    """Call an API-Football endpoint with quota tracking and retries.

    Requests are throttled to the free tier's per-minute limit. Non-200
    responses and network errors are retried with exponential backoff. A 429
    is disambiguated via the rate-limit headers: if the *daily* quota is gone
    it raises DailyQuotaExhausted (retrying cannot help); if only the
    per-minute limit was hit it waits a minute and tries again.
    """
    if request_log["count"] >= DAILY_REQUEST_LIMIT:
        raise DailyQuotaExhausted(
            "Daily request quota reached — run the pipeline again tomorrow.")

    api_key = os.environ.get("API_FOOTBALL_KEY")
    if not api_key:
        sys.exit("API_FOOTBALL_KEY is not set. Add it to your .env file.")

    headers = {"x-apisports-key": api_key}
    url = f"{API_BASE_URL}{endpoint}"

    attempt = 0
    rate_limit_waits = 0
    while True:
        throttle()
        try:
            response = requests.get(url, headers=headers, params=params,
                                    timeout=30)
        except requests.RequestException as exc:
            attempt += 1
            if attempt >= MAX_RETRIES:
                raise
            wait = 2 ** attempt
            print(f"  Network error ({exc}); retrying in {wait}s...")
            time.sleep(wait)
            continue

        # The response headers carry the authoritative daily count; sync our
        # local counter with them so it never drifts.
        daily_remaining = response.headers.get("x-ratelimit-requests-remaining")
        if daily_remaining is not None and daily_remaining.isdigit():
            request_log["count"] = max(request_log["count"] + 1,
                                       DAILY_REQUEST_LIMIT - int(daily_remaining))
        else:
            request_log["count"] += 1
        save_request_log(request_log)
        print_quota(request_log)

        if response.status_code == 200:
            body = response.json()
            # API-Football returns errors inside a 200 body sometimes.
            if body.get("errors"):
                errors = body["errors"]
                if "rateLimit" in errors:
                    # Per-minute limit reported inside a 200 body.
                    rate_limit_waits += 1
                    if rate_limit_waits > MAX_RATE_LIMIT_WAITS:
                        raise RuntimeError(f"Still rate-limited: {errors}")
                    print("  Per-minute rate limit hit; waiting 61s...")
                    time.sleep(61)
                    continue
                if "requests" in errors:
                    raise DailyQuotaExhausted(str(errors))
                raise RuntimeError(f"API error for {endpoint} {params}: {errors}")
            return body

        if response.status_code == 429:
            if daily_remaining == "0":
                raise DailyQuotaExhausted(
                    "Daily quota exhausted (429 with 0 requests remaining).")
            rate_limit_waits += 1
            if rate_limit_waits > MAX_RATE_LIMIT_WAITS:
                raise DailyQuotaExhausted(
                    "Repeatedly rate-limited; stopping for today.")
            print("  Per-minute rate limit hit (429); waiting 61s...")
            time.sleep(61)
            continue

        attempt += 1
        if attempt >= MAX_RETRIES:
            raise RuntimeError(
                f"API request failed after {MAX_RETRIES} attempts: "
                f"HTTP {response.status_code} for {endpoint} {params}")
        wait = 2 ** attempt
        print(f"  HTTP {response.status_code}; retrying in {wait}s...")
        time.sleep(wait)


def cached_or_fetch(path, endpoint, params, request_log):
    """Return the JSON at ``path`` if cached, else fetch and cache it."""
    if path.exists():
        with open(path) as f:
            return json.load(f), False
    body = api_get(endpoint, params, request_log)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(body, f)
    return body, True


def fetch_team_ids(league_id, request_log):
    """Return all team ids for a league's season (one request, cached)."""
    body, from_api = cached_or_fetch(
        teams_cache_path(league_id), "/teams",
        {"league": league_id, "season": SEASON}, request_log)
    teams = [entry["team"]["id"] for entry in body.get("response", [])]
    source = "fetched" if from_api else "cache"
    print(f"  Team list ({source}): {len(teams)} teams")
    return teams


def fetch_team_players(team_id, request_log):
    """Fetch all player pages (<=3 on free tier) for one team, via cache."""
    page = 1
    total_pages = None
    while total_pages is None or page <= min(total_pages, MAX_FREE_PAGE):
        body, from_api = cached_or_fetch(
            players_cache_path(team_id, page), "/players",
            {"team": team_id, "season": SEASON, "page": page}, request_log)
        total_pages = body.get("paging", {}).get("total", 1)
        if from_api:
            print(f"  Team {team_id}: page {page}/{total_pages} fetched")
        page += 1
    if total_pages > MAX_FREE_PAGE:
        print(f"  Warning: team {team_id} has {total_pages} pages; "
              f"free tier caps at {MAX_FREE_PAGE}.")


def fetch_league(league_id, league_name, request_log):
    """Fetch every team's players for one league, resuming from the cache.

    Returns True when the league is fully cached, False if the run stopped
    early because the daily quota ran out.
    """
    print(f"\n=== {league_name} (league id {league_id}) ===")
    try:
        team_ids = fetch_team_ids(league_id, request_log)
        for team_id in team_ids:
            fetch_team_players(team_id, request_log)
    except DailyQuotaExhausted as exc:
        print(f"  Stopping: {exc}")
        return False
    print(f"  {league_name} complete: {len(team_ids)} teams cached.")
    return True


def main():
    """Fetch all five leagues, respecting the daily quota and the cache."""
    request_log = load_request_log()
    print(f"API-Football fetcher — {SEASON}/{(SEASON + 1) % 100} season, "
          "top 5 leagues, per-team mode")
    print_quota(request_log)

    for league_id, league_name in LEAGUES.items():
        completed = fetch_league(league_id, league_name, request_log)
        if not completed:
            print("\nDaily quota exhausted. Progress is cached — re-run this "
                  "script tomorrow to resume where it left off.")
            sys.exit(0)

    print("\nAll leagues fully cached. "
          "Next step: python pipeline/build_player_table.py")


if __name__ == "__main__":
    main()
