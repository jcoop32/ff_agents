"""
General Manager (Supervisor / Orchestrator) Multi-Agent System.
Synthesizes sub-agent recommendations, resolves conflicts, enforces league rules,
and implements zero-cost response caching and budget guards.
"""

import logging
from typing import Optional, Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from app.core.config import settings
from app.core.rate_limiter import RateLimiter, RateLimitExceeded
from app.core.llm_cache import LLMCache
from app.core.llm_factory import get_llm
from app.agents.state import AgentState
from app.agents.prompts import GENERAL_MANAGER_SYSTEM_PROMPT
from app.agents.stats_agent import create_stats_agent
from app.agents.reporting_agent import create_reporting_agent
from app.agents.trade_agent import create_trade_agent
from app.agents.draft_agent import create_draft_agent
from app.agents.lineup_agent import create_lineup_agent

logger = logging.getLogger(__name__)


class SupervisorGraphManager:
    """Compiles and manages the hierarchical multi-agent workflow."""

    _compiled_graph = None

    @classmethod
    def compile_graph(cls):
        """Compiles the multi-agent graph with fallback handling."""
        if cls._compiled_graph is not None:
            return cls._compiled_graph

        supervisor_model = get_llm(role="supervisor", temperature=0.2)
        if supervisor_model is None:
            logger.warning("No LLM API keys configured. Running graph in mock passthrough mode.")
            return None

        # Instantiate sub-agents
        stats_worker = create_stats_agent()
        reporting_worker = create_reporting_agent()
        trade_worker = create_trade_agent()
        draft_worker = create_draft_agent()
        lineup_worker = create_lineup_agent()

        agents_list = [
            a for a in [stats_worker, reporting_worker, trade_worker, draft_worker, lineup_worker]
            if a is not None
        ]

        # Attempt to use langgraph_supervisor if installed and agents available
        try:
            from langgraph_supervisor import create_supervisor
            workflow = create_supervisor(
                agents=agents_list,
                model=supervisor_model,
                prompt=GENERAL_MANAGER_SYSTEM_PROMPT
            )
            cls._compiled_graph = workflow.compile()
            logger.info("Compiled multi-agent supervisor graph via langgraph_supervisor.")
            return cls._compiled_graph
        except Exception as e:
            logger.info("Using native StateGraph ReAct supervisor pattern: %s", str(e))

        # Native StateGraph fallback pattern
        from langgraph.graph import StateGraph, START, END
        builder = StateGraph(AgentState)

        async def gm_node(state: AgentState) -> Dict[str, Any]:
            # Rate limit budget check
            provider = "gemini" if settings.GOOGLE_API_KEY else "groq"
            await RateLimiter.check_budget(provider, estimated_tokens=800)

            messages = [SystemMessage(content=GENERAL_MANAGER_SYSTEM_PROMPT)] + state["messages"]
            response = await supervisor_model.ainvoke(messages)
            content_str = str(response.content) if hasattr(response, "content") else ""
            await RateLimiter.record_usage(provider, actual_tokens=len(content_str.split()) * 2)

            return {"messages": [response]}

        builder.add_node("general_manager", gm_node)
        builder.add_edge(START, "general_manager")
        builder.add_edge("general_manager", END)

        cls._compiled_graph = builder.compile()
        return cls._compiled_graph


def get_supervisor_graph():
    """Returns compiled supervisor graph instance."""
    return SupervisorGraphManager.compile_graph()


async def ask_general_manager(
    user_query: str,
    active_week: Optional[int] = 1,
    draft_id: Optional[str] = None
) -> str:
    """
    High-level entrypoint for querying the General Manager.
    Leverages Redis response cache first to conserve 100% of LLM tokens.
    """
    # 1. Check response cache
    cache_key = LLMCache.generate_cache_key(
        model=settings.SUPERVISOR_MODEL,
        system_prompt=GENERAL_MANAGER_SYSTEM_PROMPT,
        user_query=user_query,
        context_payload={"scoring": settings.SCORING_FORMAT, "week": active_week}
    )
    cached = await LLMCache.get(cache_key)
    if cached:
        return cached

    # 2. Query Redis In-Season Digest (<2ms)
    redis_digest_ctx = ""
    try:
        from app.pipelines.daily_scheduler import DailySchedulerService
        digest = await DailySchedulerService.get_cached_digest()
        if digest:
            top_vorp = ", ".join([f"{t['name']} (+{t['vorp']} VORP)" for t in digest.get("top_vorp_targets", [])[:5]])
            top_inj = ", ".join([f"{i['name']} ({i['status']}: {i['notes']})" for i in digest.get("injury_watchlist", [])[:4]])

            # Build in-season context
            redis_digest_ctx = (
                f"\n\n[LIVE REDIS IN-SEASON INTELLIGENCE - UPDATED DAILY]:\n"
                f"- Season Phase: IN-SEASON (Draft complete, Week {active_week}). "
                f"Focus on weekly lineup optimization, waiver wire pickups, trade evaluation, and matchup analysis.\n"
                f"- League Format: 12-team Full PPR starting 3 WRs + 1 FLEX. 36 WRs start weekly—WR depth is critical.\n"
                f"- Top Available VORP Targets (Free Agents): {top_vorp}\n"
                f"- Active Injury Watchlist: {top_inj}\n"
            )

            # Add waiver watchlist targets if any
            try:
                from app.core.redis_client import get_redis
                r = await get_redis()
                watchlist = await r.smembers("user:waiver_targets")
                if watchlist:
                    names = ", ".join([n if isinstance(n, str) else n.decode("utf-8") for n in watchlist])
                    redis_digest_ctx += f"- User's Active Waiver Watchlist: {names}\n"
            except Exception:
                pass
    except Exception as e:
        logger.warning("Could not read Redis digest: %s", str(e))

    # 3. Execute graph
    graph = get_supervisor_graph()

    # Detect user surveillance / tracking requests ("keep up with Caleb Williams", "track CMC", etc.)
    import re
    tracking_confirmation = ""
    lower_query = user_query.lower()
    tracking_triggers = ["keep up with", "monitor", "track", "watch", "stay on top of", "alert me on", "follow"]

    if any(t in lower_query for t in tracking_triggers):
        try:
            from app.pipelines.scheduler_api import SchedulerAPI
            # Extract player name after tracking verb
            match = re.search(
                r"(?:keep up with|monitor|track|watch|stay on top of|alert me on|follow)\s+(?:the latest\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
                user_query
            )
            target_player = match.group(1).strip() if match else None

            # If not capitalized, try matching general name pattern
            if not target_player:
                match2 = re.search(
                    r"(?:keep up with|monitor|track|watch|stay on top of|alert me on|follow)\s+(?:the latest\s+)?([a-z]+(?:\s+[a-z]+)+)",
                    user_query,
                    re.IGNORECASE
                )
                if match2:
                    raw_name = match2.group(1).strip()
                    # Filter out stopwords like "news", "updates", "status"
                    words = [w for w in raw_name.split() if w.lower() not in ["the", "news", "injury", "status", "latest", "updates", "for", "me", "this", "week"]]
                    if len(words) >= 2:
                        target_player = " ".join(words).title()

            if target_player:
                job = await SchedulerAPI.spawn_tracking_job(
                    player_name=target_player,
                    focus_areas=["injury", "depth_chart", "practice", "sentiment"],
                    frequency_minutes=60,
                    duration_hours=48,
                    reason=f"User requested: '{user_query}'",
                    source="user",
                )
                tracking_confirmation = (
                    f"\n\n---\n"
                    f"🎯 **Autonomous Surveillance Active**: I have scheduled a background watch on **{target_player}** "
                    f"(every 60m). The system is actively scanning web news, practice logs (DNP/LP), and ESPN injury tags. "
                    f"If their status deteriorates, surveillance will automatically escalate to every 15m. "
                    f"You can view, modify, or cancel this job anytime in the **Tracking** dashboard."
                )
        except Exception as te:
            logger.warning("Error spawning tracking job from query: %s", str(te))

    if graph is None:
        # In-season mock fallback
        fallback_msg = (
            "**Waiver Wire Verdict**: Check the available free agent pool for high-upside pickups at WR and RB.\n\n"
            "- **The Case**: In your 12-team Full PPR league starting 3 WRs + 1 FLEX, waiver wire depth at wide receiver "
            "is critical. Monitor snap share increases and target share trends to identify breakout candidates before "
            "your league-mates claim them.\n"
            "- **Key Action**: Review your bench for droppable assets (players with <30% snap share) and prioritize "
            "high-volume targets emerging from injury replacements or scheme changes."
        )
        return fallback_msg + tracking_confirmation

    system_prompt_with_redis = GENERAL_MANAGER_SYSTEM_PROMPT + redis_digest_ctx

    state_input: AgentState = {
        "messages": [
            SystemMessage(content=system_prompt_with_redis),
            HumanMessage(content=user_query)
        ],
        "league_context": {
            "format": settings.SCORING_FORMAT,
            "league_size": settings.LEAGUE_SIZE,
            "num_wr": settings.NUM_WR_SLOTS,
            "has_flex": settings.HAS_FLEX,
            "team_name": "Team Cooper",
            "season_phase": "IN_SEASON"
        },
        "active_week": active_week,
        "draft_id": draft_id,
        "user_roster_id": str(settings.ESPN_TEAM_ID)
    }

    try:
        result = await graph.ainvoke(state_input)
        last_message = result["messages"][-1]
        raw_content = last_message.content if hasattr(last_message, "content") else str(last_message)
        if isinstance(raw_content, list):
            text_parts = [
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in raw_content
            ]
            response_text = "".join(text_parts)
        else:
            response_text = str(raw_content)
    except Exception as e:
        logger.warning("Graph execution error, attempting direct LLM fallback: %s", str(e))
        try:
            fallback_llm = get_llm(role="heavy", temperature=0.2)
            if fallback_llm:
                resp = await fallback_llm.ainvoke(state_input["messages"])
                raw_resp = resp.content if hasattr(resp, "content") else str(resp)
                if isinstance(raw_resp, list):
                    text_parts = [
                        item.get("text", "") if isinstance(item, dict) else str(item)
                        for item in raw_resp
                    ]
                    response_text = "".join(text_parts)
                else:
                    response_text = str(raw_resp)
            else:
                raise RuntimeError("No LLM available for fallback")
        except Exception as e2:
            logger.error("Direct fallback also failed: %s", str(e2))
            response_text = (
                "**In-Season Advisory**: Review your roster for lineup optimization and waiver opportunities.\n\n"
                "- **Weekly Focus**: In your 12-team Full PPR league (3 WR + 1 FLEX), monitor practice reports for "
                "injury designations that create opportunity upgrades. Target snap share increases >15% week-over-week "
                "as the strongest predictor of emerging waiver value.\n"
                "- **Action Items**: Check your matchup projections, review the free agent pool for high-volume targets, "
                "and evaluate any trade offers through the lens of starting lineup improvement."
            )

    # Clean out thinking tags if present in output
    response_text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()
    if not response_text:
        response_text = (
            "**In-Season Advisory**: Review your roster for lineup optimization and waiver opportunities.\n\n"
            "- **Weekly Focus**: In your 12-team Full PPR league (3 WR + 1 FLEX), monitor practice reports for "
            "injury designations that create opportunity upgrades. Target snap share increases >15% week-over-week "
            "as the strongest predictor of emerging waiver value.\n"
            "- **Action Items**: Check your matchup projections, review the free agent pool for high-volume targets, "
            "and evaluate any trade offers through the lens of starting lineup improvement."
        )
    final_output = response_text + tracking_confirmation

    # 4. Store in cache
    await LLMCache.set(cache_key, final_output)
    return final_output
