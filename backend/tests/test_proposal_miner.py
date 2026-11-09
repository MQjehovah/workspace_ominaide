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


async def test_commitment_and_event_create_proposal(client):
    token, user_id = await _new_user(client)
    from datetime import datetime, timedelta
    from ai.memory.models import MemoryRecord
    from plugins.schedule.backend.models import Event
    from core.database.session import async_session
    from ai.cognition.miner import mine_user

    async with async_session() as db:
        db.add(Event(
            user_id=user_id,
            title="和张三开预算评审会",
            start_time=datetime.now() + timedelta(hours=2),
        ))
        db.add(MemoryRecord(
            user_id=user_id,
            kind="commitment",
            content="周五前把报价发给张三",
            normalized="周五前把报价发给张三",
            confidence=90,
            data={
                "person": "张三",
                "project": "预算",
                "state": "open",
                "due_at": "2026-11-13",
                "quote": "我周五前把报价发你",
            },
        ))
        await db.commit()

    result = await mine_user(user_id)
    assert result["created"] >= 1


async def test_memory_without_situation_is_rejected(client):
    token, user_id = await _new_user(client)
    from ai.cognition.miner import mine_user

    result = await mine_user(user_id)
    assert result["created"] == 0


async def test_proposal_link_action_returns_url(client):
    from ai.cognition.proposals import _execute_action

    result = await _execute_action(
        None,
        1,
        type("P", (), {"id": 1, "title": "x", "bot_id": None})(),
        {"kind": "open", "payload": {"link": "/chat?session_id=abc"}},
    )
    assert result["link"] == "/chat?session_id=abc"
