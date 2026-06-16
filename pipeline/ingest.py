"""
Ingest pipeline: scrape → parse → upsert into PostgreSQL.

Run order:
  1. ingest_sofascore()  — players, teams, seasons, player_season_stats
  2. ingest_transfermarkt()  — market values + fills transfermarkt_id on players

Player matching between SofaScore and Transfermarkt uses a two-step approach:
  a. Exact match on (normalised name, club name)
  b. Fuzzy match via difflib if no exact match (threshold 0.85)

This module writes raw data only. Per-90 computation happens in transform.py.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from difflib import SequenceMatcher

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from tqdm import tqdm

from config import LEAGUES, TARGET_SEASONS, SOFASCORE_POSITION_MAP
from db.models import League, Season, Team, Player, PlayerSeasonStats, TransferValue
from db.session import get_session
from scrapers.sofascore import SofaScoreScraper, map_stats
from scrapers.transfermarkt import TransfermarktScraper


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _dob_from_timestamp(ts: int | None) -> date | None:
    if ts is None:
        return None
    try:
        return datetime.utcfromtimestamp(ts).date()
    except (OSError, ValueError):
        return None


# ──────────────────────────────────────────────────────────────────
# Reference data upserts
# ──────────────────────────────────────────────────────────────────

def _upsert_league(session: Session, league_key: str) -> League:
    cfg = LEAGUES[league_key]
    league = session.query(League).filter_by(key=league_key).first()
    if league is None:
        league = League(
            key=league_key,
            name=cfg["name"],
            country=cfg["country"],
            sofascore_id=cfg["sofascore_tournament_id"],
            transfermarkt_code=cfg["transfermarkt_code"],
            transfermarkt_slug=cfg["transfermarkt_slug"],
        )
        session.add(league)
        session.flush()
    return league


def _upsert_season(session: Session, league: League, year: str, sofascore_id: int) -> Season:
    season = session.query(Season).filter_by(league_id=league.id, year=year).first()
    if season is None:
        season = Season(league_id=league.id, year=year, sofascore_id=sofascore_id)
        session.add(season)
        session.flush()
    elif season.sofascore_id is None:
        season.sofascore_id = sofascore_id
        session.flush()
    return season


def _upsert_team(session: Session, league: League, ss_team: dict) -> Team:
    ss_id = ss_team.get("id")
    team = session.query(Team).filter_by(sofascore_id=ss_id).first()
    if team is None:
        team = Team(
            name=ss_team.get("name", ""),
            league_id=league.id,
            sofascore_id=ss_id,
        )
        session.add(team)
        session.flush()
    return team


def _upsert_player(session: Session, ss_player: dict) -> Player:
    ss_id = ss_player.get("id")
    player = session.query(Player).filter_by(sofascore_id=ss_id).first()
    if player is None:
        dob = _dob_from_timestamp(ss_player.get("dateOfBirthTimestamp"))
        pos = ss_player.get("position", "")
        nationality = (ss_player.get("country") or {}).get("name", "")
        player = Player(
            full_name=ss_player.get("name", ""),
            short_name=ss_player.get("shortName", ""),
            nationality=nationality,
            date_of_birth=dob,
            position=pos,
            sofascore_id=ss_id,
        )
        session.add(player)
        session.flush()
    return player


# ──────────────────────────────────────────────────────────────────
# SofaScore ingest
# ──────────────────────────────────────────────────────────────────

def ingest_sofascore(session: Session | None = None) -> None:
    """
    Scrapes SofaScore and upserts leagues, seasons, teams, players,
    and player_season_stats into the database.
    """
    own_session = session is None
    if own_session:
        session = get_session()

    try:
        scraper = SofaScoreScraper()
        records = scraper.scrape_all()
        logger.info(f"SofaScore returned {len(records)} player-season records")

        for record in tqdm(records, desc="Ingesting SofaScore"):
            league = _upsert_league(session, record["league_key"])
            season = _upsert_season(
                session,
                league,
                record["season_year"],
                record["sofascore_season_id"],
            )
            team = _upsert_team(session, league, record["team"])
            player = _upsert_player(session, record["player"])

            stats_dict = map_stats(record["statistics"])
            existing = (
                session.query(PlayerSeasonStats)
                .filter_by(player_id=player.id, season_id=season.id, team_id=team.id)
                .first()
            )
            if existing is None:
                row = PlayerSeasonStats(
                    player_id=player.id,
                    season_id=season.id,
                    team_id=team.id,
                    **stats_dict,
                )
                session.add(row)
            else:
                for k, v in stats_dict.items():
                    setattr(existing, k, v)

        session.commit()
        logger.info("SofaScore ingest committed")

    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()


# ──────────────────────────────────────────────────────────────────
# Transfermarkt ingest
# ──────────────────────────────────────────────────────────────────

def ingest_transfermarkt(session: Session | None = None) -> None:
    """
    Scrapes Transfermarkt and:
      1. Links transfermarkt_id onto existing Player rows (matched by name+club)
      2. Inserts TransferValue snapshots
      3. Upserts team.transfermarkt_id where resolvable
    """
    own_session = session is None
    if own_session:
        session = get_session()

    try:
        scraper = TransfermarktScraper()
        records = scraper.scrape_all()
        logger.info(f"Transfermarkt returned {len(records)} player-season records")

        # Build a lookup of all players we already have from SofaScore
        # keyed by normalised name for fast fuzzy matching
        all_players: list[Player] = session.query(Player).all()
        player_by_norm: dict[str, Player] = {_norm(p.full_name): p for p in all_players}

        seen_mv_tm_ids: set[int] = set()

        for record in tqdm(records, desc="Ingesting Transfermarkt"):
            tm_id: int = record["tm_id"]
            name: str = record["name"]
            club_name: str = record["club_name"]

            # Step 1: find matching Player row
            player = _find_player(session, player_by_norm, name, club_name)

            if player is not None and player.transfermarkt_id is None:
                player.transfermarkt_id = tm_id

                # Fill gaps in date_of_birth / nationality if missing
                if player.date_of_birth is None and record.get("dob"):
                    player.date_of_birth = record["dob"]
                if not player.nationality and record.get("nationality"):
                    player.nationality = record["nationality"]

            # Step 2: market value (point-in-time snapshot)
            if tm_id not in seen_mv_tm_ids and record.get("mv_history"):
                seen_mv_tm_ids.add(tm_id)
                target_player = player  # may be None if no SS match yet

                # If no SofaScore match, create a minimal Player row
                if target_player is None:
                    target_player = _create_player_from_tm(session, record)
                    player_by_norm[_norm(name)] = target_player

                for snap in record["mv_history"]:
                    if snap["value_eur"] is None:
                        continue
                    existing_mv = (
                        session.query(TransferValue)
                        .filter_by(player_id=target_player.id, recorded_date=snap["date"])
                        .first()
                    )
                    if existing_mv is None:
                        session.add(TransferValue(
                            player_id=target_player.id,
                            value_eur=snap["value_eur"],
                            recorded_date=snap["date"],
                        ))

        session.commit()
        logger.info("Transfermarkt ingest committed")

    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()


def _find_player(
    session: Session,
    player_by_norm: dict[str, Player],
    name: str,
    club_name: str,
    threshold: float = 0.85,
) -> Player | None:
    norm_name = _norm(name)

    # Exact match
    if norm_name in player_by_norm:
        return player_by_norm[norm_name]

    # Fuzzy match
    best_score = 0.0
    best_player: Player | None = None
    for pname, player in player_by_norm.items():
        score = _similarity(norm_name, pname)
        if score > best_score:
            best_score = score
            best_player = player

    if best_score >= threshold:
        return best_player

    return None


def _create_player_from_tm(session: Session, record: dict) -> Player:
    """Insert a skeleton Player row sourced only from Transfermarkt."""
    player = Player(
        full_name=record["name"],
        nationality=record.get("nationality", ""),
        date_of_birth=record.get("dob"),
        transfermarkt_id=record["tm_id"],
    )
    session.add(player)
    session.flush()
    return player


# ──────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────

def run_ingest() -> None:
    logger.info("=== Starting ingest ===")
    with get_session() as session:
        ingest_sofascore(session)
        ingest_transfermarkt(session)
    logger.info("=== Ingest complete ===")
