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


async def test_goal_and_task_crud(client):
    token, _ = await _new_user(client)
    r = await client.post(
        "/api/cognition/goals",
        json={
            "title": "周五前拿到预算确认",
            "success_criteria": ["拿到书面确认"],
            "priority": 80,
        },
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    goal = r.json()
    goal_id = goal["id"]
    workspace_id = goal["workspace_id"]
    assert workspace_id

    r = await client.get(
        f"/api/cognition/workspaces/{workspace_id}",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["goal_id"] == goal_id

    r = await client.post(
        f"/api/cognition/workspaces/{workspace_id}/items",
        json={"type": "comment", "content": {"text": "先确认预算"}},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    item_id = r.json()["id"]

    r = await client.patch(
        f"/api/cognition/workspaces/{workspace_id}/items/{item_id}",
        json={"content": {"text": "先确认预算再发邮件"}},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["content"]["text"] == "先确认预算再发邮件"

    r = await client.get(
        f"/api/cognition/workspaces/{workspace_id}/export",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/zip")

    r = await client.delete(
        f"/api/cognition/workspaces/{workspace_id}/items/{item_id}",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        f"/api/cognition/goals/{goal_id}/tasks",
        json={
            "title": "起草回复",
            "agent_profile_key": "comms",
            "acceptance": ["有引用", "不承诺日期"],
        },
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    task_id = r.json()["id"]

    r = await client.get(f"/api/cognition/goals/{goal_id}/tasks", headers=auth(token))
    assert r.status_code == 200, r.text
    assert [t["id"] for t in r.json()] == [task_id]

    r = await client.patch(
        f"/api/cognition/goals/{goal_id}/tasks/{task_id}",
        json={"status": "done"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"


async def test_goal_plan_and_dispatch(client):
    token, _ = await _new_user(client)
    r = await client.post(
        "/api/cognition/goals",
        json={"title": "准备预算评审", "description": "周五前完成"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    goal_id = r.json()["id"]

    r = await client.post(
        f"/api/cognition/goals/{goal_id}/plan",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["tasks"]

    r = await client.post(
        f"/api/cognition/goals/{goal_id}/tick",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["goal"]["status"] in ("running", "ready", "waiting")
    assert body["tasks"]


async def test_proposal_accept_without_action_creates_goal(client):
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
        json={"action": "accept"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "create_goal"
    goal_id = r.json()["goal_id"]

    r = await client.get(f"/api/cognition/goals/{goal_id}", headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "跟进客户"


async def test_proposal_semantic_dedupe(client):
    token, user_id = await _new_user(client)
    from ai.cognition.proposals import create_proposal

    first = await create_proposal(
        user_id, kind="follow_up", title="跟进客户预算确认", channel="now"
    )
    second = await create_proposal(
        user_id, kind="follow_up", title="跟进客户预算的确认。", channel="now"
    )
    assert first.id == second.id


async def test_proposal_interruption_downgrades_in_quiet_hours(client, monkeypatch):
    from core.config.settings import settings

    monkeypatch.setattr(settings, "proposal_quiet_hours", "00:00-23:59")
    token, user_id = await _new_user(client)
    from ai.cognition.proposals import create_proposal

    row = await create_proposal(
        user_id, kind="follow_up", title="该发通知的提案", channel="notification"
    )
    assert row.channel == "now"
    assert row.evidence["interruption"]["deferred"] == "quiet_hours"


async def test_cognition_golden_paths(client):
    token, user_id = await _new_user(client)
    from evals.cognition import run

    assert await run(user_id) == 0


async def test_situation_now(client):
    token, _ = await _new_user(client)
    r = await client.get("/api/cognition/now", headers=auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"]
    assert body["generated_at"]
    assert isinstance(body["signals"], list)
    assert "calendar" in body and "todos" in body and "inbox" in body


async def test_handoff_reports_offline_machine(client):
    token, _ = await _new_user(client)
    r = await client.post(
        "/api/cognition/handoff",
        json={"machine_id": "missing-machine", "note": "继续看目标"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["sent"] is False


async def test_direct_mcp_call_requires_approval(client):
    token, _ = await _new_user(client)
    r = await client.post(
        "/api/mcp/call",
        json={"name": "send_email", "arguments": {"to": ["x@example.com"]}},
        headers=auth(token),
    )
    assert r.status_code == 409, r.text
