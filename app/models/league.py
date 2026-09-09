"""
SQLAlchemy models for League and Team Rosters.
"""

from sqlalchemy import Column, Integer, String, JSON, Float, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class League(Base):
    __tablename__ = "leagues"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    espn_league_id = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=False)
    scoring_format = Column(String(32), default="ppr")
    season = Column(Integer, nullable=False, default=2026)
    total_teams = Column(Integer, default=12)
    roster_positions = Column(JSON, nullable=True) # {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "K": 1, "DST": 1, "BENCH": 4, "IR": 1}
    settings_payload = Column(JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    rosters = relationship("Roster", back_populates="league", cascade="all, delete-orphan")


class Roster(Base):
    __tablename__ = "rosters"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    league_id = Column(Integer, ForeignKey("leagues.id"), nullable=False, index=True)
    espn_team_id = Column(Integer, nullable=False, index=True)
    team_name = Column(String(128), nullable=False)
    owner_name = Column(String(128), nullable=True)
    players = Column(JSON, default=list) # List of espn_id strings
    starters = Column(JSON, default=list) # List of espn_id strings
    lineup_slots = Column(JSON, default=dict) # Dict of {espn_id: "QB"|"RB"|"WR"|"TE"|"FLEX"|"K"|"D/ST"|"BENCH"}
    record = Column(JSON, default=dict) # {"wins": 0, "losses": 0, "ties": 0}
    points_for = Column(Float, default=0.0)
    points_against = Column(Float, default=0.0)
    standing = Column(Integer, default=1)
    waiver_rank = Column(Integer, default=1)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    league = relationship("League", back_populates="rosters")

    def to_dict(self):
        return {
            "id": self.id,
            "espn_team_id": self.espn_team_id,
            "team_name": self.team_name,
            "owner_name": self.owner_name,
            "players": self.players,
            "starters": self.starters,
            "record": self.record,
            "points_for": self.points_for,
            "standing": self.standing,
            "waiver_rank": self.waiver_rank
        }
