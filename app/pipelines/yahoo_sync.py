"""
Yahoo Fantasy Sports Ingestion Pipeline.
Pulls live 2026 NFL draft analysis, Yahoo Average Draft Position (ADP),
and official injury designations from Yahoo's public Fantasy API.
Zero authentication or API keys required.
"""

import json
import logging
from typing import Dict, Any, Optional
import httpx
from app.core.redis_client import get_redis
from app.pipelines.sleeper_sync import SleeperSyncService

logger = logging.getLogger(__name__)

YAHOO_DRAFT_ANALYSIS_URL = (
    "https://pub-api-ro.fantasysports.yahoo.com/fantasy/v2/game/nfl/players;"
    "position=ALL;start=0;count=250;sort=DA_AP;out=draft_analysis?format=json_f"
)


class YahooSyncService:
    @classmethod
    async def fetch_yahoo_draft_analysis(cls) -> Dict[str, Dict[str, Any]]:
        """
        Fetches live draft analysis and ADP for 250 top NFL players from Yahoo.
        Caches in Redis with a 12-hour TTL.
        Returns a dictionary keyed by normalized (name + pos).
        """
        cache_key = "cache:yahoo:draft_analysis:2026"
        try:
            r = await get_redis()
            cached = await r.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.debug("Redis cache check error for Yahoo: %s", str(e))

        logger.info("Fetching fresh draft analysis from Yahoo Fantasy Public API...")
        lookup: Dict[str, Dict[str, Any]] = {}

        try:
            async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
                resp = await client.get(YAHOO_DRAFT_ANALYSIS_URL)
                if resp.status_code != 200:
                    logger.warning("Yahoo API returned status %d", resp.status_code)
                    return {}

                data = resp.json()
                players_list = data.get("fantasy_content", {}).get("game", {}).get("players", [])

                for item in players_list:
                    player = item.get("player", {})
                    name_obj = player.get("name", {})
                    full_name = name_obj.get("full", "")
                    pos = player.get("display_position", "")
                    team = player.get("editorial_team_abbr", "")

                    if not full_name or not pos:
                        continue

                    # Positional normalization
                    normalized_pos = "D/ST" if pos in ("DEF", "DST", "D/ST") else pos

                    # Parse ADP
                    draft_analysis = player.get("draft_analysis", {})
                    avg_pick_raw = draft_analysis.get("average_pick")
                    yahoo_adp: Optional[float] = None
                    if avg_pick_raw and avg_pick_raw != "-":
                        try:
                            val = float(avg_pick_raw)
                            if 0 < val < 500:
                                yahoo_adp = round(val, 1)
                        except (ValueError, TypeError):
                            pass

                    # Parse injury notes
                    status = player.get("status")
                    status_full = player.get("status_full")
                    injury_note = player.get("injury_note")

                    norm_key = f"{SleeperSyncService.normalize_name(full_name)}:{normalized_pos}"

                    lookup[norm_key] = {
                        "name": full_name,
                        "position": normalized_pos,
                        "nfl_team": team.upper() if team else None,
                        "yahoo_adp": yahoo_adp,
                        "status": status,
                        "status_full": status_full,
                        "injury_note": injury_note,
                        "percent_drafted": draft_analysis.get("percent_drafted"),
                    }

            if lookup:
                try:
                    r = await get_redis()
                    await r.set(cache_key, json.dumps(lookup), ex=43200) # 12 hours
                    logger.info("Successfully cached %d Yahoo player draft records.", len(lookup))
                except Exception as e:
                    logger.debug("Could not cache Yahoo draft records in Redis: %s", str(e))

            return lookup

        except Exception as e:
            logger.error("Failed to fetch Yahoo draft analysis: %s", str(e))
            return {}
