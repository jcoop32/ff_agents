"""
Unit tests for the zero-cost rate limiter and budget policies.
"""

import pytest
from app.core.rate_limiter import RateLimiter, FREE_TIER_QUOTAS, RateLimitExceeded


def test_free_tier_quotas_defined():
    assert "gemini" in FREE_TIER_QUOTAS
    assert "groq" in FREE_TIER_QUOTAS
    assert FREE_TIER_QUOTAS["gemini"]["rpm"] <= 15
    assert FREE_TIER_QUOTAS["gemini"]["rpd"] <= 1500
    assert FREE_TIER_QUOTAS["groq"]["rpm"] <= 30
    assert FREE_TIER_QUOTAS["groq"]["rpd"] <= 1000


def test_get_day_key_timezone_resolution():
    day_key_gemini, ttl_gemini = RateLimiter._get_day_key("gemini")
    assert "rate_limit:gemini:day:" in day_key_gemini
    assert ttl_gemini > 0

    day_key_groq, ttl_groq = RateLimiter._get_day_key("groq")
    assert "rate_limit:groq:day:" in day_key_groq
    assert ttl_groq > 0


def test_get_minute_key_resolution():
    min_key = RateLimiter._get_minute_key("gemini")
    assert "rate_limit:gemini:min:" in min_key
