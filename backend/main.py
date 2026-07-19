"""FastAPI backend for the transfer recruitment IDSS.

Serves the KNN recommender over the Supabase ``players`` table.
Run from the repo root with:  uvicorn backend.main:app --reload
"""

import os
import sys
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import create_client

sys.path.insert(0, str(Path(__file__).parent.parent))
from model.knn import InsufficientPlayersError, recommend  # noqa: E402

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

    try:
        results = recommend(df, request.position, request.max_budget_eur,
                            request.min_age, request.max_age, request.weights)
    except InsufficientPlayersError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"results": results}
