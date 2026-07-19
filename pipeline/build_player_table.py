"""Build the unified ``players`` table from cached API-Football data.

Reads every cached ``/players`` response from ``pipeline/cache``, computes
per-90 and percentage metrics, joins the result against the teammate-scraped
``transfermarkt_players`` table in Supabase (read-only) on
``lower(name) + '_' + date_of_birth``, and upserts the merged rows into the
``players`` table keyed on ``join_key`` so re-runs are idempotent.

API-Football rows with no Transfermarkt match are kept (market_value_eur is
null) and logged to ``unmatched_players.log`` for manual review.

Run with:  python pipeline/build_player_table.py
"""

import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

CACHE_DIR = Path(__file__).parent / "cache"
UNMATCHED_LOG = Path(__file__).parent.parent / "unmatched_players.log"
# Parquet exported by pipeline/build_features.py (teammate's Transfermarkt
# pipeline) — used as the market-value source when present locally.
TRANSFERMARKT_PARQUET = (Path(__file__).parent.parent
                         / "data" / "processed" / "player_features.parquet")
UPSERT_CHUNK_SIZE = 500

# Broad labels are all the /players endpoint returns for most players; the
# detailed labels are handled in case the API provides them.
POSITION_MAP = {
    "goalkeeper": "Goalkeeper",
    "defender": "Centre Back",
    "centre-back": "Centre Back",
    "center-back": "Centre Back",
    "left-back": "Fullback",
    "right-back": "Fullback",
    "wing-back": "Fullback",
    "midfielder": "Midfielder",
    "defensive midfield": "Midfielder",
    "central midfield": "Midfielder",
    "attacking midfield": "Midfielder",
    "winger": "Winger",
    "left winger": "Winger",
    "right winger": "Winger",
    "attacker": "Striker",
    "striker": "Striker",
    "centre-forward": "Striker",
    # Transfermarkt-style labels
    "second striker": "Striker",
    "left midfield": "Winger",
    "right midfield": "Winger",
    "midfield": "Midfielder",
    "attack": "Striker",
    "defence": "Centre Back",
    "defense": "Centre Back",
}


def map_position(raw):
    """Map an API-Football position label to one of the six IDSS positions.

    Broad API labels collapse to the closest position (Defender -> Centre
    Back, Attacker -> Striker); detailed labels map precisely. Returns None
    for unknown/missing labels.
    """
    if not raw:
        return None
    return POSITION_MAP.get(raw.strip().lower())


def per90(total, minutes):
    """Return a per-90 rate, guarding against zero/missing minutes."""
    if not total and total != 0:
        return None
    if not minutes:
        return None
    return round(total / (minutes / 90), 3)


def pct(numerator, denominator):
    """Return numerator/denominator as a percentage, guarding against 0/None."""
    if numerator is None or not denominator:
        return None
    return round(numerator / denominator * 100, 1)


def extract_player_row(entry, league_ids):
    """Flatten one API-Football ``/players`` response entry into a table row.

    Keeps only statistics blocks belonging to the five target league
    competitions (team queries also return cups and European games), sums
    countable stats across them (a player can have several blocks after a
    mid-season transfer), and computes the per-90 and percentage metrics
    defined by the project spec. Returns None when the entry has no usable
    league statistics.
    """
    player = entry.get("player", {})
    stats_blocks = [
        block for block in entry.get("statistics", [])
        if (block.get("league") or {}).get("id") in league_ids
    ]
    if not player or not stats_blocks:
        return None
    league_name = league_ids[stats_blocks[0]["league"]["id"]]

    def total(path):
        """Sum one dotted stat path (e.g. 'shots.total') across blocks."""
        values = []
        for block in stats_blocks:
            node = block
            for key in path.split("."):
                node = node.get(key) if isinstance(node, dict) else None
                if node is None:
                    break
            if isinstance(node, (int, float)):
                values.append(node)
        return sum(values) if values else None

    minutes = total("games.minutes")

    position = None
    for block in stats_blocks:
        position = map_position(block.get("games", {}).get("position"))
        if position:
            break

    goals = total("goals.total")
    shots = total("shots.total")
    shots_on = total("shots.on")
    passes = total("passes.total")
    key_passes = total("passes.key")
    dribbles_success = total("dribbles.success")
    interceptions = total("tackles.interceptions")
    tackles = total("tackles.total")
    # API-Football only exposes overall duels, not an aerial split, so
    # overall duel win rate stands in for aerial_duels_won_pct.
    duels_total = total("duels.total")
    duels_won = total("duels.won")
    saves = total("goals.saves")
    conceded = total("goals.conceded")

    # passes.accuracy is already a completion percentage in this API; average
    # it across blocks rather than dividing accurate by total.
    accuracies = [b.get("passes", {}).get("accuracy") for b in stats_blocks
                  if isinstance(b.get("passes", {}).get("accuracy"), (int, float))]
    pass_completion = round(sum(accuracies) / len(accuracies), 1) if accuracies else None

    is_goalkeeper = position == "Goalkeeper"
    # Shots on target faced by a keeper = saves + goals conceded.
    shots_faced = (saves or 0) + (conceded or 0) if is_goalkeeper else None

    full_name = " ".join(
        part for part in (player.get("firstname"), player.get("lastname"))
        if part) or player.get("name")

    return {
        "name": player.get("name"),
        "full_name": full_name,
        "date_of_birth": (player.get("birth") or {}).get("date"),
        "age": player.get("age"),
        "position": position,
        "league": league_name,
        "minutes_played": minutes,
        "goals_per90": per90(goals, minutes),
        "shots_per90": per90(shots, minutes),
        "shots_on_target_pct": pct(shots_on, shots),
        "passes_per90": per90(passes, minutes),
        "pass_completion_pct": pass_completion,
        "key_passes_per90": per90(key_passes, minutes),
        "successful_dribbles_per90": per90(dribbles_success, minutes),
        "interceptions_per90": per90(interceptions, minutes),
        "tackles_won_per90": per90(tackles, minutes),
        "aerial_duels_won_pct": pct(duels_won, duels_total),
        "saves": saves if is_goalkeeper else None,
        "save_pct": pct(saves, shots_faced) if is_goalkeeper else None,
        # The /players endpoint has no per-player clean sheet count, so this
        # stays null; the KNN model tolerates all-null feature columns.
        "clean_sheets_per90": None,
    }


def load_cached_players():
    """Load every cached API-Football team page into a DataFrame of rows.

    The fetcher caches one file per team per page
    (``players_team{id}_season{year}_page{n}.json``); a player traded within
    the five leagues appears in several files and is deduplicated later in
    join_sources.
    """
    from fetch_api_football import LEAGUES  # league id -> display name

    rows = []
    files = sorted(CACHE_DIR.glob("players_team*_page*.json"))
    if not files:
        sys.exit("No cached API responses found. "
                 "Run pipeline/fetch_api_football.py first.")

    for path in files:
        with open(path) as f:
            body = json.load(f)
        for entry in body.get("response", []):
            row = extract_player_row(entry, LEAGUES)
            if row and row["name"] and row["date_of_birth"]:
                rows.append(row)

    df = pd.DataFrame(rows)
    print(f"Loaded {len(df)} player rows from {len(files)} cached team pages.")
    return df


def build_join_key(df):
    """Add the project-standard join key: lower(name) + '_' + date_of_birth."""
    df["join_key"] = df["name"].str.lower().str.strip() + "_" + df["date_of_birth"]
    return df


def normalize_tokens(name):
    """Split a name into lowercase accent-stripped tokens for matching.

    Initials and one-letter tokens are dropped: API-Football renders names
    like "T. Harwood-Bellis" while Transfermarkt has "Taylor Harwood-Bellis",
    so only substantive tokens are comparable.
    """
    if not isinstance(name, str):
        return set()
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-zA-Z ]", " ", text.replace("-", " ")).lower()
    return {token for token in text.split() if len(token) > 2}


def get_supabase_client():
    """Create a Supabase client from SUPABASE_URL / SUPABASE_KEY env vars."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL and SUPABASE_KEY must be set in your .env file.")
    return create_client(url, key)


def fetch_transfermarkt(client):
    """Load the teammate-scraped Transfermarkt data (market values).

    Prefers the local parquet exported by his pipeline
    (data/processed/player_features.parquet) when it exists; otherwise reads
    the transfermarkt_players table from Supabase. Either way the result is
    normalised to columns: name, date_of_birth, market_value_eur.
    """
    if TRANSFERMARKT_PARQUET.exists():
        df = pd.read_parquet(TRANSFERMARKT_PARQUET)
        df = df.rename(columns={"full_name": "name", "club_name": "club"})
        df["date_of_birth"] = (pd.to_datetime(df["date_of_birth"])
                               .dt.strftime("%Y-%m-%d"))
        df["tm_position"] = None
        df = df[["name", "date_of_birth", "market_value_eur", "tm_position"]]
        print(f"Loaded {len(df)} rows from {TRANSFERMARKT_PARQUET}.")
        return df

    rows, page_size, start = [], 1000, 0
    while True:
        result = (client.table("transfermarkt_players")
                  .select("name, date_of_birth, club, market_value_eur, position")
                  .range(start, start + page_size - 1)
                  .execute())
        rows.extend(result.data)
        if len(result.data) < page_size:
            break
        start += page_size
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.rename(columns={"position": "tm_position"})
    print(f"Loaded {len(df)} rows from transfermarkt_players.")
    return df


def join_sources(api_df, tm_df):
    """Join API-Football rows with Transfermarkt market values.

    Exact name equality fails between the sources (API-Football abbreviates
    to "T. Harwood-Bellis" and adds middle names in its full form, while
    Transfermarkt has "Taylor Harwood-Bellis"), so rows are matched on
    **date of birth + name-token overlap**: candidates sharing the birth
    date are scored by how many substantive name tokens they share, and the
    best overlapping candidate wins. Unmatched API rows are kept with a null
    market value and written to unmatched_players.log for manual review.
    """
    api_df["join_key"] = (api_df["full_name"].str.lower().str.strip()
                          + "_" + api_df["date_of_birth"])

    if tm_df.empty:
        print("Warning: transfermarkt_players is empty; all market values null.")
        api_df["market_value_eur"] = None
        merged = api_df
    else:
        if "tm_position" not in tm_df.columns:
            tm_df["tm_position"] = None
        tm_df = tm_df.dropna(subset=["name", "date_of_birth"])

        by_dob = defaultdict(list)
        for _, tm_row in tm_df.iterrows():
            by_dob[tm_row["date_of_birth"]].append(
                (normalize_tokens(tm_row["name"]),
                 tm_row["market_value_eur"], tm_row["tm_position"]))

        values, positions = [], []
        for _, row in api_df.iterrows():
            candidates = by_dob.get(row["date_of_birth"], [])
            tokens = (normalize_tokens(row["full_name"])
                      | normalize_tokens(row["name"]))
            best, best_overlap = None, 0
            for cand_tokens, value, tm_pos in candidates:
                overlap = len(tokens & cand_tokens)
                if overlap > best_overlap:
                    best, best_overlap = (value, tm_pos), overlap
            values.append(best[0] if best else None)
            positions.append(best[1] if best else None)

        merged = api_df.copy()
        merged["market_value_eur"] = values
        # Transfermarkt's detailed roles (e.g. "Right Winger", "Left-Back")
        # beat the API's broad labels, which can't tell fullbacks from
        # centre backs or wingers from strikers.
        refined = pd.Series(positions, index=merged.index).map(
            map_position, na_action="ignore")
        merged["position"] = refined.fillna(merged["position"])

    unmatched = merged[merged["market_value_eur"].isna()]
    with open(UNMATCHED_LOG, "w") as f:
        f.write("# API-Football players with no transfermarkt_players match\n")
        for _, row in unmatched.iterrows():
            f.write(f"{row['join_key']}\t{row['league']}\n")
    print(f"Join complete: {len(merged) - len(unmatched)} matched, "
          f"{len(unmatched)} unmatched (see {UNMATCHED_LOG.name}).")

    # A player transferred between two of the five leagues appears twice;
    # keep the row with the most minutes so join_key is unique for upsert.
    merged = (merged.sort_values("minutes_played", ascending=False)
              .drop_duplicates("join_key"))
    return merged.drop(columns=["full_name"])


INTEGER_COLUMNS = ("minutes_played", "age", "saves", "market_value_eur")


def upsert_players(client, df):
    """Upsert the merged rows into the players table, keyed on join_key."""
    records = df.astype(object).where(pd.notnull(df), None).to_dict("records")
    # pandas represents nullable ints as floats (3420.0); Postgres integer
    # columns reject that string form, so coerce them back.
    for record in records:
        for column in INTEGER_COLUMNS:
            if record.get(column) is not None:
                record[column] = int(record[column])
    for start in range(0, len(records), UPSERT_CHUNK_SIZE):
        chunk = records[start:start + UPSERT_CHUNK_SIZE]
        client.table("players").upsert(chunk, on_conflict="join_key").execute()
        print(f"  Upserted {min(start + UPSERT_CHUNK_SIZE, len(records))}"
              f"/{len(records)} rows.")


def main():
    """Run the full build: load cache, join sources, upsert to Supabase."""
    api_df = load_cached_players()
    client = get_supabase_client()
    tm_df = fetch_transfermarkt(client)
    merged = join_sources(api_df, tm_df)
    upsert_players(client, merged)
    print("Done. The players table is up to date.")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    main()
