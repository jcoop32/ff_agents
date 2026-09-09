"""
LangGraph AgentState schema.
Maintains conversational messages, league rules context, and session metadata.
"""

from typing import Annotated, TypedDict, Optional, Dict, Any, List
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Global state shared across Supervisor and specialized Worker sub-agents."""
    messages: Annotated[List[AnyMessage], add_messages]
    league_context: Dict[str, Any]
    active_week: Optional[int]
    draft_id: Optional[str]
    user_roster_id: Optional[str]
