"""
Lineup & Waiver Optimizer sub-agent.
Focuses on weekly sit/start matchups, ceiling vs. floor balances, waiver pickup evaluation,
zero-cost IR stashes, and optimal bench cut candidates.
"""

from app.core.config import settings
from app.core.llm_factory import get_llm
from app.agents.prompts import LINEUP_AGENT_SYSTEM_PROMPT
from app.tools.lineup_tools import (
    get_matchup_projections,
    get_defensive_matchup_data,
    get_available_waiver_pool,
    evaluate_waiver_pickup_tool,
)
from app.tools.league_activity_tools import get_waiver_targets, add_waiver_target
from app.tools.player_tools import resolve_player

LINEUP_TOOLS = [
    resolve_player,
    evaluate_waiver_pickup_tool,
    get_matchup_projections,
    get_defensive_matchup_data,
    get_available_waiver_pool,
    get_waiver_targets,
    add_waiver_target
]


def create_lineup_agent():
    """Creates ReAct worker node for lineup & waiver agent."""
    from langgraph.prebuilt import create_react_agent
    llm = get_llm(role="heavy", temperature=0.2)
    if llm is None:
        return None
    return create_react_agent(
        model=llm,
        tools=LINEUP_TOOLS,
        name="lineup_waiver_agent",
        prompt=LINEUP_AGENT_SYSTEM_PROMPT
    )
