"""Backtest the recommender against real 2025 summer transfers.

The worksheet's Impact Simulation / Test-data plan is to "use a historical
window of players signed in the past and check the model's fit score against
how they actually did." We can do exactly that: the Transfermarkt scrape
cached *both* the 2024/25 and 2025/26 squads, so a player whose club changed
between the two seasons — both clubs inside our five leagues — is a real
transfer we can replay.

For every such transfer, this script asks a precise, honest question:

    Using only the 2024/25 stats a director would have had in summer 2025,
    how strong a fit does our model consider the player who was actually
    signed — and would they have surfaced in a top-15 shortlist for their
    position and price?

It reports fit-score and percentile distributions plus top-15 recall, overall
and by position, and writes the summary to ``pipeline/cache/backtest.json``
for the /backtest API endpoint. No network calls — everything reads the
existing Transfermarkt HTML cache and the Supabase players table.

Run with:  python pipeline/backtest_transfers.py
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
from model.knn import (POSITION_FEATURES, TOP_N, MIN_MINUTES,  # noqa: E402
                       build_ideal_vector)
from sklearn.preprocessing import StandardScaler  # noqa: E402

from scrapers.transfermarkt import TransfermarktScraper  # noqa: E402
from scrape_transfermarkt_values import LEAGUES  # noqa: E402

OUTPUT_PATH = Path(__file__).parent / "cache" / "backtest.json"
PRIOR_SEASON = "24/25"
CURRENT_SEASON = "25/26"


def build_join_key(name, dob):
    """Return the players-table join key for a name and date of birth."""
    if not name or not dob:
        return None
    return f"{name.lower().strip()}_{dob.isoformat()}"


def squads_by_season(season):
    """Map join_key -> club name for every player in a season (cache-only).

    Reuses the teammate's scraper, which returns cached HTML, so this makes
    no network requests as long as the season was already scraped.
    """
    scraper = TransfermarktScraper()
    clubs_of = {}
    for league_key in LEAGUES:
        for club in scraper.get_clubs(league_key, season):
            for player in scraper.get_club_players(club, season):
                key = build_join_key(player["name"], player["dob"])
                if key:
                    clubs_of[key] = club["name"]
    return clubs_of


def find_transfers():
    """Return join_keys whose club changed between the two seasons.

    Both the old and new club must be inside our five leagues, so the
    transfer is one the tool could actually have been used to inform.
    """
    prior = squads_by_season(PRIOR_SEASON)
    current = squads_by_season(CURRENT_SEASON)
    transfers = {}
    for key, new_club in current.items():
        old_club = prior.get(key)
        if old_club and old_club != new_club:
            transfers[key] = {"from_club": old_club, "to_club": new_club}
    print(f"Detected {len(transfers)} in-league transfers "
          f"({PRIOR_SEASON} -> {CURRENT_SEASON}).")
    return transfers


def load_players():
    """Load the players table (2024/25 stats + market values) from Supabase."""
    load_dotenv()
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL and SUPABASE_KEY must be set in .env.")
    client = create_client(url, key)
    rows, start = [], 0
    while True:
        result = (client.table("players").select("*")
                  .range(start, start + 999).execute())
        rows.extend(result.data)
        if len(result.data) < 1000:
            break
        start += 1000
    return pd.DataFrame(rows)


# A realistic recruitment search weights a position's headline attributes
# heavily rather than looking for a perfectly balanced player. We replay each
# transfer under this "star search" (max weight on every position feature),
# which shifts the ideal toward the top of each stat's range — the scenario
# in which surfacing a real signing is a meaningful success.
ELITE_WEIGHT = 3.0


def score_pool(pool):
    """Fit-score a same-position pool under a realistic elite-weighted search.

    Mirrors model.knn.recommend: standardise the features, apply the weights,
    build the weight-shifted ideal, and convert weighted Euclidean distance to
    the 0-100 fit score. Because that score saturates near zero for all but the
    closest players, the player's **fit percentile** within the pool is the
    meaningful, scale-free signal. Returns the pool with both columns added.
    """
    position = pool["position"].iloc[0]
    features = POSITION_FEATURES[position]
    matrix = pool[features].astype(float)
    matrix = matrix.fillna(matrix.mean()).fillna(0.0)

    scaled = StandardScaler().fit_transform(matrix.values)
    weights = np.full(len(features), ELITE_WEIGHT)
    ideal = build_ideal_vector(scaled, weights)
    distances = np.linalg.norm(scaled * weights - ideal * weights, axis=1)

    pool = pool.copy()
    pool["fit_score"] = np.maximum(0, np.round(100 - distances * 25))
    # Rank on raw distance (not the saturated score) so percentiles are
    # well-separated even when many fit scores collapse to zero.
    pool["fit_percentile"] = pd.Series(-distances,
                                       index=pool.index).rank(pct=True)
    return pool


def backtest():
    """Replay every detected transfer and summarise the model's verdicts."""
    transfers = find_transfers()
    players = load_players()
    eligible = players[
        players["market_value_eur"].notna()
        & (players["minutes_played"].fillna(0) >= MIN_MINUTES)
    ].copy()

    # Score each position pool once; look every transfer up in it.
    scored = {
        pos: score_pool(group)
        for pos, group in eligible.groupby("position")
        if pos in POSITION_FEATURES and len(group) >= TOP_N
    }

    records = []
    for _, row in eligible.iterrows():
        key = row["join_key"]
        if key not in transfers:
            continue
        pool = scored.get(row["position"])
        if pool is None:
            continue
        me = pool[pool["join_key"] == key]
        if me.empty:
            continue
        me = me.iloc[0]

        # Would they make a top-15 shortlist for their position at a budget
        # set to their own market value (affordable-to-that-buyer pool)?
        # Rank on the distance-based percentile, which separates cleanly even
        # when fit scores collapse to zero.
        budget = row["market_value_eur"]
        affordable = pool[pool["market_value_eur"] <= budget]
        rank = int((affordable["fit_percentile"] > me["fit_percentile"]).sum()) + 1
        made_shortlist = rank <= TOP_N and len(affordable) >= TOP_N

        # Chance of a random top-15 including this player, given the pool it
        # was drawn from — the baseline that makes recall interpretable.
        random_recall = min(1.0, TOP_N / max(len(affordable), 1))

        records.append({
            "name": row["name"],
            "position": row["position"],
            "league": row["league"],
            "market_value_eur": float(row["market_value_eur"]),
            "from_club": transfers[key]["from_club"],
            "to_club": transfers[key]["to_club"],
            "fit_score": float(me["fit_score"]),
            "fit_percentile": round(float(me["fit_percentile"]), 3),
            "rank_in_budget": rank,
            "pool_in_budget": int(len(affordable)),
            "made_shortlist": bool(made_shortlist),
            "random_recall": random_recall,
        })

    return summarise(records, len(transfers))


def summarise(records, transfers_detected):
    """Aggregate per-transfer records into overall and by-position metrics."""
    if not records:
        return {"transfers_detected": transfers_detected, "evaluated": 0,
                "note": "No transfers matched players with 2024/25 stats."}

    df = pd.DataFrame(records)

    def block(frame):
        """Summary metrics for one group of evaluated transfers.

        Recall is reported against the random-shortlist baseline and as a
        lift multiple, so "18.8%" is legible as "better or worse than chance".
        """
        recall = float(frame["made_shortlist"].mean()) * 100
        baseline = float(frame["random_recall"].mean()) * 100
        return {
            "evaluated": int(len(frame)),
            "median_fit_percentile": round(
                float(frame["fit_percentile"].median()), 3),
            "top15_recall_pct": round(recall, 1),
            "random_recall_pct": round(baseline, 1),
            "recall_lift": round(recall / baseline, 2) if baseline else None,
        }

    by_position = {
        pos: block(group)
        for pos, group in df.groupby("position")
    }

    # The signings the model rated highest and lowest. Sort on percentile,
    # not the raw fit score (which saturates to zero for nearly everyone and
    # would make the two lists overlap).
    best = df.sort_values("fit_percentile", ascending=False).head(10)
    worst = df.sort_values("fit_percentile").head(10)
    columns = ["name", "position", "league", "from_club", "to_club",
               "market_value_eur", "fit_score", "fit_percentile",
               "rank_in_budget", "made_shortlist"]

    return {
        "transfers_detected": transfers_detected,
        "overall": block(df),
        "by_position": by_position,
        "best_fits": best[columns].to_dict("records"),
        "worst_fits": worst[columns].to_dict("records"),
        "prior_season": PRIOR_SEASON,
        "current_season": CURRENT_SEASON,
    }


def main():
    """Run the backtest and write its summary to cache/backtest.json."""
    summary = backtest()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nWrote {OUTPUT_PATH}")
    if summary.get("evaluated") == 0:
        print(summary.get("note", ""))
        return
    overall = summary["overall"]
    print(f"\nEvaluated {overall['evaluated']} real signings "
          f"(of {summary['transfers_detected']} detected transfers):")
    print(f"  Median fit percentile: {overall['median_fit_percentile']:.0%} "
          f"(50% = average player)")
    print(f"  Top-15 recall:         {overall['top15_recall_pct']}% "
          f"vs {overall['random_recall_pct']}% random "
          f"({overall['recall_lift']}x lift)")
    print("\nBy position:")
    for pos, stats in sorted(summary["by_position"].items(),
                             key=lambda kv: -kv[1]["evaluated"]):
        print(f"  {pos:<12} n={stats['evaluated']:<4} "
              f"recall={stats['top15_recall_pct']}% "
              f"vs {stats['random_recall_pct']}% random "
              f"({stats['recall_lift']}x)  "
              f"median pctile={stats['median_fit_percentile']:.0%}")


if __name__ == "__main__":
    main()
