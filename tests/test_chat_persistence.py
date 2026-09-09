"""
Tests for Chat History Persistence, Session Management, and API Endpoints.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.pipelines.chat_service import ChatService


@pytest.mark.asyncio
async def test_chat_service_lifecycle():
    # 1. Create session
    session = await ChatService.create_session("Round 1 Target Analysis")
    assert session is not None
    assert "id" in session
    assert session["title"] == "Round 1 Target Analysis"
    session_id = session["id"]

    # 2. Save user message
    user_msg = await ChatService.save_message(
        session_id=session_id,
        sender="user",
        text="Should we draft Ja'Marr Chase or Puka Nacua?",
        week=1
    )
    assert user_msg["sender"] == "user"
    assert user_msg["session_id"] == session_id

    # 3. Save GM response
    gm_msg = await ChatService.save_message(
        session_id=session_id,
        sender="gm",
        text="Prioritize Ja'Marr Chase given his high-ceiling target volume.",
        week=1
    )
    assert gm_msg["sender"] == "gm"
    assert gm_msg["session_id"] == session_id

    # 4. Fetch session history
    history = await ChatService.get_session_messages(session_id)
    assert history is not None
    assert history["session"]["id"] == session_id
    assert len(history["messages"]) == 2
    assert history["messages"][0]["text"] == "Should we draft Ja'Marr Chase or Puka Nacua?"
    assert history["messages"][1]["text"] == "Prioritize Ja'Marr Chase given his high-ceiling target volume."

    # 5. List sessions
    sessions = await ChatService.list_sessions()
    assert any(s["id"] == session_id for s in sessions)
    target_s = next(s for s in sessions if s["id"] == session_id)
    assert target_s["message_count"] == 2

    # 6. Delete session
    deleted = await ChatService.delete_session(session_id)
    assert deleted is True

    # 7. Confirm deleted
    post_delete = await ChatService.get_session_messages(session_id)
    assert post_delete is None


@pytest.mark.asyncio
async def test_chat_api_session_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create session via API
        res = await client.post("/api/chat/sessions", json={"title": "Keeper Strategy Thread"})
        assert res.status_code == 200
        s_data = res.json()
        assert "id" in s_data
        session_id = s_data["id"]

        # List sessions
        res = await client.get("/api/chat/sessions")
        assert res.status_code == 200
        l_data = res.json()
        assert "sessions" in l_data
        assert any(s["id"] == session_id for s in l_data["sessions"])

        # Send chat message attached to session
        from unittest.mock import patch, AsyncMock
        with patch("app.api.routes.ask_general_manager", new_callable=AsyncMock) as mock_gm:
            mock_gm.return_value = "Prioritize WR depth and hold firm."
            res = await client.post("/api/chat", json={
                "message": "What is our draft plan with Javonte Williams locked?",
                "week": 1,
                "session_id": session_id
            })
            assert res.status_code == 200
            chat_data = res.json()
            assert chat_data["success"] is True
            assert chat_data["session_id"] == session_id
            assert "response" in chat_data

        # Verify message history contains both user prompt and GM response
        res = await client.get(f"/api/chat/sessions/{session_id}")
        assert res.status_code == 200
        hist_data = res.json()
        assert len(hist_data["messages"]) == 2
        assert hist_data["messages"][0]["sender"] == "user"
        assert hist_data["messages"][1]["sender"] == "gm"

        # Delete session
        res = await client.delete(f"/api/chat/sessions/{session_id}")
        assert res.status_code == 200
        assert res.json()["success"] is True

        # Verify 404 after deletion
        res = await client.get(f"/api/chat/sessions/{session_id}")
        assert res.status_code == 404
