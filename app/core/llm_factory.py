"""
Centralized LLM Factory with automatic Groq → Gemini fallback.

Every agent uses `get_llm()` instead of directly constructing provider-specific
clients.  When Groq returns a 429 (or any transient error), LangChain's native
`with_fallbacks()` transparently retries the same request on Gemini Flash —
zero downtime from the user's perspective.

This approach preserves `bind_tools()` and `with_structured_output()` support
since the underlying models are real ChatModel instances, not custom wrappers.
"""

import logging
from typing import Optional, Literal

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_llm(
    role: Literal["supervisor", "fast", "heavy"] = "heavy",
    temperature: float = 0.2,
) -> Optional[BaseChatModel]:
    """
    Returns an LLM for the given agent role with automatic Groq → Gemini fallback.

    Roles:
      - "supervisor" / "heavy": Uses HEAVY_MODEL on Groq, SUPERVISOR_MODEL on Gemini
      - "fast": Uses FAST_MODEL on Groq, REPORTING_MODEL on Gemini

    If both API keys are present, uses LangChain's native `with_fallbacks()`.
    If only one key exists, returns that provider directly.
    """
    groq_model = settings.HEAVY_MODEL if role in ("supervisor", "heavy") else settings.FAST_MODEL
    gemini_model = settings.SUPERVISOR_MODEL if role in ("supervisor", "heavy") else settings.REPORTING_MODEL

    groq_llm = None
    gemini_llm = None
    gemini_backup = None

    if settings.GOOGLE_API_KEY:
        from langchain_google_genai import ChatGoogleGenerativeAI
        gemini_llm = ChatGoogleGenerativeAI(
            model=gemini_model,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=temperature,
            max_retries=1,
            timeout=20.0,
        )
        backup_model = "gemini-3.5-flash-lite" if gemini_model != "gemini-3.5-flash-lite" else "gemini-3.5-flash"
        gemini_backup = ChatGoogleGenerativeAI(
            model=backup_model,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=temperature,
            max_retries=1,
            timeout=20.0,
        )

    if settings.GROQ_API_KEY:
        from langchain_groq import ChatGroq
        groq_llm = ChatGroq(
            model=groq_model,
            groq_api_key=settings.GROQ_API_KEY,
            temperature=temperature,
            max_retries=1,
            timeout=20.0,
        )

    # Both keys → Gemini primary (1,000,000 TPM limit) with Gemini backup & Groq fallbacks
    if gemini_llm and groq_llm:
        logger.info(
            "[LLM Factory] %s role: primary=%s (Gemini), fallbacks=[%s (Gemini), %s (Groq)]",
            role, gemini_model, backup_model, groq_model,
        )
        return gemini_llm.with_fallbacks([gemini_backup, groq_llm])

    # Google key only
    if gemini_llm:
        logger.info("[LLM Factory] %s role: primary=%s (Gemini), fallback=%s (Gemini)", role, gemini_model, backup_model)
        return gemini_llm.with_fallbacks([gemini_backup])

    # Groq key only
    if groq_llm:
        logger.info("[LLM Factory] %s role: primary=%s (Groq)", role, groq_model)
        return groq_llm

    logger.warning("[LLM Factory] No API keys configured for role=%s", role)
    return None
