"""
Unit and Integration tests for Proactive Autonomous Multi-Agent features:
- Dynamic SchedulerAPI & player surveillance
- Trade equity VORP calculation
- ActionExecutor approval gates & execution
- Proactive API routes (Briefings, Tracking, Actions, Power Rankings, Strategy)
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.api.routes import router
from app.pipelines.scheduler_api import SchedulerAPI
from app.pipelines.action_executor import ActionExecutor
from app.pipelines.notification_dispatcher import NotificationDispatcher
from app.tools.trade_tools import compute_trade_equity, evaluate_player_trade_value

api_app = FastAPI()
api_app.include_router(router)
client = TestClient(api_app)


@pytest.mark.asyncio
async def test_scheduler_tracking_job_lifecycle():
    """Tests dynamic spawning, modification/escalation, and cancellation of tracking jobs."""
    # 1. Spawn tracking job
    job = await SchedulerAPI.spawn_tracking_job(
        player_name="Caleb Williams",
        focus_areas=["injury", "practice", "depth_chart"],
        frequency_minutes=60,
        duration_hours=48,
        reason="Unit test verification",
        source="user",
    )

    job_id = job["job_id"]
    assert job_id.startswith("watch_caleb_williams_")
    assert job["player_name"] == "Caleb Williams"
    assert job["frequency_minutes"] == 60
    assert job["status"] == "ACTIVE"

    # 2. Modify / Escalate tracking job
    modified = await SchedulerAPI.modify_tracking_job(
        job_id=job_id,
        new_frequency_minutes=15,
        reason="Test escalation to 15m",
    )
    assert modified is not None
    assert modified["frequency_minutes"] == 15
    assert len(modified["history"]) >= 2

    # 3. List active jobs
    jobs = await SchedulerAPI.list_tracking_jobs(include_inactive=False)
    active_ids = [j["job_id"] for j in jobs]
    assert job_id in active_ids

    # 4. Cancel tracking job
    cancelled = await SchedulerAPI.cancel_tracking_job(job_id=job_id, reason="Test complete")
    assert cancelled is True

    # 5. Verify status updated
    persisted = await SchedulerAPI.get_tracking_job(job_id)
    assert persisted["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_trade_equity_vorp_calculation():
    """Tests deterministic trade equity calculations using player projections and consolidation math."""
    equity = await compute_trade_equity(
        players_sent=["Chuba Hubbard", "Christian Watson"],
        players_received=["Kyren Williams"],
        scoring_format="ppr",
        remaining_weeks=14,
    )

    assert "total_value_sent" in equity
    assert "total_value_received" in equity
    assert "net_value_differential" in equity
    assert "verdict" in equity
    assert "consolidation_bonus" in equity
    assert equity["verdict"] in ("Accept", "Reject", "Counter")


@pytest.mark.asyncio
async def test_notification_dispatcher_briefing():
    """Tests dispatching a briefing to PostgreSQL and Redis channels."""
    briefing = await NotificationDispatcher.dispatch_briefing(
        briefing_type="TEST_ALERT",
        urgency="HIGH",
        title="Test Situational Alert",
        content="Automated test content for briefing dispatch.",
        structured_data={"test_key": "test_val"},
        source_agent="TestAgent",
    )

    assert briefing["title"] == "Test Situational Alert"
    assert briefing["urgency"] == "HIGH"
    assert briefing["source_agent"] == "TestAgent"


def test_api_briefings_endpoint():
    """Tests GET /api/briefings endpoint."""
    res = client.get("/api/briefings")
    assert res.status_code == 200
    data = res.json()
    assert "briefings" in data
    assert "count" in data


def test_api_tracking_jobs_crud():
    """Tests POST and GET and DELETE /api/tracking/jobs."""
    # Create job
    create_res = client.post("/api/tracking/jobs", json={
        "player_name": "Isaiah Likely",
        "focus_areas": ["injury", "depth_chart"],
        "frequency_minutes": 30,
        "duration_hours": 24,
        "reason": "Test route watch",
    })
    assert create_res.status_code == 200
    created = create_res.json()
    assert created["success"] is True
    job_id = created["job"]["job_id"]

    # List jobs
    list_res = client.get("/api/tracking/jobs")
    assert list_res.status_code == 200
    jobs = list_res.json()["jobs"]
    assert any(j["job_id"] == job_id for j in jobs)

    # Cancel job
    del_res = client.delete(f"/api/tracking/jobs/{job_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True


def test_api_pending_actions_endpoint():
    """Tests GET /api/actions/pending endpoint."""
    res = client.get("/api/actions/pending")
    assert res.status_code == 200
    data = res.json()
    assert "actions" in data
    assert "count" in data


def test_api_power_rankings_endpoint():
    """Tests GET /api/league/power-rankings endpoint."""
    res = client.get("/api/league/power-rankings")
    assert res.status_code == 200
    data = res.json()
    assert "rankings" in data
    assert data["league"] == "WA minus Josh"


def test_api_season_strategy_endpoint():
    """Tests GET /api/team/season-strategy endpoint."""
    res = client.get("/api/team/season-strategy")
    assert res.status_code == 200
    data = res.json()
    assert "strategy" in data
    assert data["team"] == "Team Cooper"


def test_api_proactive_trigger_validation():
    """Tests POST /api/proactive/trigger validation."""
    # Invalid job should return 400
    bad_res = client.post("/api/proactive/trigger/non_existent_job")
    assert bad_res.status_code == 400

    # Valid job should dispatch in background
    good_res = client.post("/api/proactive/trigger/job_morning_digest")
    assert good_res.status_code == 200
    assert good_res.json()["success"] is True
