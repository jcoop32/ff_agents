"""
Async Redis client singleton and helper functions.
Supports standard Hashes, Sorted Sets, Streams, and JSON metrics.
"""

import json
from typing import Optional, Dict, Any, List
import redis.asyncio as aioredis
from app.core.config import settings

_redis_pool: Optional[aioredis.ConnectionPool] = None
_redis_client: Optional[aioredis.Redis] = None
_redis_loop_id: Optional[int] = None


async def init_redis_pool() -> aioredis.Redis:
    """Initialize Redis connection pool."""
    global _redis_pool, _redis_client
    if _redis_client is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=25
        )
        _redis_client = aioredis.Redis(connection_pool=_redis_pool)
    return _redis_client


async def get_redis() -> aioredis.Redis:
    """Get active async Redis client instance, resetting if running in a new event loop."""
    global _redis_client, _redis_pool, _redis_loop_id
    import asyncio
    try:
        current_loop = asyncio.get_running_loop()
        current_loop_id = id(current_loop)
    except RuntimeError:
        current_loop_id = None

    if _redis_client is not None and _redis_loop_id != current_loop_id:
        _redis_client = None
        _redis_pool = None

    if _redis_client is None:
        _redis_loop_id = current_loop_id
        return await init_redis_pool()
    return _redis_client


async def close_redis():
    """Close Redis client and connection pool."""
    global _redis_client, _redis_pool
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
    if _redis_pool:
        await _redis_pool.disconnect()
        _redis_pool = None


class RedisRepository:
    """High-level repository for Gridiron AI data access patterns."""

    @staticmethod
    async def set_player_index(normalized_name: str, player_id: str) -> None:
        r = await get_redis()
        await r.hset("player_index", normalized_name.lower().strip(), str(player_id))

    @staticmethod
    async def resolve_player_id(normalized_name: str) -> Optional[str]:
        r = await get_redis()
        return await r.hget("player_index", normalized_name.lower().strip())

    @staticmethod
    async def set_player_hash(player_id: str, mapping: Dict[str, Any]) -> None:
        r = await get_redis()
        cleaned = {k: str(v) if v is not None else "" for k, v in mapping.items()}
        await r.hset(f"player:{player_id}", mapping=cleaned)

    @staticmethod
    async def get_player_hash(player_id: str) -> Dict[str, str]:
        r = await get_redis()
        return await r.hgetall(f"player:{player_id}")

    @staticmethod
    async def set_player_stats_json(player_id: str, stats: Dict[str, Any]) -> None:
        """Stores metrics in stats:{id}:current. Supports RedisJSON or JSON string."""
        r = await get_redis()
        key = f"stats:{player_id}:current"
        try:
            await r.json().set(key, "$", stats)
        except Exception:
            # Fallback if RedisJSON module is not loaded
            await r.set(key, json.dumps(stats))

    @staticmethod
    async def get_player_stats_json(player_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves metrics from stats:{id}:current."""
        r = await get_redis()
        key = f"stats:{player_id}:current"
        try:
            data = await r.json().get(key)
            if data is not None:
                return data
        except Exception:
            pass
        val = await r.get(key)
        return json.loads(val) if val else None

    @staticmethod
    async def add_player_news(player_id: str, epoch_time: float, payload: Dict[str, Any]) -> None:
        r = await get_redis()
        key = f"news:{player_id}"
        await r.zadd(key, {json.dumps(payload): epoch_time})

    @staticmethod
    async def get_player_news(player_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        r = await get_redis()
        key = f"news:{player_id}"
        items = await r.zrevrangebyscore(key, max="+inf", min="-inf", start=0, num=limit)
        results = []
        for raw in items:
            try:
                results.append(json.loads(raw))
            except Exception:
                results.append({"text": raw})
        return results

    @staticmethod
    async def push_raw_news_stream(payload: Dict[str, Any]) -> str:
        r = await get_redis()
        stringified = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in payload.items()}
        return await r.xadd("stream:raw_news", stringified)

    @staticmethod
    async def push_league_activity_stream(payload: Dict[str, Any]) -> str:
        r = await get_redis()
        stringified = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in payload.items()}
        return await r.xadd("stream:league_activity", stringified)
