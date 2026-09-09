"""
Reporting & Medical Intel Analyst sub-agent.
Interprets injury logs, practice progression, coach quotes, and weather.
"""

from typing import Optional
from app.core.config import settings
from app.core.llm_factory import get_llm
from app.agents.prompts import REPORTING_INTEL_SYSTEM_PROMPT
from app.tools.intel_tools import (
    get_practice_reports,
    get_player_news_feed,
    get_game_weather,
    get_depth_chart_status
)
from app.tools.player_tools import resolve_player

REPORTING_TOOLS = [
    resolve_player,
    get_practice_reports,
    get_player_news_feed,
    get_game_weather,
    get_depth_chart_status
]


def create_reporting_agent():
    """Creates ReAct worker node for reporting agent."""
    from langgraph.prebuilt import create_react_agent
    # Reporting agent prefers Gemini (higher free RPD), so use "fast" role
    # which maps to REPORTING_MODEL on Gemini side
    llm = get_llm(role="fast", temperature=0.2)
    if llm is None:
        return None
    return create_react_agent(
        model=llm,
        tools=REPORTING_TOOLS,
        name="reporting_agent",
        prompt=REPORTING_INTEL_SYSTEM_PROMPT
    )
