"""
Background Worker Loop with APScheduler AsyncIOScheduler.
Orchestrates autonomous multi-agent proactive routines, dynamic surveillance jobs,
and real-time event streaming.
"""

import asyncio
import logging
import signal
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.redis_client import init_redis_pool, close_redis
from app.pipelines.scheduler_api import SchedulerAPI
from app.pipelines.espn_sync import ESPNSyncService
from app.pipelines.draft_prep import DraftPrepService
from app.pipelines.action_executor import ActionExecutor
from app.pipelines.proactive_jobs import (
    job_morning_digest,
    job_waiver_scout,
    job_trade_finder,
    job_lineup_lock,
    job_practice_monitor,
    job_news_poller,
    job_transaction_poller,
    job_power_rankings,
    job_season_strategy,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gridiron.worker")


async def run_worker():
    logger.info("Starting Gridiron AI Autonomous Multi-Agent Worker...")
    await init_redis_pool()

    # Ensure database schema exists
    try:
        from app.core.database import init_db
        await init_db()
        logger.info("PostgreSQL database tables and vector extensions verified.")
    except Exception as e:
        logger.warning("Database schema check notice: %s", str(e))

    # Initial sync on worker boot
    try:
        logger.info("Running initial ESPN league sync & keeper detection...")
        await ESPNSyncService.sync_league_metadata()
        await DraftPrepService.sync_keepers()
        await DraftPrepService.sync_adp_rankings()
    except Exception as e:
        logger.warning("Initial startup sync encountered notice: %s", str(e))

    # Initialize Scheduler
    sched = SchedulerAPI.get_scheduler()

    # ==========================================
    # Register 9 Autonomous Proactive Jobs
    # ==========================================
    if settings.PROACTIVE_MODE_ENABLED:
        logger.info("Registering autonomous proactive agent schedules...")

        # 1. Morning Digest (Daily 07:00)
        sched.add_job(
            job_morning_digest,
            trigger=CronTrigger.from_crontab(settings.MORNING_DIGEST_CRON, timezone=settings.SCHEDULER_TIMEZONE),
            id="job_morning_digest",
            name="Morning Intelligence Digest",
            replace_existing=True,
        )

        # 2. Waiver Wire Scout (06:00, 18:00)
        sched.add_job(
            job_waiver_scout,
            trigger=CronTrigger.from_crontab(settings.WAIVER_SCOUT_CRON, timezone=settings.SCHEDULER_TIMEZONE),
            id="job_waiver_scout",
            name="Waiver Wire Upgrade Scout",
            replace_existing=True,
        )

        # 3. Trade Finder (Daily 11:00)
        sched.add_job(
            job_trade_finder,
            trigger=CronTrigger.from_crontab(settings.TRADE_FINDER_CRON, timezone=settings.SCHEDULER_TIMEZONE),
            id="job_trade_finder",
            name="League Trade Opportunity Scanner",
            replace_existing=True,
        )

        # 4. Sunday Lineup Lock Sentinel (11:30 & 12:45)
        sched.add_job(
            job_lineup_lock,
            trigger=CronTrigger.from_crontab(settings.LINEUP_LOCK_CRON, timezone=settings.SCHEDULER_TIMEZONE),
            id="job_lineup_lock",
            name="Sunday Kickoff Lineup Sentinel",
            replace_existing=True,
        )

        # 5. Practice Report Monitor (Wed/Thu/Fri 15:00 & 17:00)
        sched.add_job(
            job_practice_monitor,
            trigger=CronTrigger.from_crontab(settings.PRACTICE_MONITOR_CRON, timezone=settings.SCHEDULER_TIMEZONE),
            id="job_practice_monitor",
            name="Mid-Week Practice Injury Monitor",
            replace_existing=True,
        )

        # 6. Volatile News RSS Poller (Every 15m)
        sched.add_job(
            job_news_poller,
            trigger=IntervalTrigger(minutes=settings.NEWS_POLL_INTERVAL_MINUTES),
            id="job_news_poller",
            name="RSS Breaking News Poller",
            replace_existing=True,
        )

        # 7. Proactive League Activity Poller (Every 10m)
        sched.add_job(
            job_transaction_poller,
            trigger=IntervalTrigger(minutes=settings.LEAGUE_MONITOR_INTERVAL_MINUTES),
            id="job_transaction_poller",
            name="ESPN League Transaction Poller",
            replace_existing=True,
        )

        # 8. Weekly Power Rankings (Tuesday 09:00)
        sched.add_job(
            job_power_rankings,
            trigger=CronTrigger.from_crontab(settings.POWER_RANKINGS_CRON, timezone=settings.SCHEDULER_TIMEZONE),
            id="job_power_rankings",
            name="Weekly League Power Rankings",
            replace_existing=True,
        )

        # 9. Season Strategy Planner (Wednesday 10:00)
        sched.add_job(
            job_season_strategy,
            trigger=CronTrigger.from_crontab(settings.SEASON_STRATEGY_CRON, timezone=settings.SCHEDULER_TIMEZONE),
            id="job_season_strategy",
            name="Macro Season-Long Strategy Planner",
            replace_existing=True,
        )

    # ==========================================
    # Maintenance & Expiry Sweepers
    # ==========================================
    sched.add_job(
        SchedulerAPI.cleanup_expired_jobs,
        trigger=IntervalTrigger(minutes=5),
        id="internal_cleanup_expired_tracking",
        name="Tracking Jobs Expiry Sweeper",
        replace_existing=True,
    )

    sched.add_job(
        ActionExecutor.expire_stale_actions,
        trigger=IntervalTrigger(minutes=15),
        id="internal_cleanup_stale_actions",
        name="Pending Actions Expiry Sweeper",
        replace_existing=True,
    )

    # Restore dynamic tracking jobs persisted in Redis
    restored = await SchedulerAPI.restore_tracking_jobs()
    logger.info("Scheduler restored %d active tracking jobs from Redis.", restored)

    # Start scheduler
    SchedulerAPI.start()

    logger.info("Gridiron AI Worker running. Ready for autonomous triggers.")

    # Graceful shutdown handling
    stop_event = asyncio.Event()

    def _handle_signal(*args):
        logger.info("Received termination signal. Initiating graceful shutdown...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            pass

    # Wait until signal received
    await stop_event.wait()

    logger.info("Shutting down scheduler and database connections...")
    SchedulerAPI.stop()
    await close_redis()
    logger.info("Gridiron AI Worker successfully stopped.")


def main():
    try:
        asyncio.run(run_worker())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped.")


if __name__ == "__main__":
    main()
