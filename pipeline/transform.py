"""
Transform pipeline: raw PlayerSeasonStats → per-90 stats → PlayerFeatures rows.

For each player we pick their most recent season's stats (the season with
the most minutes if they appear in multiple).  Then we compute per-90
values and store them in player_features alongside metadata needed for
filtering at query time.

The MinMax scaling happens in build_features.py (offline, after all rows
are computed) so the scaler sees the full population.
"""

from __future__ import annotations

from datetime import date

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session
from tqdm import tqdm

from config import SOFASCORE_POSITION_MAP, MIN_MINUTES
from db.models import Player, PlayerSeasonStats, PlayerFeatures, TransferValue
from db.session import get_session


# ──────────────────────────────────────────────────────────────────
# Per-90 helpers
# ──────────────────────────────────────────────────────────────────

def _p90(stat: int | float | None, minutes: int) -> float | None:
    if stat is None or minutes == 0:
        return None
    return round(float(stat) / minutes * 90, 4)


def _pct(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return round(float(numerator) / denominator * 100, 2)


def _age(dob: date | None) -> int | None:
    if dob is None:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# ──────────────────────────────────────────────────────────────────
# Core transform
# ──────────────────────────────────────────────────────────────────

def _compute_features(stats: PlayerSeasonStats, player: Player) -> dict:
    """
    Returns a dict of feature values to write into PlayerFeatures.
    Raw per-90 values (un-scaled).
    """
    mp = stats.minutes_played or 0
    pos_group = SOFASCORE_POSITION_MAP.get(player.position or "", "MID")

    # Goalkeeping
    saves_p90 = _p90(stats.saves, mp)
    save_pct = _pct(stats.saves, (stats.saves or 0) + (stats.goals_conceded or 0))

    return {
        "position_group": pos_group,
        "minutes_played": mp,
        "age": _age(player.date_of_birth),

        # Attacking
        "goals_p90": _p90(stats.goals, mp),
        "assists_p90": _p90(stats.assists, mp),
        "xg_p90": _p90(stats.expected_goals, mp),
        "xa_p90": _p90(stats.expected_assists, mp),
        "shots_on_target_p90": _p90(stats.shots_on_target, mp),
        "key_passes_p90": _p90(stats.key_passes, mp),

        # Passing
        "passes_p90": _p90(stats.passes_total, mp),
        "pass_completion_pct": _pct(stats.passes_accurate, stats.passes_total),

        # Dribbling
        "dribbles_successful_p90": _p90(stats.dribbles_successful, mp),

        # Defending
        "tackles_won_p90": _p90(stats.tackles_won, mp),
        "interceptions_p90": _p90(stats.interceptions, mp),
        "clearances_p90": _p90(stats.clearances, mp),
        "blocks_p90": _p90(stats.blocks, mp),

        # Duels
        "aerial_duels_won_pct": _pct(stats.aerial_duels_won, stats.aerial_duels_total),

        # Goalkeeping
        "saves_p90": saves_p90,
        "save_pct": save_pct,

        # Rating
        "avg_rating": float(stats.avg_rating) if stats.avg_rating else None,
    }


# ──────────────────────────────────────────────────────────────────
# Lookup helpers
# ──────────────────────────────────────────────────────────────────

def _latest_market_value(session: Session, player_id: int) -> int | None:
    row = (
        session.query(TransferValue)
        .filter_by(player_id=player_id)
        .order_by(TransferValue.recorded_date.desc())
        .first()
    )
    return row.value_eur if row else None


def _best_season_stats(session: Session, player_id: int) -> PlayerSeasonStats | None:
    """Return the stats row with the most minutes played for this player."""
    return (
        session.query(PlayerSeasonStats)
        .filter(
            PlayerSeasonStats.player_id == player_id,
            PlayerSeasonStats.minutes_played >= MIN_MINUTES,
        )
        .order_by(PlayerSeasonStats.minutes_played.desc())
        .first()
    )


# ──────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────

def run_transform(session: Session | None = None) -> None:
    """
    Reads every player from the DB, picks their best season stats row,
    computes per-90 features, and upserts into player_features.
    """
    own_session = session is None
    if own_session:
        session = get_session()

    try:
        players: list[Player] = session.query(Player).all()
        logger.info(f"Computing features for {len(players)} players")

        written = 0
        skipped = 0

        for player in tqdm(players, desc="Transforming"):
            stats = _best_season_stats(session, player.id)
            if stats is None:
                skipped += 1
                continue

            # Gather metadata from related rows
            mv = _latest_market_value(session, player.id)
            league_name = (stats.season.league.name if stats.season and stats.season.league else "")
            club_name = (stats.team.name if stats.team else "")

            feature_dict = _compute_features(stats, player)
            feature_dict.update({
                "season_id": stats.season_id,
                "market_value_eur": mv,
                "league_name": league_name,
                "club_name": club_name,
            })

            existing = session.query(PlayerFeatures).filter_by(player_id=player.id).first()
            if existing is None:
                row = PlayerFeatures(player_id=player.id, **feature_dict)
                session.add(row)
            else:
                for k, v in feature_dict.items():
                    setattr(existing, k, v)

            written += 1

        session.commit()
        logger.info(f"Transform done: {written} written, {skipped} skipped (< {MIN_MINUTES} min)")

    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()
