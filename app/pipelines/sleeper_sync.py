"""
Sleeper Open API Ingestion Pipeline.
Pulls 2026 NFL player projections and PPR ADP with zero rate limits and no authentication required.
Recalculates raw stat volume to match the user's exact 12-team PPR league scoring rules.
"""

import json
import logging
import re
from typing import Dict, Any, Optional
import httpx
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

SLEEPER_PROJECTIONS_URL = "https://api.sleeper.app/projections/nfl/2026?season_type=regular"


class SleeperSyncService:
    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalizes player name for cross-platform identity matching."""
        if not name:
            return ""
        # Remove common suffixes and special characters
        clean = re.sub(r"\b(jr\.?|sr\.?|ii|iii|iv|v)\b", "", name, flags=re.IGNORECASE)
        clean = re.sub(r"[^\w\s]", "", clean)
        return " ".join(clean.lower().split())

    @classmethod
    def calculate_custom_points(cls, stats: Dict[str, Any]) -> float:
        """
        Calculates 2026 season fantasy points using exact league settings:
        - Passing: 1 pt per 20 yds (0.05 pt/yd), 4 pt TD, -2 INT
        - Rushing: 1 pt per 10 yds (0.1 pt/yd), 6 pt TD
        - Receiving: 1.0 PPR, 1 pt per 10 yds (0.1 pt/yd), 6 pt TD
        - Misc: -2 fumble lost, 2 pt 2-point conversions
        """
        pass_yd = float(stats.get("pass_yd") or 0.0)
        pass_td = float(stats.get("pass_td") or 0.0)
        pass_int = float(stats.get("pass_int") or 0.0)

        rush_yd = float(stats.get("rush_yd") or 0.0)
        rush_td = float(stats.get("rush_td") or 0.0)

        rec = float(stats.get("rec") or 0.0)
        rec_yd = float(stats.get("rec_yd") or 0.0)
        rec_td = float(stats.get("rec_td") or 0.0)

        fum_lost = float(stats.get("fum_lost") or 0.0)
        pass_2pt = float(stats.get("pass_2pt") or 0.0)
        rush_2pt = float(stats.get("rush_2pt") or 0.0)
        rec_2pt = float(stats.get("rec_2pt") or 0.0)

        # Formula
        pass_pts = (pass_yd * 0.05) + (pass_td * 4.0) + (pass_int * -2.0)
        rush_pts = (rush_yd * 0.10) + (rush_td * 6.0)
        rec_pts = (rec * 1.0) + (rec_yd * 0.10) + (rec_td * 6.0)
        misc_pts = (fum_lost * -2.0) + ((pass_2pt + rush_2pt + rec_2pt) * 2.0)

        pts = pass_pts + rush_pts + rec_pts + misc_pts
        return max(0.0, round(pts, 2))

    @classmethod
    async def fetch_sleeper_projections(cls) -> Dict[str, Dict[str, Any]]:
        """
        Fetches 2026 regular season projections and PPR ADP from Sleeper.
        Caches results in Redis with a 24-hour TTL.
        Returns a dictionary keyed by normalized (name + pos).
        """
        cache_key = "cache:sleeper:projections:2026"
        try:
            r = await get_redis()
            cached = await r.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.debug("Redis cache check error for Sleeper: %s", str(e))

        logger.info("Fetching fresh 2026 projections from Sleeper Open API...")
        players_lookup: Dict[str, Dict[str, Any]] = {}

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.get(SLEEPER_PROJECTIONS_URL)
                if resp.status_code != 200:
                    logger.warning("Sleeper API returned status %d", resp.status_code)
                    return {}

                data = resp.json()
                for item in data:
                    player = item.get("player") or {}
                    stats = item.get("stats") or {}
                    fn = player.get("first_name", "")
                    ln = player.get("last_name", "")
                    full_name = f"{fn} {ln}".strip()
                    pos = player.get("position", "")
                    team = player.get("team")

                    if not full_name or not pos or pos not in ("QB", "RB", "WR", "TE", "K", "DEF"):
                        continue

                    # Positional normalization for defense
                    normalized_pos = "D/ST" if pos == "DEF" else pos

                    # Calculate fantasy points under our custom scoring rules
                    calc_points = cls.calculate_custom_points(stats)
                    # If kicker or dst, fallback to sleeper default points if calculated is 0
                    if calc_points == 0.0 and pos in ("K", "DEF"):
                        calc_points = float(stats.get("pts_ppr") or stats.get("pts_std") or 0.0)

                    if calc_points <= 0.0:
                        continue

                    adp_raw = stats.get("adp_ppr")
                    adp = float(adp_raw) if adp_raw and float(adp_raw) < 900.0 else None

                    player_payload = {
                        "sleeper_id": item.get("player_id"),
                        "name": full_name,
                        "position": normalized_pos,
                        "team": team,
                        "projected_points": calc_points,
                        "projected_avg": round(calc_points / 17.0, 2),
                        "adp": adp,
                        "injury_status": player.get("injury_status"),
                        "injury_body_part": player.get("injury_body_part"),
                        "injury_notes": player.get("injury_notes"),
                        "stats": {
                            "pass_yd": stats.get("pass_yd"),
                            "pass_td": stats.get("pass_td"),
                            "pass_int": stats.get("pass_int"),
                            "rush_yd": stats.get("rush_yd"),
                            "rush_td": stats.get("rush_td"),
                            "rec": stats.get("rec"),
                            "rec_yd": stats.get("rec_yd"),
                            "rec_td": stats.get("rec_td"),
                        }
                    }

                    norm_key = f"{cls.normalize_name(full_name)}:{normalized_pos}"
                    players_lookup[norm_key] = player_payload

            # Save in Redis with 24-hour expiration
            if players_lookup:
                try:
                    r = await get_redis()
                    await r.set(cache_key, json.dumps(players_lookup), ex=86400)
                    logger.info("Successfully cached %d Sleeper player projections.", len(players_lookup))
                except Exception as e:
                    logger.debug("Could not cache Sleeper projections in Redis: %s", str(e))

            return players_lookup

        except Exception as e:
            logger.error("Failed to fetch Sleeper projections: %s", str(e))
            return {}
