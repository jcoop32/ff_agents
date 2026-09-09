"""
Tests for Consensus Engine, Sentiment Classification, and On-The-Clock Recommendations.
"""

import pytest
from app.pipelines.consensus_engine import ConsensusEngine
from app.pipelines.draft_prep import DraftPrepService


def test_sentiment_scoring_healthy():
    score, tag = ConsensusEngine.calculate_sentiment("Healthy", [])
    assert tag == "NEUTRAL"
    assert score >= 0.0


def test_sentiment_scoring_injured():
    score, tag = ConsensusEngine.calculate_sentiment("Out", [])
    assert tag == "BEARISH"
    assert score <= -0.3


@pytest.mark.asyncio
async def test_on_the_clock_recommendations_structure():
    recs = await DraftPrepService.get_on_the_clock_recommendations(user_team_id=2, current_pick=2, limit=5)
    assert "recommendations" in recs
    assert "draft_phase" in recs
    assert recs["draft_phase"] in ("PRE_DRAFT", "LIVE_DRAFT")
    assert "keeper" in recs
    assert recs["keeper"]["player_name"] == "Javonte Williams"
    assert recs["keeper"]["round_cost"] == 8
    assert len(recs["recommendations"]) <= 5

    for r in recs["recommendations"]:
        assert "draft_grade" in r
        assert "consensus_proj" in r
        assert "vorp" in r
        assert "rationale" in r
        assert r["draft_grade"] in ("A+", "A", "A-", "B+", "B", "B-", "C")
