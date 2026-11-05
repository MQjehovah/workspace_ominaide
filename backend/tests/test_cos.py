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
    """Create one mail, todo, event and RSS entry for a user."""
    from core.database.session import async_session
    from plugins.mail.backend.models import MailAccount, MailMessage
    from plugins.rss.backend.models import Entry, Feed
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
        feed = Feed(user_id=user_id, url=f"https://example.com/{tag}", title="科技资讯")
        db.add_all([mail, todo, event, feed])
        await db.flush()
        entry = Entry(
            feed_id=feed.id, guid=f"{tag}-1", title=f"{tag} 行业动态",
            summary="AI 产品更新", link=f"https://example.com/{tag}/1",
            published=now, read=False,
        )
        db.add(entry)
        await db.commit()
        return {"mail_id": mail.id, "todo_id": todo.id, "event_id": event.id, "entry_id": entry.id}


async def test_cos_requires_auth(client):
    r = await client.get("/api/cos/triage")
    assert r.status_code == 401


async def test_triage_aggregates_user_sources_only(client):
    token_a, user_a = await _new_user(client)
    token_b, user_b = await _new_user(client)
    await _seed_sources(user_a, "alpha")
    await _seed_sources(user_b, "bravo")

    r = await client.get("/api/cos/triage?days=7", headers=auth(token_a))
    assert r.status_code == 200, r.text
    body = r.json()
    text = str(body)
    assert "alpha" in text
    assert "bravo" not in text

    sources = {item["source"] for group in body["groups"].values() for item in group}
    assert {"mail", "todo", "schedule", "rss"} <= sources
    assert body["counts"]["total"] >= 4


async def test_daily_brief_has_sections_and_summary(client):
    token, user_id = await _new_user(client)
    await _seed_sources(user_id, "brief")

    r = await client.get("/api/cos/daily-brief", headers=auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]
    keys = {s["key"] for s in body["sections"]}
    assert {"schedule", "todos", "mail", "news"} <= keys
    assert body["stats"]["schedule_count"] >= 1


async def test_meeting_prep_collects_context(client):
    token, user_id = await _new_user(client)
    await _seed_sources(user_id, "prep")

    r = await client.post(
        "/api/cos/meeting-prep",
        json={"title": "预算评审会", "query": "预算", "attendees": ["张三"]},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
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

    r = await client.get("/api/cos/weekly-review", headers=auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
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


async def test_draft_reply_from_mail(client):
    token, user_id = await _new_user(client)
    ids = await _seed_sources(user_id, "reply")

    r = await client.post(
        "/api/cos/draft-reply",
        json={"source": "mail", "message_id": ids["mail_id"], "tone": "friendly"},
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
        "/api/cos/draft-reply",
        json={"source": "mail", "message_id": ids["mail_id"]},
        headers=auth(token_b),
    )
    assert r.status_code == 404
