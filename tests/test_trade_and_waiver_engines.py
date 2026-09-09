"""
Unit and integration tests for Intelligent Trade Package Finder
and Waiver Wire Pick / Drop / IR Advisor.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.tools.trade_tools import (
    evaluate_player_trade_value,
    compute_trade_equity,
    calculate_trade_equity,
    find_player_fantasy_owner,
    analyze_team_roster_needs,
    find_trade_packages_to_acquire,
    find_trade_packages_for_player,
)
from app.tools.lineup_tools import evaluate_waiver_pickup
from app.models.player import Player
from app.models.league import Roster


def _make_mock_player(
    id: int,
    espn_id: str,
    name: str,
    position: str,
    projected_avg: float,
    injury_status: str = "Healthy",
    team: str = "KC",
    pos_rank: int = 15,
) -> Player:
    p = Player()
    p.id = id
    p.espn_id = espn_id
    p.name = name
    p.position = position
    p.projected_avg = projected_avg
    p.projected_points = projected_avg * 17.0
    p.injury_status = injury_status
    p.team = team
    p.pos_rank = pos_rank
    return p


@pytest.mark.asyncio
async def test_compute_trade_equity_consolidation():
    """Verify 2-for-1 consolidation bonus applies in 4-bench league."""
    # Sending 2 players to receive 1 player
    res_consolidation = await compute_trade_equity(
        players_sent=["Kenneth Walker", "Tyler Lockett"],
        players_received=["Justin Jefferson"]
    )
    assert res_consolidation["consolidation_bonus"] > 0
    assert "verdict" in res_consolidation

    # Sending 1 player to receive 2 players (consolidation penalty)
    res_dilution = await compute_trade_equity(
        players_sent=["Justin Jefferson"],
        players_received=["Kenneth Walker", "Tyler Lockett"]
    )
    assert res_dilution["consolidation_bonus"] < 0


@pytest.mark.asyncio
async def test_find_player_fantasy_owner_mocked():
    """Test locating player owner in league and free agent detection."""
    mock_cooper_roster = Roster(
        id=1,
        league_id=1,
        espn_team_id=2,
        team_name="Team Cooper",
        owner_name="Josh",
        players=["1001", "1002"],
    )
    mock_rival_roster = Roster(
        id=2,
        league_id=1,
        espn_team_id=5,
        team_name="Rival Dynamos",
        owner_name="Bob",
        players=["2001", "2002"],
    )

    tate = _make_mock_player(1, "2001", "Carnell Tate", "WR", 11.5)
    fa_player = _make_mock_player(2, "9999", "Random FA", "RB", 8.0)

    # Mock DB session execution
    async def mock_execute(stmt):
        mock_res = MagicMock()
        stmt_str = str(stmt).lower()
        try:
            params_str = str(stmt.compile().params).lower()
        except Exception:
            params_str = ""

        if "from rosters" in stmt_str:
            mock_res.scalars.return_value.all.return_value = [mock_cooper_roster, mock_rival_roster]
        elif "carnell" in params_str:
            mock_res.scalar_one_or_none.return_value = tate
        else:
            mock_res.scalar_one_or_none.return_value = fa_player
        return mock_res

    with patch("app.tools.trade_tools.AsyncSessionLocal") as mock_session_ctx:
        mock_session = MagicMock()
        mock_session.execute = mock_execute
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        # Test owned player
        res_owned = await find_player_fantasy_owner("Carnell Tate")
        assert res_owned["found"] is True
        assert res_owned["owned"] is True
        assert res_owned["espn_team_id"] == 5
        assert res_owned["team_name"] == "Rival Dynamos"

        # Test free agent
        res_fa = await find_player_fantasy_owner("Random FA")
        assert res_fa["found"] is True
        assert res_fa["owned"] is False
        assert res_fa["status"] == "FREE_AGENT"


@pytest.mark.asyncio
async def test_analyze_team_roster_needs_identifies_deficits():
    """Verify roster auditor identifies positional weaknesses and surpluses."""
    qb1 = _make_mock_player(1, "1", "Patrick Mahomes", "QB", 19.5)
    rb1 = _make_mock_player(2, "2", "Weak Backup RB", "RB", 6.5)
    rb2 = _make_mock_player(3, "3", "Committee RB", "RB", 7.0)
    wr1 = _make_mock_player(4, "4", "CeeDee Lamb", "WR", 17.5)
    wr2 = _make_mock_player(5, "5", "Drake London", "WR", 14.0)
    wr3 = _make_mock_player(6, "6", "Chris Godwin", "WR", 13.0)
    wr4 = _make_mock_player(7, "7", "Bench Star WR", "WR", 12.5)
    te1 = _make_mock_player(8, "8", "Travis Kelce", "TE", 12.0)

    rival_roster = Roster(
        id=2,
        league_id=1,
        espn_team_id=5,
        team_name="RB Deficient Team",
        owner_name="Alex",
        players=["1", "2", "3", "4", "5", "6", "7", "8"],
    )

    async def mock_execute(stmt):
        mock_res = MagicMock()
        stmt_str = str(stmt)
        if "rosters" in stmt_str.lower():
            mock_res.scalar_one_or_none.return_value = rival_roster
        elif "players" in stmt_str.lower():
            mock_res.scalars.return_value.all.return_value = [qb1, rb1, rb2, wr1, wr2, wr3, wr4, te1]
        return mock_res

    with patch("app.tools.trade_tools.AsyncSessionLocal") as mock_session_ctx:
        mock_session = MagicMock()
        mock_session.execute = mock_execute
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        audit = await analyze_team_roster_needs(5)
        assert "position_needs" in audit
        # RB starting avg is (6.5 + 7.0)/2 = 6.75, far below 13.0 benchmark -> CRITICAL_NEED
        assert audit["position_needs"]["RB"] == "CRITICAL_NEED"
        assert audit["weakest_position"] == "RB"
        # WR has multiple studs + bench depth -> SURPLUS
        assert audit["position_needs"]["WR"] in ["SURPLUS", "BALANCED"]


@pytest.mark.asyncio
async def test_find_trade_packages_to_acquire():
    """Verify target acquisition builds 1-for-1 and 2-for-1 packages with positive net equity."""
    opp_needs = {
        "team_name": "Team Opponent",
        "owner_name": "Mike",
        "weakest_position": "RB",
        "weakest_starter": {"name": "Low Tier RB", "projected_ppg": 7.0, "position": "RB"},
        "position_needs": {"RB": "CRITICAL_NEED", "WR": "BALANCED"},
    }

    cooper_needs = {
        "team_name": "Team Cooper",
        "owner_name": "Josh",
        "starters": {"RB": [{"name": "James Cook", "position": "RB", "projected_ppg": 14.0}]},
        "bench": [{"name": "Terry McLaurin", "position": "WR", "projected_ppg": 11.5}],
    }

    owner_info = {
        "found": True,
        "owned": True,
        "player": {"name": "Carnell Tate", "position": "WR"},
        "espn_team_id": 5,
    }

    with patch("app.tools.trade_tools.find_player_fantasy_owner", new_callable=AsyncMock, return_value=owner_info), \
         patch("app.tools.trade_tools.analyze_team_roster_needs", new_callable=AsyncMock, side_effect=[opp_needs, cooper_needs]):

        res = await find_trade_packages_to_acquire("Carnell Tate", user_team_id=2)

        assert res["status"] == "PACKAGES_FOUND"
        assert len(res["packages"]) > 0
        pkg = res["packages"][0]
        assert "players_sent" in pkg
        assert "players_received" in pkg
        assert "Carnell Tate" in pkg["players_received"]
        assert pkg["opponent_weekly_delta"] > 0
        assert "negotiation_pitch" in pkg


@pytest.mark.asyncio
async def test_evaluate_waiver_pickup_zero_cost_ir():
    """Verify waiver advisor detects empty IR slot and recommends zero-cost stash without dropping."""
    injured_bench_p = _make_mock_player(1, "1", "Injured Star", "WR", 13.0, injury_status="Out")
    healthy_bench_p = _make_mock_player(2, "2", "Backup TE", "TE", 6.0)

    mock_roster = Roster(
        id=1,
        espn_team_id=2,
        team_name="Team Cooper",
        players=["1", "2"],
        lineup_slots={"1": "BENCH", "2": "BENCH"},  # IR slot is empty!
        starters=[],
    )

    async def mock_execute(stmt):
        mock_res = MagicMock()
        stmt_str = str(stmt)
        if "rosters" in stmt_str.lower():
            mock_res.scalar_one_or_none.return_value = mock_roster
        elif "players" in stmt_str.lower():
            mock_res.scalars.return_value.all.return_value = [injured_bench_p, healthy_bench_p]
        return mock_res

    with patch("app.tools.lineup_tools.AsyncSessionLocal") as mock_session_ctx:
        mock_session = MagicMock()
        mock_session.execute = mock_execute
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        res = await evaluate_waiver_pickup("Jaylen Warren", user_team_id=2)

        assert res["zero_cost_ir_stash"] is True
        assert res["verdict"] == "STRONG ADD"
        assert res["verdict_badge"] == "FREE IR ADD"
        assert res["ir_recommendation"]["eligible_player"] == "Injured Star"
        assert "NO DROP REQUIRED" in res["ir_recommendation"]["instructions"]


@pytest.mark.asyncio
async def test_evaluate_waiver_pickup_bench_cut_ranking():
    """Verify waiver advisor ranks the optimal bench cut candidate when IR is full."""
    bench_p1 = _make_mock_player(1, "1", "Solid Handcuff RB", "RB", 10.5)
    bench_p2 = _make_mock_player(2, "2", "Redundant Backup QB", "QB", 8.0)

    mock_roster = Roster(
        id=1,
        espn_team_id=2,
        team_name="Team Cooper",
        players=["1", "2"],
        lineup_slots={"1": "BENCH", "2": "BENCH"},
        starters=[],
    )

    async def mock_execute(stmt):
        mock_res = MagicMock()
        stmt_str = str(stmt)
        if "rosters" in stmt_str.lower():
            mock_res.scalar_one_or_none.return_value = mock_roster
        elif "players" in stmt_str.lower():
            mock_res.scalars.return_value.all.return_value = [bench_p1, bench_p2]
        return mock_res

    with patch("app.tools.lineup_tools.AsyncSessionLocal") as mock_session_ctx:
        mock_session = MagicMock()
        mock_session.execute = mock_execute
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        res = await evaluate_waiver_pickup("Isaiah Likely", user_team_id=2)

        assert res["zero_cost_ir_stash"] is False
        assert res["primary_cut_candidate"] is not None
        # Redundant Backup QB should be the #1 cut candidate over the solid RB handcuff
        assert res["primary_cut_candidate"]["name"] == "Redundant Backup QB"
        assert "net_weekly_delta" in res
