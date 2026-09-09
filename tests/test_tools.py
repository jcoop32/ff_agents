"""
Unit tests for deterministic agent tools.
"""

import pytest
from app.tools.trade_tools import calculate_trade_equity
from app.tools.lineup_tools import get_matchup_projections, get_defensive_matchup_data
from app.tools.draft_tools import get_tier_breakdown


@pytest.mark.asyncio
async def test_calculate_trade_equity():
    res = await calculate_trade_equity.ainvoke({
        "players_sent": ["Tyler Lockett"],
        "players_received": ["Garrett Wilson"],
        "scoring_format": "ppr"
    })
    assert "verdict" in res
    assert res["verdict"] in ("Accept", "Reject", "Counter")
    assert "net_value_differential" in res


@pytest.mark.asyncio
async def test_get_matchup_projections():
    res = await get_matchup_projections.ainvoke({
        "user_team_id": "2",
        "opponent_team_id": "5",
        "week": 1
    })
    assert res["week"] == 1
    assert "user_projected_points" in res
    assert "win_probability" in res


@pytest.mark.asyncio
async def test_get_defensive_matchup_data():
    res = await get_defensive_matchup_data.ainvoke({
        "opponent_team": "CAR",
        "position": "WR"
    })
    assert res["opponent_team"] == "CAR"
    assert "defensive_epa_rank" in res
    assert "dvoa_vs_slot_wr" in res


@pytest.mark.asyncio
async def test_get_tier_breakdown():
    res = await get_tier_breakdown.ainvoke({"position": "RB"})
    assert "tiers" in res
    assert "total_tiers" in res
