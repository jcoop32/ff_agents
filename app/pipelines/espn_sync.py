"""
Tier 1 Data Ingestion Pipeline: ESPN Fantasy Sync.
Synchronizes league settings, rosters, player entity metadata, and free agents.
"""

import json
import logging
from typing import Optional, Dict, Any, List
import httpx
from espn_api.football import League as ESPNLeague
from sqlalchemy import select, delete
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis_client import RedisRepository, get_redis
from app.models.player import Player
from app.models.league import League, Roster

logger = logging.getLogger(__name__)

ESPN_V3_BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league_id}"


class ESPNSyncService:
    """Handles bidirectional synchronization with ESPN Fantasy APIs."""

    @staticmethod
    def get_espn_league_instance() -> Optional[ESPNLeague]:
        """Creates an authenticated espn_api League instance."""
        try:
            return ESPNLeague(
                league_id=settings.ESPN_LEAGUE_ID,
                year=settings.ESPN_YEAR,
                espn_s2=settings.ESPN_S2 if settings.ESPN_S2 else None,
                swid=settings.ESPN_SWID if settings.ESPN_SWID else None
            )
        except Exception as e:
            logger.error("Failed to initialize ESPN League client: %s", str(e))
            return None

    @classmethod
    async def verify_credentials(cls) -> Dict[str, Any]:
        """Tests validity of ESPN S2 and SWID cookies."""
        if not settings.ESPN_S2 or not settings.ESPN_SWID:
            return {
                "valid": False,
                "status": "missing_cookies",
                "message": "ESPN_S2 or ESPN_SWID cookies are not configured in environment."
            }

        url = ESPN_V3_BASE_URL.format(year=settings.ESPN_YEAR, league_id=settings.ESPN_LEAGUE_ID)
        cookies = {"espn_s2": settings.ESPN_S2, "SWID": settings.ESPN_SWID}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(url, cookies=cookies)
                if resp.status_code == 200:
                    return {"valid": True, "status": "authenticated", "message": "ESPN cookies are active."}
                elif resp.status_code in (401, 403):
                    return {
                        "valid": False,
                        "status": "expired_cookies",
                        "message": f"ESPN authentication rejected (Status {resp.status_code}). Cookies require re-authentication."
                    }
                else:
                    return {"valid": False, "status": "error", "message": f"Unexpected ESPN response {resp.status_code}."}
            except Exception as e:
                return {"valid": False, "status": "network_error", "message": str(e)}

    @classmethod
    async def sync_league_metadata(cls) -> Dict[str, Any]:
        """Fetches and persists League rules, scoring configuration, and team rosters."""
        league_inst = cls.get_espn_league_instance()
        if not league_inst:
            return {"success": False, "error": "Could not connect to ESPN"}

        async with AsyncSessionLocal() as session:
            # Upsert League entity
            stmt = select(League).where(League.espn_league_id == str(settings.ESPN_LEAGUE_ID))
            result = await session.execute(stmt)
            db_league = result.scalar_one_or_none()

            roster_slots = {
                "QB": 1,
                "RB": 2,
                "WR": settings.NUM_WR_SLOTS,
                "TE": 1,
                "FLEX": 1 if settings.HAS_FLEX else 0,
                "K": 1,
                "DST": 1,
                "BENCH": settings.BENCH_SLOTS,
                "IR": settings.IR_SLOTS
            }

            if not db_league:
                db_league = League(
                    espn_league_id=str(settings.ESPN_LEAGUE_ID),
                    name=getattr(league_inst, "name", "WA minus Josh"),
                    scoring_format=settings.SCORING_FORMAT,
                    season=settings.ESPN_YEAR,
                    total_teams=len(league_inst.teams),
                    roster_positions=roster_slots
                )
                session.add(db_league)
                await session.flush()
            else:
                db_league.total_teams = len(league_inst.teams)
                db_league.roster_positions = roster_slots

            # Sync each team roster
            synced_teams = 0
            # Fetch batch ESPN ADP and season outlook metadata
            espn_meta = await cls.fetch_espn_player_metadata_batch()

            for team in league_inst.teams:
                player_ids = []
                starter_ids = []
                lineup_slots = {}
                for player in team.roster:
                    p_id = str(getattr(player, "playerId", player.name))
                    player_ids.append(p_id)

                    raw_slot = getattr(player, "lineupSlot", "BE")
                    if raw_slot == "BE":
                        slot = "BENCH"
                    elif raw_slot in ("RB/WR/TE", "RB/WR", "WR/TE", "OP"):
                        slot = "FLEX"
                        starter_ids.append(p_id)
                    elif raw_slot == "IR":
                        slot = "IR"
                    else:
                        slot = raw_slot
                        starter_ids.append(p_id)

                    lineup_slots[p_id] = slot

                    # Index player in Postgres and Redis
                    await cls._upsert_player(session, player, espn_meta, current_week=league_inst.current_week)

                # Upsert team roster record
                r_stmt = select(Roster).where(
                    Roster.league_id == db_league.id,
                    Roster.espn_team_id == team.team_id
                )
                r_res = await session.execute(r_stmt)
                db_roster = r_res.scalar_one_or_none()

                rec = {"wins": team.wins, "losses": team.losses, "ties": getattr(team, "ties", 0)}
                if not db_roster:
                    db_roster = Roster(
                        league_id=db_league.id,
                        espn_team_id=team.team_id,
                        team_name=team.team_name,
                        owner_name=getattr(team, "owner", team.team_name),
                        players=player_ids,
                        starters=starter_ids,
                        lineup_slots=lineup_slots,
                        record=rec,
                        points_for=float(team.points_for),
                        points_against=float(getattr(team, "points_against", 0.0)),
                        standing=getattr(team, "standing", 1)
                    )
                    session.add(db_roster)
                else:
                    db_roster.team_name = team.team_name
                    db_roster.players = player_ids
                    db_roster.starters = starter_ids
                    db_roster.lineup_slots = lineup_slots
                    db_roster.record = rec
                    db_roster.points_for = float(team.points_for)
                    db_roster.standing = getattr(team, "standing", 1)

                synced_teams += 1

            # Prune any stale rosters no longer in the active ESPN league
            active_team_ids = [int(team.team_id) for team in league_inst.teams]
            del_stmt = delete(Roster).where(Roster.espn_team_id.not_in(active_team_ids))
            await session.execute(del_stmt)

            # Also index top available draft pool players with projections
            try:
                fa_players = league_inst.free_agents(size=120)
                for fa in fa_players:
                    await cls._upsert_player(session, fa, espn_meta)
                logger.info("Indexed %d top draft pool players.", len(fa_players))
            except Exception as e:
                logger.warning("Could not sync free agent draft pool: %s", str(e))

            await session.commit()

        # Invalidate cached standings so UI picks up active teams immediately
        try:
            r = await get_redis()
            await r.delete("cache:league:standings")
        except Exception:
            pass

        # Trigger multi-source consensus blend with Sleeper
        try:
            from app.pipelines.consensus_engine import ConsensusEngine
            await ConsensusEngine.blend_and_store_projections()
            logger.info("Multi-source consensus projections synchronized.")
        except Exception as e:
            logger.warning("Consensus blending error: %s", str(e))

        logger.info("Successfully synced ESPN league and %d rosters.", synced_teams)
        return {"success": True, "synced_teams": synced_teams}

    @classmethod
    async def fetch_espn_player_metadata_batch(cls) -> Dict[str, Dict[str, Any]]:
        """
        Fetches live ESPN ADP (averageDraftPosition), injuryStatus, and seasonOutlook
        for the top 350 fantasy players in a single call.
        """
        cookies = {"SWID": settings.ESPN_SWID, "espn_s2": settings.ESPN_S2}
        headers = {
            "x-fantasy-filter": json.dumps({
                "players": {
                    "filterSlotIds": {"value": [0, 2, 23, 4, 6, 16, 17]},
                    "limit": 350,
                    "sortPercOwned": {"sortAsc": False, "sortPriority": 1}
                }
            }),
            "User-Agent": "Mozilla/5.0"
        }
        url = (
            f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/"
            f"{settings.ESPN_YEAR}/segments/0/leagues/{settings.ESPN_LEAGUE_ID}?view=kona_player_info"
        )
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.get(url, cookies=cookies, headers=headers)
                if r.status_code != 200:
                    return {}
                players = r.json().get("players", [])
                meta: Dict[str, Dict[str, Any]] = {}
                for p in players:
                    pl = p.get("player", {})
                    p_id = str(pl.get("id"))
                    name = pl.get("fullName")
                    adp_raw = pl.get("ownership", {}).get("averageDraftPosition")
                    pct_owned = pl.get("ownership", {}).get("percentOwned")
                    pct_started = pl.get("ownership", {}).get("percentStarted")
                    espn_adp = round(float(adp_raw), 1) if adp_raw and float(adp_raw) > 0 else None
                    outlook = pl.get("seasonOutlook")
                    inj = pl.get("injuryStatus")
                    item = {
                        "name": name,
                        "espn_adp": espn_adp,
                        "outlook": outlook,
                        "injury_status": inj,
                        "percent_owned": round(float(pct_owned), 1) if pct_owned else None,
                        "percent_started": round(float(pct_started), 1) if pct_started else None,
                    }
                    meta[p_id] = item
                    if name:
                        meta[name.lower()] = item
                logger.info("Fetched ESPN metadata for %d players.", len(meta))
                return meta
        except Exception as e:
            logger.warning("Could not fetch ESPN kona_player_info: %s", str(e))
            return {}

    @classmethod
    async def _upsert_player(cls, session, espn_player, espn_meta: Optional[Dict[str, Any]] = None, current_week: int = 1) -> None:
        """Upserts a single player into DB and caches entity in Redis."""
        espn_id = str(getattr(espn_player, "playerId", espn_player.name))
        name = espn_player.name
        pos = getattr(espn_player, "position", "FLEX")
        team = getattr(espn_player, "proTeam", "FA")
        status = getattr(espn_player, "injuryStatus", "Healthy") or "Healthy"
        proj_pts = float(getattr(espn_player, "projected_total_points", 0.0) or 0.0)
        proj_avg = float(getattr(espn_player, "projected_avg_points", 0.0) or 0.0)
        raw_pos_rank = getattr(espn_player, "posRank", None)
        pct_owned_live = getattr(espn_player, "percent_owned", None)
        pct_started_live = getattr(espn_player, "percent_started", None)
        pos_rank = None
        if isinstance(raw_pos_rank, int):
            pos_rank = raw_pos_rank
        elif isinstance(raw_pos_rank, str) and raw_pos_rank.isdigit():
            pos_rank = int(raw_pos_rank)

        stats = getattr(espn_player, "stats", {})
        breakdown = stats.get(0, {}).get("projected_breakdown", {})

        # Weekly projection for current week
        weekly_proj = 0.0
        if current_week in stats:
            weekly_proj = float(stats[current_week].get("projected_points", 0.0) or 0.0)
        if not weekly_proj and hasattr(espn_player, "stats") and isinstance(espn_player.stats, dict) and current_week in espn_player.stats:
            weekly_proj = float(espn_player.stats[current_week].get("projected_points", 0.0) or 0.0)
        if not weekly_proj and proj_avg > 0:
            weekly_proj = round(proj_avg, 2)

        # Extract ESPN ADP and outlook from batch metadata
        meta_item = (espn_meta or {}).get(espn_id) or (espn_meta or {}).get(name.lower(), {})
        espn_adp = meta_item.get("espn_adp")
        outlook = meta_item.get("outlook")
        # Prefer live ownership from espn_api, fall back to batch metadata
        pct_owned = pct_owned_live or meta_item.get("percent_owned")
        pct_started = pct_started_live or meta_item.get("percent_started")

        stmt = select(Player).where(Player.espn_id == espn_id)
        res = await session.execute(stmt)
        db_p = res.scalar_one_or_none()

        espn_payload = {
            "projected_total_points": proj_pts,
            "projected_avg_points": proj_avg,
            "weekly_projected_points": weekly_proj,
            "pos_rank": pos_rank,
            "stats": breakdown,
            "season_outlook": outlook
        }

        if not db_p:
            db_p = Player(
                espn_id=espn_id,
                name=name,
                team=team,
                position=pos,
                injury_status=status,
                projected_points=proj_pts,
                projected_avg=proj_avg,
                weekly_projected_points=weekly_proj,
                pos_rank=pos_rank,
                espn_adp=espn_adp,
                percent_owned=pct_owned,
                percent_started=pct_started,
                espn_data=espn_payload
            )
            session.add(db_p)
        else:
            db_p.name = name
            db_p.team = team
            db_p.position = pos
            db_p.injury_status = status
            db_p.projected_points = proj_pts
            db_p.projected_avg = proj_avg
            db_p.weekly_projected_points = weekly_proj
            db_p.pos_rank = pos_rank
            if espn_adp is not None:
                db_p.espn_adp = espn_adp
            if pct_owned is not None:
                db_p.percent_owned = pct_owned
            if pct_started is not None:
                db_p.percent_started = pct_started
            db_p.espn_data = espn_payload

        # Write to Redis fast index (<5ms access)
        await RedisRepository.set_player_index(name, espn_id)
        await RedisRepository.set_player_hash(espn_id, {
            "name": name,
            "team": team,
            "pos": pos,
            "status": status,
            "proj_pts": str(round(proj_pts, 1)),
            "proj_avg": str(round(proj_avg, 1)),
            "weekly_proj": str(round(weekly_proj, 1)),
            "bye": str(getattr(espn_player, "bye_week", ""))
        })

    @classmethod
    async def get_direct_draft_detail(cls) -> Optional[Dict[str, Any]]:
        """Queries ESPN V3 mDraftDetail view for live pick tracking and draft board order."""
        if not settings.ESPN_S2 or not settings.ESPN_SWID:
            return None

        url = f"{ESPN_V3_BASE_URL.format(year=settings.ESPN_YEAR, league_id=settings.ESPN_LEAGUE_ID)}?view=mDraftDetail"
        cookies = {"espn_s2": settings.ESPN_S2, "SWID": settings.ESPN_SWID}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(url, cookies=cookies)
                if resp.status_code == 200:
                    return resp.json()
            except Exception as e:
                logger.error("Error fetching ESPN direct draft detail: %s", str(e))
        return None
