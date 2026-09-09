"""
Trade Specialist sub-agent.
Evaluates trade equity, Rest-of-Season VORP, roster consolidation,
target player acquisition packages, and win-win trade opportunities across league rosters.
"""

from app.core.config import settings
from app.core.llm_factory import get_llm
from app.agents.prompts import TRADE_AGENT_SYSTEM_PROMPT
from app.tools.trade_tools import (
    get_league_rosters_tool,
    calculate_trade_equity_tool,
    simulate_starting_lineup_delta_tool,
    find_player_fantasy_owner_tool,
    analyze_team_roster_needs_tool,
    get_league_needs_matrix_tool,
    find_trade_packages_to_acquire_tool,
    find_trade_packages_for_player_tool,
)
from app.tools.player_tools import resolve_player

TRADE_TOOLS = [
    resolve_player,
    find_player_fantasy_owner_tool,
    analyze_team_roster_needs_tool,
    get_league_needs_matrix_tool,
    find_trade_packages_to_acquire_tool,
    find_trade_packages_for_player_tool,
    calculate_trade_equity_tool,
    simulate_starting_lineup_delta_tool,
    get_league_rosters_tool,
]


def create_trade_agent():
    """Creates ReAct worker node for trade agent."""
    from langgraph.prebuilt import create_react_agent
    llm = get_llm(role="heavy", temperature=0.2)
    if llm is None:
        return None
    return create_react_agent(
        model=llm,
        tools=TRADE_TOOLS,
        name="trade_agent",
        prompt=TRADE_AGENT_SYSTEM_PROMPT
    )
