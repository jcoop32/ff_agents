"""
SQLAlchemy models for analytical metrics and news context.
Includes pgvector embedding support for semantic injury and news retrieval.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Index
from sqlalchemy.sql import func
from app.core.database import Base

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False
    Vector = None


class WeeklyStats(Base):
    __tablename__ = "weekly_stats"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    espn_id = Column(String(64), index=True, nullable=False)
    season = Column(Integer, nullable=False)
    week = Column(Integer, nullable=False)

    # Underlying Opportunity & Volume
    snap_share = Column(Float, default=0.0)
    target_share = Column(Float, default=0.0)
    route_participation = Column(Float, default=0.0)
    air_yards_share = Column(Float, default=0.0) # WOPR
    red_zone_touches = Column(Integer, default=0)

    # Advanced Efficiency Metrics
    yprr = Column(Float, default=0.0) # Yards per route run
    epa_per_play = Column(Float, default=0.0)
    actual_fp = Column(Float, default=0.0)
    xfp = Column(Float, default=0.0) # Expected Fantasy Points
    xfp_delta = Column(Float, default=0.0)
    td_rate = Column(Float, default=0.0)
    td_regression_flag = Column(Boolean, default=False)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_stats_player_season_week", "player_id", "season", "week", unique=True),
        Index("ix_stats_espn_season_week", "espn_id", "season", "week"),
    )

    def to_dict(self):
        return {
            "espn_id": self.espn_id,
            "season": self.season,
            "week": self.week,
            "snap_share": self.snap_share,
            "target_share": self.target_share,
            "route_participation": self.route_participation,
            "air_yards_share": self.air_yards_share,
            "yprr": self.yprr,
            "epa_per_play": self.epa_per_play,
            "actual_fp": self.actual_fp,
            "xfp": self.xfp,
            "xfp_delta": self.xfp_delta,
            "td_regression_flag": self.td_regression_flag
        }


class NewsItem(Base):
    __tablename__ = "news_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True, index=True)
    espn_id = Column(String(64), index=True, nullable=True)
    player_name = Column(String(128), index=True, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=func.now())
    source = Column(String(64), nullable=False) # e.g. Rotoworld, FantasyPros, Official Beat
    tag = Column(String(16), nullable=True) # Healthy, Q, D, O, IR, FP, LP, DNP
    headline = Column(String(256), nullable=True)
    text = Column(String, nullable=False)
    url = Column(String(512), nullable=True, unique=True) # Dedup hash

    # pgvector embedding representation (768 dimensions for Gemini embedding-004)
    if HAS_PGVECTOR:
        embedding = Column(Vector(768), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_news_player_time", "player_id", "timestamp"),
    )
