-- Soccer IDSS Initial Schema
-- Run once against a fresh database:
--   psql soccer_idss < migrations/001_initial_schema.sql

-- ─────────────────────────────────────────────────────────────
-- Reference tables
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS leagues (
    id                    SERIAL PRIMARY KEY,
    key                   VARCHAR(50)  UNIQUE NOT NULL,   -- e.g. "premier_league"
    name                  VARCHAR(100) NOT NULL,
    country               VARCHAR(100),
    sofascore_id          INTEGER      UNIQUE,
    transfermarkt_code    VARCHAR(20),                    -- e.g. "GB1"
    transfermarkt_slug    VARCHAR(100)                    -- e.g. "premier-league"
);

CREATE TABLE IF NOT EXISTS seasons (
    id              SERIAL PRIMARY KEY,
    league_id       INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    year            VARCHAR(10) NOT NULL,    -- e.g. "23/24"
    sofascore_id    INTEGER UNIQUE,
    UNIQUE (league_id, year)
);

CREATE TABLE IF NOT EXISTS teams (
    id                   SERIAL PRIMARY KEY,
    name                 VARCHAR(200) NOT NULL,
    league_id            INTEGER REFERENCES leagues(id),
    sofascore_id         INTEGER UNIQUE,
    transfermarkt_id     INTEGER UNIQUE
);

-- ─────────────────────────────────────────────────────────────
-- Player identity
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS players (
    id                  SERIAL PRIMARY KEY,
    full_name           VARCHAR(200) NOT NULL,
    short_name          VARCHAR(100),
    nationality         VARCHAR(100),
    date_of_birth       DATE,
    position            VARCHAR(10),         -- SofaScore position code: G/D/M/F
    sofascore_id        INTEGER UNIQUE,
    transfermarkt_id    INTEGER UNIQUE,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- Market values (snapshot per scrape date)
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS transfer_values (
    id              SERIAL PRIMARY KEY,
    player_id       INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    value_eur       BIGINT,
    recorded_date   DATE,
    source          VARCHAR(50) DEFAULT 'transfermarkt'
);

CREATE INDEX IF NOT EXISTS idx_transfer_values_player ON transfer_values(player_id);

-- ─────────────────────────────────────────────────────────────
-- Raw season statistics (one row per player × season × team)
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS player_season_stats (
    id                      SERIAL PRIMARY KEY,
    player_id               INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    season_id               INTEGER NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    team_id                 INTEGER REFERENCES teams(id),

    -- Playing time
    appearances             INTEGER DEFAULT 0,
    minutes_played          INTEGER DEFAULT 0,

    -- Attacking
    goals                   INTEGER DEFAULT 0,
    assists                 INTEGER DEFAULT 0,
    shots_total             INTEGER DEFAULT 0,
    shots_on_target         INTEGER DEFAULT 0,
    expected_goals          NUMERIC(8,3),
    expected_assists        NUMERIC(8,3),
    key_passes              INTEGER DEFAULT 0,

    -- Passing
    passes_total            INTEGER DEFAULT 0,
    passes_accurate         INTEGER DEFAULT 0,
    long_balls_total        INTEGER DEFAULT 0,
    long_balls_accurate     INTEGER DEFAULT 0,
    crosses_total           INTEGER DEFAULT 0,
    crosses_accurate        INTEGER DEFAULT 0,

    -- Dribbling
    dribbles_attempted      INTEGER DEFAULT 0,
    dribbles_successful     INTEGER DEFAULT 0,

    -- Defending
    tackles_total           INTEGER DEFAULT 0,
    tackles_won             INTEGER DEFAULT 0,
    interceptions           INTEGER DEFAULT 0,
    clearances              INTEGER DEFAULT 0,
    blocks                  INTEGER DEFAULT 0,

    -- Duels
    ground_duels_total      INTEGER DEFAULT 0,
    ground_duels_won        INTEGER DEFAULT 0,
    aerial_duels_total      INTEGER DEFAULT 0,
    aerial_duels_won        INTEGER DEFAULT 0,

    -- Goalkeeping (NULL for outfield players)
    saves                   INTEGER,
    goals_conceded          INTEGER,
    clean_sheets            INTEGER,

    -- Discipline
    yellow_cards            INTEGER DEFAULT 0,
    red_cards               INTEGER DEFAULT 0,

    -- SofaScore rating (0–10)
    avg_rating              NUMERIC(4,2),

    scraped_at              TIMESTAMP DEFAULT NOW(),

    UNIQUE (player_id, season_id, team_id)
);

CREATE INDEX IF NOT EXISTS idx_pss_player ON player_season_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_pss_season ON player_season_stats(season_id);

-- ─────────────────────────────────────────────────────────────
-- Derived per-90 features (rebuilt by pipeline/transform.py)
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS player_features (
    id                      SERIAL PRIMARY KEY,
    player_id               INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE UNIQUE,
    season_id               INTEGER REFERENCES seasons(id),
    position_group          VARCHAR(5),      -- GK / DEF / MID / FWD

    -- Playing time & metadata (used for filtering, not in vector)
    minutes_played          INTEGER,
    age                     INTEGER,
    market_value_eur        BIGINT,
    league_name             VARCHAR(100),
    club_name               VARCHAR(100),

    -- Per-90 raw stats
    goals_p90               NUMERIC(6,3),
    assists_p90             NUMERIC(6,3),
    xg_p90                  NUMERIC(6,3),
    xa_p90                  NUMERIC(6,3),
    shots_on_target_p90     NUMERIC(6,3),
    key_passes_p90          NUMERIC(6,3),
    passes_p90              NUMERIC(6,3),
    pass_completion_pct     NUMERIC(5,2),
    dribbles_successful_p90 NUMERIC(6,3),
    tackles_won_p90         NUMERIC(6,3),
    interceptions_p90       NUMERIC(6,3),
    clearances_p90          NUMERIC(6,3),
    blocks_p90              NUMERIC(6,3),
    aerial_duels_won_pct    NUMERIC(5,2),
    saves_p90               NUMERIC(6,3),
    save_pct                NUMERIC(5,2),
    avg_rating              NUMERIC(4,2),

    -- MinMax-scaled vector (serialized as JSON array, ordered per POSITION_FEATURES)
    feature_vector          JSONB,

    built_at                TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_player_features_pos ON player_features(position_group);

-- ─────────────────────────────────────────────────────────────
-- Recommendation logs (for monitoring / outcome tracking)
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS recommendation_logs (
    id                  SERIAL PRIMARY KEY,
    session_id          UUID DEFAULT gen_random_uuid(),
    queried_at          TIMESTAMP DEFAULT NOW(),
    position_filter     VARCHAR(10),
    budget_eur          BIGINT,
    min_age             INTEGER,
    max_age             INTEGER,
    min_minutes         INTEGER,
    league_filter       VARCHAR(100),
    ideal_vector        JSONB,
    weights             JSONB,
    result_player_ids   INTEGER[],
    result_scores       NUMERIC(6,3)[]
);
