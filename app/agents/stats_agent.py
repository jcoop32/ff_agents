"""
Stats Analyst sub-agent.
Focuses on underlying volume, opportunity share, xFP, and regression deltas.
"""

from typing import Optional
from langchain_core.tools import BaseTool
from app.core.config import settings
from app.core.llm_factory import get_llm
from app.agents.prompts import STATS_ANALYST_SYSTEM_PROMPT
from app.tools.stats_tools import (
    get_player_metrics,
    get_advanced_efficiency,
    get_expected_fantasy_points,
    get_historical_baselines
)
from app.tools.player_tools import resolve_player

STATS_TOOLS = [
    resolve_player,
    get_player_metrics,
    get_advanced_efficiency,
    get_expected_fantasy_points,
    get_historical_baselines
]


def create_stats_agent():
    """Creates ReAct worker node for stats analyst."""
    from langgraph.prebuilt import create_react_agent
    llm = get_llm(role="fast", temperature=0.1)
    if llm is None:
        return None
    return create_react_agent(
        model=llm,
        tools=STATS_TOOLS,
        name="stats_analyst",
        prompt=STATS_ANALYST_SYSTEM_PROMPT
    )
