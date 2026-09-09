"""
SQLAlchemy AgentBriefing model for proactive multi-agent intelligence.
Stores autonomous morning digests, injury alerts, waiver scouts, trade proposals,
and player tracking updates delivered across UI, SSE, and Discord.
"""

from sqlalchemy import Column, Integer, String, Text, JSON, Boolean, DateTime, Index
from sqlalchemy.sql import func
from app.core.database import Base


class AgentBriefing(Base):
    __tablename__ = "agent_briefings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    briefing_type = Column(String(32), index=True, nullable=False)
    # MORNING_DIGEST, INJURY_ALERT, WAIVER_SCOUT, TRADE_ALERT,
    # TRANSACTION_REACTION, LINEUP_REMINDER, TRACKING_UPDATE, POWER_RANKINGS, SEASON_STRATEGY
    urgency = Column(String(16), index=True, default="MEDIUM")
    # LOW, MEDIUM, HIGH, CRITICAL
    title = Column(String(256), nullable=False)
    content = Column(Text, nullable=False)
    structured_data = Column(JSON, default=dict)
    # Player IDs, trade specs, matchup context, stat diffs
    action_items = Column(JSON, default=list)
    # Recommended concrete actions: [{"type": "WAIVER_CLAIM", "label": "Pick up Isaiah Likely"}]
    source_agent = Column(String(64), index=True, nullable=False, default="GeneralManager")
    # InjurySpecialist, WaiverAnalyst, TradeStrategist, GeneralManager, TrackingAgent
    read = Column(Boolean, default=False, index=True)
    notified_discord = Column(Boolean, default=False)
    notified_sse = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_briefing_type_urgency", "briefing_type", "urgency"),
        Index("ix_briefing_read_created", "read", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "briefing_type": self.briefing_type,
            "urgency": self.urgency,
            "title": self.title,
            "content": self.content,
            "structured_data": self.structured_data or {},
            "action_items": self.action_items or [],
            "source_agent": self.source_agent,
            "read": self.read,
            "notified_discord": self.notified_discord,
            "notified_sse": self.notified_sse,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
