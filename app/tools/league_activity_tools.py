"""
Tools for querying recent league transactions, activity history, and waiver target watchlist.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from langchain_core.tools import tool
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis
from app.models.transaction import Transaction


async def fetch_recent_transactions(league_id: Optional[str] = None, hours: int = 24) -> List[Dict[str, Any]]:
    """
    Core query fetching recent league transactions from the PostgreSQL audit table.
    """
    since_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        async with AsyncSessionLocal() as session:
            stmt = (
                select(Transaction)
                .where(Transaction.timestamp >= since_time)
                .order_by(Transaction.timestamp.desc())
                .limit(50)
            )
            res = await session.execute(stmt)
            txs = res.scalars().all()
            return [t.to_dict() for t in txs]
    except Exception:
        return []


@tool
async def get_recent_transactions(league_id: Optional[str] = None, hours: int = 24) -> List[Dict[str, Any]]:
    """
    Returns recent league transactions (trades, waivers, free agent pickups)
    from the PostgreSQL audit table, sorted from newest to oldest.
    """
    return await fetch_recent_transactions(league_id=league_id, hours=hours)


@tool
async def get_transaction_impact(transaction_id: str) -> Dict[str, Any]:
    """
    Returns the impact classification and proactive agent analysis text for a specific transaction.
    """
    async with AsyncSessionLocal() as session:
        stmt = select(Transaction).where(Transaction.espn_transaction_id == transaction_id)
        res = await session.execute(stmt)
        tx = res.scalar_one_or_none()
        if not tx:
            return {"found": False, "message": f"Transaction {transaction_id} not found."}
        return {"found": True, **tx.to_dict()}


@tool
async def get_waiver_targets() -> List[str]:
    """
    Returns the watchlist of player names the user is actively monitoring for waiver claims or pickups.
    """
    r = await get_redis()
    targets = await r.smembers("user:waiver_targets")
    return list(targets)


@tool
async def add_waiver_target(player_name: str) -> Dict[str, Any]:
    """
    Adds a player name to the user's active waiver target watchlist in Redis.
    If another league manager claims this player, an immediate CRITICAL alert will trigger.
    """
    r = await get_redis()
    await r.sadd("user:waiver_targets", player_name.strip())
    return {
        "success": True,
        "player_name": player_name,
        "message": f"'{player_name}' added to waiver watchlist. You will be alerted if another team moves for this player."
    }
