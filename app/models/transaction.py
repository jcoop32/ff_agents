"""
SQLAlchemy Transaction model for proactive league monitoring.
Tracks all waiver claims, free agent pickups, trades, and roster adjustments.
"""

from sqlalchemy import Column, Integer, String, JSON, Boolean, DateTime, Index
from sqlalchemy.sql import func
from app.core.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    espn_transaction_id = Column(String(128), unique=True, index=True, nullable=False)
    league_id = Column(String(64), index=True, nullable=False)
    type = Column(String(32), index=True, nullable=False) # WAIVER, FREE_AGENT, TRADE, IR_STASH, ROSTER_MOVE
    team_id = Column(Integer, index=True, nullable=False)
    team_name = Column(String(128), nullable=False)
    players_added = Column(JSON, default=list)   # [{"id": "...", "name": "...", "pos": "..."}]
    players_dropped = Column(JSON, default=list) # [{"id": "...", "name": "...", "pos": "..."}]
    trade_partner_team_id = Column(Integer, nullable=True)
    trade_partner_name = Column(String(128), nullable=True)
    trade_partner_players = Column(JSON, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=func.now())
    impact_level = Column(String(16), default="LOW", index=True) # LOW, MEDIUM, HIGH, CRITICAL
    analysis_text = Column(String, nullable=True) # LLM synthesis for CRITICAL/HIGH moves
    notified = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_tx_league_time", "league_id", "timestamp"),
        Index("ix_tx_impact_notified", "impact_level", "notified"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "espn_transaction_id": self.espn_transaction_id,
            "type": self.type,
            "team_id": self.team_id,
            "team_name": self.team_name,
            "players_added": self.players_added,
            "players_dropped": self.players_dropped,
            "trade_partner_team_id": self.trade_partner_team_id,
            "trade_partner_name": self.trade_partner_name,
            "trade_partner_players": self.trade_partner_players,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "impact_level": self.impact_level,
            "analysis_text": self.analysis_text,
            "notified": self.notified
        }
