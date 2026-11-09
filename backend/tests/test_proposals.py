"""Proposal lifecycle and unified capability authorization."""

import random
import string

from conftest import auth


async def _new_user(client):
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"proposal_{suffix}"
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


async def test_proposal_accept_executes_todo(client):
    token, user_id = await _new_user(client)
    from ai.cognition.models import Proposal
    from core.database.session import async_session

    async with async_session() as db:
        row = Proposal(
            user_id=user_id,
            kind="todo",
            title="准备产品评审",
            reason="会议将至",
            confidence=0.8,
            status="new",
            actions=[{
                "key": "create_todo",
                "label": "执行",
                "kind": "create_todo",
                "payload": {"title": "准备产品评审", "priority": 1},
            }],
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        proposal_id = row.id

    r = await client.get("/api/proposals", headers=auth(token))
    assert r.status_code == 200, r.text
    assert any(item["id"] == proposal_id for item in r.json()["items"])

    r = await client.post(
        f"/api/proposals/{proposal_id}/act",
        json={"action": "accept"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "executed"

    r = await client.get("/api/plugins/todo/items", headers=auth(token))
    assert r.status_code == 200, r.text
    assert any(item["title"] == "准备产品评审" for item in r.json())


async def test_proposal_dismiss(client):
    token, user_id = await _new_user(client)
    from ai.cognition.models import Proposal
    from core.database.session import async_session

    async with async_session() as db:
        row = Proposal(user_id=user_id, kind="follow_up", title="跟进客户", status="new")
        db.add(row)
        await db.commit()
        await db.refresh(row)
        proposal_id = row.id

    r = await client.post(
        f"/api/proposals/{proposal_id}/act",
        json={"action": "dismiss"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "dismissed"


async def test_capability_grant_turns_ask_into_allow(client):
    token, user_id = await _new_user(client)
    from ai.bots.registry import get_active_bot
    from ai.cognition.authorization import authorize

    bot = await get_active_bot(user_id)
    first = await authorize(user_id, "send_email", {"to": ["x@example.com"]}, bot=bot)
    assert first.decision == "require_approval", first

    r = await client.post(
        "/api/capabilities/grants",
        json={
            "capability_key": "send_email",
            "decision": "allow",
            "scope": "always",
            "bot_id": bot.id,
        },
        headers=auth(token),
    )
    assert r.status_code == 201, r.text

    second = await authorize(user_id, "send_email", {"to": ["x@example.com"]}, bot=bot)
    assert second.decision == "allow", second


async def test_capability_list_and_grant_revoke(client):
    token, _ = await _new_user(client)
    r = await client.get("/api/capabilities", headers=auth(token))
    assert r.status_code == 200, r.text
    assert any(item["key"] == "send_email" for item in r.json())

    r = await client.post(
        "/api/capabilities/grants",
        json={"capability_key": "send_email", "scope": "once"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    grant_id = r.json()["id"]

    r = await client.get("/api/capabilities/grants", headers=auth(token))
    assert r.status_code == 200, r.text
    assert any(item["id"] == grant_id for item in r.json())

    r = await client.delete(f"/api/capabilities/grants/{grant_id}", headers=auth(token))
    assert r.status_code == 200, r.text


async def test_direct_mcp_call_requires_approval(client):
    token, _ = await _new_user(client)
    r = await client.post(
        "/api/mcp/call",
        json={"name": "send_email", "arguments": {"to": ["x@example.com"]}},
        headers=auth(token),
    )
    assert r.status_code == 409, r.text
