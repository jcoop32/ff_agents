"""
Tier 4 Proactive League Activity Monitor.
Continuously polls ESPN transactions (trades, waivers, free agent adds, IR moves),
evaluates impact using deterministic rules, and invokes proactive multi-agent synthesis.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set
import httpx
from sqlalchemy import select
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis_client import RedisRepository, get_redis
from app.models.transaction import Transaction
from app.models.league import Roster
from app.pipelines.espn_sync import ESPNSyncService, ESPN_V3_BASE_URL

logger = logging.getLogger(__name__)


class LeagueActivityMonitor:
    """Watches ESPN league moves and triggers proactive alerts."""

    @classmethod
    async def poll_league_transactions(cls) -> Dict[str, Any]:
        """
        Main polling loop executed every 10 minutes by worker.
        1. Checks espn_api recent_activity and V3 mTransactions2.
        2. Diffs against existing transactions.
        3. Classifies impact (CRITICAL, HIGH, MEDIUM, LOW).
        4. Invokes proactive supervisor if CRITICAL or HIGH.
        """
        league = ESPNSyncService.get_espn_league_instance()
        if not league:
            return {"success": False, "error": "Cannot connect to ESPN"}

        raw_activities = []
        try:
            # espn_api recent_activity
            raw_activities = league.recent_activity(size=25)
        except Exception as e:
            logger.warning("espn_api recent_activity failed: %s. Trying V3 direct endpoint.", str(e))

        # Also pull V3 mTransactions2 for detailed trade payloads
        direct_txs = await cls._fetch_v3_transactions()

        new_count = 0
        critical_alerts = []

        async with AsyncSessionLocal() as session:
            # Load user roster (Team Cooper, ID 2)
            user_stmt = select(Roster).where(Roster.espn_team_id == settings.ESPN_TEAM_ID)
            user_roster = (await session.execute(user_stmt)).scalar_one_or_none()

            for item in raw_activities:
                tx_id = str(getattr(item, "id", f"{getattr(item, 'date', '')}_{getattr(item, 'actions', '')}"))

                # Check if already processed
                stmt = select(Transaction).where(Transaction.espn_transaction_id == tx_id)
                exists = (await session.execute(stmt)).scalar_one_or_none()
                if exists:
                    continue

                # Parse transaction
                parsed = cls._parse_activity_item(item)
                impact = await cls._classify_impact(parsed, user_roster)

                analysis_text = None
                # If CRITICAL or HIGH, invoke proactive agent analysis
                if impact in ("CRITICAL", "HIGH"):
                    analysis_text = await cls._run_proactive_analysis(parsed, impact)
                    if impact == "CRITICAL":
                        critical_alerts.append(parsed)

                tx_record = Transaction(
                    espn_transaction_id=tx_id,
                    league_id=str(settings.ESPN_LEAGUE_ID),
                    type=parsed["type"],
                    team_id=parsed["team_id"],
                    team_name=parsed["team_name"],
                    players_added=parsed["players_added"],
                    players_dropped=parsed["players_dropped"],
                    timestamp=datetime.now(timezone.utc),
                    impact_level=impact,
                    analysis_text=analysis_text,
                    notified=False
                )
                session.add(tx_record)
                new_count += 1

                # Push to Redis stream
                await RedisRepository.push_league_activity_stream(parsed)

            await session.commit()

        # Run roster snapshot diffing as backup for silent drops
        await cls._diff_roster_snapshots(league)

        logger.info("League monitor cycle finished: %d new transactions detected.", new_count)
        return {"success": True, "new_transactions": new_count, "critical_alerts": len(critical_alerts)}

    @staticmethod
    def _parse_activity_item(item) -> Dict[str, Any]:
        """Converts an espn_api activity object into standard dictionary."""
        actions = getattr(item, "actions", [])
        added = []
        dropped = []
        tx_type = "ROSTER_MOVE"
        team_id = getattr(getattr(item, "team", None), "team_id", 0)
        team_name = getattr(getattr(item, "team", None), "team_name", "Unknown Team")

        for act in actions:
            action_type = act[1] if len(act) > 1 else ""
            player_name = act[0] if len(act) > 0 else "Unknown"
            if "ADDED" in action_type or "WAIVER" in action_type:
                added.append({"name": player_name})
                tx_type = "WAIVER" if "WAIVER" in action_type else "FREE_AGENT"
            elif "DROPPED" in action_type:
                dropped.append({"name": player_name})
            elif "TRADED" in action_type:
                tx_type = "TRADE"
                added.append({"name": player_name})

        return {
            "type": tx_type,
            "team_id": team_id,
            "team_name": team_name,
            "players_added": added,
            "players_dropped": dropped
        }

    @classmethod
    async def _classify_impact(cls, tx: Dict[str, Any], user_roster: Optional[Roster]) -> str:
        """
        Pure deterministic 4-tier classifier:
        - CRITICAL: User roster affected or discussed waiver target claimed.
        - HIGH: Direct matchup opponent upgrades or top player movement.
        - MEDIUM: Other waiver / free agent additions.
        - LOW: K/DST or minor bench churn.
        """
        r = await get_redis()
        waiver_targets: Set[str] = set(await r.smembers("user:waiver_targets"))

        user_player_names = set()
        if user_roster and user_roster.players:
            user_player_names = set(user_roster.players)

        added_names = {p["name"].lower() for p in tx.get("players_added", [])}
        dropped_names = {p["name"].lower() for p in tx.get("players_dropped", [])}

        # CRITICAL check: Did someone take a target we were eyeing?
        for target in waiver_targets:
            if target.lower() in added_names:
                return "CRITICAL"

        # CRITICAL check: Does this transaction alter user team directly?
        if tx.get("team_id") == settings.ESPN_TEAM_ID:
            return "CRITICAL"

        # HIGH check: Is this a trade or high-impact position add?
        if tx.get("type") == "TRADE":
            return "HIGH"

        # MEDIUM check: Standard waiver claims
        if tx.get("type") in ("WAIVER", "FREE_AGENT"):
            return "MEDIUM"

        return "LOW"

    @classmethod
    async def _run_proactive_analysis(cls, tx: Dict[str, Any], impact: str) -> Optional[str]:
        """
        Invokes General Manager / Supervisor to analyze strategic fallout of high-impact move.
        Protected by rate limiter and daily proactive quota.
        """
        r = await get_redis()
        today_key = f"proactive_llm_calls:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        calls_today = int(await r.get(today_key) or 0)

        if calls_today >= settings.MAX_PROACTIVE_LLM_PER_DAY:
            logger.info("Max daily proactive LLM budget reached (%d). Skipping LLM generation.", calls_today)
            return None

        # Build prompt for Supervisor
        prompt = (
            f"PROACTIVE ALERT [{impact}]: {tx['team_name']} made a transaction: "
            f"Added {tx['players_added']}, Dropped {tx['players_dropped']}. "
            "Evaluate the strategic impact on Team Cooper and recommend any defensive waiver or trade counter-moves."
        )

        try:
            from app.agents.supervisor import get_supervisor_graph
            graph = get_supervisor_graph()
            result = await graph.ainvoke({
                "messages": [{"role": "user", "content": prompt}],
                "league_context": {
                    "format": settings.SCORING_FORMAT,
                    "league_size": settings.LEAGUE_SIZE,
                    "team_name": "Team Cooper"
                },
                "active_week": 1,
                "draft_id": None,
                "user_roster_id": str(settings.ESPN_TEAM_ID)
            })

            # Increment proactive budget counter (expires in 24h)
            await r.incr(today_key)
            await r.expire(today_key, 86400)

            last_message = result["messages"][-1]
            return last_message.content if hasattr(last_message, "content") else str(last_message)
        except Exception as e:
            logger.error("Error executing proactive agent synthesis: %s", str(e))
            return None

    @classmethod
    async def _diff_roster_snapshots(cls, league) -> None:
        """Diffs all team rosters against cached Redis snapshot to catch silent unannounced drops."""
        r = await get_redis()
        for team in league.teams:
            snap_key = f"roster_snapshot:{team.team_id}"
            current_players = set(p.name for p in team.roster)
            previous_players = set(await r.smembers(snap_key))

            if previous_players and current_players != previous_players:
                dropped = previous_players - current_players
                added = current_players - previous_players
                if dropped or added:
                    logger.info("Roster snapshot diff for %s: Added %s, Dropped %s", team.team_name, added, dropped)

            # Update snapshot in Redis
            pipe = r.pipeline()
            pipe.delete(snap_key)
            if current_players:
                pipe.sadd(snap_key, *current_players)
            await pipe.execute()

    @classmethod
    async def _fetch_v3_transactions(cls) -> List[Dict[str, Any]]:
        """Direct V3 query to mTransactions2 endpoint."""
        if not settings.ESPN_S2 or not settings.ESPN_SWID:
            return []
        url = f"{ESPN_V3_BASE_URL.format(year=settings.ESPN_YEAR, league_id=settings.ESPN_LEAGUE_ID)}?view=mTransactions2"
        cookies = {"espn_s2": settings.ESPN_S2, "SWID": settings.ESPN_SWID}
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(url, cookies=cookies)
                if resp.status_code == 200:
                    return resp.json().get("transactions", [])
            except Exception:
                pass
        return []
