"""Best-effort player enrichment for the recommendation detail view.

The Supabase ``players`` table stores only the modelling stats, not the
descriptive metadata a sporting director wants when inspecting a shortlisted
player (photo, current club, national team, physical profile). All of that
already sits in the API-Football responses cached under ``pipeline/cache/``,
so we build a one-time in-memory index from those files and attach it to each
recommendation at request time — no schema change and no pipeline re-run.

Everything here is best-effort: a missing or malformed cache simply yields an
empty index, and the API returns players with ``details: null``.
"""
import json
from functools import lru_cache
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "pipeline" / "cache"


def _minutes(block):
    return (block.get("games") or {}).get("minutes") or 0


def _detail_from_entry(entry):
    """Build one detail dict from a cached API-Football player entry."""
    player = entry.get("player") or {}
    name = player.get("name")
    if not name:
        return None

    blocks = entry.get("statistics") or []
    # A player can have several competition blocks (league, cups, friendlies).
    # The block with the most minutes is their primary club this season; sum
    # appearances and minutes across blocks for a season total.
    primary = max(blocks, key=_minutes) if blocks else {}
    team = primary.get("team") or {}
    games = primary.get("games") or {}
    birth = player.get("birth") or {}

    total_minutes = sum(_minutes(b) for b in blocks)
    total_apps = sum((b.get("games") or {}).get("appearences") or 0 for b in blocks)

    return {
        "name": name,
        "age": player.get("age"),
        "photo": player.get("photo"),
        "nationality": player.get("nationality"),
        "birth_place": birth.get("place"),
        "birth_country": birth.get("country"),
        "height": player.get("height"),
        "weight": player.get("weight"),
        "club": team.get("name"),
        "club_logo": team.get("logo"),
        "appearances": total_apps or None,
        "minutes": total_minutes or None,
        "rating": (round(float(games["rating"]), 2)
                   if games.get("rating") not in (None, "") else None),
    }


@lru_cache(maxsize=1)
def _index():
    """name (lowercased) -> list of detail dicts, built once and cached."""
    index = {}
    if not CACHE_DIR.is_dir():
        return index
    for path in sorted(CACHE_DIR.glob("players_team*_page*.json")):
        try:
            with open(path) as f:
                body = json.load(f)
        except (OSError, ValueError):
            continue
        for entry in body.get("response", []):
            detail = _detail_from_entry(entry)
            if detail:
                index.setdefault(detail["name"].lower(), []).append(detail)
    return index


def enrich(name, age=None):
    """Return descriptive details for a shortlisted player, or None.

    Matches on the API-Football short name; when several players share a name,
    ``age`` disambiguates (a shortlist of 15 rarely collides, but be safe).
    """
    candidates = _index().get((name or "").lower(), [])
    if not candidates:
        return None
    if age is not None and len(candidates) > 1:
        for candidate in candidates:
            if candidate.get("age") == age:
                return candidate
    return candidates[0]
