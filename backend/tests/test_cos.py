"""Chief-of-Staff scenario API: triage, briefs, meeting prep and drafts."""

from conftest import auth
from datetime import date, datetime, timedelta


async def _new_user(client):
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"cos_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def _seed_sources(user_id: int, tag: str) -> dict:
    """Create one mail, todo, event and information item for a user."""
    from core.database.session import async_session
    from plugins.mail.backend.models import MailAccount, MailMessage
    from plugins.sources.backend.models import ContentItem, ContentSource
    from plugins.schedule.backend.models import Event
    from plugins.todo.backend.models import PluginTodoItem

    now = datetime.now()
    async with async_session() as db:
        account = MailAccount(
            user_id=user_id, email=f"{tag}@example.com", imap_host="imap.example.com",
            smtp_host="smtp.example.com", username="u", password="p",
        )
        db.add(account)
        await db.flush()
        mail = MailMessage(
            user_id=user_id, account_id=account.id, uid=1,
            subject=f"{tag} 预算评审",
            from_address="boss@example.com",
            preview="请确认预算方案",
            content="请在下周一前确认预算方案，并同步给项目组。",
            date=now, important=True, read=False,
        )
        todo = PluginTodoItem(
            user_id=user_id, title=f"{tag} 提交预算",
            status="pending", priority=2, due_date=now + timedelta(hours=2),
        )
        event = Event(
            user_id=user_id, title=f"{tag} 周会",
            start_time=now, end_time=now + timedelta(hours=1),
            notes="讨论预算与排期",
        )
        source = ContentSource(
            user_id=user_id,
            provider="rss",
            url=f"https://example.com/{tag}",
            title="科技资讯",
        )
        db.add_all([mail, todo, event, source])
        await db.flush()
        item = ContentItem(
            source_id=source.id, guid=f"{tag}-1", title=f"{tag} 行业动态",
            summary="AI 产品更新", link=f"https://example.com/{tag}/1",
            published=now, read=False,
        )
        db.add(item)
        await db.commit()
        return {
            "mail_id": mail.id,
            "todo_id": todo.id,
            "event_id": event.id,
            "item_id": item.id,
        }


async def test_cos_requires_auth(client):
    r = await client.get("/api/inbox/groups")
    assert r.status_code == 401


async def test_triage_aggregates_user_sources_only(client):
    token_a, user_a = await _new_user(client)
    token_b, user_b = await _new_user(client)
    await _seed_sources(user_a, "alpha")
    await _seed_sources(user_b, "bravo")

    r = await client.get("/api/inbox/groups?days=7", headers=auth(token_a))
    assert r.status_code == 200, r.text
    body = r.json()
    text = str(body)
    assert "alpha" in text
    assert "bravo" not in text

    sources = {item["source"] for group in body["groups"].values() for item in group}
    assert {"mail", "todo", "schedule", "sources"} <= sources
    assert body["counts"]["total"] >= 4


async def test_daily_brief_has_sections_and_summary(client):
    token, user_id = await _new_user(client)
    await _seed_sources(user_id, "brief")

    r = await client.post(
        "/api/skills/daily-brief/run",
        json={"input": {}},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()["output"]
    assert body["summary"]
    keys = {s["key"] for s in body["sections"]}
    assert {"schedule", "todos", "mail", "news"} <= keys
    assert body["stats"]["schedule_count"] >= 1


async def test_meeting_prep_collects_context(client):
    token, user_id = await _new_user(client)
    await _seed_sources(user_id, "prep")

    r = await client.post(
        "/api/skills/meeting-prepare/run",
        json={"input": {"title": "预算评审会", "query": "预算", "attendees": ["张三"]}},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()["output"]
    assert body["agenda"]
    assert any("预算" in (c.get("title") or "") for c in body["context"])
    assert "张三" in str(body)


async def test_weekly_review_uses_daily_insights(client):
    from core.ai.insight_models import DailyInsight
    from core.database.session import async_session

    token, user_id = await _new_user(client)
    async with async_session() as db:
        db.add(DailyInsight(
            user_id=user_id,
            day=date.today() - timedelta(days=1),
            summary="完成了预算评审并同步项目组",
            highlights=["预算评审"],
            patterns=["上午专注度高"],
            suggestions=[{"text": "跟进预算确认", "action": "todo"}],
            stats={"todo_done_count": 2},
            session_ids=[],
        ))
        await db.commit()
    await _seed_sources(user_id, "weekly")

    r = await client.post(
        "/api/skills/weekly-review/run",
        json={"input": {}},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()["output"]
    assert "预算评审" in body["summary"]
    assert body["stats"]["insight_days"] == 1
    assert body["period"]["start"] and body["period"]["end"]


async def test_dingtalk_payload_ignores_sender_objects(client):
    from core.cos.collectors import normalise_dingtalk_payload

    payload = {
        "conversations": [
            {
                "conversationTitle": "项目群",
                "lastMessage": "预算已发，请确认",
                "lastMessageTime": "1762300800000",
                "openConversationId": "cid-1",
                "sender": {"name": "张三"},
            },
            {"sender": {"name": "李四"}},
            {"name": "王五"},
        ]
    }
    items = normalise_dingtalk_payload(payload)
    assert len(items) == 1
    assert items[0]["title"] == "项目群"
    assert items[0]["id"] == "dingtalk:cid-1"
    assert "预算" in items[0]["summary"]
    assert items[0]["time"]


async def test_skill_toggle_disables_run(client):
    token, _ = await _new_user(client)
    bots = (await client.get("/api/bots", headers=auth(token))).json()
    bot_id = next(b for b in bots if b["is_default"])["id"]

    r = await client.get(f"/api/bots/{bot_id}/skills", headers=auth(token))
    assert r.status_code == 200, r.text
    skills = {s["key"]: s for s in r.json()["skills"]}
    assert {"daily-brief", "meeting-prepare", "weekly-review"} <= set(skills)
    assert skills["daily-brief"]["enabled"] is True

    r = await client.put(
        f"/api/bots/{bot_id}/skills/daily-brief",
        json={"enabled": False},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        "/api/skills/daily-brief/run",
        json={"bot_id": bot_id, "input": {}},
        headers=auth(token),
    )
    assert r.status_code == 409, r.text

    r = await client.put(
        f"/api/bots/{bot_id}/skills/daily-brief",
        json={"enabled": True},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text


async def test_mark_all_mail_read(client):
    token, user_id = await _new_user(client)
    await _seed_sources(user_id, "readall")

    r = await client.put(
        "/api/plugins/mail/messages/read-all",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] >= 1

    r = await client.get(
        "/api/plugins/mail/messages?unread=true",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []


async def test_dingtalk_unread_is_cached(monkeypatch):
    import json
    import types

    from core.cos import collectors
    from core.mcp_hub.hub import mcp_hub

    calls = 0

    async def fake_server(user_id):
        return types.SimpleNamespace(id=4242)

    async def fake_call(*args, **kwargs):
        nonlocal calls
        calls += 1
        payload = {
            "data": {
                "conversations": [
                    {
                        "conversationTitle": "项目群",
                        "lastMessage": "下午开会",
                        "openConversationId": "cid-1",
                    }
                ]
            }
        }
        return types.SimpleNamespace(
            isError=False,
            content=[types.SimpleNamespace(text=json.dumps(payload))],
        )

    collectors._DINGTALK_UNREAD_CACHE.clear()
    monkeypatch.setattr(collectors, "_dingtalk_server", fake_server)
    monkeypatch.setattr(mcp_hub, "call_external", fake_call)

    items1, status1 = await collectors.dingtalk_items(1, limit=5)
    items2, status2 = await collectors.dingtalk_items(1, limit=5)

    assert calls == 1
    assert status1 == status2 == "ok"
    assert items1 and items2
    collectors._DINGTALK_UNREAD_CACHE.clear()


async def test_workbench_suggestions_from_user_context(client, monkeypatch):
    token, user_id = await _new_user(client)
    await _seed_sources(user_id, "suggest")

    from core.workbench import suggestions as workbench

    workbench._CACHE.clear()
    monkeypatch.setattr(workbench.settings, "llm_api_key", "")

    r = await client.get("/api/inbox/suggestions", headers=auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["suggestions"]) == 3
    assert all(isinstance(item, str) and item for item in body["suggestions"])
    assert body["source"] == "fallback"
    assert body["expires_at"]


async def test_draft_reply_from_mail(client):
    token, user_id = await _new_user(client)
    ids = await _seed_sources(user_id, "reply")

    r = await client.post(
        f"/api/plugins/mail/messages/{ids['mail_id']}/ai-draft",
        json={"tone": "friendly"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["body"]
    assert body["sent"] is False
    assert body["to"] == "boss@example.com"
    assert body["subject"].startswith("Re:")

    # Cannot draft from another user's message.
    token_b, _ = await _new_user(client)
    r = await client.post(
        f"/api/plugins/mail/messages/{ids['mail_id']}/ai-draft",
        json={},
        headers=auth(token_b),
    )
    assert r.status_code == 404
