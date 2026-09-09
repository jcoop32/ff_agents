"""
SchedulerAPI: Adaptive scheduling infrastructure wrapping APScheduler AsyncIOScheduler.
Allows agents and users to dynamically spawn, modify, escalate, cancel, and persist
player tracking and surveillance jobs in real-time.
"""

import logging
import json
import uuid
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.base import JobLookupError

from app.core.config import settings
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

_scheduler_instance: Optional[AsyncIOScheduler] = None


class SchedulerAPI:
    """Central registry and controller for background scheduled tasks and dynamic tracking jobs."""

    @classmethod
    def get_scheduler(cls) -> AsyncIOScheduler:
        """Returns or instantiates the global AsyncIOScheduler singleton, resetting if loop closed."""
        global _scheduler_instance
        import asyncio

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if _scheduler_instance is not None:
            loop = getattr(_scheduler_instance, "_eventloop", None)
            if loop is not None and (loop.is_closed() or (current_loop is not None and loop != current_loop)):
                try:
                    if _scheduler_instance.running:
                        _scheduler_instance.shutdown(wait=False)
                except Exception:
                    pass
                _scheduler_instance = None

        if _scheduler_instance is None:
            _scheduler_instance = AsyncIOScheduler(
                timezone=settings.SCHEDULER_TIMEZONE
            )
        return _scheduler_instance

    @classmethod
    def start(cls) -> None:
        """Starts the scheduler if not already running."""
        sched = cls.get_scheduler()
        if not sched.running:
            sched.start()
            logger.info("SchedulerAPI: AsyncIOScheduler started successfully.")

    @classmethod
    def stop(cls) -> None:
        """Shuts down the scheduler gracefully."""
        global _scheduler_instance
        if _scheduler_instance and _scheduler_instance.running:
            _scheduler_instance.shutdown(wait=False)
            logger.info("SchedulerAPI: AsyncIOScheduler shut down.")
            _scheduler_instance = None

    @classmethod
    async def spawn_tracking_job(
        cls,
        player_name: str,
        focus_areas: Optional[List[str]] = None,
        frequency_minutes: int = 60,
        duration_hours: int = 48,
        reason: str = "User requested monitoring",
        source: str = "user",
        custom_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dynamically spawns a player surveillance job.
        Registers the job in APScheduler and persists state in Redis.
        """
        if focus_areas is None:
            focus_areas = ["injury", "depth_chart", "practice", "sentiment"]

        clean_slug = re.sub(r"[^a-zA-Z0-9]+", "_", player_name.strip().lower())
        short_id = uuid.uuid4().hex[:8]
        job_id = f"watch_{clean_slug}_{short_id}"

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=duration_hours)

        job_data = {
            "job_id": job_id,
            "player_name": player_name.strip(),
            "focus_areas": focus_areas,
            "frequency_minutes": frequency_minutes,
            "duration_hours": duration_hours,
            "reason": reason,
            "source": source,
            "custom_query": custom_query,
            "status": "ACTIVE",
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "last_run_at": None,
            "next_run_at": None,
            "run_count": 0,
            "history": [
                {
                    "timestamp": now.isoformat(),
                    "event": "SPAWNED",
                    "frequency_minutes": frequency_minutes,
                    "reason": reason,
                }
            ],
        }

        # Lazy import of worker execution func
        from app.pipelines.player_watch import run_player_watch_tick

        sched = cls.get_scheduler()
        if not sched.running:
            cls.start()

        # Register in APScheduler
        sched.add_job(
            run_player_watch_tick,
            trigger=IntervalTrigger(minutes=frequency_minutes),
            id=job_id,
            name=f"Player Watch: {player_name}",
            kwargs={"job_id": job_id},
            replace_existing=True,
            next_run_time=now,  # Run immediately on spawn
        )

        # Persist to Redis
        try:
            r = await get_redis()
            await r.set(f"gridiron:tracking_jobs:{job_id}", json.dumps(job_data))
            await r.sadd("gridiron:tracking_jobs:active", job_id)
            await r.sadd("gridiron:tracking_jobs:all", job_id)
        except Exception as e:
            logger.error("Failed to persist tracking job %s to Redis: %s", job_id, str(e))

        logger.info(
            "SchedulerAPI: Spawned tracking job %s for '%s' (every %dm, expires in %dh)",
            job_id,
            player_name,
            frequency_minutes,
            duration_hours,
        )
        return job_data

    @classmethod
    async def modify_tracking_job(
        cls,
        job_id: str,
        new_frequency_minutes: int,
        new_duration_hours: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Dynamically reschedules an active tracking job (escalation or cooldown).
        Updates APScheduler trigger and Redis metadata.
        """
        sched = cls.get_scheduler()
        r = await get_redis()
        raw = await r.get(f"gridiron:tracking_jobs:{job_id}")
        if not raw:
            logger.warning("Tracking job %s not found in Redis", job_id)
            return None

        job_data = json.loads(raw)
        now = datetime.now(timezone.utc)

        job_data["frequency_minutes"] = new_frequency_minutes
        if new_duration_hours:
            new_expires = now + timedelta(hours=new_duration_hours)
            job_data["expires_at"] = new_expires.isoformat()
            job_data["duration_hours"] = new_duration_hours

        hist_entry = {
            "timestamp": now.isoformat(),
            "event": "MODIFIED",
            "frequency_minutes": new_frequency_minutes,
            "reason": reason or "Frequency adjusted",
        }
        job_data.setdefault("history", []).append(hist_entry)

        # Update in APScheduler if running
        try:
            sched.reschedule_job(
                job_id,
                trigger=IntervalTrigger(minutes=new_frequency_minutes),
            )
        except JobLookupError:
            # Re-add if missing
            from app.pipelines.player_watch import run_player_watch_tick

            sched.add_job(
                run_player_watch_tick,
                trigger=IntervalTrigger(minutes=new_frequency_minutes),
                id=job_id,
                name=f"Player Watch: {job_data.get('player_name')}",
                kwargs={"job_id": job_id},
                replace_existing=True,
            )

        # Update Redis
        await r.set(f"gridiron:tracking_jobs:{job_id}", json.dumps(job_data))
        logger.info(
            "SchedulerAPI: Rescheduled tracking job %s to every %dm (reason: %s)",
            job_id,
            new_frequency_minutes,
            reason,
        )
        return job_data

    @classmethod
    async def cancel_tracking_job(
        cls, job_id: str, reason: str = "User cancelled"
    ) -> bool:
        """Cancels and cleans up a tracking job."""
        sched = cls.get_scheduler()
        try:
            sched.remove_job(job_id)
        except JobLookupError:
            pass

        r = await get_redis()
        raw = await r.get(f"gridiron:tracking_jobs:{job_id}")
        if raw:
            job_data = json.loads(raw)
            job_data["status"] = "CANCELLED"
            job_data.setdefault("history", []).append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": "CANCELLED",
                    "reason": reason,
                }
            )
            await r.set(f"gridiron:tracking_jobs:{job_id}", json.dumps(job_data))

        await r.srem("gridiron:tracking_jobs:active", job_id)
        logger.info("SchedulerAPI: Cancelled tracking job %s (reason: %s)", job_id, reason)
        return True

    @classmethod
    async def get_tracking_job(cls, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves single tracking job data decorated with live scheduler info."""
        r = await get_redis()
        raw = await r.get(f"gridiron:tracking_jobs:{job_id}")
        if not raw:
            return None
        data = json.loads(raw)
        sched = cls.get_scheduler()
        job = sched.get_job(job_id)
        if job and job.next_run_time:
            data["next_run_at"] = job.next_run_time.isoformat()
        return data

    @classmethod
    async def list_tracking_jobs(
        cls, include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """Lists active (or all) tracking jobs decorated with live next_run_time."""
        r = await get_redis()
        sched = cls.get_scheduler()

        if include_inactive:
            job_ids = await r.smembers("gridiron:tracking_jobs:all")
        else:
            job_ids = await r.smembers("gridiron:tracking_jobs:active")

        jobs = []
        for jid in job_ids:
            raw = await r.get(f"gridiron:tracking_jobs:{jid}")
            if not raw:
                continue
            data = json.loads(raw)
            job = sched.get_job(jid)
            if job and job.next_run_time:
                data["next_run_at"] = job.next_run_time.isoformat()
            jobs.append(data)

        # Sort by creation desc
        jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return jobs

    @classmethod
    async def restore_tracking_jobs(cls) -> int:
        """
        Restores tracking jobs from Redis upon worker startup.
        Re-registers unexpired jobs into APScheduler.
        """
        r = await get_redis()
        active_ids = await r.smembers("gridiron:tracking_jobs:active")
        now = datetime.now(timezone.utc)
        restored = 0

        from app.pipelines.player_watch import run_player_watch_tick

        sched = cls.get_scheduler()
        if not sched.running:
            cls.start()

        for jid in active_ids:
            raw = await r.get(f"gridiron:tracking_jobs:{jid}")
            if not raw:
                await r.srem("gridiron:tracking_jobs:active", jid)
                continue

            try:
                job_data = json.loads(raw)
                expires_at_str = job_data.get("expires_at")
                if expires_at_str:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    if now >= expires_at:
                        job_data["status"] = "EXPIRED"
                        await r.set(f"gridiron:tracking_jobs:{jid}", json.dumps(job_data))
                        await r.srem("gridiron:tracking_jobs:active", jid)
                        continue

                freq = job_data.get("frequency_minutes", 60)
                sched.add_job(
                    run_player_watch_tick,
                    trigger=IntervalTrigger(minutes=freq),
                    id=jid,
                    name=f"Player Watch: {job_data.get('player_name')}",
                    kwargs={"job_id": jid},
                    replace_existing=True,
                )
                restored += 1
            except Exception as e:
                logger.error("Error restoring tracking job %s: %s", jid, str(e))

        logger.info("SchedulerAPI: Restored %d active tracking jobs from Redis.", restored)
        return restored

    @classmethod
    async def cleanup_expired_jobs(cls) -> int:
        """Scans active jobs and expires any that have passed expires_at."""
        r = await get_redis()
        active_ids = await r.smembers("gridiron:tracking_jobs:active")
        now = datetime.now(timezone.utc)
        expired_count = 0
        sched = cls.get_scheduler()

        for jid in active_ids:
            raw = await r.get(f"gridiron:tracking_jobs:{jid}")
            if not raw:
                await r.srem("gridiron:tracking_jobs:active", jid)
                continue

            job_data = json.loads(raw)
            expires_at_str = job_data.get("expires_at")
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
                if now >= expires_at:
                    job_data["status"] = "EXPIRED"
                    job_data.setdefault("history", []).append(
                        {
                            "timestamp": now.isoformat(),
                            "event": "EXPIRED",
                            "reason": "Tracking duration completed",
                        }
                    )
                    try:
                        sched.remove_job(jid)
                    except JobLookupError:
                        pass
                    await r.set(f"gridiron:tracking_jobs:{jid}", json.dumps(job_data))
                    await r.srem("gridiron:tracking_jobs:active", jid)
                    expired_count += 1
                    logger.info("SchedulerAPI: Job %s expired and cleaned up", jid)

        return expired_count

    @classmethod
    async def trigger_job_now(cls, job_id: str) -> bool:
        """Forces an immediate execution of a registered job."""
        sched = cls.get_scheduler()
        job = sched.get_job(job_id)
        if job:
            job.modify(next_run_time=datetime.now(timezone.utc))
            return True
        return False
