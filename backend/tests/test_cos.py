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


async def test_dingtalk_items_read_synced_conversations(client):
    token, user_id = await _new_user(client)
    from core.database.session import async_session
    from core.events.models import UserActivity
    from core.cos import collectors

    async with async_session() as db:
        db.add(UserActivity(
            user_id=user_id,
            event_type="dingtalk.conversation",
            entity_type="dingtalk",
            summary="项目群",
            details={
                "conversation": "项目群",
                "conversation_id": "cid-1",
                "day": "2026-11-08",
                "message_count": 2,
                "content": "张三: 预算已发，请确认\n李四: 下午开会",
            },
        ))
        await db.commit()

    items, status = await collectors.dingtalk_items(user_id, limit=5)
    assert status == "cached"
    assert items and items[0]["title"] == "项目群"
    assert items[0]["id"] == "dingtalk:cid-1"
    assert "预算" in items[0]["summary"]

    hits, _ = await collectors.dingtalk_items(user_id, query="开会", limit=5)
    assert hits and "开会" in hits[0]["summary"]


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


async def test_dingtalk_items_never_calls_the_cli(monkeypatch):
    """Workbench reads must not shell out to dws; the scheduler owns syncing."""
    from core.cos import collectors
    from core.mcp_hub.hub import mcp_hub

    async def fail(*args, **kwargs):
        raise AssertionError("dingtalk collector must not call MCP/dws")

    monkeypatch.setattr(mcp_hub, "call_external", fail)
    items, status = await collectors.dingtalk_items(999999, limit=5)
    assert items == []
    assert status == "empty"


async def test_daily_brief_is_served_from_hourly_cache(client, monkeypatch):
    token, user_id = await _new_user(client)
    await _seed_sources(user_id, "briefcache")

    from core.cos import service as cos_service

    calls = 0
    original = cos_service.daily_brief

    async def counting(*args, **kwargs):
        nonlocal calls
        calls += 1
        return await original(*args, **kwargs)

    monkeypatch.setattr(cos_service, "daily_brief", counting)

    r = await client.post(
        "/api/skills/daily-brief/run",
        json={"input": {}},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    first = r.json()["output"]

    r = await client.post(
        "/api/skills/daily-brief/run",
        json={"input": {}},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["output"] == first
    assert calls == 1

    # An explicit refresh bypasses the hourly snapshot.
    r = await client.post(
        "/api/skills/daily-brief/run",
        json={"input": {"refresh": True}},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert calls == 2


async def test_weekly_review_is_persisted(client):
    token, user_id = await _new_user(client)
    await _seed_sources(user_id, "weeklystore")

    r = await client.post(
        "/api/insights/weekly/run",
        json={"force": True, "notify": False},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"]
    assert data["period"]["start"] and data["period"]["end"]

    r = await client.get("/api/insights/weekly/latest", headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["id"] == data["id"]

    # Without force the stored row is reused instead of calling the LLM again.
    r = await client.post(
        "/api/insights/weekly/run",
        json={"force": False, "notify": False},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == data["id"]


async def test_daily_review_skill_persists(client):
    token, user_id = await _new_user(client)
    await _seed_sources(user_id, "dailyreview")

    r = await client.post(
        "/api/skills/daily-review/run",
        json={"input": {"force": True, "notify": False}},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    output = r.json()["output"]
    assert output["summary"]

    r = await client.get("/api/insights/latest", headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["summary"] == output["summary"]


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


async def test_workbench_summary_aggregates_sections(client, monkeypatch):
    token, user_id = await _new_user(client)
    await _seed_sources(user_id, "summary")

    from core.workbench import suggestions as workbench

    workbench._CACHE.clear()
    monkeypatch.setattr(workbench.settings, "llm_api_key", "")

    r = await client.get("/api/workbench/summary", headers=auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["events"]
    assert body["todos"]
    assert isinstance(body["recent"]["files"], list)
    assert isinstance(body["recent"]["notes"], list)
    assert body["inbox"]["pending"] >= 1


async def test_send_mail_saves_to_sent(client, monkeypatch):
    token, user_id = await _new_user(client)
    await _seed_sources(user_id, "sender")

    from plugins.mail.backend import send as mail_send

    monkeypatch.setattr(
        mail_send,
        "_smtp_send",
        lambda *args, **kwargs: "<test-message@example.com>",
    )

    r = await client.post(
        "/api/plugins/mail/messages/send",
        json={
            "to": ["boss@example.com"],
            "subject": "预算确认",
            "body": "预算方案已确认。",
        },
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["message_id"] == "<test-message@example.com>"

    r = await client.get(
        "/api/plugins/mail/messages?folder=sent",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["subject"] == "预算确认"
    assert items[0]["folder"] == "sent"
    assert items[0]["direction"] == "outbound"


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
