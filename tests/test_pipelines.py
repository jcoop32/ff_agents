"""
Unit tests for data pipelines, news extraction, and proactive transaction parsing.
"""

import pytest
from app.pipelines.news_stream import NewsIngestionService
from app.pipelines.league_monitor import LeagueActivityMonitor
from app.core.llm_cache import LLMCache


def test_extract_injury_tag():
    assert NewsIngestionService._extract_injury_tag("Ruled out for Sunday with ankle sprain") == "Out"
    assert NewsIngestionService._extract_injury_tag("Player is questionable after limited session") == "Questionable"
    assert NewsIngestionService._extract_injury_tag("Listed as DNP on Wednesday practice report") == "DNP"
    assert NewsIngestionService._extract_injury_tag("Logged full participation (FP) Friday") == "FP"
    assert NewsIngestionService._extract_injury_tag("Healthy scratch") is None


def test_llm_cache_key_generation():
    key1 = LLMCache.generate_cache_key(
        model="gemini-3.6-flash",
        system_prompt="You are GM",
        user_query="Start Chase or St. Brown?",
        context_payload={"week": 1}
    )
    key2 = LLMCache.generate_cache_key(
        model="gemini-3.6-flash",
        system_prompt="You are GM",
        user_query="Start chase or st. brown? ", # case and whitespace differences
        context_payload={"week": 1}
    )
    # Cache keys must match deterministically
    assert key1 == key2
    assert key1.startswith("llm_cache:")


def test_parse_activity_item_structure():
    class DummyTeam:
        team_id = 4
        team_name = "Team Palmby"

    class DummyActivity:
        actions = [
            ("Demarcus Robinson", "WAIVER ADDED"),
            ("Kadarius Toney", "DROPPED")
        ]
        team = DummyTeam()

    parsed = LeagueActivityMonitor._parse_activity_item(DummyActivity())
    assert parsed["type"] == "WAIVER"
    assert parsed["team_name"] == "Team Palmby"
    assert len(parsed["players_added"]) == 1
    assert parsed["players_added"][0]["name"] == "Demarcus Robinson"
    assert len(parsed["players_dropped"]) == 1
    assert parsed["players_dropped"][0]["name"] == "Kadarius Toney"
