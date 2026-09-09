"""
Consensus Projection & Multi-Source ADP Engine.
Blends multi-source projections and ADPs (ESPN, Sleeper, Yahoo),
computes statistical consensus ADP, floor/ceiling spreads,
player sentiment scoring, and extracts granular injury intelligence.
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.player import Player
from app.models.stats import NewsItem
from app.pipelines.sleeper_sync import SleeperSyncService
from app.pipelines.yahoo_sync import YahooSyncService

logger = logging.getLogger(__name__)


class ConsensusEngine:
    @staticmethod
    def calculate_sentiment(injury_status: Optional[str], news_items: List[NewsItem]) -> tuple[float, str]:
        """
        Computes a sentiment score (-1.0 to +1.0) and label (BULLISH, NEUTRAL, BEARISH)
        based on injury status and recent beat reporting context.
        """
        score = 0.0
        s = (injury_status or "").lower()

        if "out" in s or "ir" in s or "reserve" in s:
            score -= 0.7
        elif "doubtful" in s:
            score -= 0.5
        elif "questionable" in s:
            score -= 0.2
        elif "healthy" in s or "active" in s:
            score += 0.2

        for item in news_items:
            tag = (item.tag or "").upper()
            text = (item.text or "").lower()
            if tag in ("IR", "O", "DNP"):
                score -= 0.3
            elif tag in ("FP", "ACTIVE"):
                score += 0.2

            if any(w in text for w in ("impressing", "breakout", "surging", "dominant", "lead back", "wr1")):
                score += 0.25
            if any(w in text for w in ("setback", "struggling", "demoted", "benched", "surgery", "sprain")):
                score -= 0.3

        clamped = max(-1.0, min(1.0, round(score, 2)))
        if clamped >= 0.3:
            tag_label = "BULLISH"
        elif clamped <= -0.3:
            tag_label = "BEARISH"
        else:
            tag_label = "NEUTRAL"

        return clamped, tag_label

    @classmethod
    async def blend_and_store_projections(cls) -> Dict[str, Any]:
        """
        Blends ESPN, Sleeper, and Yahoo data in PostgreSQL:
        - Calculates consensus projected points (ESPN + Sleeper)
        - Calculates consensus ADP across Sleeper, ESPN, and Yahoo
        - Synthesizes injury notes and populates NewsItems
        """
        sleeper_data = await SleeperSyncService.fetch_sleeper_projections()
        yahoo_data = await YahooSyncService.fetch_yahoo_draft_analysis()
        updated_count = 0

        async with AsyncSessionLocal() as session:
            stmt = select(Player)
            res = await session.execute(stmt)
            players = res.scalars().all()

            for p in players:
                espn_pts = float(p.projected_points or 0.0)
                norm_name = SleeperSyncService.normalize_name(p.name)
                norm_pos = "D/ST" if p.position in ("DST", "D/ST", "DEF") else p.position
                lookup_key = f"{norm_name}:{norm_pos}"

                sleeper_match = sleeper_data.get(lookup_key)
                sleeper_pts = float(sleeper_match.get("projected_points", 0.0)) if sleeper_match else 0.0
                s_adp = sleeper_match.get("adp") if sleeper_match else None

                yahoo_match = yahoo_data.get(lookup_key)
                y_adp = yahoo_match.get("yahoo_adp") if yahoo_match else None

                e_adp = p.espn_adp

                # Compute Consensus ADP across Sleeper, ESPN, Yahoo
                valid_adps = [float(a) for a in (s_adp, e_adp, y_adp) if a is not None and float(a) > 0]
                consensus_adp = round(sum(valid_adps) / len(valid_adps), 1) if valid_adps else None

                # Compute Projections Consensus
                if espn_pts > 0 and sleeper_pts > 0:
                    consensus_pts = round((espn_pts + sleeper_pts) / 2.0, 1)
                    floor_pts = round(min(espn_pts, sleeper_pts), 1)
                    ceiling_pts = round(max(espn_pts, sleeper_pts), 1)
                elif espn_pts > 0:
                    consensus_pts = round(espn_pts, 1)
                    floor_pts = round(espn_pts * 0.85, 1)
                    ceiling_pts = round(espn_pts * 1.15, 1)
                elif sleeper_pts > 0:
                    consensus_pts = round(sleeper_pts, 1)
                    floor_pts = round(sleeper_pts * 0.85, 1)
                    ceiling_pts = round(sleeper_pts * 1.15, 1)
                else:
                    consensus_pts = 0.0
                    floor_pts = 0.0
                    ceiling_pts = 0.0

                consensus_avg = round(consensus_pts / 17.0, 1) if consensus_pts > 0 else 0.0

                # Synthesize Multi-Source Injury Intelligence
                notes_list = []
                if yahoo_match and yahoo_match.get("injury_note"):
                    y_stat = yahoo_match.get("status_full") or "Injured"
                    notes_list.append(f"Yahoo: {y_stat} ({yahoo_match['injury_note']})")

                if sleeper_match and (sleeper_match.get("injury_body_part") or sleeper_match.get("injury_notes")):
                    s_part = sleeper_match.get("injury_body_part") or ""
                    s_notes = sleeper_match.get("injury_notes") or ""
                    s_stat = sleeper_match.get("injury_status") or "Injured"
                    detail = f"{s_part} {f'({s_notes})' if s_notes else ''}".strip()
                    notes_list.append(f"Sleeper: {s_stat} ({detail})")

                espn_stat = p.injury_status or "Healthy"
                if espn_stat not in ("Healthy", "ACTIVE", "NORMAL") and not notes_list:
                    notes_list.append(f"ESPN: Designated as {espn_stat}")

                injury_summary = " | ".join(notes_list) if notes_list else None

                # Query recent news or seed synthesized injury news
                news_stmt = select(NewsItem).where(NewsItem.player_name == p.name).limit(5)
                news_res = await session.execute(news_stmt)
                news_items = list(news_res.scalars().all())

                if injury_summary and not news_items:
                    # Seed news item for scouting drawer
                    seeded_news = NewsItem(
                        player_id=p.id,
                        espn_id=p.espn_id,
                        player_name=p.name,
                        source="Beat Reports",
                        tag=espn_stat if espn_stat not in ("Healthy", "NORMAL") else "Q",
                        headline=f"{p.name} Injury Update",
                        text=injury_summary,
                        url=None
                    )
                    session.add(seeded_news)
                    news_items.append(seeded_news)

                sentiment_score, sentiment_tag = cls.calculate_sentiment(p.injury_status, news_items)

                # Volume stat lines
                espn_stats = (p.espn_data or {}).get("stats", {})
                sleeper_stats = sleeper_match.get("stats", {}) if sleeper_match else {}

                cons_pass_yd = round(((float(espn_stats.get("passingYards") or 0)) + (float(sleeper_stats.get("pass_yd") or 0))) / (2 if espn_pts and sleeper_pts else 1), 1)
                cons_rush_yd = round(((float(espn_stats.get("rushingYards") or 0)) + (float(sleeper_stats.get("rush_yd") or 0))) / (2 if espn_pts and sleeper_pts else 1), 1)
                cons_rec_yd = round(((float(espn_stats.get("receivingYards") or 0)) + (float(sleeper_stats.get("rec_yd") or 0))) / (2 if espn_pts and sleeper_pts else 1), 1)
                cons_rec = round(((float(espn_stats.get("receivingReceptions") or 0)) + (float(sleeper_stats.get("rec") or 0))) / (2 if espn_pts and sleeper_pts else 1), 1)

                source_payload = {
                    "consensus": {
                        "points": consensus_pts,
                        "avg": consensus_avg,
                        "floor": floor_pts,
                        "ceiling": ceiling_pts,
                        "adp": consensus_adp,
                        "pass_yds": cons_pass_yd,
                        "rush_yds": cons_rush_yd,
                        "rec_yds": cons_rec_yd,
                        "rec": cons_rec,
                    },
                    "espn": {
                        "points": round(espn_pts, 1),
                        "avg": round(espn_pts / 17.0, 1) if espn_pts > 0 else 0.0,
                        "adp": e_adp,
                        "stats": espn_stats,
                        "season_outlook": (p.espn_data or {}).get("season_outlook")
                    },
                    "sleeper": {
                        "points": round(sleeper_pts, 1),
                        "avg": round(sleeper_pts / 17.0, 1) if sleeper_pts > 0 else 0.0,
                        "adp": s_adp,
                        "injury_body_part": sleeper_match.get("injury_body_part") if sleeper_match else None,
                        "stats": sleeper_stats
                    },
                    "yahoo": {
                        "adp": y_adp,
                        "status": yahoo_match.get("status_full") if yahoo_match else None,
                        "injury_note": yahoo_match.get("injury_note") if yahoo_match else None,
                        "percent_drafted": yahoo_match.get("percent_drafted") if yahoo_match else None
                    },
                    "variance": {
                        "points_delta": round(abs(espn_pts - sleeper_pts), 1) if (espn_pts and sleeper_pts) else 0.0,
                        "adp_spread": round(max(valid_adps) - min(valid_adps), 1) if len(valid_adps) >= 2 else 0.0,
                        "agreement_rating": "HIGH" if abs(espn_pts - sleeper_pts) < 15 else ("MODERATE" if abs(espn_pts - sleeper_pts) < 35 else "WIDE_SPREAD")
                    }
                }

                # Update player record
                p.espn_proj = espn_pts
                p.sleeper_proj = sleeper_pts
                p.consensus_proj = consensus_pts
                p.proj_floor = floor_pts
                p.proj_ceiling = ceiling_pts
                p.adp = consensus_adp or s_adp or e_adp or y_adp
                p.consensus_adp = consensus_adp
                p.sleeper_adp = s_adp
                p.espn_adp = e_adp
                p.yahoo_adp = y_adp
                p.injury_notes = injury_summary
                p.projected_points = consensus_pts
                p.projected_avg = consensus_avg
                p.sentiment_score = sentiment_score
                p.sentiment_tag = sentiment_tag
                p.source_projections = source_payload

                updated_count += 1

            await session.commit()
            logger.info("ConsensusEngine: Updated %d players with multi-source ADPs and injury notes.", updated_count)

        return {"success": True, "players_updated": updated_count}
