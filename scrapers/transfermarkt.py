"""
Transfermarkt scraper.

Collects:
  1. Club rosters per league/season (club list → per-club player table)
  2. Current market value for each player

Transfermarkt anti-scraping notes:
  - Requires Accept-Language and a real User-Agent.
  - Enforce ≥2 s delay between requests (configurable via SCRAPE_DELAY_SECONDS).
  - The HTML structure uses specific class names; update _parse_club_players()
    if they change a template.

Endpoints:
  League clubs:
    https://www.transfermarkt.com/{slug}/startseite/wettbewerb/{code}
    /plus/?saison_id={year}

  Club squad:
    https://www.transfermarkt.com/{club_slug}/kader/verein/{club_id}
    /saison_id/{year}/plus/1

  Market value JSON (CEAPI — no JS required):
    https://www.transfermarkt.com/ceapi/marketValueDevelopment/graph/{player_id}
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Iterator

from bs4 import BeautifulSoup
from loguru import logger
from tqdm import tqdm

from config import LEAGUES, TARGET_SEASONS, TRANSFERMARKT_BASE
from scrapers.base import RateLimitedSession


class TransfermarktScraper(RateLimitedSession):
    SOURCE = "transfermarkt"

    TM_HEADERS = {
        "Referer": "https://www.transfermarkt.com/",
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def __init__(self):
        super().__init__()
        self._session.headers.update(self.TM_HEADERS)

    # ──────────────────────────────────────────────────────────────
    # Year helpers
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _year_to_saison(year: str) -> int:
        """'23/24' → 2023"""
        return 2000 + int(year.split("/")[0])

    # ──────────────────────────────────────────────────────────────
    # Club list for a league/season
    # ──────────────────────────────────────────────────────────────

    def get_clubs(self, league_key: str, year: str) -> list[dict]:
        """
        Returns list of dicts:
          { "tm_id": int, "slug": str, "name": str }
        """
        cfg = LEAGUES[league_key]
        saison = self._year_to_saison(year)
        url = (
            f"{TRANSFERMARKT_BASE}/{cfg['transfermarkt_slug']}"
            f"/startseite/wettbewerb/{cfg['transfermarkt_code']}"
            f"/plus/?saison_id={saison}"
        )
        key = f"clubs_{league_key}_{saison}"
        html = self.get_html(url, cache_key=key)
        return self._parse_clubs(html)

    def _parse_clubs(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        clubs: list[dict] = []

        # The main clubs table has class "items"
        table = soup.find("table", {"class": "items"})
        if table is None:
            logger.warning("Could not find clubs table on Transfermarkt page")
            return clubs

        for row in table.find_all("tr", {"class": ["odd", "even"]}):
            # Transfermarkt dropped the vereinprofil_tooltip class (2025
            # template); match the club link by its href pattern instead:
            # /{slug}/startseite/verein/{id}
            link = None
            for a in row.find_all("a", href=True):
                if "/startseite/verein/" in a["href"] and a.get_text(strip=True):
                    link = a
                    break
            if link is None:
                continue
            href = link.get("href", "")
            m = re.search(r"/verein/(\d+)", href)
            if not m:
                continue
            clubs.append({
                "tm_id": int(m.group(1)),
                "slug": href.split("/")[1],
                "name": link.get_text(strip=True),
            })
        return clubs

    # ──────────────────────────────────────────────────────────────
    # Player list for a club/season
    # ──────────────────────────────────────────────────────────────

    def get_club_players(self, club: dict, year: str) -> list[dict]:
        """
        Returns list of player dicts for a club roster:
          { "tm_id", "name", "slug", "position", "dob", "nationality",
            "market_value_eur", "club_tm_id", "club_name" }
        """
        saison = self._year_to_saison(year)
        url = (
            f"{TRANSFERMARKT_BASE}/{club['slug']}"
            f"/kader/verein/{club['tm_id']}"
            f"/saison_id/{saison}/plus/1"
        )
        key = f"squad_{club['tm_id']}_{saison}"
        html = self.get_html(url, cache_key=key)
        players = self._parse_club_players(html)
        for p in players:
            p["club_tm_id"] = club["tm_id"]
            p["club_name"] = club["name"]
        return players

    def _parse_club_players(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        players: list[dict] = []

        table = soup.find("table", {"class": "items"})
        if table is None:
            return players

        for row in table.find_all("tr", {"class": ["odd", "even"]}):
            cells = row.find_all("td")
            if len(cells) < 5:
                continue

            # Player name & link
            name_cell = row.find("td", {"class": "hauptlink"})
            if name_cell is None:
                continue
            link = name_cell.find("a")
            if link is None:
                continue
            href = link.get("href", "")
            m = re.search(r"/spieler/(\d+)", href)
            if not m:
                continue
            tm_id = int(m.group(1))
            slug = href.split("/")[1] if "/" in href else ""
            name = link.get_text(strip=True)

            # Position: the inline table inside the posrela cell has the
            # player link in its first row and the position text in its last.
            pos_cell = row.find("td", {"class": "posrela"})
            position = ""
            if pos_cell:
                pos_tbl = pos_cell.find("table")
                if pos_tbl:
                    inner_rows = pos_tbl.find_all("tr")
                    if inner_rows:
                        position = inner_rows[-1].get_text(strip=True)

            # Date of birth: rendered as "17/08/1993 (31)" (or "Aug 17, 1993
            # (31)" in the US locale). The trailing "(age)" distinguishes it
            # from the same-shaped "joined" date cell, so require it.
            dob: date | None = None
            for cell in row.find_all("td", {"class": "zentriert"}):
                text = cell.get_text(strip=True)
                m_dob = re.match(r"^(.+?)\s*\(\d+\)$", text)
                if not m_dob:
                    continue
                dob_str = m_dob.group(1).strip()
                for fmt in ("%d/%m/%Y", "%b %d, %Y"):
                    try:
                        dob = datetime.strptime(dob_str, fmt).date()
                        break
                    except ValueError:
                        continue
                if dob:
                    break

            # Nationality (flag img alt text)
            nat = ""
            for img in row.find_all("img", {"class": "flaggenrahmen"}):
                nat = img.get("title", "")
                break

            # Market value (last <td class="rechts hauptlink">)
            mv_eur: int | None = None
            for td in reversed(row.find_all("td")):
                classes = td.get("class", [])
                if "rechts" in classes and "hauptlink" in classes:
                    mv_eur = _parse_value(td.get_text(strip=True))
                    break

            players.append({
                "tm_id": tm_id,
                "slug": slug,
                "name": name,
                "position": position,
                "dob": dob,
                "nationality": nat,
                "market_value_eur": mv_eur,
            })

        return players

    # ──────────────────────────────────────────────────────────────
    # Market value history (CEAPI — returns JSON, no JS needed)
    # ──────────────────────────────────────────────────────────────

    def get_market_value_history(self, tm_id: int) -> list[dict]:
        """
        Returns a list of historical market value snapshots:
          [{"date": date, "value_eur": int, "club": str, "age": int}, ...]
        """
        url = f"{TRANSFERMARKT_BASE}/ceapi/marketValueDevelopment/graph/{tm_id}"
        key = f"mv_history_{tm_id}"
        data = self.get_json(url, cache_key=key, headers={"Accept": "application/json"})

        history: list[dict] = []
        for entry in data.get("list", []):
            raw_date = entry.get("datum_mw", "")
            try:
                d = datetime.strptime(raw_date, "%b %d, %Y").date()
            except ValueError:
                continue
            mv = entry.get("y") or _parse_value(str(entry.get("mw", "")))
            history.append({
                "date": d,
                "value_eur": int(mv) if mv else None,
                "club": entry.get("verein", ""),
                "age": entry.get("age"),
            })
        return history

    def get_latest_market_value(self, tm_id: int) -> int | None:
        """Most recent market value in EUR for a player."""
        history = self.get_market_value_history(tm_id)
        if not history:
            return None
        return history[-1]["value_eur"]

    # ──────────────────────────────────────────────────────────────
    # High-level: scrape all leagues/seasons
    # ──────────────────────────────────────────────────────────────

    def scrape_all(self) -> list[dict]:
        """
        Returns a flat list of player records enriched with the most recent
        market value and metadata needed to link to SofaScore players:
          {
            "league_key", "league_name", "season_year",
            "tm_id", "name", "slug", "position", "dob", "nationality",
            "market_value_eur", "club_tm_id", "club_name",
          }
        """
        records: list[dict] = []
        seen_tm_ids: set[int] = set()

        for league_key, cfg in LEAGUES.items():
            for year in TARGET_SEASONS:
                logger.info(f"Transfermarkt → {cfg['name']} {year}")
                clubs = self.get_clubs(league_key, year)
                logger.info(f"  {len(clubs)} clubs")

                for club in tqdm(clubs, desc=f"{cfg['name']} {year}", leave=False):
                    players = self.get_club_players(club, year)
                    for p in players:
                        record = {
                            "league_key": league_key,
                            "league_name": cfg["name"],
                            "season_year": year,
                            **p,
                        }
                        records.append(record)

                        # Fetch market value history once per player (not per season)
                        if p["tm_id"] not in seen_tm_ids:
                            seen_tm_ids.add(p["tm_id"])
                            history = self.get_market_value_history(p["tm_id"])
                            record["mv_history"] = history
                        else:
                            record["mv_history"] = []

        return records


# ──────────────────────────────────────────────────────────────────
# Value parsing helpers
# ──────────────────────────────────────────────────────────────────

def _parse_value(raw: str) -> int | None:
    """
    Parse Transfermarkt value strings like "€50.00m", "€850k", "€-" → int EUR.
    """
    raw = raw.strip().replace(",", ".")
    if not raw or raw in ("-", "€-", "N/A"):
        return None
    raw = raw.lstrip("€").strip()
    try:
        if raw.endswith("m"):
            return int(float(raw[:-1]) * 1_000_000)
        elif raw.endswith("k"):
            return int(float(raw[:-1]) * 1_000)
        else:
            return int(float(raw))
    except (ValueError, IndexError):
        return None
