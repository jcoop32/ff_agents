"""
Chat Service for multi-session conversation history management.
Handles persistence in PostgreSQL and lightning-fast retrieval/caching in Redis.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis
from app.models.chat import ChatSession, ChatMessage

logger = logging.getLogger(__name__)


class ChatService:
    """Manages chat session lifecycle, message persistence, and dual-write caching."""

    @classmethod
    async def create_session(cls, title: Optional[str] = None) -> Dict[str, Any]:
        """Creates an explicit new ChatSession and caches in Redis."""
        session_id = str(uuid.uuid4())
        session_title = (title or "New Conversation").strip()
        now = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as session:
            new_session = ChatSession(
                id=session_id,
                title=session_title,
                created_at=now,
                updated_at=now,
            )
            session.add(new_session)
            await session.commit()

        session_data = {
            "id": session_id,
            "title": session_title,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "message_count": 0,
            "last_message": None,
        }

        # Cache in Redis
        try:
            r = await get_redis()
            await r.zadd("chat:sessions:list", {session_id: now.timestamp()})
            await r.set(f"chat:session:{session_id}:meta", json.dumps(session_data))
        except Exception as e:
            logger.warning("Redis cache error in create_session: %s", str(e))

        return session_data

    @classmethod
    async def get_or_create_session(
        cls, session_id: Optional[str] = None, initial_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetches existing session or creates a new one if session_id is None/missing."""
        if session_id:
            async with AsyncSessionLocal() as session:
                stmt = select(ChatSession).where(ChatSession.id == session_id)
                res = await session.execute(stmt)
                existing = res.scalar_one_or_none()
                if existing:
                    return {
                        "id": existing.id,
                        "title": existing.title,
                        "created_at": existing.created_at.isoformat(),
                        "updated_at": existing.updated_at.isoformat(),
                    }

        return await cls.create_session(title=initial_title)

    @classmethod
    async def list_sessions(cls, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists chat sessions ordered by most recently updated."""
        async with AsyncSessionLocal() as session:
            stmt = (
                select(
                    ChatSession,
                    func.count(ChatMessage.id).label("msg_count"),
                )
                .outerjoin(ChatMessage, ChatSession.id == ChatMessage.session_id)
                .group_by(ChatSession.id)
                .order_by(ChatSession.updated_at.desc())
                .limit(limit)
            )
            res = await session.execute(stmt)
            rows = res.all()

            output = []
            for row in rows:
                cs = row[0]
                count = row[1]
                output.append({
                    "id": cs.id,
                    "title": cs.title,
                    "created_at": cs.created_at.isoformat() if cs.created_at else None,
                    "updated_at": cs.updated_at.isoformat() if cs.updated_at else None,
                    "message_count": count,
                })

            return output

    @classmethod
    async def get_session_messages(cls, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves session metadata and full chronological message history."""
        async with AsyncSessionLocal() as session:
            stmt = (
                select(ChatSession)
                .options(selectinload(ChatSession.messages))
                .where(ChatSession.id == session_id)
            )
            res = await session.execute(stmt)
            cs = res.scalar_one_or_none()
            if not cs:
                return None

            messages = []
            for m in cs.messages:
                # Format friendly timestamp string
                created_dt = m.created_at if m.created_at else datetime.now(timezone.utc)
                ts_str = created_dt.strftime("%I:%M %p")
                messages.append({
                    "id": m.id,
                    "session_id": m.session_id,
                    "sender": m.sender,
                    "text": m.text,
                    "week": m.week,
                    "timestamp": ts_str,
                    "created_at": created_dt.isoformat(),
                })

            return {
                "session": {
                    "id": cs.id,
                    "title": cs.title,
                    "created_at": cs.created_at.isoformat() if cs.created_at else None,
                    "updated_at": cs.updated_at.isoformat() if cs.updated_at else None,
                    "message_count": len(messages),
                },
                "messages": messages,
            }

    @classmethod
    async def save_message(
        cls, session_id: str, sender: str, text: str, week: int = 1
    ) -> Dict[str, Any]:
        """Saves a message to the specified session, updating session title and timestamp."""
        msg_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as session:
            # Check if session exists; if not create
            stmt = select(ChatSession).where(ChatSession.id == session_id)
            res = await session.execute(stmt)
            cs = res.scalar_one_or_none()

            if not cs:
                title = text[:45] + ("..." if len(text) > 45 else "")
                cs = ChatSession(id=session_id, title=title, created_at=now, updated_at=now)
                session.add(cs)
            else:
                cs.updated_at = now
                # If title is generic and this is a user message, update title
                if sender == "user" and (cs.title == "New Conversation" or not cs.title):
                    clean_title = text.strip()
                    if clean_title:
                        cs.title = clean_title[:45] + ("..." if len(clean_title) > 45 else "")

            new_msg = ChatMessage(
                id=msg_id,
                session_id=session_id,
                sender=sender,
                text=text,
                week=week,
                created_at=now,
            )
            session.add(new_msg)
            await session.commit()

        formatted_msg = {
            "id": msg_id,
            "session_id": session_id,
            "sender": sender,
            "text": text,
            "week": week,
            "timestamp": now.strftime("%I:%M %p"),
            "created_at": now.isoformat(),
        }

        # Cache in Redis
        try:
            r = await get_redis()
            await r.zadd("chat:sessions:list", {session_id: now.timestamp()})
            await r.rpush(f"chat:session:{session_id}:messages", json.dumps(formatted_msg))
        except Exception as e:
            logger.warning("Redis cache error in save_message: %s", str(e))

        return formatted_msg

    @classmethod
    async def delete_session(cls, session_id: str) -> bool:
        """Deletes a chat session and all cascading messages."""
        async with AsyncSessionLocal() as session:
            stmt = delete(ChatSession).where(ChatSession.id == session_id)
            res = await session.execute(stmt)
            await session.commit()
            deleted = res.rowcount > 0

        # Remove from Redis
        try:
            r = await get_redis()
            await r.zrem("chat:sessions:list", session_id)
            await r.delete(f"chat:session:{session_id}:meta")
            await r.delete(f"chat:session:{session_id}:messages")
        except Exception as e:
            logger.warning("Redis cache error in delete_session: %s", str(e))

        return deleted
