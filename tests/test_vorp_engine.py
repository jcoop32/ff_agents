"""
Unit tests for deterministic VORP engine and tier clustering algorithms.
"""

import pytest
from app.pipelines.vorp_engine import VORPEngine, DEFAULT_BASELINES


def test_calculate_vorp_for_position():
    sample_wrs = [
        {"name": "CeeDee Lamb", "projected_points": 315.0},
        {"name": "Justin Jefferson", "projected_points": 310.0},
        {"name": "Ja'Marr Chase", "projected_points": 305.0},
        {"name": "Amon-Ra St. Brown", "projected_points": 298.0},
        {"name": "Replacement WR", "projected_points": 200.0}
    ]

    # With baseline rank 5, baseline points = 200.0
    results = VORPEngine.calculate_vorp_for_position(sample_wrs, "WR", baseline_rank=5)
    assert len(results) == 5
    assert results[0]["name"] == "CeeDee Lamb"
    assert results[0]["vorp"] == 115.0
    assert results[0]["positional_rank"] == 1
    assert results[-1]["vorp"] == 0.0


def test_cross_positional_vorp():
    players_by_pos = {
        "WR": [
            {"name": "CeeDee Lamb", "position": "WR", "projected_points": 315.0},
            {"name": "Baseline WR", "position": "WR", "projected_points": 215.0}
        ],
        "RB": [
            {"name": "Breece Hall", "position": "RB", "projected_points": 290.0},
            {"name": "Baseline RB", "position": "RB", "projected_points": 220.0}
        ],
        "QB": [
            {"name": "Josh Allen", "position": "QB", "projected_points": 370.0},
            {"name": "Baseline QB", "position": "QB", "projected_points": 320.0}
        ]
    }

    baselines = {"WR": 2, "RB": 2, "QB": 2}
    ranked = VORPEngine.calculate_cross_positional_vorp(players_by_pos, baselines=baselines)

    assert len(ranked) == 6
    # CeeDee VORP = 315 - 215 = 100.0
    # Breece VORP = 290 - 220 = 70.0
    # Josh Allen VORP = 370 - 320 = 50.0
    assert ranked[0]["name"] == "CeeDee Lamb"
    assert ranked[0]["vorp"] == 100.0
    assert ranked[1]["name"] == "Breece Hall"
    assert ranked[1]["vorp"] == 70.0
    assert ranked[2]["name"] == "Josh Allen"
    assert ranked[2]["vorp"] == 50.0


def test_tier_breakdown_cliff_detection():
    # Large drop from Jefferson (305) to Tier 2 (275) = 30 pt cliff
    sample_players = [
        {"name": "CeeDee Lamb", "projected_points": 315.0},
        {"name": "Tyreek Hill", "projected_points": 312.0},
        {"name": "Justin Jefferson", "projected_points": 305.0},
        {"name": "WR Tier 2 Starter", "projected_points": 270.0},
        {"name": "WR Tier 2 Follower", "projected_points": 268.0}
    ]

    tier_data = VORPEngine.generate_tier_breakdown(sample_players)
    assert tier_data["total_tiers"] >= 2
    assert tier_data["tier_1_count"] == 3
    assert tier_data["next_cliff_delta"] >= 30.0
