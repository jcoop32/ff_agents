"""
PlayerWatch Pipeline: Autonomous player surveillance tick execution.
Monitors targeted players across web, RSS, and ESPN APIs.
Performs state diffing, adaptive frequency escalation, and proactive briefing generation.
"""

import json
import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.core.redis_client import get_redis
from app.tools.web_research import WebResearchService
from app.pipelines.notification_dispatcher import NotificationDispatcher

logger = logging.getLogger(__name__)


async def run_player_watch_tick(job_id: str) -> None:
    """
    Periodic tick for an individual player tracking job.
    Called by APScheduler on its dynamic interval.
    """
    r = await get_redis()
    raw_job = await r.get(f"gridiron:tracking_jobs:{job_id}")
    if not raw_job:
        logger.warning("PlayerWatch: Job %s not found in Redis, aborting tick", job_id)
        return

    job_data = json.loads(raw_job)
    if job_data.get("status") != "ACTIVE":
        return

    player_name = job_data.get("player_name")
    focus_areas = job_data.get("focus_areas", [])
    custom_query = job_data.get("custom_query")
    now = datetime.now(timezone.utc)

    # Check expiration
    expires_at_str = job_data.get("expires_at")
    if expires_at_str:
        expires_at = datetime.fromisoformat(expires_at_str)
        if now >= expires_at:
            job_data["status"] = "EXPIRED"
            await r.set(f"gridiron:tracking_jobs:{job_id}", json.dumps(job_data))
            await r.srem("gridiron:tracking_jobs:active", job_id)
            logger.info("PlayerWatch: Job %s expired at %s", job_id, expires_at_str)
            return

    logger.info("PlayerWatch: Running surveillance tick for '%s' (Job: %s)", player_name, job_id)

    # 1. Fetch latest multi-source intelligence
    intel = await WebResearchService.research_player(
        player_name=player_name,
        focus_areas=focus_areas,
        custom_query=custom_query,
    )
    summary_text = intel.get("summary", "")
    sources = intel.get("sources", [])

    # 2. Check previous state from Redis
    state_key = f"gridiron:tracking_state:{job_id}"
    raw_prev = await r.get(state_key)
    prev_state = json.loads(raw_prev) if raw_prev else {}

    # Compute content signature to prevent duplicate alerts
    content_hash = hashlib.md5(summary_text.strip().encode("utf-8")).hexdigest()
    prev_hash = prev_state.get("content_hash", "")

    # 3. Analyze severity & detect changes
    lower_text = summary_text.lower()
    is_critical = any(kw in lower_text for kw in ["out for season", "placed on ir", "torn", "ruptured", "ruled out", "suspended"])
    is_high = any(kw in lower_text for kw in ["doubtful", "game-time decision", "dnp", "did not practice", "benched", "named starter"])
    is_medium = any(kw in lower_text for kw in ["questionable", "limited practice", "lp", "sprained", "soreness"])

    urgency = "LOW"
    if is_critical:
        urgency = "CRITICAL"
    elif is_high:
        urgency = "HIGH"
    elif is_medium:
        urgency = "MEDIUM"

    is_new_intel = (content_hash != prev_hash) and bool(summary_text)

    # 4. Adaptive Scheduling Escalation
    current_freq = job_data.get("frequency_minutes", 60)
    should_escalate = False
    new_freq = current_freq

    if urgency == "CRITICAL" and current_freq > 30:
        new_freq = 15
        should_escalate = True
    elif urgency == "HIGH" and current_freq > 60:
        new_freq = 30
        should_escalate = True

    if should_escalate:
        from app.pipelines.scheduler_api import SchedulerAPI
        await SchedulerAPI.modify_tracking_job(
            job_id=job_id,
            new_frequency_minutes=new_freq,
            reason=f"Auto-escalated to every {new_freq}m due to {urgency} injury/status development."
        )

    # 5. Dispatch Briefing if new or noteworthy
    if is_new_intel or urgency in ["HIGH", "CRITICAL"]:
        title = f"🎯 Watch Alert: {player_name} Update"
        if urgency == "CRITICAL":
            title = f"🚨 URGENT: {player_name} Severe Status Change"
        elif urgency == "HIGH":
            title = f"⚠️ High Impact: {player_name} Alert"

        # Construct actionable recommendations
        action_items = []
        if is_critical or "ruled out" in lower_text:
            action_items.append({
                "type": "LINEUP_CHECK",
                "label": f"Swap {player_name} out of starting lineup immediately",
            })
            action_items.append({
                "type": "WAIVER_SCOUT",
                "label": f"Scout top available replacements for {player_name}",
            })

        await NotificationDispatcher.dispatch_briefing(
            briefing_type="TRACKING_UPDATE",
            urgency=urgency,
            title=title,
            content=summary_text,
            structured_data={
                "job_id": job_id,
                "player_name": player_name,
                "urgency": urgency,
                "sources": sources,
                "frequency_minutes": new_freq if should_escalate else current_freq,
            },
            action_items=action_items,
            source_agent="TrackingAgent",
        )

    # 6. Save current state and update job telemetry
    new_state = {
        "content_hash": content_hash,
        "last_summary": summary_text[:300],
        "urgency": urgency,
        "updated_at": now.isoformat(),
    }
    await r.set(state_key, json.dumps(new_state))

    job_data["last_run_at"] = now.isoformat()
    job_data["run_count"] = job_data.get("run_count", 0) + 1
    await r.set(f"gridiron:tracking_jobs:{job_id}", json.dumps(job_data))
    logger.info("PlayerWatch: Finished tick for %s (Urgency: %s, Next check at %dm)", player_name, urgency, new_freq)
