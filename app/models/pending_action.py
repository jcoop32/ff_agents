"""
SQLAlchemy PendingAction model for Approval Gate workflow.
Allows agents to formulate concrete roster moves (waiver claims, lineup swaps,
trade proposals, IR movements) which require human approval before automated ESPN execution.
"""

from sqlalchemy import Column, Integer, String, Text, JSON, Float, DateTime, Index
from sqlalchemy.sql import func
from app.core.database import Base


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    action_type = Column(String(32), index=True, nullable=False)
    # WAIVER_CLAIM, FREE_AGENT_ADD, LINEUP_SWAP, TRADE_PROPOSAL, IR_STASH, DROP_PLAYER
    status = Column(String(16), index=True, default="PENDING", nullable=False)
    # PENDING, APPROVED, REJECTED, EXECUTED, FAILED, EXPIRED
    urgency = Column(String(16), index=True, default="MEDIUM")
    # LOW, MEDIUM, HIGH, CRITICAL
    confidence_score = Column(Float, nullable=False, default=0.75)
    # 0.0 to 1.0 confidence rating from LLM
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    # Parameters needed to execute:
    # WAIVER_CLAIM: {"add_player_id": int, "drop_player_id": int, "bid_amount": int}
    # LINEUP_SWAP: {"bench_player_id": int, "start_player_id": int, "slot_id": int}
    # TRADE_PROPOSAL: {"target_team_id": int, "send_player_ids": [int], "receive_player_ids": [int]}
    # IR_STASH: {"player_id": int}
    source_agent = Column(String(64), index=True, nullable=False, default="GeneralManager")
    # WaiverAnalyst, InjurySpecialist, TradeStrategist, GeneralManager
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    execution_result = Column(JSON, nullable=True)
    # ESPN API response payload or error message trace
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_action_status_urgency", "status", "urgency"),
        Index("ix_action_status_expires", "status", "expires_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "action_type": self.action_type,
            "status": self.status,
            "urgency": self.urgency,
            "confidence_score": round(self.confidence_score, 2) if self.confidence_score else 0.0,
            "title": self.title,
            "description": self.description,
            "rationale": self.rationale,
            "payload": self.payload or {},
            "source_agent": self.source_agent,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "execution_result": self.execution_result,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
