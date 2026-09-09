import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from app.api.routes import router
from app.pipelines.draft_prep import DraftPrepService

test_app = FastAPI()
test_app.include_router(router)
client = TestClient(test_app)


@pytest.mark.asyncio
async def test_live_draft_status_pre_draft():
    status = await DraftPrepService.get_live_draft_status()
    assert "is_live" in status
    assert isinstance(status["is_live"], bool)
    assert "status" in status
    assert "keeper" in status
    assert status["keeper"]["player_name"] == "Javonte Williams"
    assert status["keeper"]["round_cost"] == 8


def test_multi_position_filtering_api():
    res = client.get("/api/draft/players?position=WR,RB&limit=25")
    assert res.status_code == 200
    data = res.json()
    assert "players" in data
    assert len(data["players"]) > 0
    positions = {p["position"] for p in data["players"]}
    assert positions.issubset({"WR", "RB"})
    assert "WR" in positions or "RB" in positions


def test_keeper_serialized_in_players_api():
    res = client.get("/api/draft/players?search=Javonte&limit=10")
    assert res.status_code == 200
    data = res.json()
    assert len(data["players"]) >= 1
    javonte = next(p for p in data["players"] if "javonte" in p["name"].lower())
    assert javonte["is_keeper"] is True
    assert javonte["keeper_round"] == 8
    assert javonte["keeper_team"] == "Team Cooper"


def test_dynamic_draft_prompts_api():
    res = client.get("/api/draft/prompts")
    assert res.status_code == 200
    data = res.json()
    assert "prompts" in data
    assert len(data["prompts"]) >= 3
    prompts_text = " ".join(data["prompts"])
    assert "Javonte Williams" in prompts_text or "keeper" in prompts_text.lower() or "draft" in prompts_text.lower()
