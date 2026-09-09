"""
Smoke tests for General Manager response orchestration and API endpoints.
"""

import pytest
from app.agents.supervisor import ask_general_manager
from app.api.routes import router
from fastapi.testclient import TestClient
from fastapi import FastAPI

test_app = FastAPI()
test_app.include_router(router)
client = TestClient(test_app)


@pytest.mark.asyncio
async def test_ask_general_manager_smoke():
    response = await ask_general_manager(
        user_query="Should I start Ja'Marr Chase or Amon-Ra St. Brown in PPR?",
        active_week=1
    )
    assert response is not None
    assert len(response) > 0
    assert "Verdict" in response or "Start" in response or "Chase" in response or "Recommendation" in response


def test_api_health_endpoint():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "espn_auth" in data
    assert "cache_metrics" in data


def test_api_chat_endpoint():
    res = client.post("/api/chat", json={
        "message": "Evaluate our WR depth for Week 1",
        "week": 1
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "response" in data


def test_api_roster_endpoint():
    res = client.get("/api/roster/2")
    assert res.status_code == 200
    data = res.json()
    assert "team_id" in data
    assert data["team_id"] == 2
    assert "players" in data


def test_api_standings_endpoint():
    res = client.get("/api/league/standings")
    assert res.status_code == 200
    data = res.json()
    assert "league_name" in data
    assert "standings" in data

