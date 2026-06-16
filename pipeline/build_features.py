"""
Feature builder: player_features DB rows → data/processed/player_features.parquet

Steps:
  1. Read all player_features rows joined with player identity.
  2. For each position group, MinMax-scale the feature columns defined in
     config.POSITION_FEATURES and store the scaler to disk (as JSON min/max).
  3. Write the scaled feature_vector back to the DB (JSONB column).
  4. Export the full enriched DataFrame to Parquet.

The parquet file is the read-only input for the KNN query at runtime.
It is rebuilt from scratch on every pipeline run.

Scaler persisted at: data/processed/scalers.json
  {
    "FWD": { "goals_p90": {"min": 0.0, "max": 1.23}, ... },
    "MID": { ... },
    ...
  }
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy import text

from config import POSITION_FEATURES, PROCESSED_DIR
from db.models import Player, PlayerFeatures
from db.session import get_session

PARQUET_PATH = PROCESSED_DIR / "player_features.parquet"
SCALER_PATH = PROCESSED_DIR / "scalers.json"

# All per-90 / percentage stat columns present in player_features table
ALL_STAT_COLS = [
    "goals_p90", "assists_p90", "xg_p90", "xa_p90",
    "shots_on_target_p90", "key_passes_p90", "passes_p90",
    "pass_completion_pct", "dribbles_successful_p90",
    "tackles_won_p90", "interceptions_p90", "clearances_p90",
    "blocks_p90", "aerial_duels_won_pct",
    "saves_p90", "save_pct", "avg_rating",
]


# ──────────────────────────────────────────────────────────────────
# Load from DB
# ──────────────────────────────────────────────────────────────────

def _load_dataframe(session: Session) -> pd.DataFrame:
    """
    Returns a DataFrame with one row per player, joining player identity
    and feature columns.
    """
    query = text("""
        SELECT
            p.id                AS player_id,
            p.full_name,
            p.short_name,
            p.nationality,
            p.date_of_birth,
            p.position          AS sofascore_position,
            p.sofascore_id,
            p.transfermarkt_id,
            pf.position_group,
            pf.season_id,
            pf.minutes_played,
            pf.age,
            pf.market_value_eur,
            pf.league_name,
            pf.club_name,
            pf.goals_p90,
            pf.assists_p90,
            pf.xg_p90,
            pf.xa_p90,
            pf.shots_on_target_p90,
            pf.key_passes_p90,
            pf.passes_p90,
            pf.pass_completion_pct,
            pf.dribbles_successful_p90,
            pf.tackles_won_p90,
            pf.interceptions_p90,
            pf.clearances_p90,
            pf.blocks_p90,
            pf.aerial_duels_won_pct,
            pf.saves_p90,
            pf.save_pct,
            pf.avg_rating
        FROM players p
        JOIN player_features pf ON pf.player_id = p.id
        WHERE pf.position_group IS NOT NULL
    """)
    rows = session.execute(query).mappings().all()
    return pd.DataFrame([dict(r) for r in rows])


# ──────────────────────────────────────────────────────────────────
# Scaler (MinMax per position group per feature)
# ──────────────────────────────────────────────────────────────────

def _fit_scalers(df: pd.DataFrame) -> dict:
    """
    Returns nested dict:
      { position_group: { feature_name: {"min": float, "max": float} } }
    """
    scalers: dict = {}
    for pos_group, features in POSITION_FEATURES.items():
        subset = df[df["position_group"] == pos_group]
        scalers[pos_group] = {}
        for feat in features:
            if feat not in subset.columns:
                scalers[pos_group][feat] = {"min": 0.0, "max": 1.0}
                continue
            col = subset[feat].dropna()
            col_min = float(col.min()) if len(col) > 0 else 0.0
            col_max = float(col.max()) if len(col) > 0 else 1.0
            # Avoid zero-range edge case
            if col_max == col_min:
                col_max = col_min + 1.0
            scalers[pos_group][feat] = {"min": col_min, "max": col_max}
    return scalers


def _apply_scaler(row: pd.Series, scalers: dict) -> list[float]:
    """
    Scales a single player row's features to [0, 1] using the fitted scaler.
    Returns the vector in the order defined by POSITION_FEATURES.
    Missing values are filled with 0.0.
    """
    pos_group = row["position_group"]
    features = POSITION_FEATURES.get(pos_group, [])
    pos_scalers = scalers.get(pos_group, {})
    vector: list[float] = []
    for feat in features:
        val = row.get(feat)
        s = pos_scalers.get(feat, {"min": 0.0, "max": 1.0})
        if pd.isna(val) or val is None:
            scaled = 0.0
        else:
            scaled = (float(val) - s["min"]) / (s["max"] - s["min"])
            scaled = float(np.clip(scaled, 0.0, 1.0))
        vector.append(round(scaled, 6))
    return vector


# ──────────────────────────────────────────────────────────────────
# Write feature_vector back to DB
# ──────────────────────────────────────────────────────────────────

def _write_vectors_to_db(df: pd.DataFrame, session: Session) -> None:
    logger.info("Writing scaled feature_vectors to player_features table")
    for _, row in df.iterrows():
        fv = row.get("feature_vector")
        if fv is None:
            continue
        session.execute(
            text(
                "UPDATE player_features SET feature_vector = :fv WHERE player_id = :pid"
            ),
            {"fv": json.dumps(fv), "pid": int(row["player_id"])},
        )
    session.commit()


# ──────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────

def run_build_features(session: Session | None = None) -> None:
    own_session = session is None
    if own_session:
        session = get_session()

    try:
        logger.info("Loading player features from DB")
        df = _load_dataframe(session)
        if df.empty:
            logger.warning("No player features found. Run 'transform' first.")
            return

        logger.info(f"Loaded {len(df)} players")

        # Fit MinMax scalers
        scalers = _fit_scalers(df)
        SCALER_PATH.write_text(json.dumps(scalers, indent=2))
        logger.info(f"Scalers saved → {SCALER_PATH}")

        # Apply scalers → feature_vector column
        df["feature_vector"] = df.apply(lambda row: _apply_scaler(row, scalers), axis=1)
        df["feature_names"] = df["position_group"].map(POSITION_FEATURES)

        # Write vectors back to DB for use by the recommendation engine
        _write_vectors_to_db(df, session)

        # Export to parquet
        export_cols = [
            "player_id", "full_name", "short_name", "nationality",
            "date_of_birth", "sofascore_position", "sofascore_id",
            "transfermarkt_id", "position_group", "season_id",
            "minutes_played", "age", "market_value_eur",
            "league_name", "club_name",
            *ALL_STAT_COLS,
            "feature_vector", "feature_names",
        ]
        # Only keep columns that exist in the dataframe
        export_cols = [c for c in export_cols if c in df.columns]
        df[export_cols].to_parquet(PARQUET_PATH, index=False)
        logger.info(f"Parquet exported → {PARQUET_PATH}  ({len(df)} rows)")

        # Print a quick summary
        for pos, group_df in df.groupby("position_group"):
            logger.info(
                f"  {pos}: {len(group_df)} players  "
                f"(avg market value €{group_df['market_value_eur'].mean(skipna=True):,.0f})"
            )

    except Exception:
        if own_session:
            session.rollback()
        raise
    finally:
        if own_session:
            session.close()
