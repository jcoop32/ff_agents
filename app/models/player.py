"""
SQLAlchemy Player entity model.
Stores canonical player metadata mapped from ESPN and NFL data.
"""

from sqlalchemy import Column, Integer, String, Float, JSON, Index, DateTime, Text
from sqlalchemy.sql import func
from app.core.database import Base


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    espn_id = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(128), index=True, nullable=False)
    team = Column(String(16), index=True, nullable=True)
    position = Column(String(16), index=True, nullable=False)
    age = Column(Integer, nullable=True)
    status = Column(String(32), default="Active")
    injury_status = Column(String(32), nullable=True) # Healthy, Questionable, Doubtful, Out, IR
    bye_week = Column(Integer, nullable=True)
    projected_points = Column(Float, default=0.0) # Canonical projection
    projected_avg = Column(Float, default=0.0)
    weekly_projected_points = Column(Float, default=0.0) # Current week matchup projection
    pos_rank = Column(Integer, nullable=True)
    espn_proj = Column(Float, default=0.0)
    sleeper_proj = Column(Float, default=0.0)
    consensus_proj = Column(Float, default=0.0)
    proj_floor = Column(Float, default=0.0)
    proj_ceiling = Column(Float, default=0.0)
    adp = Column(Float, nullable=True)
    espn_adp = Column(Float, nullable=True)
    sleeper_adp = Column(Float, nullable=True)
    yahoo_adp = Column(Float, nullable=True)
    consensus_adp = Column(Float, nullable=True)
    injury_notes = Column(Text, nullable=True)
    market_arbitrage_delta = Column(Float, default=0.0)
    sentiment_score = Column(Float, default=0.0)
    sentiment_tag = Column(String(16), default="NEUTRAL")
    percent_owned = Column(Float, nullable=True)   # ESPN % Owned across all leagues
    percent_started = Column(Float, nullable=True)  # ESPN % Started across all leagues
    source_projections = Column(JSON, nullable=True)
    scouting_notes = Column(JSON, nullable=True)
    espn_data = Column(JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_players_team_pos", "team", "position"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "espn_id": self.espn_id,
            "name": self.name,
            "team": self.team,
            "position": self.position,
            "status": self.status,
            "injury_status": self.injury_status,
            "injury_notes": self.injury_notes,
            "bye_week": self.bye_week,
            "projected_points": round(float(self.consensus_proj or self.projected_points or 0.0), 1),
            "projected_avg": round(float(self.projected_avg or 0.0), 1),
            "espn_proj": round(float(self.espn_proj or self.projected_points or 0.0), 1),
            "sleeper_proj": round(float(self.sleeper_proj or 0.0), 1),
            "consensus_proj": round(float(self.consensus_proj or self.projected_points or 0.0), 1),
            "proj_floor": round(float(self.proj_floor or 0.0), 1),
            "proj_ceiling": round(float(self.proj_ceiling or 0.0), 1),
            "adp": round(float(self.consensus_adp or self.adp), 1) if (self.consensus_adp is not None or self.adp is not None) else None,
            "consensus_adp": round(float(self.consensus_adp), 1) if self.consensus_adp is not None else None,
            "sleeper_adp": round(float(self.sleeper_adp or self.adp), 1) if (self.sleeper_adp is not None or self.adp is not None) else None,
            "espn_adp": round(float(self.espn_adp), 1) if self.espn_adp is not None else None,
            "yahoo_adp": round(float(self.yahoo_adp), 1) if self.yahoo_adp is not None else None,
            "market_arbitrage_delta": round(float(self.market_arbitrage_delta or 0.0), 1),
            "sentiment_score": round(float(self.sentiment_score or 0.0), 2),
            "sentiment_tag": self.sentiment_tag or "NEUTRAL",
            "pos_rank": self.pos_rank,
            "source_projections": self.source_projections or {},
            "scouting_notes": self.scouting_notes or {},
            "stats": (self.espn_data or {}).get("stats", {}),
            "percent_owned": round(float(self.percent_owned or 0.0), 1),
            "percent_started": round(float(self.percent_started or 0.0), 1),
        }
