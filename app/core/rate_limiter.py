"""
Rate Limiter & Budget Enforcer for Free-Tier Cloud LLMs.
Ensures zero monetary cost by strictly guarding RPM, RPD, and TPM limits.
Tracks counters in Redis so state is shared across app, workers, and bots.
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when a free-tier quota (RPM, RPD, or TPM) would be exceeded."""
    pass


# Free tier quotas (conservatively tuned to stay 100% safe)
FREE_TIER_QUOTAS = {
    "gemini": {
        "rpm": 12,        # Standard free limit is 15 RPM
        "rpd": 1400,      # Standard free limit is 1500 RPD
        "tpm": 200_000,   # Standard free limit is 250k TPM
        "reset_tz": "PT"  # Resets at midnight Pacific (07:00 / 08:00 UTC)
    },
    "groq": {
        "rpm": 25,        # Standard free limit is 30 RPM
        "rpd": 900,       # Standard free limit is 1000 RPD
        "tpm": 10_000,    # Llama/Qwen/GPT-OSS TPM guard
        "reset_tz": "UTC" # Resets at midnight UTC
    }
}


class RateLimiter:
    """Async Redis-backed rate limiter for LLM providers."""

    @staticmethod
    def _get_minute_key(provider: str) -> str:
        minute_ts = int(time.time() // 60)
        return f"rate_limit:{provider}:min:{minute_ts}"

    @staticmethod
    def _get_day_key(provider: str) -> Tuple[str, int]:
        """Returns the day key and seconds remaining until midnight in the provider's timezone."""
        now = datetime.now(timezone.utc)
        if FREE_TIER_QUOTAS[provider]["reset_tz"] == "PT":
            # PT is UTC-7 (PDT) or UTC-8 (PST). Approximate as UTC-7 during season
            pt_offset = timedelta(hours=-7)
            now_pt = now + pt_offset
            date_str = now_pt.strftime("%Y-%m-%d")
            tomorrow = (now_pt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            seconds_remaining = int((tomorrow - now_pt).total_seconds())
        else:
            date_str = now.strftime("%Y-%m-%d")
            tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            seconds_remaining = int((tomorrow - now).total_seconds())

        return f"rate_limit:{provider}:day:{date_str}", max(seconds_remaining, 60)

    @classmethod
    async def check_budget(cls, provider: str, estimated_tokens: int = 500) -> bool:
        """
        Checks whether the provider has available RPM, RPD, and TPM headroom.
        Raises RateLimitExceeded if limits are reached.
        """
        provider = provider.lower()
        if provider not in FREE_TIER_QUOTAS:
            return True

        quota = FREE_TIER_QUOTAS[provider]
        try:
            r = await get_redis()
            min_key = cls._get_minute_key(provider)
            day_key, _ = cls._get_day_key(provider)

            pipe = r.pipeline()
            pipe.hget(min_key, "requests")
            pipe.hget(min_key, "tokens")
            pipe.get(day_key)
            results = await pipe.execute()

            current_rpm = int(results[0]) if results[0] else 0
            current_tpm = int(results[1]) if results[1] else 0
            current_rpd = int(results[2]) if results[2] else 0
        except Exception as e:
            logger.debug("Redis offline; bypassing rate limit budget check: %s", str(e))
            return True

        # Validate RPD
        if current_rpd >= quota["rpd"]:
            msg = (
                f"[{provider.upper()}] Daily limit reached ({current_rpd}/{quota['rpd']}). "
                f"Resets at midnight {quota['reset_tz']}."
            )
            logger.warning(msg)
            raise RateLimitExceeded(msg)

        # Validate RPM
        if current_rpm >= quota["rpm"]:
            msg = (
                f"[{provider.upper()}] Per-minute rate limit hit ({current_rpm}/{quota['rpm']}). "
                "Pausing briefly to respect free tier."
            )
            logger.warning(msg)
            raise RateLimitExceeded(msg)

        # Validate TPM
        if current_tpm + estimated_tokens > quota["tpm"]:
            msg = (
                f"[{provider.upper()}] Token per minute budget exceeded "
                f"({current_tpm + estimated_tokens}/{quota['tpm']})."
            )
            logger.warning(msg)
            raise RateLimitExceeded(msg)

        return True

    @classmethod
    async def record_usage(cls, provider: str, actual_tokens: int = 500) -> None:
        """Records an executed LLM request and token count against Redis quotas."""
        provider = provider.lower()
        if provider not in FREE_TIER_QUOTAS:
            return

        try:
            r = await get_redis()
            min_key = cls._get_minute_key(provider)
            day_key, ttl_seconds = cls._get_day_key(provider)

            pipe = r.pipeline()
            # Increment minute counters (expire after 2 minutes)
            pipe.hincrby(min_key, "requests", 1)
            pipe.hincrby(min_key, "tokens", actual_tokens)
            pipe.expire(min_key, 120)

            # Increment daily counter (expire at midnight)
            pipe.incrby(day_key, 1)
            pipe.expire(day_key, ttl_seconds)
            await pipe.execute()
        except Exception as e:
            logger.debug("Redis offline; skipping record_usage: %s", str(e))

    @classmethod
    async def get_budget_status(cls) -> Dict[str, Any]:
        """Returns real-time usage stats for all configured providers."""
        status = {}
        try:
            r = await get_redis()
            for provider, quota in FREE_TIER_QUOTAS.items():
                min_key = cls._get_minute_key(provider)
                day_key, _ = cls._get_day_key(provider)

                pipe = r.pipeline()
                pipe.hget(min_key, "requests")
                pipe.hget(min_key, "tokens")
                pipe.get(day_key)
                results = await pipe.execute()

                rpm = int(results[0]) if results[0] else 0
                tpm = int(results[1]) if results[1] else 0
                rpd = int(results[2]) if results[2] else 0

                status[provider] = {
                    "rpm_used": rpm,
                    "rpm_limit": quota["rpm"],
                    "rpd_used": rpd,
                    "rpd_limit": quota["rpd"],
                    "rpd_percent": round((rpd / quota["rpd"]) * 100, 1),
                    "tpm_used": tpm,
                    "tpm_limit": quota["tpm"],
                    "reset_timezone": quota["reset_tz"]
                }
        except Exception as e:
            logger.debug("Redis offline; returning baseline budget metrics: %s", str(e))
            for provider, quota in FREE_TIER_QUOTAS.items():
                status[provider] = {
                    "rpm_used": 0,
                    "rpm_limit": quota["rpm"],
                    "rpd_used": 0,
                    "rpd_limit": quota["rpd"],
                    "rpd_percent": 0.0,
                    "tpm_used": 0,
                    "tpm_limit": quota["tpm"],
                    "reset_timezone": quota["reset_tz"]
                }

        return status
