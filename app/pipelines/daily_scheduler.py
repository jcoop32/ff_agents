"""
Daily Ingestion & Pre-Draft Intelligence Scheduler.
Executes once every 24 hours (or on demand), ingesting Sleeper, ESPN, Yahoo,
and beat reporting RSS feeds, computing consensus ADP, and caching a structured
pre-draft intelligence digest in Redis (<2ms access for agents).
"""

import json
import time
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy import select

from app.core.config import settings
from app.core.redis_client import get_redis
from app.core.database import AsyncSessionLocal
from app.models.player import Player
from app.pipelines.consensus_engine import ConsensusEngine
from app.pipelines.draft_prep import DraftPrepService
from app.pipelines.news_stream import NewsIngestionService

logger = logging.getLogger(__name__)

DAILY_SYNC_INTERVAL_SECONDS = 86400  # 24 hours


class DailySchedulerService:
    """Orchestrates the 24-hour automated data ingestion pipeline and compiles Redis digest."""

    @classmethod
    async def should_run_daily_sync(cls) -> bool:
        """Returns True if the daily sync has never run or last ran >24 hours ago."""
        try:
            r = await get_redis()
            last_run = await r.get("sync:last_daily_run")
            if not last_run:
                return True
            elapsed = time.time() - float(last_run)
            return elapsed >= DAILY_SYNC_INTERVAL_SECONDS
        except Exception as e:
            logger.warning("Error checking daily sync timestamp: %s", str(e))
            return True

    @classmethod
    async def run_daily_ingestion_and_synthesis(cls, force: bool = False) -> Dict[str, Any]:
        """
        Runs the comprehensive ingestion pipeline:
        1. Ingests Sleeper, ESPN, Yahoo, and RSS news beat feeds.
        2. Computes consensus ADP, projections, and injury intelligence.
        3. Seeds Team Cooper's locked Round 8 keeper (Javonte Williams).
        4. Compiles and caches a Pre-Draft Scouting Digest in Redis key 'draft_intel:digest:2026'.
        5. Generates dynamic, data-driven pre-draft prompts in Redis key 'draft_intel:prompts:2026'.
        6. Updates 'sync:last_daily_run' timestamp.
        """
        if not force and not await cls.should_run_daily_sync():
            r = await get_redis()
            last_run = await r.get("sync:last_daily_run")
            return {
                "synced": False,
                "message": f"Daily sync skipped: last executed {int(time.time() - float(last_run or 0))}s ago (interval 24h).",
                "last_run": float(last_run or 0)
            }

        logger.info("=== Starting 24-Hour Daily Ingestion Pipeline ===")
        start_ts = time.time()

        # 1. Ingest news feeds first for fresh injury context
        try:
            await NewsIngestionService.poll_rss_feeds()
        except Exception as e:
            logger.warning("News RSS polling error during daily sync: %s", str(e))

        # 2. Ingest ESPN league metadata and top player metadata batch
        try:
            from app.pipelines.espn_sync import ESPNSyncService
            await ESPNSyncService.sync_league_metadata()
        except Exception as e:
            logger.warning("ESPN sync warning during daily sync: %s", str(e))

        # 3. Blend Sleeper, Yahoo, ESPN into consensus projections and multi-source ADP
        try:
            consensus_summary = await ConsensusEngine.blend_and_store_projections()
            logger.info("Consensus computed: %s", str(consensus_summary))
        except Exception as e:
            logger.error("Consensus engine failed during daily sync: %s", str(e))

        # 3. Ensure Team Cooper keeper is locked in Redis
        keeper = await DraftPrepService.get_user_keeper(team_id=2)

        # 4. Compile the comprehensive Pre-Draft Digest from DB
        digest = await cls._compile_pre_draft_digest(keeper)

        # 5. Generate dynamic contextual prompts based on recent data
        prompts = cls._generate_dynamic_prompts(digest)

        # 6. Store digest and prompts in Redis (<2ms access for agents and UI)
        r = await get_redis()
        await r.set("draft_intel:digest:2026", json.dumps(digest))
        await r.set("draft_intel:prompts:2026", json.dumps(prompts))
        await r.set("sync:last_daily_run", str(time.time()))

        elapsed_sec = round(time.time() - start_ts, 2)
        logger.info("=== Daily Ingestion Pipeline Completed in %ss ===", elapsed_sec)

        return {
            "synced": True,
            "duration_seconds": elapsed_sec,
            "keeper": keeper,
            "digest_summary": {
                "top_vorp_count": len(digest.get("top_vorp_targets", [])),
                "adp_arbitrage_count": len(digest.get("adp_arbitrage_targets", [])),
                "injury_alerts_count": len(digest.get("injury_watchlist", [])),
                "prompts_count": len(prompts)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @classmethod
    async def _compile_pre_draft_digest(cls, keeper: Dict[str, Any]) -> Dict[str, Any]:
        """Queries database to extract top VORP targets, tier cliffs, ADP arbitrage, and injury notes."""
        async with AsyncSessionLocal() as session:
            stmt = select(Player).where(Player.consensus_proj > 0).order_by(Player.consensus_proj.desc())
            res = await session.execute(stmt)
            players = res.scalars().all()

            pos_groups: Dict[str, List[Player]] = {"WR": [], "RB": [], "TE": [], "QB": []}
            for p in players:
                if p.position in pos_groups:
                    pos_groups[p.position].append(p)

            # Calculate VORP with 3-WR PPR baseline
            baselines = {
                "QB": (pos_groups["QB"][12].consensus_proj if len(pos_groups["QB"]) > 12 else 280.0),
                "RB": (pos_groups["RB"][24].consensus_proj if len(pos_groups["RB"]) > 24 else 170.0),
                "WR": (pos_groups["WR"][36].consensus_proj if len(pos_groups["WR"]) > 36 else 160.0),
                "TE": (pos_groups["TE"][12].consensus_proj if len(pos_groups["TE"]) > 12 else 115.0),
            }

            # Top 15 cross-positional VORP
            vorp_targets = []
            for p in players[:60]:
                b_line = baselines.get(p.position, 100.0)
                vorp = round(max(0.0, (p.consensus_proj or 0.0) - b_line), 1)
                vorp_targets.append({
                    "name": p.name,
                    "position": p.position,
                    "team": p.team,
                    "vorp": vorp,
                    "consensus_pts": round(float(p.consensus_proj or 0.0), 1),
                    "consensus_adp": round(float(p.consensus_adp), 1) if p.consensus_adp else None,
                    "injury_status": p.injury_status or "Healthy"
                })
            vorp_targets.sort(key=lambda x: x["vorp"], reverse=True)

            # ADP Arbitrage (Yahoo vs Sleeper vs ESPN divergence)
            arbitrage = []
            for p in players:
                adps = [v for v in [p.sleeper_adp, p.espn_adp, p.yahoo_adp] if v is not None and v > 0]
                if len(adps) >= 2:
                    spread = round(max(adps) - min(adps), 1)
                    if spread >= 6.0:
                        cheapest = "Yahoo" if p.yahoo_adp == min(adps) else ("Sleeper" if p.sleeper_adp == min(adps) else "ESPN")
                        expensive = "Yahoo" if p.yahoo_adp == max(adps) else ("Sleeper" if p.sleeper_adp == max(adps) else "ESPN")
                        arbitrage.append({
                            "name": p.name,
                            "position": p.position,
                            "team": p.team,
                            "spread": spread,
                            "sleeper_adp": p.sleeper_adp,
                            "espn_adp": p.espn_adp,
                            "yahoo_adp": p.yahoo_adp,
                            "consensus_adp": p.consensus_adp,
                            "cheapest_source": cheapest,
                            "expensive_source": expensive
                        })
            arbitrage.sort(key=lambda x: x["spread"], reverse=True)

            # Injury Watchlist
            injury_watchlist = []
            for p in players:
                if (p.injury_status and p.injury_status.lower() not in ("active", "healthy", "")) or p.injury_notes:
                    injury_watchlist.append({
                        "name": p.name,
                        "position": p.position,
                        "team": p.team,
                        "status": p.injury_status,
                        "notes": p.injury_notes or "Under monitoring",
                        "consensus_adp": p.consensus_adp
                    })
            injury_watchlist.sort(key=lambda x: (x["consensus_adp"] is None, x["consensus_adp"] or 999.0))

            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "league_format": "12-Team Full PPR, 3-WR + 1 FLEX, 10 Starters",
                "draft_status": "PRE_DRAFT",
                "draft_order": "TBD",
                "keeper": keeper,
                "strategy_directive": (
                    "Team Cooper locks Javonte Williams (DAL RB) in Round 8 at significant surplus value (ADP #33.5). "
                    "In this 3-WR format, prioritize Tier 1 and Tier 2 Wide Receivers in early rounds "
                    "to secure an elite weekly floor before WR depth evaporates."
                ),
                "baselines": baselines,
                "top_vorp_targets": vorp_targets[:15],
                "adp_arbitrage_targets": arbitrage[:8],
                "injury_watchlist": injury_watchlist[:12]
            }

    @classmethod
    def _generate_dynamic_prompts(cls, digest: Dict[str, Any]) -> List[str]:
        """Generates dynamic pre-draft inquiry prompts grounded in the latest digest."""
        prompts = [
            "How does keeping Javonte Williams in Round 8 impact our early-round WR vs RB draft priority?",
            "What is our best draft strategy in a 3-WR format with a locked Round 8 RB keeper?",
        ]

        # Ingest top arbitrage candidate
        arb = digest.get("adp_arbitrage_targets", [])
        if arb:
            top_arb = arb[0]
            prompts.append(
                f"Why is {top_arb['name']} drafted at #{top_arb.get('yahoo_adp')} on Yahoo vs #{top_arb.get('sleeper_adp')} on Sleeper?"
            )

        # Ingest top injured star
        inj = digest.get("injury_watchlist", [])
        if inj:
            top_inj = inj[0]
            prompts.append(
                f"How should we handle {top_inj['name']}'s injury risk ({top_inj.get('notes')}) on our draft board?"
            )

        prompts.append("Run VORP baseline analysis on Tier 1 and Tier 2 Wide Receivers")
        prompts.append("Should we draft Hero RB or Zero RB given our Round 8 Javonte Williams surplus?")
        return prompts[:5]

    @classmethod
    async def get_cached_digest(cls) -> Optional[Dict[str, Any]]:
        """Reads the pre-draft scouting digest directly from Redis (<2ms)."""
        r = await get_redis()
        raw = await r.get("draft_intel:digest:2026")
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
        # If not present, run compilation
        res = await cls.run_daily_ingestion_and_synthesis(force=True)
        raw = await r.get("draft_intel:digest:2026")
        return json.loads(raw) if raw else None

    @classmethod
    async def get_cached_prompts(cls) -> List[str]:
        """Reads cached dynamic prompts from Redis, falling back to compiled prompts."""
        r = await get_redis()
        raw = await r.get("draft_intel:prompts:2026")
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
        digest = await cls.get_cached_digest()
        if digest:
            prompts = cls._generate_dynamic_prompts(digest)
            await r.set("draft_intel:prompts:2026", json.dumps(prompts))
            return prompts
        return [
            "How does keeping Javonte Williams in Round 8 impact our early-round WR vs RB draft priority?",
            "What is our best draft strategy in a 3-WR format with a locked Round 8 RB keeper?",
            "Which players have the biggest ADP discount on Yahoo vs Sleeper right now?",
            "Run VORP baseline analysis on Tier 1 and Tier 2 Wide Receivers",
            "Should we draft Hero RB or Zero RB given our Round 8 Javonte Williams surplus?"
        ]
