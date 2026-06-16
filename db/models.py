from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Float,
    ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class League(Base):
    __tablename__ = "leagues"

    id = Column(Integer, primary_key=True)
    key = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    country = Column(String(100))
    sofascore_id = Column(Integer, unique=True)
    transfermarkt_code = Column(String(20))
    transfermarkt_slug = Column(String(100))

    seasons = relationship("Season", back_populates="league", cascade="all, delete-orphan")
    teams = relationship("Team", back_populates="league")


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (UniqueConstraint("league_id", "year"),)

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False)
    year = Column(String(10), nullable=False)   # e.g. "23/24"
    sofascore_id = Column(Integer, unique=True)

    league = relationship("League", back_populates="seasons")
    stats = relationship("PlayerSeasonStats", back_populates="season")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    league_id = Column(Integer, ForeignKey("leagues.id"))
    sofascore_id = Column(Integer, unique=True)
    transfermarkt_id = Column(Integer, unique=True)

    league = relationship("League", back_populates="teams")
    stats = relationship("PlayerSeasonStats", back_populates="team")


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True)
    full_name = Column(String(200), nullable=False)
    short_name = Column(String(100))
    nationality = Column(String(100))
    date_of_birth = Column(Date)
    position = Column(String(10))           # SofaScore code: G/D/M/F
    sofascore_id = Column(Integer, unique=True)
    transfermarkt_id = Column(Integer, unique=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    stats = relationship("PlayerSeasonStats", back_populates="player", cascade="all, delete-orphan")
    transfer_values = relationship("TransferValue", back_populates="player", cascade="all, delete-orphan")
    features = relationship("PlayerFeatures", back_populates="player", uselist=False, cascade="all, delete-orphan")


class TransferValue(Base):
    __tablename__ = "transfer_values"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    value_eur = Column(BigInteger)
    recorded_date = Column(Date)
    source = Column(String(50), default="transfermarkt")

    player = relationship("Player", back_populates="transfer_values")

    __table_args__ = (
        Index("idx_transfer_values_player", "player_id"),
    )


class PlayerSeasonStats(Base):
    __tablename__ = "player_season_stats"
    __table_args__ = (
        UniqueConstraint("player_id", "season_id", "team_id"),
        Index("idx_pss_player", "player_id"),
        Index("idx_pss_season", "season_id"),
    )

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(Integer, ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"))

    # Playing time
    appearances = Column(Integer, default=0)
    minutes_played = Column(Integer, default=0)

    # Attacking
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    shots_total = Column(Integer, default=0)
    shots_on_target = Column(Integer, default=0)
    expected_goals = Column(Numeric(8, 3))
    expected_assists = Column(Numeric(8, 3))
    key_passes = Column(Integer, default=0)

    # Passing
    passes_total = Column(Integer, default=0)
    passes_accurate = Column(Integer, default=0)
    long_balls_total = Column(Integer, default=0)
    long_balls_accurate = Column(Integer, default=0)
    crosses_total = Column(Integer, default=0)
    crosses_accurate = Column(Integer, default=0)

    # Dribbling
    dribbles_attempted = Column(Integer, default=0)
    dribbles_successful = Column(Integer, default=0)

    # Defending
    tackles_total = Column(Integer, default=0)
    tackles_won = Column(Integer, default=0)
    interceptions = Column(Integer, default=0)
    clearances = Column(Integer, default=0)
    blocks = Column(Integer, default=0)

    # Duels
    ground_duels_total = Column(Integer, default=0)
    ground_duels_won = Column(Integer, default=0)
    aerial_duels_total = Column(Integer, default=0)
    aerial_duels_won = Column(Integer, default=0)

    # Goalkeeping (NULL for outfield)
    saves = Column(Integer)
    goals_conceded = Column(Integer)
    clean_sheets = Column(Integer)

    # Discipline
    yellow_cards = Column(Integer, default=0)
    red_cards = Column(Integer, default=0)

    avg_rating = Column(Numeric(4, 2))
    scraped_at = Column(DateTime, default=func.now())

    player = relationship("Player", back_populates="stats")
    season = relationship("Season", back_populates="stats")
    team = relationship("Team", back_populates="stats")


class PlayerFeatures(Base):
    __tablename__ = "player_features"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id", ondelete="CASCADE"), unique=True, nullable=False)
    season_id = Column(Integer, ForeignKey("seasons.id"))
    position_group = Column(String(5))

    minutes_played = Column(Integer)
    age = Column(Integer)
    market_value_eur = Column(BigInteger)
    league_name = Column(String(100))
    club_name = Column(String(200))

    # Per-90 stats
    goals_p90 = Column(Numeric(6, 3))
    assists_p90 = Column(Numeric(6, 3))
    xg_p90 = Column(Numeric(6, 3))
    xa_p90 = Column(Numeric(6, 3))
    shots_on_target_p90 = Column(Numeric(6, 3))
    key_passes_p90 = Column(Numeric(6, 3))
    passes_p90 = Column(Numeric(6, 3))
    pass_completion_pct = Column(Numeric(5, 2))
    dribbles_successful_p90 = Column(Numeric(6, 3))
    tackles_won_p90 = Column(Numeric(6, 3))
    interceptions_p90 = Column(Numeric(6, 3))
    clearances_p90 = Column(Numeric(6, 3))
    blocks_p90 = Column(Numeric(6, 3))
    aerial_duels_won_pct = Column(Numeric(5, 2))
    saves_p90 = Column(Numeric(6, 3))
    save_pct = Column(Numeric(5, 2))
    avg_rating = Column(Numeric(4, 2))

    # MinMax-scaled vector for KNN (JSON array, ordered per config.POSITION_FEATURES)
    feature_vector = Column(JSONB)

    built_at = Column(DateTime, default=func.now())

    player = relationship("Player", back_populates="features")

    __table_args__ = (
        Index("idx_player_features_pos", "position_group"),
    )


class RecommendationLog(Base):
    __tablename__ = "recommendation_logs"

    id = Column(Integer, primary_key=True)
    session_id = Column(UUID(as_uuid=True), server_default=func.gen_random_uuid())
    queried_at = Column(DateTime, default=func.now())
    position_filter = Column(String(10))
    budget_eur = Column(BigInteger)
    min_age = Column(Integer)
    max_age = Column(Integer)
    min_minutes = Column(Integer)
    league_filter = Column(String(100))
    ideal_vector = Column(JSONB)
    weights = Column(JSONB)
    result_player_ids = Column(ARRAY(Integer))
    result_scores = Column(ARRAY(Numeric(6, 3)))
