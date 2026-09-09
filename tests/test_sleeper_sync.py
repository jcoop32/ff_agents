"""
Tests for Sleeper Open API Ingestion and Custom Scoring Formula.
"""

from app.pipelines.sleeper_sync import SleeperSyncService


def test_normalize_name():
    assert SleeperSyncService.normalize_name("Amon-Ra St. Brown Jr.") == "amonra st brown"
    assert SleeperSyncService.normalize_name("Kenneth Walker III") == "kenneth walker"
    assert SleeperSyncService.normalize_name("De'Von Achane") == "devon achane"


def test_calculate_custom_points():
    # Test scoring: 0.05 pass yd, 4.0 pass TD, -2.0 pass int, 0.1 rush/rec yd, 6.0 TD, 1.0 PPR
    stats = {
        "pass_yd": 4000.0, # 4000 * 0.05 = 200.0
        "pass_td": 30.0,   # 30 * 4 = 120.0
        "pass_int": 10.0,  # 10 * -2 = -20.0
        "rush_yd": 500.0,  # 500 * 0.1 = 50.0
        "rush_td": 5.0,    # 5 * 6 = 30.0
        "rec": 0.0,
        "rec_yd": 0.0,
        "rec_td": 0.0,
        "fum_lost": 2.0,   # 2 * -2 = -4.0
    }
    pts = SleeperSyncService.calculate_custom_points(stats)
    # Expected: 200 + 120 - 20 + 50 + 30 - 4 = 376.0
    assert pts == 376.0


def test_wr_ppr_custom_points():
    # 100 rec, 1200 rec yds, 10 rec TDs
    stats = {
        "rec": 100.0,    # 100 * 1 = 100.0
        "rec_yd": 1200.0,# 1200 * 0.1 = 120.0
        "rec_td": 10.0,  # 10 * 6 = 60.0
        "rush_yd": 50.0, # 50 * 0.1 = 5.0
        "fum_lost": 1.0, # -2.0
    }
    pts = SleeperSyncService.calculate_custom_points(stats)
    # Expected: 100 + 120 + 60 + 5 - 2 = 283.0
    assert pts == 283.0
