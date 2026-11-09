"""Memory x situation proposal mining."""

import random
import string

from conftest import auth


async def _new_user(client):
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"miner_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "testpass123",
        },
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "testpass123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def test_memory_record_keeps_structured_data(client):
    token, user_id = await _new_user(client)
    from ai.memory.models import MemoryRecord
    from core.database.session import async_session

    async with async_session() as db:
        row = MemoryRecord(
            user_id=user_id,
            kind="commitment",
            content="周五前把报价发给张三",
            normalized="周五前把报价发给张三",
            data={"person": "张三", "due_at": "2026-11-13", "state": "open"},
        )
        db.add(row)
        await db.commit()
        assert row.data["person"] == "张三"


async def test_proposal_link_action_returns_url(client):
    from ai.cognition.proposals import _execute_action

    result = await _execute_action(
        None,
        1,
        type("P", (), {"id": 1, "title": "x", "bot_id": None})(),
        {"kind": "open", "payload": {"link": "/chat?session_id=abc"}},
    )
    assert result["link"] == "/chat?session_id=abc"
