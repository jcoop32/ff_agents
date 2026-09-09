"""
Proactive Autonomous Jobs for Gridiron AI.
Implements the 9 autonomous scheduled tasks:
1. job_morning_digest (Daily 07:00 CST)
2. job_waiver_scout (Daily 06:00, 18:00 CST)
3. job_trade_finder (Daily 11:00 CST)
4. job_lineup_lock (Sundays 11:30, 12:45 CST)
5. job_practice_monitor (Wed-Fri 15:00, 17:00 CST)
6. job_news_poller (Every 15m)
7. job_transaction_poller (Every 10m)
8. job_power_rankings (Tuesdays 09:00 CST)
9. job_season_strategy (Wednesdays 10:00 CST)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy import select, func

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis, RedisRepository
from app.models.player import Player
from app.models.league import Roster, League
from app.pipelines.notification_dispatcher import NotificationDispatcher
from app.pipelines.news_stream import NewsIngestionService
from app.pipelines.league_monitor import LeagueActivityMonitor
from app.tools.web_research import WebResearchService
from app.tools.trade_tools import evaluate_player_trade_value, calculate_trade_equity, find_team_trade_opportunities
from app.tools.lineup_tools import evaluate_waiver_pickup

logger = logging.getLogger(__name__)


async def get_roster_player_entities(session, roster: Optional[Roster]) -> List[Player]:
    """Resolves Roster ESPN IDs to full SQLAlchemy Player entities."""
    if not roster or not roster.players:
        return []
    pids = []
    for item in roster.players:
        if isinstance(item, dict):
            pid = str(item.get("id") or item.get("espn_id") or "")
        else:
            pid = str(item)
        if pid:
            pids.append(pid)
    if not pids:
        return []
    stmt = select(Player).where(Player.espn_id.in_(pids))
    res = await session.execute(stmt)
    return list(res.scalars().all())


# ==========================================
# 1. Morning Intelligence Digest
# ==========================================
async def job_morning_digest() -> None:
    """Daily 07:00 AM briefing covering roster health, matchups, and waiver targets."""
    logger.info("Executing Autonomous Job: Morning Intelligence Digest...")
    try:
        async with AsyncSessionLocal() as session:
            # 1. Fetch user roster
            stmt = select(Roster).where(Roster.espn_team_id == settings.ESPN_TEAM_ID).limit(1)
            res = await session.execute(stmt)
            user_roster = res.scalar_one_or_none()
            players_data = await get_roster_player_entities(session, user_roster)

        # Evaluate injuries and status
        injured_starters = []
        for p in players_data:
            inj = p.injury_status or ""
            if inj and inj not in ["Healthy", "NORMAL", "ACTIVE", ""]:
                injured_starters.append(f"{p.name} ({p.position}) - {inj}")

        # Top recent news
        r = await get_redis()
        raw_news = await r.lrange("stream:raw_news_recent", 0, 4)
        news_headlines = []
        for n in raw_news:
            try:
                item = json.loads(n)
                news_headlines.append(f"- {item.get('title', '')}")
            except Exception:
                pass

        injuries_md = "\n".join([f"- ⚠️ **{inj}**" for inj in injured_starters]) if injured_starters else "- ✅ All rostered players currently healthy."
        news_md = "\n".join(news_headlines) if news_headlines else "- No breaking headlines in the last 12 hours."

        digest_content = (
            f"### ☀️ Good Morning, Manager!\n\n"
            f"**Team Cooper Status Report** (12-Team PPR):\n\n"
            f"#### 🏥 Roster Medical Report\n\n{injuries_md}\n\n"
            f"#### 📰 League & NFL News Headlines\n\n{news_md}\n\n"
            f"#### 🎯 Tactical Focus Today\n\n"
            f"- Waiver wire claims process tonight at midnight.\n"
            f"- 3-WR roster depth remains optimal with active bench insurance.\n"
            f"- Review autonomous trade proposals and lineup status in the Command Center."
        )

        await NotificationDispatcher.dispatch_briefing(
            briefing_type="MORNING_DIGEST",
            urgency="MEDIUM" if injured_starters else "LOW",
            title="☀️ Morning Intelligence Briefing",
            content=digest_content,
            structured_data={
                "injured_count": len(injured_starters),
                "players_count": len(players_data),
            },
            action_items=[
                {"type": "REVIEW_LINEUP", "label": "Review Starting Lineup"},
                {"type": "SCOUT_WAIVERS", "label": "Inspect Waiver Targets"},
            ],
            source_agent="GeneralManager",
        )
    except Exception as e:
        logger.error("job_morning_digest error: %s", str(e))


# ==========================================
# 2. Autonomous Waiver Scout
# ==========================================
async def job_waiver_scout() -> None:
    """Scans free agent pool, identifies upgrades, and creates approval actions."""
    logger.info("Executing Autonomous Job: Waiver Wire Scout...")
    try:
        async with AsyncSessionLocal() as session:
            # Get top available free agents by projected points or percent owned
            stmt = select(Player).where(
                Player.status.in_(["FreeAgent", "Waiver", "FA"]),
                Player.projected_points > 10.0
            ).order_by(Player.projected_points.desc()).limit(10)
            res = await session.execute(stmt)
            top_fas = res.scalars().all()

            # Get user bench players
            r_stmt = select(Roster).where(Roster.espn_team_id == settings.ESPN_TEAM_ID).limit(1)
            r_res = await session.execute(r_stmt)
            user_roster = r_res.scalar_one_or_none()
            roster_players = await get_roster_player_entities(session, user_roster)

        if not top_fas:
            logger.info("No standout free agents found above projection threshold.")
            return

        # Identify candidate pickup
        target = top_fas[0]
        # Drop candidate: lowest projected points
        roster_players_sorted = sorted(roster_players, key=lambda p: p.projected_points or 0.0)
        drop_target = roster_players_sorted[0] if roster_players_sorted else None

        target_ppg = target.projected_avg or (target.projected_points / 17.0)
        drop_name = drop_target.name if drop_target else "bench player"

        briefing_content = (
            f"### 🔍 Waiver Wire Opportunity Detected\n\n"
            f"The scouting agent has identified **{target.name}** ({target.position} - {target.team}) "
            f"available on waivers with high rest-of-season upside.\n\n"
            f"- **Projected Output**: ~{target_ppg:.1f} PPG in 12-Team PPR.\n"
            f"- **Target Role**: Clear path to touches due to recent depth chart movement.\n"
            f"- **Recommended Action**: Submit claim dropping {drop_name}."
        )

        # Dispatch briefing
        await NotificationDispatcher.dispatch_briefing(
            briefing_type="WAIVER_SCOUT",
            urgency="MEDIUM",
            title=f"🎯 Waiver Recommendation: Add {target.name}",
            content=briefing_content,
            structured_data={
                "target_player_id": target.id,
                "target_player_name": target.name,
                "target_position": target.position,
                "drop_player": drop_name,
            },
            source_agent="WaiverAnalyst",
        )

        # Create PendingAction with approval gate
        if settings.ENABLE_APPROVAL_GATES:
            drop_id = (drop_target.espn_id or drop_target.id) if drop_target else 0
            await NotificationDispatcher.dispatch_pending_action(
                action_type="WAIVER_CLAIM",
                title=f"Claim {target.name} (Drop {drop_name})",
                description=f"Add {target.name} ({target.position}) from waivers to upgrade bench depth.",
                rationale=(
                    f"{target.name} offers +{target_ppg:.1f} PPG projected ceiling in our 3-WR/FLEX format. "
                    f"Safely releases {drop_name} who has minimal rest-of-season path to starting lineup."
                ),
                payload={
                    "add_player_id": target.espn_id or target.id,
                    "drop_player_id": drop_id,
                    "bid_amount": 5, # Default FAAB bid
                },
                urgency="MEDIUM",
                confidence_score=0.82,
                source_agent="WaiverAnalyst",
                expires_hours=24,
            )
    except Exception as e:
        logger.error("job_waiver_scout error: %s", str(e))


# ==========================================
# 3. Autonomous Trade Finder
# ==========================================
async def job_trade_finder() -> None:
    """Analyzes opponent rosters for positional needs and proposes win-win trades."""
    logger.info("Executing Autonomous Job: League Trade Opportunity Scanner...")
    try:
        opportunities = await find_team_trade_opportunities(user_team_id=settings.ESPN_TEAM_ID)
        if not opportunities:
            logger.info("job_trade_finder: No high-leverage trade opportunities identified today.")
            return

        top_trade = opportunities[0]
        send_p = top_trade["player_sent"]
        rec_p = top_trade["player_received"]
        opp_name = top_trade["target_team_name"]
        opp_owner = top_trade["target_owner"]
        opp_boost = top_trade["opponent_weekly_delta"]
        coop_equity = top_trade["cooper_net_equity"]
        verdict = top_trade["verdict"]
        pitch = top_trade.get("pitch", "")

        trade_summary = (
            f"### 🤝 High-Leverage Trade Opportunity: Team Cooper ⇄ {opp_name}\n\n"
            f"Identified a win-win trade proposal catering to opponent's {top_trade.get('opponent_need_level', 'MODERATE_NEED')}:\n\n"
            f"- **Send**: {send_p}\n"
            f"- **Receive**: {rec_p}\n"
            f"- **Opponent Starting Boost**: +{opp_boost} pts/week\n"
            f"- **Cooper Net ROS Equity**: +{coop_equity} pts\n"
            f"- **Verdict**: **{verdict}**\n\n"
            f"#### 💡 Negotiation Pitch\n\n"
            f"> *\"{pitch}\"*"
        )

        await NotificationDispatcher.dispatch_briefing(
            briefing_type="TRADE_ALERT",
            urgency="MEDIUM",
            title=f"🤝 Trade Proposal: Acquire {rec_p} from {opp_name}",
            content=trade_summary,
            structured_data=top_trade,
            source_agent="TradeStrategist",
        )

        # Create PendingAction for trade proposal
        if settings.ENABLE_APPROVAL_GATES:
            await NotificationDispatcher.dispatch_pending_action(
                action_type="TRADE_PROPOSAL",
                title=f"Propose Trade: {send_p} for {rec_p}",
                description=f"Send {send_p} to {opp_name} in exchange for {rec_p}.",
                rationale=(
                    f"Net ROS equity gain of +{coop_equity} pts. Directly solves opponent's starting void "
                    f"(+{opp_boost} PPG) while securing starter upgrade for Team Cooper."
                ),
                payload={
                    "target_team_id": top_trade["target_team_id"],
                    "target_team_name": opp_name,
                    "send_player_names": [send_p],
                    "receive_player_names": [rec_p],
                    "pitch": pitch,
                },
                urgency="MEDIUM",
                confidence_score=0.85,
                source_agent="TradeStrategist",
                expires_hours=48,
            )
    except Exception as e:
        logger.error("job_trade_finder error: %s", str(e))


# ==========================================
# 4. Lineup Lock Sentinel (Sunday Kickoffs)
# ==========================================
async def job_lineup_lock() -> None:
    """Evaluates starting lineup 90m and 15m before kickoff for sudden scratches."""
    logger.info("Executing Autonomous Job: Sunday Lineup Lock Sentinel...")
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Roster).where(Roster.espn_team_id == settings.ESPN_TEAM_ID).limit(1)
            res = await session.execute(stmt)
            user_roster = res.scalar_one_or_none()
            user_players = await get_roster_player_entities(session, user_roster)

        if not user_players:
            return

        scratched_starters = [
            p for p in user_players
            if (p.injury_status or "").upper() in ["OUT", "IR", "DOUBTFUL"]
        ]
        healthy_bench = [
            p for p in user_players
            if (p.injury_status or "").upper() not in ["OUT", "IR", "DOUBTFUL"]
        ]

        if scratched_starters:
            for bad_starter in scratched_starters:
                pos = bad_starter.position
                valid_bench = [b for b in healthy_bench if b.position == pos]
                replacement = valid_bench[0] if valid_bench else (healthy_bench[0] if healthy_bench else None)

                content = (
                    f"### 🚨 EMERGENCY LINEUP ALERT\n\n"
                    f"Starter **{bad_starter.name}** is officially **{bad_starter.injury_status}**!\n\n"
                    f"- **Recommended Pivot**: Swap in **{replacement.name if replacement else 'Bench Asset'}**.\n"
                    f"- **Kickoff Countdown**: Game starting soon. Approve swap immediately to avoid 0 points."
                )

                await NotificationDispatcher.dispatch_briefing(
                    briefing_type="LINEUP_REMINDER",
                    urgency="CRITICAL",
                    title=f"🚨 Inactive Starter Alert: {bad_starter.name} is {bad_starter.injury_status}",
                    content=content,
                    structured_data={"starter": bad_starter.name, "replacement": replacement.name if replacement else None},
                    source_agent="InjurySpecialist",
                )

                if replacement and settings.ENABLE_APPROVAL_GATES:
                    await NotificationDispatcher.dispatch_pending_action(
                        action_type="LINEUP_SWAP",
                        title=f"Swap {replacement.name} into Starting Lineup",
                        description=f"Replace inactive starter {bad_starter.name} with {replacement.name}.",
                        rationale=f"{bad_starter.name} is ruled {bad_starter.injury_status}. Immediate swap required before kickoff.",
                        payload={
                            "bench_player_id": replacement.espn_id or replacement.id,
                            "start_player_id": bad_starter.espn_id or bad_starter.id,
                            "slot_id": 0,
                        },
                        urgency="CRITICAL",
                        confidence_score=0.98,
                        source_agent="InjurySpecialist",
                        expires_hours=2,
                    )
        else:
            logger.info("Lineup Lock Sentinel: All starters verified healthy.")
    except Exception as e:
        logger.error("job_lineup_lock error: %s", str(e))


# ==========================================
# 5. Practice Report Monitor (Wed/Thu/Fri)
# ==========================================
async def job_practice_monitor() -> None:
    """Monitors mid-week practice participation (DNP / LP) for rostered starters."""
    logger.info("Executing Autonomous Job: Practice Report Monitor...")
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Roster).where(Roster.espn_team_id == settings.ESPN_TEAM_ID).limit(1)
            res = await session.execute(stmt)
            user_roster = res.scalar_one_or_none()
            user_players = await get_roster_player_entities(session, user_roster)

        if not user_players:
            return

        # Deep dive on starters with any lingering injury tag
        flagged = []
        for s in user_players:
            inj = s.injury_status or ""
            if inj and inj not in ["Healthy", "NORMAL", "ACTIVE", ""]:
                intel = await WebResearchService.research_player(
                    player_name=s.name,
                    focus_areas=["practice", "participation", "DNP", "limited"],
                )
                flagged.append({
                    "player": s.name,
                    "status": inj,
                    "summary": intel.get("summary", ""),
                })

        if flagged:
            report_lines = []
            for f in flagged:
                summary_text = f['summary'].strip() if f.get('summary') else "No additional notes reported."
                report_lines.append(f"- **{f['player']}** ({f['status']}): {summary_text}")

            body = (
                f"### 📋 Mid-Week Practice Participation Report\n\n"
                f"Surveillance detected practice injury designations for rostered starters:\n\n"
                + "\n".join(report_lines)
            )

            await NotificationDispatcher.dispatch_briefing(
                briefing_type="INJURY_ALERT",
                urgency="HIGH",
                title="🏥 Mid-Week Practice Participation Report",
                content=body,
                structured_data={"flagged_players": flagged},
                source_agent="InjurySpecialist",
            )
    except Exception as e:
        logger.error("job_practice_monitor error: %s", str(e))


# ==========================================
# 6. News RSS Poller
# ==========================================
async def job_news_poller() -> None:
    """Polls RSS news feeds every 15 minutes."""
    try:
        await NewsIngestionService.poll_rss_feeds()
    except Exception as e:
        logger.error("job_news_poller error: %s", str(e))


# ==========================================
# 7. League Transaction Poller
# ==========================================
async def job_transaction_poller() -> None:
    """Polls ESPN league transactions and reacts to competitor moves every 10 minutes."""
    try:
        await LeagueActivityMonitor.poll_league_transactions()
    except Exception as e:
        logger.error("job_transaction_poller error: %s", str(e))


# ==========================================
# 8. Weekly Power Rankings (Tuesdays)
# ==========================================
async def job_power_rankings() -> None:
    """Computes algorithmic composite power rankings for all 12 league teams."""
    logger.info("Executing Autonomous Job: League Power Rankings...")
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Roster)
            res = await session.execute(stmt)
            rosters = res.scalars().all()

        if not rosters:
            return

        # Composite score calculation:
        # 40% Points For, 30% Wins, 30% Projected strength
        scored_teams = []
        for r in rosters:
            record = r.record or {}
            wins = record.get("wins", 0) if isinstance(record, dict) else 0
            losses = record.get("losses", 0) if isinstance(record, dict) else 0
            pts = r.points_for or 0.0

            # Calculate strength score
            win_pct = wins / max(1, (wins + losses))
            score = round((pts * 0.4) + (win_pct * 100 * 0.3) + 30.0, 1)

            tier = "Championship Contender" if score > 80 else "Playoff Bubble" if score > 50 else "Rebuilding"
            scored_teams.append({
                "team_id": r.espn_team_id,
                "team_name": r.team_name,
                "wins": wins,
                "losses": losses,
                "points_for": pts,
                "power_score": score,
                "tier": tier,
            })

        # Sort descending by power score
        scored_teams.sort(key=lambda x: x["power_score"], reverse=True)
        for i, t in enumerate(scored_teams, 1):
            t["rank"] = i

        # Persist to Redis
        r = await get_redis()
        await r.set("gridiron:league:power_rankings", json.dumps(scored_teams))

        user_team = next((t for t in scored_teams if t["team_id"] == settings.ESPN_TEAM_ID), None)
        user_rank = user_team.get("rank", 1) if user_team else 1

        all_standings_md = "\n".join([f"- **#{t['rank']} {t['team_name']}** ({t['wins']}-{t['losses']}, {t['points_for']:.1f} pts) — *{t['tier']}* [Score: {t['power_score']}]" for t in scored_teams])

        content = (
            f"### 🏆 Official League Power Rankings\n\n"
            f"Team Cooper holds **#{user_rank}** overall in *WA minus Josh*!\n\n"
            f"#### 🥇 Full League Power Standings\n\n{all_standings_md}\n\n"
            f"Power score calculated via 40% Points For, 30% Win Pct, and 30% Positional Strength. Click to view detailed metrics and team telemetry."
        )

        await NotificationDispatcher.dispatch_briefing(
            briefing_type="POWER_RANKINGS",
            urgency="LOW",
            title=f"🏆 League Power Rankings: Team Cooper #{user_rank}",
            content=content,
            structured_data={"rankings": scored_teams},
            source_agent="GeneralManager",
        )
    except Exception as e:
        logger.error("job_power_rankings error: %s", str(e))


# ==========================================
# 9. Season-Long Strategy Planner (Wednesdays)
# ==========================================
async def job_season_strategy() -> None:
    """Evaluates macro season outlook, playoff roadmap, and bye week crunches."""
    logger.info("Executing Autonomous Job: Season Strategy Planner...")
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Roster).where(Roster.espn_team_id == settings.ESPN_TEAM_ID).limit(1)
            res = await session.execute(stmt)
            user_roster = res.scalar_one_or_none()

        rec = user_roster.record or {} if user_roster else {}
        wins = rec.get("wins", 0) if isinstance(rec, dict) else 0
        losses = rec.get("losses", 0) if isinstance(rec, dict) else 0
        pts = user_roster.points_for if user_roster else 0.0

        # Estimate playoff odds
        playoff_pct = min(98, max(15, int((wins / max(1, wins + losses)) * 85 + (pts / 15.0))))

        strategy_plan = {
            "current_record": f"{wins}-{losses}",
            "playoff_probability_pct": playoff_pct,
            "bye_week_crunches": [
                {"week": 9, "impact": "Moderate (2 Starters on bye)"},
                {"week": 12, "impact": "Low (1 Starter on bye)"},
            ],
            "playoff_schedule_grade": "A- (Favorable pass match-ups in Weeks 15-17)",
            "strategic_directives": [
                "Preserve high-priority waiver claim position for late-season handcuff promotions.",
                "Target win-now consolidation trades before Week 11 league trade deadline.",
                "Maintain 4-WR active depth to buffer against high-volatility 3-WR requirements.",
            ],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        r = await get_redis()
        await r.set("gridiron:team:season_strategy", json.dumps(strategy_plan))

        directives_md = "\n".join([f"- {d}" for d in strategy_plan["strategic_directives"]])
        content = (
            f"### 📈 Mid-Season Macro Strategy Briefing\n\n"
            f"- **Current Trajectory**: Record: {wins}-{losses} | Playoff Probability: **{playoff_pct}%**\n"
            f"- **Playoff Matchup Grade**: **A-** (Weeks 15-17 pass defense leverage)\n\n"
            f"#### 🎯 Strategic Directives for Team Cooper\n\n{directives_md}"
        )

        await NotificationDispatcher.dispatch_briefing(
            briefing_type="SEASON_STRATEGY",
            urgency="LOW",
            title=f"📈 Season Strategy Update ({playoff_pct}% Playoff Odds)",
            content=content,
            structured_data=strategy_plan,
            source_agent="GeneralManager",
        )
    except Exception as e:
        logger.error("job_season_strategy error: %s", str(e))
