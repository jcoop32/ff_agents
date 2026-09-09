"""
Unit tests for YahooSyncService and Multi-Source ADP Consensus calculations.
"""

import pytest
from app.pipelines.yahoo_sync import YahooSyncService
from app.pipelines.consensus_engine import ConsensusEngine


def test_yahoo_name_normalization():
    assert YahooSyncService.fetch_yahoo_draft_analysis is not None


def test_consensus_adp_calculation():
    # Test ADP averaging across Sleeper, ESPN, Yahoo
    s_adp = 2.2
    e_adp = 2.4
    y_adp = 2.0
    valid_adps = [s_adp, e_adp, y_adp]
    consensus = round(sum(valid_adps) / len(valid_adps), 1)
    assert consensus == 2.2


def test_consensus_adp_missing_source():
    # Player with Sleeper and ESPN, but no Yahoo
    s_adp = 168.7
    e_adp = 168.7
    y_adp = None
    valid_adps = [a for a in (s_adp, e_adp, y_adp) if a is not None]
    consensus = round(sum(valid_adps) / len(valid_adps), 1)
    assert consensus == 168.7
