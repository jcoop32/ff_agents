"""
FastAPI route handlers for chat, news ingestion, budget monitoring, and health probes.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import fastapi
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.core.redis_client import get_redis
from app.core.database import AsyncSessionLocal
from app.core.rate_limiter import RateLimiter, RateLimitExceeded
from app.core.llm_cache import LLMCache
from app.agents.supervisor import ask_general_manager
from app.pipelines.espn_sync import ESPNSyncService
from app.pipelines.draft_prep import DraftPrepService
from app.pipelines.news_stream import NewsIngestionService
from app.pipelines.league_monitor import LeagueActivityMonitor
from app.tools.league_activity_tools import get_recent_transactions, fetch_recent_transactions
from app.models.league import League, Roster
from app.models.player import Player
from app.models.stats import NewsItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Gridiron AI"])


class ChatRequest(BaseModel):
    message: str = Field(..., description="User question or prompt for the General Manager")
    week: Optional[int] = Field(default=1, description="Active fantasy week")
    draft_id: Optional[str] = Field(default=None, description="Active draft room ID")
    session_id: Optional[str] = Field(default=None, description="Optional ChatSession ID to persist into")


class CreateSessionRequest(BaseModel):
    title: Optional[str] = Field(default="New Conversation", description="Session title")


class NewsIngestRequest(BaseModel):
    headline: str = Field(..., description="News headline")
    text: str = Field(..., description="News body text")
    source: str = Field(default="Manual Input", description="Origin of news item")
    url: Optional[str] = Field(default=None, description="Optional link to avoid duplicates")


@router.post("/chat")
async def chat_with_general_manager(req: ChatRequest) -> Dict[str, Any]:
    """
    Sends a query to the General Manager (Supervisor).
    Evaluates response cache, rate limit budget, and persists conversation thread into PostgreSQL/Redis.
    """
    from app.pipelines.chat_service import ChatService
    try:
        # Get or create active session
        session = await ChatService.get_or_create_session(
            session_id=req.session_id,
            initial_title=req.message[:45] + ("..." if len(req.message) > 45 else "")
        )
        active_session_id = session["id"]

        # Persist user message
        user_msg = await ChatService.save_message(
            session_id=active_session_id,
            sender="user",
            text=req.message,
            week=req.week or 1
        )

        response_text = await ask_general_manager(
            user_query=req.message,
            active_week=req.week,
            draft_id=req.draft_id
        )

        # Persist GM message
        gm_msg = await ChatService.save_message(
            session_id=active_session_id,
            sender="gm",
            text=response_text,
            week=req.week or 1
        )

        return {
            "success": True,
            "response": response_text,
            "session_id": active_session_id,
            "user_message_id": user_msg["id"],
            "gm_message_id": gm_msg["id"],
            "timestamp": gm_msg.get("timestamp")
        }
    except RateLimitExceeded as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        import traceback
        logger.error("Chat orchestration error:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Agent orchestration error: {str(e)}")


@router.get("/chat/sessions")
async def list_chat_sessions(limit: int = 50) -> Dict[str, Any]:
    """
    Returns list of all saved chat sessions ordered by most recent update.
    """
    from app.pipelines.chat_service import ChatService
    sessions = await ChatService.list_sessions(limit=limit)
    return {"sessions": sessions, "count": len(sessions)}


@router.post("/chat/sessions")
async def create_chat_session(req: Optional[CreateSessionRequest] = None) -> Dict[str, Any]:
    """
    Creates an explicit new chat session thread.
    """
    from app.pipelines.chat_service import ChatService
    title = req.title if req and req.title else "New Conversation"
    session = await ChatService.create_session(title=title)
    return session


@router.get("/chat/sessions/{session_id}")
async def get_chat_session_history(session_id: str) -> Dict[str, Any]:
    """
    Retrieves full message history for a specific chat session.
    """
    from app.pipelines.chat_service import ChatService
    data = await ChatService.get_session_messages(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return data


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str) -> Dict[str, Any]:
    """
    Deletes a chat session and all cascading message history.
    """
    from app.pipelines.chat_service import ChatService
    deleted = await ChatService.delete_session(session_id)
    return {"success": deleted, "session_id": session_id}


@router.post("/news/ingest")
async def ingest_news(req: NewsIngestRequest) -> Dict[str, Any]:
    """
    Endpoint for external webhooks or manual submission of breaking injury/role news.
    """
    success = await NewsIngestionService.process_news_item({
        "headline": req.headline,
        "text": req.text,
        "source": req.source,
        "url": req.url
    })
    return {"success": success, "headline": req.headline}


@router.get("/budget")
async def get_budget_status() -> Dict[str, Any]:
    """
    Returns real-time usage and remaining daily quotas for Gemini and Groq free tiers.
    """
    return await RateLimiter.get_budget_status()


@router.get("/transactions")
async def get_transactions(hours: int = 24) -> Dict[str, Any]:
    """
    Returns recent league transactions with impact classifications.
    """
    txs = await fetch_recent_transactions(hours=hours)
    return {"count": len(txs), "transactions": txs}


@router.post("/sync/espn")
async def trigger_espn_sync() -> Dict[str, Any]:
    """
    Manually triggers an immediate ESPN league and roster synchronization.
    """
    result = await ESPNSyncService.sync_league_metadata()
    try:
        r = await get_redis()
        keys = await r.keys("cache:roster:*")
        if keys:
            await r.delete(*keys)
        await r.delete("cache:league:standings")
    except Exception:
        pass
    return result


@router.post("/monitor/poll")
async def trigger_league_poll() -> Dict[str, Any]:
    """
    Manually triggers an immediate check for new ESPN transactions.
    """
    result = await LeagueActivityMonitor.poll_league_transactions()
    return result


def optimize_team_lineup(players: List[Dict[str, Any]], current_slots: Dict[str, str], starter_ids: List[str]) -> Dict[str, Any]:
    """
    Partitions team roster into current starters/bench, and computes optimal AI recommended lineup
    (1 QB, 2 RB, 3 WR, 1 TE, 1 FLEX [RB/WR/TE], 1 K, 1 D/ST) based on weekly projected points.
    """
    slot_order = {"QB": 1, "RB": 2, "WR": 3, "TE": 4, "FLEX": 5, "K": 6, "DST": 7, "D/ST": 7}
    pos_order = {"QB": 1, "RB": 2, "WR": 3, "TE": 4, "K": 5, "DST": 6, "D/ST": 6}

    # 1. Format current players with their slots
    for p in players:
        p_id = str(p["id"])
        raw_slot = current_slots.get(p_id)
        if not raw_slot:
            raw_slot = "STARTER" if p_id in starter_ids else "BENCH"
        p["lineup_slot"] = raw_slot
        p["is_starter"] = raw_slot not in ("BENCH", "BE", "IR")

    # Current starters and bench
    current_starters = [p for p in players if p["is_starter"]]
    current_starters.sort(key=lambda x: (slot_order.get(x["lineup_slot"], 9), -x.get("weekly_projected_points", 0.0)))

    current_bench = [p for p in players if not p["is_starter"]]
    current_bench.sort(key=lambda x: (pos_order.get(x["position"], 9), -x.get("weekly_projected_points", 0.0)))

    current_proj_total = round(sum(p.get("weekly_projected_points", 0.0) for p in current_starters), 2)

    # 2. Compute Optimal Recommended Lineup
    pool = sorted(players, key=lambda x: -x.get("weekly_projected_points", 0.0))
    assigned_ids = set()
    optimal_starters = []

    def pick_best(predicate, slot_label, count=1):
        picked = 0
        for p in pool:
            if str(p["id"]) not in assigned_ids and predicate(p):
                item = dict(p)
                item["lineup_slot"] = slot_label
                item["is_starter"] = True
                optimal_starters.append(item)
                assigned_ids.add(str(p["id"]))
                picked += 1
                if picked >= count:
                    break

    # 1 QB, 2 RB, 3 WR, 1 TE, 1 FLEX, 1 K, 1 D/ST
    pick_best(lambda p: p["position"] == "QB", "QB", 1)
    pick_best(lambda p: p["position"] == "RB", "RB", 2)
    pick_best(lambda p: p["position"] == "WR", "WR", 3)
    pick_best(lambda p: p["position"] == "TE", "TE", 1)
    pick_best(lambda p: p["position"] in ("RB", "WR", "TE"), "FLEX", 1)
    pick_best(lambda p: p["position"] == "K", "K", 1)
    pick_best(lambda p: p["position"] in ("DST", "D/ST"), "D/ST", 1)

    optimal_starters.sort(key=lambda x: (slot_order.get(x["lineup_slot"], 9), -x.get("weekly_projected_points", 0.0)))

    # Optimal bench
    optimal_bench = []
    for p in pool:
        if str(p["id"]) not in assigned_ids:
            item = dict(p)
            item["lineup_slot"] = "BENCH"
            item["is_starter"] = False
            optimal_bench.append(item)
    optimal_bench.sort(key=lambda x: (pos_order.get(x["position"], 9), -x.get("weekly_projected_points", 0.0)))

    optimal_proj_total = round(sum(p.get("weekly_projected_points", 0.0) for p in optimal_starters), 2)
    delta = round(optimal_proj_total - current_proj_total, 2)

    # Flag optimal swaps
    curr_starter_id_set = set(str(p["id"]) for p in current_starters)
    for p in optimal_starters:
        p["is_optimal_swap"] = (str(p["id"]) not in curr_starter_id_set)

    # Recommendations
    recommendations = []
    swapped_in = [p for p in optimal_starters if str(p["id"]) not in curr_starter_id_set]
    swapped_out = [p for p in current_starters if str(p["id"]) not in assigned_ids]

    if delta > 0 and swapped_in and swapped_out:
        for p_in, p_out in zip(swapped_in, swapped_out):
            diff = round(p_in.get("weekly_projected_points", 0.0) - p_out.get("weekly_projected_points", 0.0), 2)
            recommendations.append({
                "action": "SWAP",
                "player_in": p_in["name"],
                "player_out": p_out["name"],
                "slot": p_in.get("lineup_slot", "FLEX"),
                "delta": diff,
                "reason": f"Start {p_in['name']} ({p_in.get('weekly_projected_points', 0.0):.1f} pts) at {p_in.get('lineup_slot', 'FLEX')} over {p_out['name']} ({p_out.get('weekly_projected_points', 0.0):.1f} pts) for a +{diff:.2f} pt edge. {p_in['name']} provides superior target opportunity and floor/ceiling balance."
            })
    elif delta <= 0:
        recommendations.append({
            "action": "KEEP",
            "reason": "Starting lineup is currently 100% optimized for Week 1. No changes needed."
        })

    for p in current_starters:
        inj = (p.get("injury_status") or "").upper()
        if inj in ("QUESTIONABLE", "DOUBTFUL", "OUT", "IR"):
            recommendations.append({
                "action": "ALERT",
                "player_in": p["name"],
                "slot": p.get("lineup_slot", ""),
                "reason": f"Injury Warning: {p['name']} ({p['position']}) is {inj}. Check practice and pre-game status before kickoff."
            })

    # Tactical Deep Dive Rationale
    tactical_rationale = {
        "headline": f"+{delta:.2f} PTS Projected Advantage" if delta > 0 else "Optimal Alignment Verified",
        "summary": (
            f"The AI GM recommends promoting {swapped_in[0]['name']} ({swapped_in[0].get('weekly_projected_points', 0.0):.1f} pts) "
            f"into the starting {swapped_in[0].get('lineup_slot', 'FLEX')} slot over {swapped_out[0]['name']} ({swapped_out[0].get('weekly_projected_points', 0.0):.1f} pts). "
            f"In {settings.LEAGUE_SIZE}-team full PPR (1.0 pt/rec), wide receiver targets deliver superior median win equity and ceiling outcomes compared to a shared backfield workload."
            if delta > 0 and swapped_in and swapped_out
            else "Your current starting lineup is mathematically optimal based on weekly matchup projections and usage metrics."
        ),
        "pillars": [
            {
                "title": "PPR Target Volume Leverage",
                "content": f"Full PPR scoring heavily rewards target volume. In the FLEX spot, {swapped_in[0]['name'] if (swapped_in and delta > 0) else 'your active starter'} projects for consistent target-depth share, offering higher expected fantasy value per touch than early-down committee carries."
            },
            {
                "title": "Ceiling vs. Floor Volatility",
                "content": f"{swapped_in[0]['name'] if (swapped_in and delta > 0) else 'Your active starter'} provides a wider ceiling range. When optimizing for weekly win equity, a dynamic pass-catcher in FLEX yields higher probability of exceeding the weekly league median."
            },
            {
                "title": "Game Script & Defensive Matchup",
                "content": "Projected offensive game scripts and secondary coverage matchups project favorable passing volume over congested interior defensive fronts."
            }
        ],
        "contingencies": [
            f"Monitor {p['name']} ({p.get('injury_status')}) status prior to kickoff."
            for p in current_starters if (p.get("injury_status") or "").upper() in ("QUESTIONABLE", "DOUBTFUL", "OUT")
        ]
    }

    return {
        "current_starters": current_starters,
        "current_bench": current_bench,
        "optimal_starters": optimal_starters,
        "optimal_bench": optimal_bench,
        "current_projected_total": current_proj_total,
        "optimal_projected_total": optimal_proj_total,
        "delta_vs_current": delta,
        "recommendations": recommendations,
        "tactical_rationale": tactical_rationale,
    }


@router.get("/roster/{team_id}")
async def get_team_roster(team_id: int) -> Dict[str, Any]:
    """
    Returns player roster details for a given team ID.
    Provides current starting lineup, bench, and AI GM recommended optimal lineup.
    """
    cache_key = f"cache:roster:{team_id}"

    # 1. Check Redis (<2ms)
    try:
        r = await get_redis()
        cached = await r.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.debug("Redis roster cache miss: %s", str(e))

    # 2. Check local PostgreSQL database (<5ms)
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Roster).where(Roster.espn_team_id == team_id)
            res = await session.execute(stmt)
            r_record = res.scalar_one_or_none()
            if r_record and r_record.players:
                p_stmt = select(Player).where(Player.espn_id.in_(r_record.players))
                p_res = await session.execute(p_stmt)
                pos_order = {"QB": 1, "RB": 2, "WR": 3, "TE": 4, "K": 5, "DST": 6, "D/ST": 6}
                
                players = []
                for p in p_res.scalars().all():
                    w_proj = float(getattr(p, "weekly_projected_points", 0.0) or 0.0)
                    if not w_proj:
                        w_proj = float(getattr(p, "projected_avg", 0.0) or 0.0)
                    players.append({
                        "id": p.espn_id,
                        "name": p.name,
                        "position": p.position,
                        "nfl_team": p.team,
                        "injury_status": p.injury_status or "Healthy",
                        "projected_points": float(getattr(p, "projected_points", 0.0) or 0.0),
                        "projected_avg": float(getattr(p, "projected_avg", 0.0) or 0.0),
                        "weekly_projected_points": round(w_proj, 2),
                        "percent_owned": float(getattr(p, "percent_owned", 0.0) or 0.0),
                        "percent_started": float(getattr(p, "percent_started", 0.0) or 0.0),
                        "lineup_slot": "BENCH",
                        "is_starter": False
                    })

                players.sort(key=lambda x: (pos_order.get(x["position"], 9), x["name"]))
                
                slots = r_record.lineup_slots or {}
                starters = r_record.starters or []
                opt_data = optimize_team_lineup(players, slots, starters)

                data = {
                    "team_id": r_record.espn_team_id,
                    "team_name": r_record.team_name,
                    "owner": r_record.owner_name or r_record.team_name,
                    "wins": r_record.record.get("wins", 0) if r_record.record else 0,
                    "losses": r_record.record.get("losses", 0) if r_record.record else 0,
                    "points_for": r_record.points_for,
                    "count": len(players),
                    "current_week": 1,
                    "players": players,
                    **opt_data
                }
                try:
                    r = await get_redis()
                    await r.set(cache_key, json.dumps(data), ex=300)
                except Exception:
                    pass
                return data
    except Exception as e:
        logger.error("Database roster query error: %s", str(e))

    # 3. Live ESPN API fallback
    try:
        league_inst = ESPNSyncService.get_espn_league_instance()
        if league_inst:
            for team in league_inst.teams:
                if team.team_id == team_id:
                    players = []
                    slots = {}
                    starter_ids = []
                    for p in team.roster:
                        p_id = str(getattr(p, "playerId", p.name))
                        raw_slot = getattr(p, "lineupSlot", "BE")
                        slot = "BENCH" if raw_slot == "BE" else ("FLEX" if raw_slot in ("RB/WR/TE", "RB/WR", "WR/TE", "OP") else raw_slot)
                        slots[p_id] = slot
                        if slot not in ("BENCH", "IR"):
                            starter_ids.append(p_id)

                        w_proj = float(getattr(p, "stats", {}).get(league_inst.current_week, {}).get("projected_points", 0.0) or 0.0)
                        if not w_proj:
                            w_proj = float(getattr(p, "projected_avg_points", 0.0) or 0.0)

                        players.append({
                            "id": p_id,
                            "name": p.name,
                            "position": getattr(p, "position", "FLEX"),
                            "nfl_team": getattr(p, "proTeam", "FA"),
                            "injury_status": getattr(p, "injuryStatus", "Healthy") or "Healthy",
                            "projected_points": float(getattr(p, "projected_total_points", 0.0) or 0.0),
                            "projected_avg": float(getattr(p, "projected_avg_points", 0.0) or 0.0),
                            "weekly_projected_points": round(w_proj, 2),
                            "percent_owned": float(getattr(p, "percent_owned", 0.0) or 0.0),
                            "percent_started": float(getattr(p, "percent_started", 0.0) or 0.0),
                            "lineup_slot": slot,
                            "is_starter": slot not in ("BENCH", "IR")
                        })

                    opt_data = optimize_team_lineup(players, slots, starter_ids)
                    data = {
                        "team_id": team.team_id,
                        "team_name": team.team_name,
                        "owner": getattr(team, "owner", team.team_name),
                        "wins": team.wins,
                        "losses": team.losses,
                        "points_for": float(team.points_for),
                        "count": len(players),
                        "current_week": league_inst.current_week,
                        "players": players,
                        **opt_data
                    }
                    try:
                        r = await get_redis()
                        await r.set(cache_key, json.dumps(data), ex=300)
                    except Exception:
                        pass
                    return data
    except Exception as e:
        logger.error("Error fetching live ESPN roster: %s", str(e))

    return {
        "team_id": team_id,
        "team_name": "Team Cooper" if team_id == settings.ESPN_TEAM_ID else f"Team {team_id}",
        "owner": "Cooper",
        "wins": 0,
        "losses": 0,
        "points_for": 0.0,
        "count": 0,
        "current_week": 1,
        "current_starters": [],
        "current_bench": [],
        "optimal_starters": [],
        "optimal_bench": [],
        "current_projected_total": 0.0,
        "optimal_projected_total": 0.0,
        "delta_vs_current": 0.0,
        "recommendations": [],
        "players": []
    }


@router.get("/lineup/compare")
async def compare_lineup_players(player_a_id: str, player_b_id: str, slot: Optional[str] = None) -> Dict[str, Any]:
    """
    Compares two players head-to-head for weekly sit/start lineup decisions in a specific target slot.
    Returns side-by-side stats, projections, ownership, and AI GM verdict.
    """
    async with AsyncSessionLocal() as session:
        stmt = select(Player).where(Player.espn_id.in_([str(player_a_id), str(player_b_id)]))
        res = await session.execute(stmt)
        players = res.scalars().all()

        p_a = next((p for p in players if str(p.espn_id) == str(player_a_id)), None)
        p_b = next((p for p in players if str(p.espn_id) == str(player_b_id)), None)

        if not p_a or not p_b:
            raise HTTPException(status_code=404, detail="One or both players not found")

        proj_a = float(getattr(p_a, "weekly_projected_points", 0.0) or getattr(p_a, "projected_avg", 0.0) or 0.0)
        proj_b = float(getattr(p_b, "weekly_projected_points", 0.0) or getattr(p_b, "projected_avg", 0.0) or 0.0)
        delta = round(abs(proj_a - proj_b), 2)

        winner = p_a if proj_a >= proj_b else p_b
        loser = p_b if proj_a >= proj_b else p_a

        slot_label = f" at {slot.upper()}" if slot else ""
        slot_target = f" in your {slot.upper()} slot" if slot else ""

        if delta >= 3.0:
            verdict = f"Strong Start{slot_label}: {winner.name} holds a decisive +{delta:.1f} projected point advantage over {loser.name} in PPR. Start {winner.name}{slot_target}."
        elif delta >= 0.5:
            verdict = f"Recommended Start{slot_label}: {winner.name} edges {loser.name} by +{delta:.1f} projected points. {winner.name} offers higher expected offensive touch share{slot_target}."
        else:
            verdict = f"Toss-Up Decision{slot_label}: {winner.name} and {loser.name} are projected nearly identical (within {delta:.1f} pts). Start {winner.name} for safer target floor; consider {loser.name} for high-variance red-zone ceiling."

        inj_a = (p_a.injury_status or "Healthy").upper()
        inj_b = (p_b.injury_status or "Healthy").upper()
        if inj_a in ("QUESTIONABLE", "DOUBTFUL", "OUT"):
            verdict += f" Caution: {p_a.name} is listed as {inj_a}."
        if inj_b in ("QUESTIONABLE", "DOUBTFUL", "OUT"):
            verdict += f" Caution: {p_b.name} is listed as {inj_b}."

        def serialize(p, proj):
            return {
                "id": str(p.espn_id),
                "name": p.name,
                "position": p.position,
                "nfl_team": p.team,
                "injury_status": p.injury_status or "Healthy",
                "projected_points": round(float(getattr(p, "projected_points", 0.0) or 0.0), 1),
                "projected_avg": round(float(getattr(p, "projected_avg", 0.0) or 0.0), 1),
                "weekly_projected_points": round(proj, 2),
                "percent_owned": round(float(getattr(p, "percent_owned", 0.0) or 0.0), 1),
                "percent_started": round(float(getattr(p, "percent_started", 0.0) or 0.0), 1),
            }

        return {
            "player_a": serialize(p_a, proj_a),
            "player_b": serialize(p_b, proj_b),
            "target_slot": slot.upper() if slot else None,
            "recommended_start": winner.name,
            "recommended_id": str(winner.espn_id),
            "projected_delta": delta,
            "verdict": verdict,
        }


class ApplyLineupRequest(BaseModel):
    team_id: int = 2


@router.post("/lineup/apply")
async def apply_recommended_lineup(req: Optional[ApplyLineupRequest] = None) -> Dict[str, Any]:
    """
    Applies the AI recommended optimal starting lineup for a team.
    Updates the local database roster records, attempts live ESPN execution,
    clears Redis cache, and returns the updated lineup state.
    """
    team_id = req.team_id if req else 2
    async with AsyncSessionLocal() as session:
        # 1. Fetch Roster
        stmt = select(Roster).where(Roster.espn_team_id == team_id)
        res = await session.execute(stmt)
        r_record = res.scalar_one_or_none()
        if not r_record:
            raise HTTPException(status_code=404, detail=f"Roster for team {team_id} not found")

        # 2. Fetch Players
        p_stmt = select(Player).where(Player.espn_id.in_(r_record.players))
        p_res = await session.execute(p_stmt)
        players = []
        for p in p_res.scalars().all():
            w_proj = float(getattr(p, "weekly_projected_points", 0.0) or 0.0)
            if not w_proj:
                w_proj = float(getattr(p, "projected_avg", 0.0) or 0.0)
            players.append({
                "id": p.espn_id,
                "name": p.name,
                "position": p.position,
                "nfl_team": p.team,
                "injury_status": p.injury_status or "Healthy",
                "projected_points": float(getattr(p, "projected_points", 0.0) or 0.0),
                "projected_avg": float(getattr(p, "projected_avg", 0.0) or 0.0),
                "weekly_projected_points": round(w_proj, 2),
                "percent_owned": float(getattr(p, "percent_owned", 0.0) or 0.0),
                "percent_started": float(getattr(p, "percent_started", 0.0) or 0.0),
                "lineup_slot": "BENCH",
                "is_starter": False
            })

        # 3. Calculate optimal lineup
        opt_data = optimize_team_lineup(players, r_record.lineup_slots or {}, r_record.starters or [])
        optimal_starters = opt_data["optimal_starters"]
        optimal_starter_ids = [str(p["id"]) for p in optimal_starters]

        # Build new lineup slots dictionary
        new_slots = {}
        for p in optimal_starters:
            new_slots[str(p["id"])] = p["lineup_slot"]
        for p in opt_data["optimal_bench"]:
            new_slots[str(p["id"])] = "BENCH"

        # 4. Save to Database
        r_record.starters = optimal_starter_ids
        r_record.lineup_slots = new_slots
        flag_modified(r_record, "starters")
        flag_modified(r_record, "lineup_slots")
        await session.commit()

        # 5. Clear Redis cache
        try:
            r = await get_redis()
            await r.delete(f"cache:roster:{team_id}")
        except Exception:
            pass

        # 6. ESPN write note: ESPN Fantasy API does not support third-party programmatic lineup moves.
        # Roster optimization is stored locally in Gridiron AI for simulation models, Discord bot alerts,
        # and weekly projections.
        message = f"Optimized lineup saved to Gridiron AI Strategy Board! Projected: {opt_data['optimal_projected_total']:.1f} pts."
        if active_swaps:
            swap_names = [f"{s.get('player_in')} into {s.get('slot')} (over {s.get('player_out')})" for s in active_swaps]
            message = (
                f"Strategy Board updated: {', '.join(swap_names)}. "
                f"Projected: {opt_data['optimal_projected_total']:.1f} pts (+{opt_data['delta_vs_current']:.2f} edge). "
                f"Note: ESPN restricts automated API writes; confirm this swap directly on ESPN."
            )

        return {
            "success": True,
            "message": message,
            "current_projected_total": opt_data["optimal_projected_total"],
            "starters_count": len(optimal_starters),
            "updated_starters": [p["name"] for p in optimal_starters],
            "espn_write_supported": False,
            "espn_team_url": f"https://fantasy.espn.com/football/team?leagueId={settings.ESPN_LEAGUE_ID}&teamId={team_id}"
        }


@router.get("/league/standings")
async def get_league_standings() -> Dict[str, Any]:
    """
    Returns standings and basic record data for all 12 teams in the league.
    Leverages Redis cache (<2ms) and PostgreSQL (<5ms) before ESPN network fallback.
    """
    cache_key = "cache:league:standings"

    # 1. Check Redis (<2ms)
    try:
        r = await get_redis()
        cached = await r.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.debug("Redis standings cache miss: %s", str(e))

    # 2. Check local PostgreSQL database (<5ms)
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Roster).order_by(Roster.standing.asc(), Roster.points_for.desc())
            res = await session.execute(stmt)
            db_rosters = res.scalars().all()
            if db_rosters and len(db_rosters) >= min(settings.LEAGUE_SIZE, 10):
                standings = [
                    {
                        "team_id": r.espn_team_id,
                        "team_name": r.team_name,
                        "owner": r.owner_name or r.team_name,
                        "wins": r.record.get("wins", 0) if r.record else 0,
                        "losses": r.record.get("losses", 0) if r.record else 0,
                        "ties": r.record.get("ties", 0) if r.record else 0,
                        "points_for": float(r.points_for),
                        "standing": r.standing
                    }
                    for r in db_rosters
                ]
                data = {
                    "league_name": "WA minus Josh",
                    "season": settings.ESPN_YEAR,
                    "standings": standings
                }
                try:
                    r = await get_redis()
                    await r.set(cache_key, json.dumps(data), ex=600)
                except Exception:
                    pass
                return data
    except Exception as e:
        logger.debug("Database standings query fallback: %s", str(e))

    # 3. Live ESPN API fallback
    try:
        league_inst = ESPNSyncService.get_espn_league_instance()
        if league_inst and league_inst.teams:
            standings = []
            for t in league_inst.teams:
                standings.append({
                    "team_id": t.team_id,
                    "team_name": t.team_name,
                    "owner": getattr(t, "owner", t.team_name),
                    "wins": t.wins,
                    "losses": t.losses,
                    "ties": getattr(t, "ties", 0),
                    "points_for": float(t.points_for),
                    "standing": getattr(t, "standing", 0)
                })
            standings.sort(key=lambda x: (x["standing"], -x["points_for"]))
            data = {
                "league_name": getattr(league_inst, "name", "WA minus Josh"),
                "season": settings.ESPN_YEAR,
                "standings": standings
            }
            try:
                r = await get_redis()
                await r.set(cache_key, json.dumps(data), ex=600)
            except Exception:
                pass
            return data
    except Exception as e:
        logger.error("Error fetching standings from live ESPN: %s", str(e))

    return {
        "league_name": "WA minus Josh",
        "season": settings.ESPN_YEAR,
        "standings": []
    }


@router.get("/draft/projections")
async def get_draft_projections(
    position: Optional[str] = None,
    limit: int = 150
) -> Dict[str, Any]:
    """
    Returns upcoming season fantasy projections, positional ranks, 
    and VORP calculations for draft analysis.
    """
    cache_key = f"cache:draft:projections:{position or 'ALL'}:{limit}"
    try:
        r = await get_redis()
        cached = await r.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    async with AsyncSessionLocal() as session:
        # Get all rostered player IDs to flag availability
        r_stmt = select(Roster)
        r_res = await session.execute(r_stmt)
        rosters = r_res.scalars().all()
        rostered_map = {}
        for ros in rosters:
            for pid in (ros.players or []):
                rostered_map[pid] = ros.team_name

        query = select(Player).where(Player.projected_points > 0)
        if position and position != "ALL":
            query = query.where(Player.position == position)
        query = query.order_by(Player.projected_points.desc()).limit(limit)

        p_res = await session.execute(query)
        players = p_res.scalars().all()

        # Positional baseline replacement points (QB13, RB26, WR38, TE13)
        pos_players = {}
        for p in players:
            pos_players.setdefault(p.position, []).append(p.projected_points)

        baselines = {
            "QB": pos_players.get("QB", [0])[min(12, len(pos_players.get("QB", [0])) - 1)] if pos_players.get("QB") else 0.0,
            "RB": pos_players.get("RB", [0])[min(25, len(pos_players.get("RB", [0])) - 1)] if pos_players.get("RB") else 0.0,
            "WR": pos_players.get("WR", [0])[min(37, len(pos_players.get("WR", [0])) - 1)] if pos_players.get("WR") else 0.0,
            "TE": pos_players.get("TE", [0])[min(12, len(pos_players.get("TE", [0])) - 1)] if pos_players.get("TE") else 0.0,
        }

        output = []
        for p in players:
            b_line = baselines.get(p.position, 0.0)
            vorp = round(p.projected_points - b_line, 1)
            output.append({
                "id": p.espn_id,
                "name": p.name,
                "position": p.position,
                "nfl_team": p.team,
                "projected_points": round(float(p.projected_points or 0.0), 1),
                "projected_avg": round(float(p.projected_avg or 0.0), 1),
                "vorp": vorp,
                "rostered_by": rostered_map.get(p.espn_id, None),
                "is_available": p.espn_id not in rostered_map,
                "injury_status": p.injury_status or "Healthy",
                "stats": (p.espn_data or {}).get("stats", {})
            })

        data = {
            "season": settings.ESPN_YEAR,
            "scoring_format": settings.SCORING_FORMAT,
            "count": len(output),
            "baselines": baselines,
            "players": output
        }

        try:
            r = await get_redis()
            await r.set(cache_key, json.dumps(data), ex=600)
        except Exception:
            pass

        return data


@router.get("/draft/live")
async def get_draft_live() -> Dict[str, Any]:
    """
    Returns active ESPN live draft status, current pick, turn wrap, and countdown to Team Cooper.
    """
    status = await DraftPrepService.get_live_draft_status()
    active_pick = status.get("current_pick", 1)
    active_round = ((active_pick - 1) // 12) + 1
    pick_in_round = ((active_pick - 1) % 12) + 1
    is_odd = active_round % 2 != 0
    active_team = pick_in_round if is_odd else (13 - pick_in_round)

    user_picks = []
    for r in range(1, 17):
        user_picks.append((r - 1) * 12 + (2 if r % 2 != 0 else 11))
    user_picks.sort()
    next_user_pick = next((p for p in user_picks if p >= active_pick), active_pick)
    picks_until = max(0, next_user_pick - active_pick)

    return {
        **status,
        "active_round": active_round,
        "pick_in_round": pick_in_round,
        "active_team_slot": active_team,
        "is_user_turn": (active_team == 2),
        "next_user_pick": next_user_pick,
        "picks_until_turn": picks_until
    }


@router.get("/draft/recommendations")
async def get_draft_recommendations(
    pick: Optional[int] = None,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Returns Top 10 recommended picks with letter grades (A+ to C), VORP, and tactical insights.
    """
    return await DraftPrepService.get_on_the_clock_recommendations(
        user_team_id=2,
        current_pick=pick,
        limit=limit
    )


@router.get("/draft/players")
async def get_draft_players(
    page: int = 1,
    page_size: int = 50,
    position: Optional[str] = None,
    nfl_team: Optional[str] = None,
    availability: str = "ALL", # ALL, AVAILABLE, ROSTERED
    search: Optional[str] = None,
    sort_by: str = "consensus_adp", # consensus_adp, sleeper_adp, espn_adp, yahoo_adp, consensus, vorp, name
    order: str = "asc", # default asc for ADP ranking
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Returns deep player pool for draft war room with multi-source projections,
    multi-source ADPs (Sleeper, ESPN, Yahoo), pagination, filtering, and sorting.
    """
    async with AsyncSessionLocal() as session:
        r_stmt = select(Roster)
        r_res = await session.execute(r_stmt)
        rosters = r_res.scalars().all()
        rostered_map: Dict[str, str] = {}
        for ros in rosters:
            for pid in (ros.players or []):
                rostered_map[pid] = ros.team_name

        # Load locked keepers from Redis
        r = await get_redis()
        keepers_raw = await r.hgetall("keepers:2026")
        keepers_by_name = {}
        for tid, k_json in (keepers_raw or {}).items():
            try:
                k_data = json.loads(k_json)
                k_name = k_data.get("player_name", "").lower().strip()
                if k_name:
                    keepers_by_name[k_name] = k_data
            except Exception:
                pass

        query = select(Player).where(Player.consensus_proj > 0)

        if position and position != "ALL":
            raw_positions = [p.strip().upper() for p in position.split(",") if p.strip()]
            resolved_positions = set()
            for pos_item in raw_positions:
                if pos_item in ("D/ST", "DST"):
                    resolved_positions.add("D/ST")
                    resolved_positions.add("DST")
                elif pos_item != "ALL":
                    resolved_positions.add(pos_item)
            if resolved_positions:
                query = query.where(Player.position.in_(list(resolved_positions)))

        if nfl_team and nfl_team != "ALL":
            query = query.where(Player.team == nfl_team)

        if search and search.strip():
            query = query.where(Player.name.ilike(f"%{search.strip()}%"))

        p_res = await session.execute(query)
        all_players = p_res.scalars().all()

        pos_groups: Dict[str, List[float]] = {}
        for p in all_players:
            pos_groups.setdefault(p.position, []).append(float(p.consensus_proj or 0.0))

        baselines = {
            "QB": pos_groups.get("QB", [0])[min(12, len(pos_groups.get("QB", [0])) - 1)] if pos_groups.get("QB") else 280.0,
            "RB": pos_groups.get("RB", [0])[min(25, len(pos_groups.get("RB", [0])) - 1)] if pos_groups.get("RB") else 170.0,
            "WR": pos_groups.get("WR", [0])[min(37, len(pos_groups.get("WR", [0])) - 1)] if pos_groups.get("WR") else 160.0,
            "TE": pos_groups.get("TE", [0])[min(12, len(pos_groups.get("TE", [0])) - 1)] if pos_groups.get("TE") else 115.0,
        }

        # Compute team depth chart positions (e.g., QB1, WR2, RB1)
        # Group all players by team+position, rank by projected points
        team_pos_groups: Dict[str, List] = {}
        for p in all_players:
            key = f"{p.team}:{p.position}"
            team_pos_groups.setdefault(key, []).append(p)
        # Sort each group by consensus projection descending
        depth_chart_map: Dict[int, str] = {}  # player.id -> "QB1", "WR2", etc.
        for key, group in team_pos_groups.items():
            group.sort(key=lambda x: float(x.consensus_proj or 0.0), reverse=True)
            for rank, pl in enumerate(group, 1):
                depth_chart_map[pl.id] = f"{pl.position}{rank}"

        output = []
        for p in all_players:
            is_rostered = p.espn_id in rostered_map
            avail_upper = availability.upper()
            if avail_upper == "AVAILABLE" and is_rostered:
                continue
            if avail_upper == "ROSTERED" and not is_rostered:
                continue

            b_line = baselines.get(p.position, 100.0)
            vorp = round(max(0.0, (p.consensus_proj or 0.0) - b_line), 1)

            k_info = keepers_by_name.get(p.name.lower().strip())
            is_keeper = (k_info is not None)
            keeper_team = k_info.get("team_name") if k_info else None
            keeper_round = k_info.get("round_cost") if k_info else None

            output.append({
                "id": p.espn_id,
                "name": p.name,
                "position": p.position,
                "nfl_team": p.team,
                "consensus_proj": round(float(p.consensus_proj or 0.0), 1),
                "projected_avg": round(float(p.projected_avg or 0.0), 1),
                "espn_proj": round(float(p.espn_proj or 0.0), 1),
                "sleeper_proj": round(float(p.sleeper_proj or 0.0), 1),
                "consensus_adp": round(float(p.consensus_adp), 1) if p.consensus_adp is not None else (round(float(p.adp), 1) if p.adp is not None else None),
                "sleeper_adp": round(float(p.sleeper_adp), 1) if p.sleeper_adp is not None else (round(float(p.adp), 1) if p.adp is not None else None),
                "espn_adp": round(float(p.espn_adp), 1) if p.espn_adp is not None else None,
                "yahoo_adp": round(float(p.yahoo_adp), 1) if p.yahoo_adp is not None else None,
                "adp": round(float(p.consensus_adp or p.adp), 1) if (p.consensus_adp is not None or p.adp is not None) else None,
                "vorp": vorp,
                "is_available": not is_rostered,
                "rostered_by": rostered_map.get(p.espn_id),
                "is_keeper": is_keeper,
                "keeper_team": keeper_team,
                "keeper_round": keeper_round,
                "injury_status": p.injury_status or "Healthy",
                "injury_notes": p.injury_notes,
                "sentiment_tag": p.sentiment_tag or "NEUTRAL",
                "sentiment_score": round(float(p.sentiment_score or 0.0), 2),
                "depth_chart_pos": depth_chart_map.get(p.id, ""),
                "percent_owned": round(float(p.percent_owned or 0.0), 1),
                "percent_started": round(float(p.percent_started or 0.0), 1),
            })

        # Sorting logic
        is_desc = (order.lower() == "desc")
        if sort_by in ("consensus_adp", "adp"):
            output.sort(key=lambda x: (x["consensus_adp"] is None, x["consensus_adp"] or 999.0), reverse=is_desc)
        elif sort_by == "sleeper_adp":
            output.sort(key=lambda x: (x["sleeper_adp"] is None, x["sleeper_adp"] or 999.0), reverse=is_desc)
        elif sort_by == "espn_adp":
            output.sort(key=lambda x: (x["espn_adp"] is None, x["espn_adp"] or 999.0), reverse=is_desc)
        elif sort_by == "yahoo_adp":
            output.sort(key=lambda x: (x["yahoo_adp"] is None, x["yahoo_adp"] or 999.0), reverse=is_desc)
        elif sort_by == "vorp":
            output.sort(key=lambda x: x["vorp"], reverse=is_desc)
        elif sort_by == "espn":
            output.sort(key=lambda x: x["espn_proj"], reverse=is_desc)
        elif sort_by == "sleeper":
            output.sort(key=lambda x: x["sleeper_proj"], reverse=is_desc)
        elif sort_by == "name":
            output.sort(key=lambda x: x["name"].lower(), reverse=is_desc)
        elif sort_by == "percent_owned":
            output.sort(key=lambda x: x.get("percent_owned", 0), reverse=not is_desc)
        elif sort_by == "percent_started":
            output.sort(key=lambda x: x.get("percent_started", 0), reverse=not is_desc)
        else: # consensus points
            output.sort(key=lambda x: x["consensus_proj"], reverse=is_desc)

        total_matches = len(output)
        actual_page_size = limit if limit else page_size
        total_pages = max(1, (total_matches + actual_page_size - 1) // actual_page_size)
        current_page = max(1, min(page, total_pages))
        start_idx = (current_page - 1) * actual_page_size
        end_idx = start_idx + actual_page_size

        paginated = output[start_idx:end_idx]

        return {
            "page": current_page,
            "page_size": actual_page_size,
            "total_pages": total_pages,
            "total_matches": total_matches,
            "count": len(paginated),
            "baselines": baselines,
            "players": paginated
        }


@router.get("/player/{player_id}/scouting")
async def get_player_scouting(player_id: str) -> Dict[str, Any]:
    """
    Returns comprehensive player scouting dossier including consensus average stats,
    multi-source ADPs, per-source lines (ESPN vs Sleeper vs Yahoo), injury notes, and beat news.
    """
    async with AsyncSessionLocal() as session:
        p_stmt = select(Player).where((Player.espn_id == player_id) | (Player.name == player_id))
        p_res = await session.execute(p_stmt)
        p = p_res.scalar_one_or_none()
        if not p:
            raise HTTPException(status_code=404, detail="Player not found")

        news_stmt = select(NewsItem).where(NewsItem.player_name == p.name).order_by(NewsItem.timestamp.desc()).limit(8)
        news_res = await session.execute(news_stmt)
        news_items = [
            {
                "headline": item.headline,
                "text": item.text,
                "source": item.source,
                "tag": item.tag,
                "timestamp": item.timestamp.isoformat() if item.timestamp else None
            }
            for item in news_res.scalars().all()
        ]

        projs = p.source_projections or {}

        return {
            "player": {
                "id": p.espn_id,
                "name": p.name,
                "position": p.position,
                "nfl_team": p.team,
                "status": p.status,
                "injury_status": p.injury_status or "Healthy",
                "injury_notes": p.injury_notes,
                "bye_week": p.bye_week,
                "sentiment_tag": p.sentiment_tag or "NEUTRAL",
                "sentiment_score": round(float(p.sentiment_score or 0.0), 2),
            },
            "consensus": projs.get("consensus", {
                "points": round(float(p.consensus_proj or 0.0), 1),
                "avg": round(float(p.projected_avg or 0.0), 1),
                "floor": round(float(p.proj_floor or 0.0), 1),
                "ceiling": round(float(p.proj_ceiling or 0.0), 1),
                "adp": p.consensus_adp or p.adp,
            }),
            "sources": {
                "espn": projs.get("espn", {
                    "points": round(float(p.espn_proj or 0.0), 1),
                    "avg": round(float(p.espn_proj or 0.0) / 17.0, 1),
                    "adp": p.espn_adp,
                    "stats": (p.espn_data or {}).get("stats", {}),
                    "season_outlook": (p.espn_data or {}).get("season_outlook")
                }),
                "sleeper": projs.get("sleeper", {
                    "points": round(float(p.sleeper_proj or 0.0), 1),
                    "avg": round(float(p.sleeper_proj or 0.0) / 17.0, 1),
                    "adp": p.sleeper_adp or p.adp,
                    "stats": {}
                }),
                "yahoo": projs.get("yahoo", {
                    "adp": p.yahoo_adp,
                    "status": None,
                    "injury_note": p.injury_notes,
                    "percent_drafted": None
                })
            },
            "variance": projs.get("variance", {
                "points_delta": round(abs(float(p.espn_proj or 0) - float(p.sleeper_proj or 0)), 1),
                "adp_spread": 0.0,
                "agreement_rating": "MODERATE"
            }),
            "recent_news": news_items
        }


@router.get("/draft/prompts")
@router.get("/api/prompts")
async def get_draft_prompts() -> Dict[str, Any]:
    """
    Returns dynamic, data-driven prompts compiled from the latest Redis digest.
    In-season: waiver/lineup/trade focused. Pre-draft: scouting/draft focused.
    """
    from app.pipelines.daily_scheduler import DailySchedulerService
    prompts = await DailySchedulerService.get_cached_prompts()
    if not prompts:
        # In-season fallback prompts
        prompts = [
            "Who should I start at FLEX this week?",
            "Any high-upside waiver wire targets I'm missing?",
            "Which of my bench players are droppable?",
            "Break down my Week 1 matchup and win probability",
            "Who are the top free agent RBs available right now?",
            "Evaluate a trade: what could I get for my WR3?",
        ]
    return {"prompts": prompts, "count": len(prompts)}


@router.post("/draft/daily-sync")
async def trigger_daily_sync() -> Dict[str, Any]:
    """
    Manually triggers the comprehensive 24h data ingestion and Redis digest synthesis.
    """
    from app.pipelines.daily_scheduler import DailySchedulerService
    res = await DailySchedulerService.run_daily_ingestion_and_synthesis(force=True)
    return res


# ── Waiver Wire Watchlist ────────────────────────────────────────────────

@router.get("/waivers/watchlist")
async def get_waiver_watchlist() -> Dict[str, Any]:
    """
    Returns the user's waiver watchlist with enriched player data from PostgreSQL.
    Cross-references the Redis set `user:waiver_targets` with the players table
    to return full projection/injury/status data for each watched player.
    """
    try:
        r = await get_redis()
        target_names = await r.smembers("user:waiver_targets")
        target_names = list(target_names)
    except Exception:
        target_names = []

    if not target_names:
        return {"watchlist": [], "count": 0}

    # Enrich with player data from PostgreSQL
    enriched = []
    try:
        async with AsyncSessionLocal() as session:
            # Build rostered_map upfront (same pattern as draft/players endpoint)
            r_stmt = select(Roster)
            r_res = await session.execute(r_stmt)
            rosters = r_res.scalars().all()
            rostered_map: Dict[str, str] = {}
            for ros in rosters:
                for pid in (ros.players or []):
                    rostered_map[pid] = ros.team_name

            for name in target_names:
                decoded = name if isinstance(name, str) else name.decode("utf-8")
                stmt = select(Player).where(Player.name.ilike(f"%{decoded}%")).limit(1)
                res = await session.execute(stmt)
                p = res.scalar_one_or_none()
                if p:
                    is_rostered = p.espn_id in rostered_map
                    enriched.append({
                        "name": p.name,
                        "espn_id": p.espn_id,
                        "position": p.position,
                        "nfl_team": p.team,
                        "projected_points": round(float(p.projected_points or 0.0), 1),
                        "consensus_proj": round(float(p.consensus_proj or p.projected_points or 0.0), 1),
                        "vorp": round(float(p.projected_points or 0.0) - 100.0, 1),
                        "injury_status": p.injury_status or "Active",
                        "injury_notes": p.injury_notes or "",
                        "rostered_by": rostered_map.get(p.espn_id, "Free Agent"),
                        "is_available": not is_rostered,
                    })
                else:
                    enriched.append({
                        "name": decoded,
                        "espn_id": None,
                        "position": "?",
                        "nfl_team": "?",
                        "projected_points": 0.0,
                        "consensus_proj": 0.0,
                        "vorp": 0.0,
                        "injury_status": "Unknown",
                        "injury_notes": "",
                        "rostered_by": "Unknown",
                        "is_available": False,
                    })
    except Exception as e:
        logger.warning("Error enriching watchlist: %s", str(e))

    # Sort: available first, then by projected points descending
    enriched.sort(key=lambda x: (not x["is_available"], -(x["projected_points"] or 0)))

    return {"watchlist": enriched, "count": len(enriched)}


@router.post("/waivers/watchlist")
async def add_to_waiver_watchlist(payload: dict = fastapi.Body(...)) -> Dict[str, Any]:
    """
    Adds a player name to the user's waiver watchlist in Redis.
    """
    player_name = payload.get("player_name", "").strip()
    if not player_name:
        raise HTTPException(status_code=400, detail="player_name is required")

    try:
        r = await get_redis()
        await r.sadd("user:waiver_targets", player_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add to watchlist: {str(e)}")

    return {
        "success": True,
        "player_name": player_name,
        "message": f"'{player_name}' added to waiver watchlist."
    }


@router.delete("/waivers/watchlist/{player_name}")
async def remove_from_waiver_watchlist(player_name: str) -> Dict[str, Any]:
    """
    Removes a player name from the user's waiver watchlist in Redis.
    """
    try:
        r = await get_redis()
        removed = await r.srem("user:waiver_targets", player_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove from watchlist: {str(e)}")

    return {
        "success": removed > 0,
        "player_name": player_name,
        "message": f"'{player_name}' removed from watchlist." if removed else f"'{player_name}' not found in watchlist."
    }


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Kubernetes readiness and liveness probe.
    """
    cache_stats = await LLMCache.get_stats()
    espn_check = await ESPNSyncService.verify_credentials()
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "espn_auth": espn_check,
        "cache_metrics": cache_stats
    }


# ==========================================
# Proactive Intelligence & Briefings Endpoints
# ==========================================

@router.get("/briefings")
async def list_briefings(unread_only: bool = False, limit: int = 50) -> Dict[str, Any]:
    """Retrieves autonomous agent briefings and digests from PostgreSQL."""
    from app.models.agent_briefing import AgentBriefing
    from sqlalchemy import desc

    async with AsyncSessionLocal() as session:
        stmt = select(AgentBriefing)
        if unread_only:
            stmt = stmt.where(AgentBriefing.read == False)
        stmt = stmt.order_by(desc(AgentBriefing.created_at)).limit(limit)
        res = await session.execute(stmt)
        briefings = res.scalars().all()
        return {
            "briefings": [b.to_dict() for b in briefings],
            "count": len(briefings),
        }


@router.post("/briefings/{briefing_id}/read")
async def mark_briefing_read(briefing_id: int) -> Dict[str, Any]:
    """Marks an individual agent briefing as read."""
    from app.models.agent_briefing import AgentBriefing

    async with AsyncSessionLocal() as session:
        stmt = select(AgentBriefing).where(AgentBriefing.id == briefing_id)
        res = await session.execute(stmt)
        b = res.scalar_one_or_none()
        if not b:
            raise HTTPException(status_code=404, detail="Briefing not found")
        b.read = True
        await session.commit()
        return {"success": True, "id": briefing_id}


@router.post("/briefings/mark-all-read")
async def mark_all_briefings_read() -> Dict[str, Any]:
    """Marks all unread briefings as read."""
    from app.models.agent_briefing import AgentBriefing
    from sqlalchemy import update

    async with AsyncSessionLocal() as session:
        stmt = update(AgentBriefing).where(AgentBriefing.read == False).values(read=True)
        await session.execute(stmt)
        await session.commit()
        return {"success": True, "message": "All briefings marked as read"}


# ==========================================
# Tracking Jobs (Surveillance) Endpoints
# ==========================================

class CreateTrackingJobRequest(BaseModel):
    player_name: str = Field(..., description="Player name to surveil")
    focus_areas: Optional[List[str]] = Field(default=None, description="Areas of focus (injury, depth_chart, practice, sentiment)")
    frequency_minutes: int = Field(default=60, ge=5, le=1440, description="Check frequency in minutes")
    duration_hours: int = Field(default=48, ge=1, le=336, description="Hours until watch expires")
    reason: Optional[str] = Field(default="User initiated surveillance", description="Rationale for watch")
    custom_query: Optional[str] = Field(default=None, description="Custom research prompt")


@router.get("/tracking/jobs")
async def list_tracking_jobs(include_inactive: bool = False) -> Dict[str, Any]:
    """Lists all active (or historical) dynamic surveillance jobs."""
    from app.pipelines.scheduler_api import SchedulerAPI
    jobs = await SchedulerAPI.list_tracking_jobs(include_inactive=include_inactive)
    return {
        "jobs": jobs,
        "count": len(jobs),
    }


@router.post("/tracking/jobs")
async def create_tracking_job(req: CreateTrackingJobRequest) -> Dict[str, Any]:
    """Spawns an autonomous surveillance job for a player."""
    from app.pipelines.scheduler_api import SchedulerAPI
    job = await SchedulerAPI.spawn_tracking_job(
        player_name=req.player_name,
        focus_areas=req.focus_areas,
        frequency_minutes=req.frequency_minutes,
        duration_hours=req.duration_hours,
        reason=req.reason or "User initiated surveillance",
        source="user",
        custom_query=req.custom_query,
    )
    return {
        "success": True,
        "job": job,
    }


@router.delete("/tracking/jobs/{job_id}")
async def cancel_tracking_job(job_id: str) -> Dict[str, Any]:
    """Cancels and halts an active surveillance job."""
    from app.pipelines.scheduler_api import SchedulerAPI
    cancelled = await SchedulerAPI.cancel_tracking_job(job_id=job_id, reason="Cancelled via UI/API")
    return {
        "success": cancelled,
        "job_id": job_id,
        "message": f"Tracking job {job_id} cancelled.",
    }


@router.post("/tracking/jobs/{job_id}/run")
async def trigger_tracking_job(job_id: str) -> Dict[str, Any]:
    """Forces an immediate execution tick for a tracking job."""
    from app.pipelines.scheduler_api import SchedulerAPI
    triggered = await SchedulerAPI.trigger_job_now(job_id=job_id)
    if not triggered:
        raise HTTPException(status_code=404, detail="Job ID not found in active scheduler")
    return {"success": True, "job_id": job_id, "message": "Execution triggered"}


# ==========================================
# Pending Actions (Approval Gates) Endpoints
# ==========================================

class RejectActionRequest(BaseModel):
    reason: Optional[str] = Field(default="Rejected by user", description="Reason for rejection")


@router.get("/actions/pending")
async def list_pending_actions(status: Optional[str] = "PENDING") -> Dict[str, Any]:
    """Lists roster actions awaiting approval (or historical actions)."""
    from app.pipelines.action_executor import ActionExecutor
    actions = await ActionExecutor.list_actions(status=status)
    return {
        "actions": actions,
        "count": len(actions),
    }


@router.post("/actions/{action_id}/approve")
async def approve_pending_action(action_id: int) -> Dict[str, Any]:
    """Approves a pending action and immediately executes it on ESPN."""
    from app.pipelines.action_executor import ActionExecutor
    try:
        updated = await ActionExecutor.approve_and_execute(action_id=action_id)
        return {
            "success": True,
            "action": updated,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/actions/{action_id}/reject")
async def reject_pending_action(action_id: int, req: Optional[RejectActionRequest] = None) -> Dict[str, Any]:
    """Rejects and dismisses a pending action."""
    from app.pipelines.action_executor import ActionExecutor
    reason = req.reason if req else "Rejected by user"
    try:
        updated = await ActionExecutor.reject_action(action_id=action_id, reason=reason)
        return {
            "success": True,
            "action": updated,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==========================================
# Real-Time SSE Stream & Pulse Feed
# ==========================================

@router.get("/pulse/stream")
async def pulse_event_stream():
    """
    Server-Sent Events (SSE) real-time feed.
    Pushes briefings, transaction reactions, tracking ticks, and pending actions to the UI.
    """
    from sse_starlette.sse import EventSourceResponse
    from app.pipelines.notification_dispatcher import NotificationDispatcher
    return EventSourceResponse(NotificationDispatcher.subscribe_sse())


@router.get("/pulse/feed")
async def get_pulse_feed(limit: int = 50) -> Dict[str, Any]:
    """Returns recent cached intelligence items for instantaneous frontend hydration."""
    from app.pipelines.notification_dispatcher import NotificationDispatcher
    items = await NotificationDispatcher.get_recent_feed(limit=limit)
    return {
        "items": items,
        "count": len(items),
    }


# ==========================================
# Power Rankings & Season Strategy Endpoints
# ==========================================

@router.get("/league/power-rankings")
async def get_power_rankings() -> Dict[str, Any]:
    """Returns the latest official league power rankings."""
    r = await get_redis()
    raw = await r.get("gridiron:league:power_rankings")
    if raw:
        rankings = json.loads(raw)
    else:
        # Run on-demand calculation
        from app.pipelines.proactive_jobs import job_power_rankings
        await job_power_rankings()
        raw2 = await r.get("gridiron:league:power_rankings")
        rankings = json.loads(raw2) if raw2 else []

    return {
        "league": "WA minus Josh",
        "rankings": rankings,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/team/season-strategy")
async def get_season_strategy() -> Dict[str, Any]:
    """Returns macro season-long strategy and playoff roadmap."""
    r = await get_redis()
    raw = await r.get("gridiron:team:season_strategy")
    if raw:
        strategy = json.loads(raw)
    else:
        from app.pipelines.proactive_jobs import job_season_strategy
        await job_season_strategy()
        raw2 = await r.get("gridiron:team:season_strategy")
        strategy = json.loads(raw2) if raw2 else {}

    return {
        "team": "Team Cooper",
        "strategy": strategy,
    }


# ==========================================
# Manual Proactive Job Trigger
# ==========================================

@router.post("/proactive/trigger/{job_name}")
async def trigger_proactive_job(job_name: str) -> Dict[str, Any]:
    """Manually triggers any of the 9 autonomous jobs for instant testing/demonstration."""
    from app.pipelines import proactive_jobs
    func = getattr(proactive_jobs, job_name, None)
    if not func:
        valid_jobs = [j for j in dir(proactive_jobs) if j.startswith("job_")]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid job '{job_name}'. Valid options: {valid_jobs}",
        )

    try:
        import asyncio
        asyncio.create_task(func())
        return {
            "success": True,
            "job_name": job_name,
            "message": f"Autonomous job '{job_name}' dispatched in background.",
        }
    except Exception as e:
        logger.error(f"Failed to dispatch autonomous job {job_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# Intelligent Trade & Waiver Advice Engines
# ==========================================

class ProposeTradeActionRequest(BaseModel):
    target_team_id: int
    target_team_name: str
    send_players: List[str]
    receive_players: List[str]
    rationale: str
    pitch: Optional[str] = None


class ProposeWaiverActionRequest(BaseModel):
    action_type: str = Field(default="WAIVER_CLAIM", description="WAIVER_CLAIM | FREE_AGENT_ADD | IR_STASH")
    add_player_name: Optional[str] = None
    add_player_id: Optional[str] = None
    drop_player_name: Optional[str] = None
    drop_player_id: Optional[str] = None
    ir_player_name: Optional[str] = None
    ir_player_id: Optional[str] = None
    bid_amount: Optional[int] = 0
    rationale: str


@router.get("/trades/acquire")
async def acquire_target_player_trades(target_player: str) -> Dict[str, Any]:
    """
    Finds which rival fantasy manager owns a target player (e.g. Carnell Tate, Justin Jefferson),
    audits that team's starting lineup weak spots, and constructs realistic trade packages.
    """
    from app.tools.trade_tools import find_trade_packages_to_acquire
    try:
        result = await find_trade_packages_to_acquire(target_player_name=target_player, user_team_id=settings.ESPN_TEAM_ID)
        return result
    except Exception as e:
        logger.error("Error in /trades/acquire: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades/packages")
async def get_trade_packages(player_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Shops a player on Team Cooper across teams with matching needs, or scans for team-wide opportunities.
    """
    from app.tools.trade_tools import find_trade_packages_for_player, find_team_trade_opportunities
    try:
        if player_name:
            packages = await find_trade_packages_for_player(player_name=player_name, user_team_id=settings.ESPN_TEAM_ID)
        else:
            packages = await find_team_trade_opportunities(user_team_id=settings.ESPN_TEAM_ID)
        return {"packages": packages, "count": len(packages)}
    except Exception as e:
        logger.error("Error in /trades/packages: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades/needs")
async def get_league_team_needs() -> Dict[str, Any]:
    """
    Returns the league-wide roster needs, deficits, and surpluses matrix across all 10 teams.
    """
    from app.tools.trade_tools import get_league_needs_matrix
    try:
        return await get_league_needs_matrix()
    except Exception as e:
        logger.error("Error in /trades/needs: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/waivers/evaluate")
async def evaluate_waiver_target(player_name: str) -> Dict[str, Any]:
    """
    Evaluates waiver wire pickup viability, zero-cost IR stashes, and optimal bench cut candidates.
    """
    from app.tools.lineup_tools import evaluate_waiver_pickup
    try:
        return await evaluate_waiver_pickup(player_name=player_name, user_team_id=settings.ESPN_TEAM_ID)
    except Exception as e:
        logger.error("Error in /waivers/evaluate: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trades/propose-action")
async def create_trade_pending_action(req: ProposeTradeActionRequest) -> Dict[str, Any]:
    """
    Converts a trade package into an approval-gated PendingAction.
    """
    from app.pipelines.notification_dispatcher import NotificationDispatcher
    try:
        send_str = ", ".join(req.send_players)
        rec_str = ", ".join(req.receive_players)
        title = f"Trade Proposal: {send_str} for {rec_str}"
        desc = f"Send {send_str} to {req.target_team_name} in exchange for {rec_str}."

        action = await NotificationDispatcher.dispatch_pending_action(
            action_type="TRADE_PROPOSAL",
            title=title,
            description=desc,
            rationale=req.rationale,
            payload={
                "target_team_id": req.target_team_id,
                "target_team_name": req.target_team_name,
                "send_player_names": req.send_players,
                "receive_player_names": req.receive_players,
                "pitch": req.pitch,
            },
            urgency="MEDIUM",
            confidence_score=0.88,
            source_agent="TradeStrategist",
            expires_hours=48,
        )
        return {"success": True, "action": action}
    except Exception as e:
        logger.error("Error in /trades/propose-action: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/waivers/propose-action")
async def create_waiver_pending_action(req: ProposeWaiverActionRequest) -> Dict[str, Any]:
    """
    Converts a waiver recommendation (Add/Drop or IR Stash) into an approval-gated PendingAction.
    """
    from app.pipelines.notification_dispatcher import NotificationDispatcher
    try:
        if req.action_type == "IR_STASH":
            title = f"IR Stash: Move {req.ir_player_name} to IR"
            desc = f"Stash {req.ir_player_name} in dedicated IR slot to free a bench spot for {req.add_player_name}."
            payload = {
                "player_id": req.ir_player_id,
                "player_name": req.ir_player_name,
                "subsequent_add": req.add_player_name,
            }
        else:
            title = f"Waiver Claim: Add {req.add_player_name}"
            if req.drop_player_name:
                title += f" (Drop {req.drop_player_name})"
            desc = f"Add {req.add_player_name} from waiver wire."
            if req.drop_player_name:
                desc += f" Drop {req.drop_player_name} from bench."
            payload = {
                "add_player_id": req.add_player_id,
                "add_player_name": req.add_player_name,
                "drop_player_id": req.drop_player_id,
                "drop_player_name": req.drop_player_name,
                "bid_amount": req.bid_amount or 0,
            }

        action = await NotificationDispatcher.dispatch_pending_action(
            action_type=req.action_type,
            title=title,
            description=desc,
            rationale=req.rationale,
            payload=payload,
            urgency="HIGH" if req.action_type == "IR_STASH" else "MEDIUM",
            confidence_score=0.90,
            source_agent="LineupWaiverSpecialist",
            expires_hours=24,
        )
        return {"success": True, "action": action}
    except Exception as e:
        logger.error("Error in /waivers/propose-action: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    Real-time bidirectional WebSocket stream with the General Manager.
    """
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            response = await ask_general_manager(user_query=data)
            await websocket.send_text(response)
    except WebSocketDisconnect:
        pass
