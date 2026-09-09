"""
Live Draft Room Strategist sub-agent.
Evaluates VORP rankings, navigates tier cliffs, and plans around positional runs.
"""

from app.core.config import settings
from app.core.llm_factory import get_llm
from app.agents.prompts import DRAFT_AGENT_SYSTEM_PROMPT
from app.tools.draft_tools import (
    get_live_draft_board,
    get_vorp_rankings,
    get_tier_breakdown,
    get_player_historical_profile,
    get_user_keeper_profile,
    get_redis_draft_digest
)
from app.tools.player_tools import resolve_player

DRAFT_TOOLS = [
    resolve_player,
    get_live_draft_board,
    get_vorp_rankings,
    get_tier_breakdown,
    get_player_historical_profile,
    get_user_keeper_profile,
    get_redis_draft_digest
]


def create_draft_agent():
    """Creates ReAct worker node for draft agent."""
    from langgraph.prebuilt import create_react_agent
    llm = get_llm(role="heavy", temperature=0.2)
    if llm is None:
        return None
    return create_react_agent(
        model=llm,
        tools=DRAFT_TOOLS,
        name="draft_agent",
        prompt=DRAFT_AGENT_SYSTEM_PROMPT
    )
