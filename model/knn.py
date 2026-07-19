"""Position-aware KNN recommender for the transfer IDSS.

Given a position, budget, age range, and per-feature weights, this module
filters the player pool, scales the position's relevant features, applies
the user's weights (after scaling, so weights express importance rather than
unit magnitude), builds an "ideal player" query vector, and returns the 15
nearest players with 0-100 fit scores and feature breakdowns.
"""

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

TOP_N = 15
MAX_WEIGHT = 3.0
# Below this many minutes, per-90 stats are small-sample noise (a sub off
# the bench with 2 goals in 40 minutes projects to 4.5 goals/90).
MIN_MINUTES = 450

POSITION_FEATURES = {
    "Goalkeeper": ["save_pct", "clean_sheets_per90", "saves",
                   "pass_completion_pct"],
    "Fullback": ["tackles_won_per90", "interceptions_per90",
                 "key_passes_per90", "passes_per90"],
    "Centre Back": ["aerial_duels_won_pct", "tackles_won_per90",
                    "interceptions_per90", "pass_completion_pct"],
    "Midfielder": ["passes_per90", "key_passes_per90", "interceptions_per90",
                   "successful_dribbles_per90"],
    "Winger": ["successful_dribbles_per90", "goals_per90", "key_passes_per90",
               "shots_per90"],
    "Striker": ["goals_per90", "shots_per90", "shots_on_target_pct",
                "aerial_duels_won_pct"],
}


class InsufficientPlayersError(Exception):
    """Raised when fewer than TOP_N players match the position/budget/age
    filters, so a meaningful top-15 shortlist cannot be produced."""


def filter_players(players_df, position, max_budget_eur, min_age, max_age):
    """Apply position, budget, and age filters before any model fitting.

    Players with a null market value stay in the database but are excluded
    here so the model only considers players known to be affordable.
    """
    if position not in POSITION_FEATURES:
        raise ValueError(f"Unknown position '{position}'. "
                         f"Valid: {', '.join(POSITION_FEATURES)}")
    df = players_df[
        (players_df["position"] == position)
        & players_df["market_value_eur"].notna()
        & (players_df["market_value_eur"] <= max_budget_eur)
        & (players_df["age"] >= min_age)
        & (players_df["age"] <= max_age)
        & (players_df["minutes_played"].fillna(0) >= MIN_MINUTES)
    ].copy()
    return df


def build_ideal_vector(scaled, weights_arr):
    """Build the scaled-space query vector for the "ideal player".

    Starts at the midpoint of each feature's distribution in the filtered
    dataset, then shifts toward that feature's maximum in proportion to how
    heavily the user weighted it (weight / MAX_WEIGHT).
    """
    col_min = scaled.min(axis=0)
    col_max = scaled.max(axis=0)
    midpoint = (col_min + col_max) / 2
    shift_fraction = np.clip(weights_arr / MAX_WEIGHT, 0, 1)
    return midpoint + shift_fraction * (col_max - midpoint)


def recommend(players_df, position, max_budget_eur, min_age, max_age, weights):
    """Return the TOP_N best-fitting affordable players for the given brief.

    Args:
        players_df: full players table as a DataFrame.
        position: one of the six POSITION_FEATURES keys.
        max_budget_eur: maximum market value in euros.
        min_age, max_age: inclusive age bounds.
        weights: dict mapping feature name -> float in [0, 3]; features not
            supplied default to weight 1.

    Returns:
        List of dicts with name, position, age, league, market_value_eur,
        fit_score, and a per-feature breakdown of player value vs the ideal
        vector value (in original units).

    Raises:
        InsufficientPlayersError: fewer than TOP_N players match the filters.
    """
    features = POSITION_FEATURES[position]
    df = filter_players(players_df, position, max_budget_eur, min_age, max_age)

    if len(df) < TOP_N:
        raise InsufficientPlayersError(
            f"Only {len(df)} {position}s match a budget of "
            f"€{max_budget_eur / 1e6:.1f}m and age {min_age}-{max_age}; "
            f"at least {TOP_N} are needed. Try raising the budget or "
            f"widening the age range.")

    # Missing stats are imputed with the column mean so they sit at the
    # neutral point after scaling instead of dragging distances around.
    feature_matrix = df[features].astype(float)
    feature_matrix = feature_matrix.fillna(feature_matrix.mean()).fillna(0.0)

    scaler = StandardScaler()
    scaled = scaler.fit_transform(feature_matrix.values)

    weights_arr = np.array([float(weights.get(f, 1.0)) for f in features])
    weighted = scaled * weights_arr

    ideal_scaled = build_ideal_vector(scaled, weights_arr)
    ideal_original = scaler.inverse_transform(ideal_scaled.reshape(1, -1))[0]
    ideal_weighted = ideal_scaled * weights_arr

    knn = NearestNeighbors(n_neighbors=TOP_N, metric="euclidean")
    knn.fit(weighted)
    distances, indices = knn.kneighbors(ideal_weighted.reshape(1, -1))

    results = []
    for distance, idx in zip(distances[0], indices[0]):
        row = df.iloc[idx]
        fit_score = max(0, round(100 - (distance * 25)))
        breakdown = [
            {
                "feature": feature,
                "player_value": round(float(feature_matrix.iloc[idx][feature]), 2),
                "ideal_value": round(float(ideal_original[j]), 2),
            }
            for j, feature in enumerate(features)
        ]
        results.append({
            "name": row["name"],
            "position": row["position"],
            "age": int(row["age"]) if pd.notna(row["age"]) else None,
            "league": row["league"],
            "market_value_eur": float(row["market_value_eur"]),
            "fit_score": fit_score,
            "breakdown": breakdown,
        })
    return results
