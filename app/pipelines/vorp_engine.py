"""
Pure Deterministic VORP (Value Over Replacement Player) & Tier Clustering Engine.
No LLM involvement — calculated using strictly deterministic mathematical algorithms.
"""

from typing import List, Dict, Any
import numpy as np

from app.core.config import settings


def default_baselines(league_size: int = None) -> Dict[str, int]:
    """
    Derives positional replacement baselines from league settings instead of
    hardcoded 12-team values. Baseline rank = (starters x teams) + offset,
    where the offset reserves room for FLEX-share (RB/WR) or a plain
    replacement (+1) at the other positions.
    """
    n = league_size or settings.LEAGUE_SIZE
    starters = {
        "QB": 1,
        "RB": 2,
        "WR": settings.NUM_WR_SLOTS,
        "TE": 1,
        "K": 1,
        "DST": 1,
    }
    flex_share = {"RB": 2, "WR": 2}  # FLEX spot draws from the RB/WR/TE pool
    return {pos: starters[pos] * n + flex_share.get(pos, 1) for pos in starters}


# Positional replacement baselines tuned for "WA minus Josh"
# (derived from settings: e.g. 10-team league, 1QB, 2RB, 3WR, 1TE, 1FLEX, 1K, 1DST)
DEFAULT_BASELINES = default_baselines()


class VORPEngine:
    """Calculates VORP rankings and tier-cliff boundaries."""

    @staticmethod
    def calculate_vorp_for_position(
        players: List[Dict[str, Any]],
        position: str,
        baseline_rank: int = None
    ) -> List[Dict[str, Any]]:
        """
        Computes VORP for a list of players at a specific position.
        VORP_i = Projected_Points_i - Baseline_Points_pos
        """
        if not players:
            return []

        # Sort descending by projected fantasy points
        sorted_players = sorted(
            players,
            key=lambda p: float(p.get("projected_points", 0.0)),
            reverse=True
        )

        cutoff_idx = (baseline_rank or default_baselines().get(position.upper(), settings.LEAGUE_SIZE + 1)) - 1
        cutoff_idx = max(0, min(cutoff_idx, len(sorted_players) - 1))
        baseline_points = float(sorted_players[cutoff_idx].get("projected_points", 0.0))

        enriched = []
        for rank, p in enumerate(sorted_players, start=1):
            pts = float(p.get("projected_points", 0.0))
            vorp = round(pts - baseline_points, 2)
            player_copy = dict(p)
            player_copy["positional_rank"] = rank
            player_copy["baseline_points"] = baseline_points
            player_copy["vorp"] = vorp
            enriched.append(player_copy)

        return enriched

    @staticmethod
    def calculate_cross_positional_vorp(
        players_by_pos: Dict[str, List[Dict[str, Any]]],
        baselines: Dict[str, int] = None
    ) -> List[Dict[str, Any]]:
        """
        Combines all positions and ranks overall by VORP to dictate draft board priorities.
        """
        baselines = baselines or DEFAULT_BASELINES
        all_enriched = []

        for pos, players in players_by_pos.items():
            rank_cutoff = baselines.get(pos.upper(), settings.LEAGUE_SIZE + 1)
            enriched_pos = VORPEngine.calculate_vorp_for_position(players, pos, rank_cutoff)
            all_enriched.extend(enriched_pos)

        # Sort all players across all positions by VORP descending
        all_enriched.sort(key=lambda p: p["vorp"], reverse=True)
        for overall_rank, p in enumerate(all_enriched, start=1):
            p["overall_vorp_rank"] = overall_rank

        return all_enriched

    @staticmethod
    def generate_tier_breakdown(players: List[Dict[str, Any]], max_tiers: int = 5) -> Dict[str, Any]:
        """
        Groups players at a position into tiers by detecting projection cliffs.
        Returns active tier members and point drop-off delta to subsequent tier.
        """
        if not players:
            return {"tiers": {}, "current_tier": 1, "next_cliff_delta": 0.0}

        sorted_players = sorted(
            players,
            key=lambda p: float(p.get("projected_points", 0.0)),
            reverse=True
        )

        pts = np.array([float(p.get("projected_points", 0.0)) for p in sorted_players])
        if len(pts) <= 1:
            return {
                "tiers": {1: sorted_players},
                "current_tier": 1,
                "next_cliff_delta": 0.0
            }

        # Calculate deltas between consecutive players
        deltas = np.abs(np.diff(pts))
        # Significant drop-off threshold (e.g. drop > 75th percentile of differences or > 12 pts)
        threshold = max(float(np.percentile(deltas, 75)), 8.0)

        tiers: Dict[int, List[Dict[str, Any]]] = {}
        current_tier = 1
        tiers[current_tier] = [sorted_players[0]]

        for i in range(len(deltas)):
            if deltas[i] >= threshold and current_tier < max_tiers:
                current_tier += 1
                tiers[current_tier] = []
            tiers[current_tier].append(sorted_players[i + 1])

        # Compute cliff delta from Tier 1 to Tier 2
        tier1_last_pts = float(tiers[1][-1].get("projected_points", 0.0)) if 1 in tiers else 0.0
        tier2_first_pts = float(tiers[2][0].get("projected_points", 0.0)) if 2 in tiers else 0.0
        next_cliff_delta = round(tier1_last_pts - tier2_first_pts, 2)

        return {
            "tiers": tiers,
            "total_tiers": len(tiers),
            "tier_1_count": len(tiers.get(1, [])),
            "next_cliff_delta": next_cliff_delta
        }
