"""Create the ``player_decisions`` table in Supabase.

Backs the recruitment decision log: as a sporting director works through
shortlists, they mark players as pursued, passed, or signed. Unlike
``recommendation_logs`` (which records every search), this table records the
director's *verdict* on individual players, giving the system memory of
decisions across sessions — the difference between a lookup tool and a
decision-support system.

Keyed on ``join_key`` so it lines up with the ``players`` table. Run once:
    python pipeline/create_decisions_table.py
"""

import os
import sys
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv

load_dotenv()

CREATE_TABLE_SQL = """
create table if not exists player_decisions (
  join_key text primary key,
  player_name text not null,
  position text,
  league text,
  market_value_eur bigint,
  status text not null default 'shortlisted',
  note text,
  fit_score numeric(6,2),
  updated_at timestamptz not null default now()
);
"""


def get_db_connection():
    """Open a direct Postgres connection to the Supabase project database."""
    supabase_url = os.environ.get("SUPABASE_URL", "")
    password = os.environ.get("SUPABASE_DB_PASSWORD")
    project_ref = urlparse(supabase_url).hostname.split(".")[0] \
        if supabase_url else None
    if not project_ref or not password:
        sys.exit("SUPABASE_URL and SUPABASE_DB_PASSWORD must be set in .env.")
    return psycopg2.connect(
        host=f"db.{project_ref}.supabase.co", port=5432,
        dbname="postgres", user="postgres", password=password,
        connect_timeout=10)


def main():
    """Create the player_decisions table if it does not already exist."""
    conn = get_db_connection()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
    conn.close()
    print("player_decisions table ready.")


if __name__ == "__main__":
    main()
