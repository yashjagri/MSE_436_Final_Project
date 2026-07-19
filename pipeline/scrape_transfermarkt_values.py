"""Scrape current Transfermarkt market values and load them into Supabase.

Uses the teammate's TransfermarktScraper (rate-limited, disk-cached) to walk
every club squad in the five target leagues for the 2024/25 season, then
upserts one row per player into the ``transfermarkt_players`` table that
pipeline/build_player_table.py joins against.

Unlike the teammate's full ``scrape_all`` flow this skips the per-player
market-value-history endpoint (~3000 extra requests) — the squad pages
already carry each player's current market value, so the whole run is about
100 cached-able page fetches.

Run with:  python pipeline/scrape_transfermarkt_values.py
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import LEAGUES  # noqa: E402
from scrapers.transfermarkt import TransfermarktScraper  # noqa: E402

load_dotenv()

# Scraped in order; a later season's row replaces an earlier one, so values
# are current (25/26) wherever possible while 24/25 squads keep coverage of
# players who left the five leagues (relegated clubs, summer transfers).
SEASON_YEARS = ["24/25", "25/26"]

CREATE_TABLE_SQL = """
create table if not exists transfermarkt_players (
  name text not null,
  date_of_birth date not null,
  club text,
  market_value_eur bigint,
  position text,
  primary key (name, date_of_birth)
);
alter table transfermarkt_players add column if not exists position text;
"""

UPSERT_SQL = """
insert into transfermarkt_players
  (name, date_of_birth, club, market_value_eur, position)
values (%s, %s, %s, %s, %s)
on conflict (name, date_of_birth) do update
  set club = excluded.club,
      market_value_eur = coalesce(excluded.market_value_eur,
                                  transfermarkt_players.market_value_eur),
      position = coalesce(excluded.position,
                          transfermarkt_players.position);
"""


def scrape_market_values():
    """Scrape every squad in the five leagues for both target seasons.

    Returns one row per unique (name, dob). Later seasons overwrite earlier
    ones (unless the newer market value is missing), so a player's club and
    value are as current as possible.
    """
    scraper = TransfermarktScraper()
    rows = {}
    for season in SEASON_YEARS:
        for league_key, cfg in LEAGUES.items():
            clubs = scraper.get_clubs(league_key, season)
            print(f"{cfg['name']} {season}: {len(clubs)} clubs")
            for club in clubs:
                players = scraper.get_club_players(club, season)
                kept = 0
                for p in players:
                    if not p["name"] or not p["dob"]:
                        continue
                    key = (p["name"], p["dob"])
                    if key not in rows or p["market_value_eur"] is not None:
                        rows[key] = (p["name"], p["dob"], club["name"],
                                     p["market_value_eur"],
                                     p["position"] or None)
                    kept += 1
                print(f"  {club['name']}: {kept} players")
    return list(rows.values())


def get_db_connection():
    """Open a direct Postgres connection to the Supabase project database."""
    supabase_url = os.environ.get("SUPABASE_URL", "")
    password = os.environ.get("SUPABASE_DB_PASSWORD")
    project_ref = urlparse(supabase_url).hostname.split(".")[0] \
        if supabase_url else None
    if not project_ref or not password:
        sys.exit("SUPABASE_URL and SUPABASE_DB_PASSWORD must be set in .env.")
    return psycopg2.connect(
        host=f"db.{project_ref}.supabase.co", port=5432,
        dbname="postgres", user="postgres", password=password,
        connect_timeout=10)


def upload(rows):
    """Create the table if needed and upsert all scraped rows."""
    conn = get_db_connection()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
        cur.executemany(UPSERT_SQL, rows)
        cur.execute("select count(*) from transfermarkt_players")
        total = cur.fetchone()[0]
    conn.close()
    print(f"Upserted {len(rows)} rows; transfermarkt_players now has "
          f"{total} rows.")


def main():
    """Scrape squad market values and load them into Supabase."""
    rows = scrape_market_values()
    print(f"\nScraped {len(rows)} unique players with name+DOB.")
    upload(rows)


if __name__ == "__main__":
    main()
