"""Information source tests: providers, digest, scoping and scheduled refresh."""
from datetime import datetime, timedelta

import pytest

from conftest import auth


async def _new_user(client) -> tuple[str, int]:
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"src_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def _add_source_and_items(user_id: int, count: int = 3) -> int:
    from core.database.session import async_session
    from plugins.sources.backend.models import ContentItem, ContentSource

    async with async_session() as db:
        source = ContentSource(
            user_id=user_id,
            provider="rss",
            url="https://example.com/rss",
            title="科技日报",
        )
        db.add(source)
        await db.flush()
        for i in range(count):
            db.add(ContentItem(
                source_id=source.id,
                guid=f"g{i}",
                title=f"文章 {i}: AI 进展",
                link=f"https://example.com/{i}",
                summary=f"摘要 {i}",
                content=f"正文 {i}",
                published=datetime.utcnow() - timedelta(hours=i + 1),
                created_at=datetime.utcnow() - timedelta(hours=i + 1),
            ))
        await db.commit()
        return source.id


def test_github_trending_provider_builds_rsshub_url(monkeypatch):
    from core.config.settings import settings
    from plugins.sources.backend.providers import get_provider

    monkeypatch.setattr(settings, "rsshub_base_url", "https://rsshub.test/")
    url, title = get_provider("github_trending").build(
        {"since": "weekly", "language": "python"}
    )
    assert url == "https://rsshub.test/github/trending/weekly/python"
    assert "本周" in title and "Python" in title


def test_github_trending_requires_rsshub(monkeypatch):
    from core.config.settings import settings
    from plugins.sources.backend.providers import ProviderError, get_provider

    monkeypatch.setattr(settings, "rsshub_base_url", "")
    with pytest.raises(ProviderError):
        get_provider("github_trending").build({"since": "daily", "language": "any"})


async def test_providers_endpoint_and_github_source_creation(client, monkeypatch):
    from core.config.settings import settings

    monkeypatch.setattr(settings, "rsshub_base_url", "https://rsshub.test")
    token, _ = await _new_user(client)

    r = await client.get("/api/sources/providers", headers=auth(token))
    assert r.status_code == 200, r.text
    keys = {item["key"] for item in r.json()}
    assert {"rss", "github_trending"} <= keys

    r = await client.post(
        "/api/sources",
        json={
            "provider": "github_trending",
            "config": {"since": "daily", "language": "typescript"},
        },
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["provider"] == "github_trending"
    assert body["url"] == "https://rsshub.test/github/trending/daily/typescript"


async def test_sources_digest_uses_backend_data_and_falls_back_without_llm(client):
    from plugins.sources.backend.digest import build_digest, generate_sources_digest

    _, user_id = await _new_user(client)
    await _add_source_and_items(user_id, 3)

    digest = await build_digest(user_id, hours=24)
    assert digest["count"] == 3
    assert digest["items"][0]["source"] == "科技日报"

    generated = await generate_sources_digest(user_id, notify=False)
    assert generated is not None
    assert generated["summary"]
    assert "AI 进展" in generated["summary"]


async def test_sources_digest_api_is_scoped(client):
    token_a, user_a = await _new_user(client)
    token_b, _ = await _new_user(client)
    await _add_source_and_items(user_a, 2)

    assert (await client.get("/api/sources/digest")).status_code == 401

    r = await client.get("/api/sources/digest", headers=auth(token_a))
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 2

    r = await client.get("/api/sources/digest", headers=auth(token_b))
    assert r.status_code == 200
    assert r.json()["count"] == 0


async def test_scheduled_source_refresh_calls_fetch_for_stale_sources(client, monkeypatch):
    from plugins.sources.backend.jobs import refresh_due_sources_job
    from core.database.session import async_session
    from plugins.sources.backend.models import ContentSource
    from plugins.sources.backend import service as sources_service

    _, user_id = await _new_user(client)
    source_id = await _add_source_and_items(user_id, 1)

    async with async_session() as db:
        source = await db.get(ContentSource, source_id)
        source.last_fetch = datetime.utcnow() - timedelta(days=1)
        await db.commit()

    called: list[int] = []

    async def fake_fetch(db, source):
        called.append(source.id)
        return 1

    monkeypatch.setattr(sources_service, "fetch_source_content", fake_fetch)
    await refresh_due_sources_job()
    assert source_id in called


async def test_mark_all_source_items_read(client):
    token, user_id = await _new_user(client)
    await _add_source_and_items(user_id, count=3)

    r = await client.put(
        "/api/sources/items/read-all", headers=auth(token), json={}
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 3

    r = await client.get(
        "/api/sources/items?page_size=10", headers=auth(token)
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 3
    assert all(item["read"] is True for item in items)
