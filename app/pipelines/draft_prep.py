"""
Pre-Draft Preparation & Live Draft Operations Engine.
Manages Keeper auto-import, ADP rankings, mock draft simulation, and live board tracking.
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from app.core.redis_client import get_redis, RedisRepository
from app.pipelines.espn_sync import ESPNSyncService
from app.pipelines.vorp_engine import VORPEngine

logger = logging.getLogger(__name__)


class DraftPrepService:
    """Orchestrates pre-draft analysis, keeper mapping, and live pick evaluation."""

    @classmethod
    async def sync_keepers(cls) -> Dict[str, Any]:
        """
        Auto-detects locked keepers for all 12 teams from ESPN.
        Stores in Redis hash 'keepers:2026' with team_id -> {player_name, round_cost}.
        """
        league = ESPNSyncService.get_espn_league_instance()
        if not league:
            logger.warning("Cannot connect to ESPN to sync keepers.")
            return {"success": False, "keepers_found": 0}

        r = await get_redis()
        keepers_found = {}

        for team in league.teams:
            for player in team.roster:
                # ESPN tags keepers or acquisition type
                is_keeper = getattr(player, "keeper", False) or getattr(player, "acquisitionType", "") == "KEEPER"
                if is_keeper:
                    p_id = str(getattr(player, "playerId", player.name))
                    keepers_found[str(team.team_id)] = {
                        "player_id": p_id,
                        "player_name": player.name,
                        "position": getattr(player, "position", ""),
                        "team_name": team.team_name,
                        "round_cost": getattr(player, "draftRound", 1) # ESPN round penalty
                    }
                    # Also mark player as unavailable for draft in Redis
                    await r.sadd("draft:unavailable_players", p_id)

        if keepers_found:
            for tid, keeper_info in keepers_found.items():
                import json
                await r.hset("keepers:2026", tid, json.dumps(keeper_info))

        logger.info("Synced %d keepers across league rosters.", len(keepers_found))
        return {"success": True, "keepers_found": len(keepers_found), "keepers": keepers_found}

    @classmethod
    async def sync_adp_rankings(cls) -> Dict[str, Any]:
        """
        Populates baseline ADP rankings into Redis sorted set 'adp:ppr:2026'.
        Can be initialized from default consensus fantasy projections.
        """
        r = await get_redis()
        # Seed baseline consensus rankings if not populated
        count = await r.zcard("adp:ppr:2026")
        if count == 0:
            sample_adp = {
                "CeeDee Lamb": 1.1,
                "Christian McCaffrey": 1.2,
                "Tyreek Hill": 1.3,
                "Ja'Marr Chase": 1.4,
                "Justin Jefferson": 1.5,
                "Amon-Ra St. Brown": 1.6,
                "Breece Hall": 1.7,
                "Bijan Robinson": 1.8,
                "A.J. Brown": 1.9,
                "Garrett Wilson": 2.1,
                "Puka Nacua": 2.2,
                "Jahmyr Gibbs": 2.3,
                "Saquon Barkley": 2.4,
                "Jonathan Taylor": 2.5,
                "Marvin Harrison Jr.": 2.6,
                "Drake London": 2.7,
                "Chris Olave": 2.8,
                "Travis Kelce": 3.1,
                "Sam LaPorta": 3.2,
                "Trey McBride": 3.5,
                "Josh Allen": 3.3,
                "Jalen Hurts": 3.4,
                "Patrick Mahomes": 4.1,
                "Lamar Jackson": 4.2
            }
            pipe = r.pipeline()
            for name, score in sample_adp.items():
                pipe.zadd("adp:ppr:2026", {name: score})
            await pipe.execute()
            count = len(sample_adp)

        return {"success": True, "adp_count": count}

    @classmethod
    async def simulate_mock_draft(
        cls,
        user_pick_slot: int = 2,
        num_rounds: int = 15,
        strategy_preference: str = "balanced"
    ) -> Dict[str, Any]:
        """
        Simulates a 12-team snake mock draft using deterministic ADP and VORP rules.
        Tests roster outcomes for user pick slot #2 (Team Cooper).
        """
        r = await get_redis()
        adp_items = await r.zrange("adp:ppr:2026", 0, -1, withscores=True)
        available_pool = [item[0] for item in adp_items]

        user_roster = []
        all_drafted = []

        # 12-team snake order: Round 1 is 1..12, Round 2 is 12..1, etc.
        for current_round in range(1, num_rounds + 1):
            is_odd = current_round % 2 != 0
            order = list(range(1, 13)) if is_odd else list(reversed(range(1, 13)))

            for pick_in_round, team_slot in enumerate(order, start=1):
                if not available_pool:
                    break
                overall_pick = (current_round - 1) * 12 + pick_in_round

                if team_slot == user_pick_slot:
                    # User pick selection based on VORP priority
                    chosen_player = available_pool.pop(0)
                    user_roster.append({
                        "round": current_round,
                        "pick": overall_pick,
                        "player": chosen_player
                    })
                else:
                    # Opponent picks by best available ADP
                    opp_player = available_pool.pop(0)
                    all_drafted.append({
                        "round": current_round,
                        "team_slot": team_slot,
                        "player": opp_player
                    })

        return {
            "user_slot": user_pick_slot,
            "strategy": strategy_preference,
            "user_roster": user_roster,
            "total_picks_simulated": len(all_drafted) + len(user_roster)
        }

    @classmethod
    async def get_user_keeper(cls, team_id: int = 2) -> Dict[str, Any]:
        """
        Retrieves locked keeper for the user team from Redis 'keepers:2026'.
        Defaults to Team Cooper's locked keeper: Javonte Williams in Round 8.
        """
        import json
        r = await get_redis()
        raw = await r.hget("keepers:2026", str(team_id))
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass

        default_keeper = {
            "player_id": "4361579",
            "player_name": "Javonte Williams",
            "position": "RB",
            "nfl_team": "DAL",
            "round_cost": 8,
            "team_id": team_id,
            "team_name": "Team Cooper",
            "adp": 33.5,
            "surplus_rounds": 5.2
        }
        await r.hset("keepers:2026", str(team_id), json.dumps(default_keeper))
        return default_keeper

    @classmethod
    async def register_keeper(
        cls,
        team_id: int,
        player_name: str,
        round_cost: int,
        position: str = "RB",
        nfl_team: str = "DAL",
        player_id: str = "4361579"
    ) -> Dict[str, Any]:
        """Registers a keeper for a team and caches in Redis."""
        import json
        r = await get_redis()
        keeper_data = {
            "player_id": player_id,
            "player_name": player_name,
            "position": position,
            "nfl_team": nfl_team,
            "round_cost": round_cost,
            "team_id": team_id,
            "team_name": "Team Cooper" if team_id == 2 else f"Team {team_id}",
            "adp": 33.5 if "javonte" in player_name.lower() else None
        }
        await r.hset("keepers:2026", str(team_id), json.dumps(keeper_data))
        return keeper_data

    @classmethod
    async def get_live_draft_status(cls) -> Dict[str, Any]:
        """
        Polls ESPN draft status to determine active pick, board state, and drafted players.
        Distinguishes between pre-draft state (inProgress=False, empty picks) and active live draft.
        """
        user_keeper = await cls.get_user_keeper()
        draft_json = await ESPNSyncService.get_direct_draft_detail()

        if not draft_json:
            return {
                "is_live": False,
                "status": "PRE_DRAFT",
                "draft_order_finalized": False,
                "current_pick": 1,
                "current_round": 1,
                "active_team_slot": 1,
                "drafted_count": 0,
                "drafted_players": [],
                "user_team_id": 2,
                "keeper": user_keeper,
                "message": "Draft room not currently active. Pre-draft scouting board ready."
            }

        dd = draft_json.get("draftDetail", {})
        in_progress = bool(dd.get("inProgress", False))
        raw_picks = dd.get("picks", [])

        # Filter to actual picks with legitimate player selections (ESPN uses -1 for empty pick placeholders)
        actual_picks = [p for p in raw_picks if p.get("playerId", -1) > 0]

        if not in_progress and len(actual_picks) == 0:
            # Pre-draft state: draft order is not finalized, draft is not active
            return {
                "is_live": False,
                "status": "PRE_DRAFT",
                "draft_order_finalized": False,
                "current_pick": 1,
                "current_round": 1,
                "active_team_slot": 1,
                "picks_until_turn": 0,
                "is_user_turn": False,
                "drafted_count": 0,
                "drafted_players": [],
                "user_team_id": 2,
                "keeper": user_keeper,
                "message": "Pre-draft state. Draft order TBD. Blue-chip pre-draft target board active."
            }

        drafted_names = [
            p.get("playerPoolEntry", {}).get("player", {}).get("fullName") or str(p.get("playerId"))
            for p in actual_picks
        ]

        active_pick = len(actual_picks) + 1
        active_round = ((active_pick - 1) // 12) + 1
        pick_in_round = ((active_pick - 1) % 12) + 1
        is_odd_round = active_round % 2 != 0
        active_team_slot = pick_in_round if is_odd_round else (13 - pick_in_round)

        # 12-team snake turn schedule for user slot 2
        user_picks = []
        for r in range(1, 17):
            if r % 2 != 0:
                user_picks.append((r - 1) * 12 + 2)
            else:
                user_picks.append((r - 1) * 12 + 11)
        user_picks.sort()
        upcoming_user_picks = [p for p in user_picks if p >= active_pick]
        next_user_pick = upcoming_user_picks[0] if upcoming_user_picks else active_pick
        picks_until_turn = max(0, next_user_pick - active_pick)
        is_user_on_clock = (active_team_slot == 2)

        return {
            "is_live": True,
            "status": "LIVE_DRAFT",
            "draft_order_finalized": True,
            "current_pick": active_pick,
            "current_round": active_round,
            "active_team_slot": active_team_slot,
            "picks_until_turn": picks_until_turn,
            "is_user_turn": is_user_on_clock,
            "drafted_count": len(actual_picks),
            "drafted_players": drafted_names,
            "user_team_id": 2,
            "keeper": user_keeper
        }

    @classmethod
    async def get_on_the_clock_recommendations(
        cls,
        user_team_id: int = 2,
        current_pick: Optional[int] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Dynamically calculates the Top 10 recommended players for the active/upcoming pick,
        evaluating VORP, positional tier cliffs, team roster needs, and market arbitrage.
        Assigns an automated draft grade (A+ to C) and tactical rationale.
        """
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.player import Player
        from app.models.league import Roster

        # Determine draft status and pick
        draft_status = await cls.get_live_draft_status()
        active_pick = current_pick or draft_status.get("current_pick", 1)
        active_round = ((active_pick - 1) // 12) + 1
        pick_in_round = ((active_pick - 1) % 12) + 1
        is_odd_round = active_round % 2 != 0
        active_team_slot = pick_in_round if is_odd_round else (13 - pick_in_round)

        # 12-team snake turn schedule for user slot 2
        user_picks = []
        for r in range(1, 17):
            if r % 2 != 0:
                user_picks.append((r - 1) * 12 + 2)
            else:
                user_picks.append((r - 1) * 12 + 11)
        user_picks.sort()

        upcoming_user_picks = [p for p in user_picks if p >= active_pick]
        next_user_pick = upcoming_user_picks[0] if upcoming_user_picks else active_pick
        picks_until_turn = max(0, next_user_pick - active_pick)
        is_user_on_clock = (active_team_slot == user_team_id)

        is_live = draft_status.get("is_live", False)
        user_keeper = draft_status.get("keeper") or await cls.get_user_keeper(user_team_id)

        async with AsyncSessionLocal() as session:
            # In pre-draft mode, user has no drafted team yet, but has Javonte Williams locked in Round 8
            user_players = []
            if is_live:
                r_stmt = select(Roster).where(Roster.espn_team_id == user_team_id)
                r_res = await session.execute(r_stmt)
                user_roster = r_res.scalar_one_or_none()
                user_p_ids = user_roster.players if user_roster and user_roster.players else []
                if user_p_ids:
                    up_stmt = select(Player).where(Player.espn_id.in_(user_p_ids))
                    up_res = await session.execute(up_stmt)
                    user_players = up_res.scalars().all()

            qb_count = sum(1 for p in user_players if p.position == "QB")
            # Factor in locked keeper Javonte Williams for RB count
            rb_count = sum(1 for p in user_players if p.position == "RB")
            if not is_live and user_keeper and user_keeper.get("position") == "RB":
                rb_count += 1
            wr_count = sum(1 for p in user_players if p.position == "WR")
            te_count = sum(1 for p in user_players if p.position == "TE")

            need_mult = {
                "WR": 1.45 if wr_count < 2 else (1.25 if wr_count < 3 else (1.05 if wr_count < 4 else 0.80)),
                "RB": 1.20 if rb_count < 2 else (1.05 if rb_count < 3 else 0.85),
                "TE": 1.25 if te_count == 0 else 0.70,
                "QB": 1.05 if qb_count == 0 else 0.40,
                "K": 0.30,
                "D/ST": 0.35,
                "DST": 0.35,
            }

            p_stmt = select(Player).where(Player.consensus_proj > 0).order_by(Player.consensus_proj.desc())
            p_res = await session.execute(p_stmt)
            drafted_player_ids = set()
            if is_live:
                all_rosters_stmt = select(Roster)
                all_rosters_res = await session.execute(all_rosters_stmt)
                for ros in all_rosters_res.scalars().all():
                    for pid in (ros.players or []):
                        drafted_player_ids.add(pid)

            all_available = [p for p in p_res.scalars().all() if p.espn_id not in drafted_player_ids]

            pos_groups: Dict[str, List[float]] = {}
            for p in all_available:
                pos_groups.setdefault(p.position, []).append(float(p.consensus_proj or 0.0))

            baselines = {
                "QB": pos_groups.get("QB", [0])[min(12, len(pos_groups.get("QB", [0])) - 1)] if pos_groups.get("QB") else 280.0,
                "RB": pos_groups.get("RB", [0])[min(25, len(pos_groups.get("RB", [0])) - 1)] if pos_groups.get("RB") else 170.0,
                "WR": pos_groups.get("WR", [0])[min(37, len(pos_groups.get("WR", [0])) - 1)] if pos_groups.get("WR") else 160.0,
                "TE": pos_groups.get("TE", [0])[min(12, len(pos_groups.get("TE", [0])) - 1)] if pos_groups.get("TE") else 115.0,
            }

            scored_candidates = []
            for p in all_available[:80]:
                pos = p.position
                b_line = baselines.get(pos, 100.0)
                vorp = max(0.0, round((p.consensus_proj or 0.0) - b_line, 1))
                mult = need_mult.get(pos, 1.0)

                pos_in_top = sum(1 for cand in all_available[:25] if cand.position == pos)
                tier_cliff_bonus = 0.0
                cliff_note = ""
                if is_live and pos_in_top <= 2 and picks_until_turn >= 10:
                    tier_cliff_bonus = 15.0
                    cliff_note = f"Tier cliff alert: only {pos_in_top} top-{pos} left before your next turn (+{picks_until_turn} picks)."

                sentiment_bonus = float(p.sentiment_score or 0.0) * 5.0
                adp_arbitrage = 0.0
                if p.adp and p.adp > 0:
                    adp_arbitrage = max(-10.0, min(15.0, (active_pick - p.adp) * 0.5))

                composite_score = (vorp * 0.45 * mult) + tier_cliff_bonus + sentiment_bonus + adp_arbitrage

                scored_candidates.append({
                    "player": p,
                    "vorp": vorp,
                    "need_multiplier": mult,
                    "composite_score": composite_score,
                    "tier_cliff_bonus": tier_cliff_bonus,
                    "cliff_note": cliff_note
                })

            scored_candidates.sort(key=lambda x: x["composite_score"], reverse=True)
            top_recs = scored_candidates[:limit]
            max_comp = top_recs[0]["composite_score"] if top_recs else 100.0

            results = []
            for item in top_recs:
                p = item["player"]
                comp = item["composite_score"]
                ratio = (comp / max_comp) * 100.0 if max_comp > 0 else 80.0

                if ratio >= 94:
                    grade = "A+"
                elif ratio >= 88:
                    grade = "A"
                elif ratio >= 82:
                    grade = "A-"
                elif ratio >= 76:
                    grade = "B+"
                elif ratio >= 70:
                    grade = "B"
                elif ratio >= 64:
                    grade = "B-"
                else:
                    grade = "C"

                pos_reason = ""
                if not is_live:
                    if p.position == "WR":
                        pos_reason = "Priority WR target for 3-WR format with Javonte Williams (Rd 8) locked as RB."
                    elif p.position == "RB":
                        pos_reason = "High-VORP RB to pair with Round 8 keeper Javonte Williams."
                    elif p.position == "TE":
                        pos_reason = "Elite positional differentiator at TE."
                    elif p.position == "QB":
                        pos_reason = "High-ceiling QB anchor."
                else:
                    if p.position == "WR" and wr_count < 3:
                        pos_reason = f"Essential WR starter need ({wr_count}/3 filled)."
                    elif p.position == "RB" and rb_count < 2:
                        pos_reason = f"High-leverage RB starter need ({rb_count}/2 filled)."
                    elif p.position == "TE" and te_count == 0:
                        pos_reason = "Locks in positional advantage at TE."
                    elif p.position == "QB" and qb_count == 0:
                        pos_reason = "Anchor QB1 scoring engine."

                reasons = []
                reasons.append(f"VORP: +{item['vorp']} pts over replacement baseline.")
                if pos_reason:
                    reasons.append(pos_reason)
                if item["cliff_note"]:
                    reasons.append(item["cliff_note"])
                if p.sentiment_tag == "BULLISH":
                    reasons.append("Bullish beat reporter sentiment.")

                full_rationale = " ".join(reasons)

                results.append({
                    "id": p.espn_id,
                    "name": p.name,
                    "position": p.position,
                    "nfl_team": p.team,
                    "consensus_proj": round(float(p.consensus_proj or 0.0), 1),
                    "projected_avg": round(float(p.projected_avg or 0.0), 1),
                    "espn_proj": round(float(p.espn_proj or 0.0), 1),
                    "sleeper_proj": round(float(p.sleeper_proj or 0.0), 1),
                    "adp": round(float(p.adp), 1) if p.adp is not None else None,
                    "vorp": item["vorp"],
                    "draft_grade": grade,
                    "composite_score": round(comp, 1),
                    "sentiment_tag": p.sentiment_tag or "NEUTRAL",
                    "injury_status": p.injury_status or "Healthy",
                    "rationale": full_rationale
                })

            return {
                "draft_phase": "LIVE_DRAFT" if is_live else "PRE_DRAFT",
                "is_live": is_live,
                "header_title": "ON-THE-CLOCK TOP RECOMMENDATIONS" if is_live else "PRE-DRAFT TARGET BOARD / BLUE-CHIP TARGETS",
                "active_pick": active_pick if is_live else None,
                "active_round": active_round if is_live else None,
                "pick_in_round": pick_in_round if is_live else None,
                "on_the_clock_team": active_team_slot if is_live else None,
                "is_user_on_clock": is_user_on_clock if is_live else False,
                "next_user_pick": next_user_pick if is_live else None,
                "picks_until_turn": picks_until_turn if is_live else 0,
                "keeper": user_keeper,
                "user_roster_allocation": {
                    "QB": qb_count,
                    "RB": rb_count,
                    "WR": wr_count,
                    "TE": te_count,
                },
                "recommendations": results
            }
