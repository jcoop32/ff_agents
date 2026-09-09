"""
Redis-backed response cache for LLM queries.
Prevents duplicate LLM invocations and conserves free-tier API quotas.
"""

import hashlib
import json
import logging
from typing import Optional, Dict, Any
from app.core.redis_client import get_redis
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMCache:
    """Deterministic response cache for agent decisions."""

    @staticmethod
    def generate_cache_key(model: str, system_prompt: str, user_query: str, context_payload: Optional[Dict[str, Any]] = None) -> str:
        """Computes SHA-256 fingerprint for the model, prompt, and query context."""
        hasher = hashlib.sha256()
        hasher.update(model.encode("utf-8"))
        hasher.update(system_prompt.encode("utf-8"))
        hasher.update(user_query.lower().strip().encode("utf-8"))
        if context_payload:
            hasher.update(json.dumps(context_payload, sort_keys=True).encode("utf-8"))
        return f"llm_cache:{hasher.hexdigest()}"

    @classmethod
    async def get(cls, cache_key: str) -> Optional[str]:
        """Retrieves cached response from Redis if present. Fail-open: returns None on any error."""
        try:
            r = await get_redis()
            val = await r.get(cache_key)
            if val:
                await r.incr("llm_cache_hits")
                logger.info("LLM cache hit: %s", cache_key)
                return val
            await r.incr("llm_cache_misses")
        except Exception as e:
            logger.debug("Redis cache get failed: %s", str(e))
        return None

    @classmethod
    async def set(cls, cache_key: str, response_text: str, ttl_hours: Optional[int] = None) -> None:
        """Stores LLM response in Redis with TTL expiration."""
        r = await get_redis()
        ttl = (ttl_hours or settings.LLM_CACHE_TTL_HOURS) * 3600
        try:
            await r.setex(cache_key, ttl, response_text)
        except Exception as e:
            logger.debug("Redis cache set failed: %s", str(e))

    @classmethod
    async def get_stats(cls) -> Dict[str, Any]:
        """Retrieves cache hit/miss statistics."""
        try:
            r = await get_redis()
            pipe = r.pipeline()
            pipe.get("llm_cache_hits")
            pipe.get("llm_cache_misses")
            hits, misses = await pipe.execute()
            h = int(hits) if hits else 0
            m = int(misses) if misses else 0
        except Exception:
            h, m = 0, 0

        total = h + m
        ratio = round((h / total * 100), 1) if total > 0 else 0.0
        return {
            "hits": h,
            "misses": m,
            "total_requests": total,
            "hit_ratio_percent": ratio
        }
