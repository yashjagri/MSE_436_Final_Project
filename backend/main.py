"""FastAPI backend for the transfer recruitment IDSS.

Serves the KNN recommender over the Supabase ``players`` table.
Run from the repo root with:  uvicorn backend.main:app --reload
"""

import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import create_client

sys.path.insert(0, str(Path(__file__).parent.parent))
from model.knn import (InsufficientPlayersError, MIN_MINUTES,  # noqa: E402
                       filter_players, recommend)
from backend.enrich import enrich  # noqa: E402

load_dotenv()

app = FastAPI(title="Transfer IDSS API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_players_cache = None


class RecommendRequest(BaseModel):
    """Request body for POST /recommend."""

    position: str
    max_budget_eur: float = Field(gt=0)
    min_age: int = Field(ge=15, le=50)
    max_age: int = Field(ge=15, le=50)
    min_minutes: int = Field(default=MIN_MINUTES, ge=0, le=4000)
    leagues: Optional[List[str]] = Field(
        default=None,
        description="Restrict the pool to these leagues; null/empty = all.")
    weights: Dict[str, float] = Field(
        default_factory=dict,
        description="Feature name -> weight between 0 and 3.")


def get_supabase_client():
    """Create a Supabase client from SUPABASE_URL / SUPABASE_KEY env vars."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise HTTPException(
            status_code=503,
            detail="SUPABASE_URL and SUPABASE_KEY must be set in .env.")
    return create_client(url, key)


def load_players(force_refresh=False):
    """Load the players table into a cached DataFrame.

    The table only changes when the pipeline runs, so one load per process
    is enough; pass force_refresh=True to re-read after a pipeline run.
    """
    global _players_cache
    if _players_cache is not None and not force_refresh:
        return _players_cache

    client = get_supabase_client()
    rows, page_size, start = [], 1000, 0
    while True:
        result = (client.table("players").select("*")
                  .range(start, start + page_size - 1).execute())
        rows.extend(result.data)
        if len(result.data) < page_size:
            break
        start += page_size
    _players_cache = pd.DataFrame(rows)
    return _players_cache


@app.get("/health")
def health():
    """Return API status and the number of players in the database."""
    try:
        df = load_players()
        return {"status": "ok", "player_count": len(df)}
    except HTTPException:
        raise
    except Exception as exc:
        return {"status": "error", "detail": str(exc), "player_count": 0}


@app.get("/players")
def list_players(position: Optional[str] = None,
                 max_budget_eur: Optional[float] = None):
    """Return the raw player list, optionally filtered for browsing."""
    df = load_players()
    if df.empty:
        return []
    if position is not None:
        df = df[df["position"] == position]
    if max_budget_eur is not None:
        df = df[df["market_value_eur"].notna()
                & (df["market_value_eur"] <= max_budget_eur)]
    return df.astype(object).where(pd.notnull(df), None).to_dict("records")


@app.post("/recommend")
def recommend_players(request: RecommendRequest):
    """Return the top 15 recommended players for the given brief.

    A thin, validated wrapper over model.knn.recommend; too-few-players
    conditions come back as a readable 422 message instead of a 500.
    """
    if request.min_age > request.max_age:
        raise HTTPException(status_code=422,
                            detail="min_age cannot be greater than max_age.")
    for feature, weight in request.weights.items():
        if not 0 <= weight <= 3:
            raise HTTPException(
                status_code=422,
                detail=f"Weight for '{feature}' must be between 0 and 3.")

    df = load_players()
    if df.empty:
        raise HTTPException(
            status_code=422,
            detail="The players table is empty — run the data pipeline first.")

    started = time.perf_counter()
    try:
        results = recommend(df, request.position, request.max_budget_eur,
                            request.min_age, request.max_age, request.weights,
                            request.min_minutes, request.leagues)
    except InsufficientPlayersError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    response_ms = (time.perf_counter() - started) * 1000

    # Attach descriptive detail (photo, club, national team, physical profile)
    # from the API-Football cache for the shortlist drill-down. Best-effort:
    # never let an enrichment failure break the recommendation response.
    try:
        for result in results:
            result["details"] = enrich(result["name"], result.get("age"))
    except Exception as exc:  # noqa: BLE001 - enrichment is non-essential
        print(f"enrichment skipped: {exc}")

    log_search(request, results, response_ms, df)
    return {"results": results, "response_ms": round(response_ms, 1)}


def log_search(request, results, response_ms, players_df):
    """Record a search in recommendation_logs for the monitoring dashboard.

    Best-effort: a logging failure must never break the recommendation
    response, so errors are printed and swallowed.
    """
    try:
        pool = filter_players(players_df, request.position,
                              request.max_budget_eur, request.min_age,
                              request.max_age, request.min_minutes,
                              request.leagues)
        get_supabase_client().table("recommendation_logs").insert({
            "position": request.position,
            "max_budget_eur": request.max_budget_eur,
            "min_age": request.min_age,
            "max_age": request.max_age,
            "min_minutes": request.min_minutes,
            "leagues": request.leagues,
            "weights": request.weights,
            "result_names": [
                {"name": r["name"], "league": r["league"],
                 "fit_score": r["fit_score"]} for r in results],
            "fit_scores": [r["fit_score"] for r in results],
            "response_ms": round(response_ms, 1),
            "candidate_pool_size": len(pool),
        }).execute()
    except Exception as exc:  # pragma: no cover - non-critical path
        print(f"recommendation_logs insert failed: {exc}")


@app.get("/monitoring")
def monitoring():
    """Aggregate system-health, fairness, and coverage metrics.

    Backs the monitoring dashboard: query response times (5s target), fit
    score distribution, average fit and appearance share per league vs that
    league's share of the eligible pool, coverage rate, and data freshness.
    """
    df = load_players()
    if df.empty:
        raise HTTPException(status_code=422,
                            detail="The players table is empty.")

    eligible = df[df["market_value_eur"].notna()
                  & (df["minutes_played"].fillna(0) >= MIN_MINUTES)]
    league_pool = eligible["league"].value_counts().to_dict()

    logs = (get_supabase_client().table("recommendation_logs")
            .select("created_at, fit_scores, result_names, response_ms")
            .order("created_at", desc=True).limit(500).execute().data)

    response_times = [l["response_ms"] for l in logs if l.get("response_ms")]
    all_scores, league_hits, recommended = [], {}, set()
    for log in logs:
        all_scores.extend(log.get("fit_scores") or [])
        for r in (log.get("result_names") or []):
            recommended.add(r["name"])
            entry = league_hits.setdefault(r["league"],
                                           {"appearances": 0, "score_sum": 0})
            entry["appearances"] += 1
            entry["score_sum"] += r["fit_score"]

    histogram = [0] * 10
    for score in all_scores:
        histogram[min(int(score) // 10, 9)] += 1

    total_hits = sum(e["appearances"] for e in league_hits.values()) or 1
    total_pool = sum(league_pool.values()) or 1
    fairness = [
        {
            "league": league,
            "eligible_players": pool_n,
            "pool_share_pct": round(pool_n / total_pool * 100, 1),
            "appearance_share_pct": round(
                league_hits.get(league, {}).get("appearances", 0)
                / total_hits * 100, 1),
            "avg_fit_score": round(
                league_hits[league]["score_sum"]
                / league_hits[league]["appearances"], 1)
            if league in league_hits else None,
        }
        for league, pool_n in sorted(league_pool.items(),
                                     key=lambda kv: -kv[1])
    ]

    return {
        "system_health": {
            "searches_logged": len(logs),
            "avg_response_ms": round(float(np.mean(response_times)), 1)
            if response_times else None,
            "p95_response_ms": round(float(np.percentile(response_times, 95)), 1)
            if response_times else None,
            "response_target_ms": 5000,
            "last_search_at": logs[0]["created_at"] if logs else None,
        },
        "data_freshness": {
            "players_total": len(df),
            "players_with_market_value": int(df["market_value_eur"].notna().sum()),
            "eligible_pool": len(eligible),
            "last_pipeline_run": str(df["updated_at"].max())
            if "updated_at" in df.columns else None,
            "players_by_position": df["position"].value_counts().to_dict(),
        },
        "fit_score_distribution": {
            "buckets": [f"{i * 10}-{i * 10 + 9}" for i in range(10)],
            "counts": histogram,
        },
        "fairness_by_league": fairness,
        "coverage": {
            "distinct_players_recommended": len(recommended),
            "eligible_pool": len(eligible),
            "coverage_rate_pct": round(len(recommended) / max(len(eligible), 1)
                                       * 100, 1),
        },
    }
