"""Daily insight tests: per-day collection, idempotent generation, API and context."""
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from conftest import auth


async def _new_user(client) -> tuple[str, int]:
    """Register and log in a fresh user so tests never share insight rows."""
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"ins_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post(
        "/api/auth/login", json={"username": username, "password": "testpass123"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def _add_activity(user_id: int, day: date, hour: int = 10, event_type: str = "app.used",
                        summary: str = "", details: dict | None = None) -> int:
    from core.database.session import async_session
    from core.activities.models import UserActivity

    async with async_session() as db:
        e = UserActivity(
            user_id=user_id,
            event_type=event_type,
            summary=summary,
            details=details or {},
            created_at=datetime.combine(day, time(hour=hour)),
        )
        db.add(e)
        await db.commit()
        return e.id


async def _add_chat(user_id: int, day: date, session_id: str, role: str, content: str,
                    hour: int = 11) -> int:
    from core.database.session import async_session
    from plugins.chat.backend.models import ChatMessage

    async with async_session() as db:
        m = ChatMessage(
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
            created_at=datetime.combine(day, time(hour=hour)),
        )
        db.add(m)
        await db.commit()
        return m.id


async def _add_done_todo(user_id: int, day: date, title: str) -> int:
    from core.database.session import async_session
    from plugins.todo.backend.models import PluginTodoItem

    async with async_session() as db:
        t = PluginTodoItem(
            user_id=user_id,
            title=title,
            status="done",
            updated_at=datetime.combine(day, time(hour=15)),
        )
        db.add(t)
        await db.commit()
        return t.id


async def _add_event(user_id: int, day: date, title: str, hour: int = 9) -> int:
    from core.database.session import async_session
    from plugins.schedule.backend.models import Event

    async with async_session() as db:
        e = Event(
            user_id=user_id,
            title=title,
            start_time=datetime.combine(day, time(hour=hour)),
            end_time=datetime.combine(day, time(hour=hour + 1)),
        )
        db.add(e)
        await db.commit()
        return e.id


async def test_daily_insight_model_enforces_one_row_per_user_day(client):
    from core.ai.insight_models import DailyInsight
    from core.database.session import async_session

    _, user_id = await _new_user(client)
    day = date(2026, 1, 2)

    kwargs = dict(
        user_id=user_id,
        day=day,
        summary="测试回顾",
        highlights=[],
        patterns=[],
        suggestions=[],
        stats={},
        session_ids=[],
    )
    async with async_session() as db:
        db.add(DailyInsight(**kwargs))
        await db.commit()

    async with async_session() as db:
        db.add(DailyInsight(**kwargs))
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_collect_day_data_is_scoped_to_user_and_day(client):
    from core.ai.daily_insights import collect_day_data

    _, user_a = await _new_user(client)
    _, user_b = await _new_user(client)
    day = date(2026, 2, 3)
    other_day = day - timedelta(days=1)

    await _add_activity(user_a, day, event_type="app.used", details={"app": "VS Code", "minutes": 30})
    await _add_activity(user_a, day, hour=14, event_type="file.uploaded", summary="上传预算.xlsx")
    await _add_activity(user_a, day, event_type="sources.item.new", summary="AI 行业周报",
                        details={"title": "AI 行业周报", "url": "https://example.com/a"})
    await _add_activity(user_a, day, event_type="sources.refreshed", summary="资讯源刷新",
                        details={"source": "科技资讯", "new_items": 3})
    await _add_activity(user_a, other_day, event_type="app.used", details={"app": "Chrome", "minutes": 60})
    await _add_activity(user_b, day, event_type="app.used", details={"app": "Slack", "minutes": 20})

    await _add_chat(user_a, day, "s1", "user", "帮我整理预算")
    await _add_chat(user_a, day, "s1", "assistant", "已整理并生成摘要")
    await _add_chat(user_a, other_day, "s2", "user", "昨天的问题")
    await _add_chat(user_b, day, "bx", "user", "别人的会话")

    await _add_done_todo(user_a, day, "提交预算")
    await _add_event(user_a, day, "周会", hour=9)

    data = await collect_day_data(user_a, day)

    assert data["day"] == day.isoformat()
    assert data["stats"]["activity_count"] == 2
    assert data["stats"]["chat_message_count"] == 2
    assert data["stats"]["todo_done_count"] == 1
    assert data["stats"]["schedule_count"] == 1
    assert data["stats"]["top_apps"][0] == {"app": "VS Code", "minutes": 30}
    assert data["session_ids"] == ["s1"]
    assert data["todos_done"] == ["提交预算"]
    assert data["schedule"][0]["title"] == "周会"
    assert "VS Code" in data["digest"]
    assert "预算" in data["digest"]
    assert "AI 行业周报" not in data["digest"]
    assert "科技资讯" not in data["digest"]
    assert "别人的会话" not in data["digest"]


async def test_generate_daily_insight_is_idempotent_and_falls_back_without_llm(client):
    from core.ai.daily_insights import generate_daily_insight
    from core.database.session import async_session
    from sqlalchemy import func, select

    token, user_id = await _new_user(client)
    day = date(2026, 3, 4)
    await _add_activity(user_id, day, details={"app": "VS Code", "minutes": 45})
    await _add_chat(user_id, day, "s1", "user", "帮我把周报写完")

    first = await generate_daily_insight(user_id, day)
    assert first is not None
    assert first.summary
    assert first.stats["activity_count"] == 1

    second = await generate_daily_insight(user_id, day)
    assert second is not None
    assert second.id == first.id

    async with async_session() as db:
        count = (await db.execute(
            select(func.count()).select_from(type(first)).where(
                type(first).user_id == user_id, type(first).day == day
            )
        )).scalar()
    assert count == 1


async def test_generate_daily_insight_returns_none_without_data(client):
    from core.ai.daily_insights import generate_daily_insight

    _, user_id = await _new_user(client)
    result = await generate_daily_insight(user_id, date(2020, 1, 1))
    assert result is None


async def test_insights_api_requires_auth_and_scopes_to_user(client):
    from core.ai.daily_insights import generate_daily_insight

    token_a, user_a = await _new_user(client)
    token_b, _ = await _new_user(client)
    day = date(2026, 4, 5)
    await _add_activity(user_a, day, summary="今天完成了方案")

    assert (await client.get("/api/insights/daily")).status_code == 401

    r = await client.post(
        "/api/insights/daily/run", json={"day": day.isoformat()}, headers=auth(token_a)
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/insights/daily?days=7", headers=auth(token_a))
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1
    assert items[0]["day"] == day.isoformat()

    # Another user sees nothing and cannot read the row by date.
    r = await client.get("/api/insights/daily?days=7", headers=auth(token_b))
    assert r.status_code == 200
    assert r.json() == []
    r = await client.get(f"/api/insights/daily/{day.isoformat()}", headers=auth(token_b))
    assert r.status_code == 404


async def test_ensure_daily_insight_backfills_yesterday(client):
    from core.ai.daily_insights import ensure_daily_insight

    _, user_id = await _new_user(client)
    yesterday = date.today() - timedelta(days=1)
    await _add_activity(user_id, yesterday, summary="昨天完成的事情")

    row = await ensure_daily_insight(user_id, yesterday)
    assert row is not None
    assert row.day == yesterday
    # Second call reuses the row.
    again = await ensure_daily_insight(user_id, yesterday)
    assert again is not None and again.id == row.id


async def test_bot_context_includes_recent_daily_review(client):
    from core.ai.daily_insights import generate_daily_insight
    from core.bots.memory import build_bot_context

    _, user_id = await _new_user(client)
    day = date.today()
    await _add_activity(user_id, day, summary="完成了知识库检索优化")
    await generate_daily_insight(user_id, day)

    context = await build_bot_context(user_id)
    assert context
    assert "昨日回顾" in context or "今日回顾" in context
    assert "知识库检索优化" in context



