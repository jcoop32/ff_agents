"""
NotificationDispatcher: Unified multi-channel fan-out service.
Delivers agent briefings and pending approval actions to:
1. PostgreSQL (agent_briefings and pending_actions tables)
2. Redis Pub/Sub channel 'gridiron:pulse:stream' (for SSE real-time web streaming)
3. Redis List 'gridiron:pulse:recent' (capped at 100 recent notifications)
4. Discord (via DB unnotified queue processed by Discord bot)
"""

import json
import logging
from typing import Dict, Any, Optional, AsyncGenerator, List
from datetime import datetime, timezone
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis
from app.models.agent_briefing import AgentBriefing
from app.models.pending_action import PendingAction

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Central fan-out dispatcher for briefings and approval actions."""

    @classmethod
    async def dispatch_briefing(
        cls,
        briefing_type: str,
        title: str,
        content: str,
        urgency: str = "MEDIUM",
        structured_data: Optional[Dict[str, Any]] = None,
        action_items: Optional[List[Dict[str, Any]]] = None,
        source_agent: str = "GeneralManager",
    ) -> Dict[str, Any]:
        """
        Creates and dispatches an AgentBriefing across DB, SSE, and Discord.
        """
        structured_data = structured_data or {}
        action_items = action_items or []

        # 1. Persist to PostgreSQL
        briefing_record = None
        briefing_dict = {}
        try:
            async with AsyncSessionLocal() as session:
                briefing = AgentBriefing(
                    briefing_type=briefing_type,
                    urgency=urgency,
                    title=title,
                    content=content,
                    structured_data=structured_data,
                    action_items=action_items,
                    source_agent=source_agent,
                    read=False,
                    notified_discord=False,
                    notified_sse=True,
                )
                session.add(briefing)
                await session.commit()
                await session.refresh(briefing)
                briefing_dict = briefing.to_dict()
        except Exception as e:
            logger.warning("Failed to persist briefing to PostgreSQL (falling back to memory/Redis): %s", str(e))
            briefing_dict = {
                "id": None,
                "briefing_type": briefing_type,
                "urgency": urgency,
                "title": title,
                "content": content,
                "structured_data": structured_data,
                "action_items": action_items,
                "source_agent": source_agent,
                "read": False,
                "notified_discord": False,
                "notified_sse": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        # 2. Publish to Redis Pub/Sub for SSE
        envelope = {
            "type": "BRIEFING",
            "data": briefing_dict,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            r = await get_redis()
            payload_str = json.dumps(envelope)
            await r.publish("gridiron:pulse:stream", payload_str)

            # 3. Store in recent history list (capped at 100)
            await r.lpush("gridiron:pulse:recent", payload_str)
            await r.ltrim("gridiron:pulse:recent", 0, 99)
        except Exception as e:
            logger.error("Failed to publish briefing to Redis: %s", str(e))

        logger.info(
            "NotificationDispatcher: Dispatched [%s] '%s' (Urgency: %s)",
            briefing_type,
            title,
            urgency,
        )
        return briefing_dict

    @classmethod
    async def dispatch_pending_action(
        cls,
        action_type: str,
        title: str,
        description: str,
        rationale: str,
        payload: Dict[str, Any],
        urgency: str = "MEDIUM",
        confidence_score: float = 0.85,
        source_agent: str = "GeneralManager",
        expires_hours: int = 24,
    ) -> Dict[str, Any]:
        """
        Creates and dispatches a PendingAction for user approval before execution.
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=expires_hours)

        action_dict = {}
        try:
            async with AsyncSessionLocal() as session:
                action = PendingAction(
                    action_type=action_type,
                    status="PENDING",
                    urgency=urgency,
                    confidence_score=confidence_score,
                    title=title,
                    description=description,
                    rationale=rationale,
                    payload=payload,
                    source_agent=source_agent,
                    expires_at=expires_at,
                )
                session.add(action)
                await session.commit()
                await session.refresh(action)
                action_dict = action.to_dict()
        except Exception as e:
            logger.warning("Failed to persist pending action to PostgreSQL: %s", str(e))
            action_dict = {
                "id": None,
                "action_type": action_type,
                "status": "PENDING",
                "urgency": urgency,
                "confidence_score": confidence_score,
                "title": title,
                "description": description,
                "rationale": rationale,
                "payload": payload,
                "source_agent": source_agent,
                "expires_at": expires_at.isoformat(),
                "created_at": now.isoformat(),
            }

        # Publish action creation event to SSE
        envelope = {
            "type": "PENDING_ACTION",
            "data": action_dict,
            "timestamp": now.isoformat(),
        }
        try:
            r = await get_redis()
            payload_str = json.dumps(envelope)
            await r.publish("gridiron:pulse:stream", payload_str)
            await r.lpush("gridiron:pulse:recent", payload_str)
            await r.ltrim("gridiron:pulse:recent", 0, 99)
        except Exception as e:
            logger.error("Failed to publish pending action to Redis: %s", str(e))

        logger.info(
            "NotificationDispatcher: Dispatched PendingAction [%s] '%s' (Confidence: %.2f)",
            action_type,
            title,
            confidence_score,
        )
        return action_dict

    @classmethod
    async def get_recent_feed(cls, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent notifications from Redis cache."""
        try:
            r = await get_redis()
            raw_list = await r.lrange("gridiron:pulse:recent", 0, limit - 1)
            results = []
            for item in raw_list:
                try:
                    results.append(json.loads(item))
                except Exception:
                    pass
            return results
        except Exception as e:
            logger.error("Failed to fetch recent feed from Redis: %s", str(e))
            return []

    @classmethod
    async def subscribe_sse(cls) -> AsyncGenerator[str, None]:
        """
        Async generator for FastAPI Server-Sent Events (SSE).
        Subscribes to 'gridiron:pulse:stream' and yields formatted SSE messages.
        """
        import asyncio
        r = await get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe("gridiron:pulse:stream")

        try:
            # Yield initial keepalive
            yield f": keepalive\n\n"
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=15.0
                )
                if message and message["type"] == "message":
                    data_str = message["data"]
                    yield f"data: {data_str}\n\n"
                else:
                    # Periodic heartbeat to keep HTTP connection alive
                    yield f": keepalive\n\n"
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logger.info("SSE client disconnected.")
        finally:
            try:
                await pubsub.unsubscribe("gridiron:pulse:stream")
                await pubsub.aclose()
            except Exception:
                pass
