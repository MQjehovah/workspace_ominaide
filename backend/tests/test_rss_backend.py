"""Backend-first RSS tests: digest generation, scoping and scheduled refresh."""
from datetime import datetime, timedelta

from conftest import auth


async def _new_user(client) -> tuple[str, int]:
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"rss_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def _add_feed_and_entries(user_id: int, count: int = 3) -> int:
    from core.database.session import async_session
    from plugins.rss.backend.models import Entry, Feed

    async with async_session() as db:
        feed = Feed(user_id=user_id, url="https://example.com/rss", title="科技日报")
        db.add(feed)
        await db.flush()
        for i in range(count):
            db.add(Entry(
                feed_id=feed.id,
                guid=f"g{i}",
                title=f"文章 {i}: AI 进展",
                link=f"https://example.com/{i}",
                summary=f"摘要 {i}",
                content=f"正文 {i}",
                published=datetime.utcnow() - timedelta(hours=i + 1),
                created_at=datetime.utcnow() - timedelta(hours=i + 1),
            ))
        await db.commit()
        return feed.id


async def test_rss_digest_uses_backend_data_and_falls_back_without_llm(client):
    from plugins.rss.backend.digest import build_digest, generate_rss_digest

    _, user_id = await _new_user(client)
    await _add_feed_and_entries(user_id, 3)

    digest = await build_digest(user_id, hours=24)
    assert digest["count"] == 3
    assert digest["items"][0]["feed"] == "科技日报"

    generated = await generate_rss_digest(user_id, notify=False)
    assert generated is not None
    assert generated["summary"]
    assert "AI 进展" in generated["summary"]


async def test_rss_digest_api_is_scoped(client):
    token_a, user_a = await _new_user(client)
    token_b, _ = await _new_user(client)
    await _add_feed_and_entries(user_a, 2)

    assert (await client.get("/api/rss/digest")).status_code == 401

    r = await client.get("/api/rss/digest", headers=auth(token_a))
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 2

    r = await client.get("/api/rss/digest", headers=auth(token_b))
    assert r.status_code == 200
    assert r.json()["count"] == 0


async def test_scheduled_rss_refresh_calls_fetch_for_stale_feeds(client, monkeypatch):
    from core.ai import scheduler
    from core.database.session import async_session
    from plugins.rss.backend.models import Feed
    from plugins.rss.backend import service as rss_service

    _, user_id = await _new_user(client)
    feed_id = await _add_feed_and_entries(user_id, 1)

    # Make the feed stale and record the refresh call.
    async with async_session() as db:
        feed = await db.get(Feed, feed_id)
        feed.last_fetch = datetime.utcnow() - timedelta(days=1)
        await db.commit()

    called: list[int] = []

    async def fake_fetch(db, feed):
        called.append(feed.id)
        return 1

    monkeypatch.setattr(rss_service, "fetch_feed_content", fake_fetch)
    await scheduler._refresh_rss()
    assert feed_id in called
