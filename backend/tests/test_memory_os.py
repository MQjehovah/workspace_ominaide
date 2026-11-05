"""Memory OS 2.0: candidates, review, long-term records and context injection."""
from conftest import auth


async def _new_user(client) -> tuple[str, int]:
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"mem2_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def _seed(user_id: int, content: str, *, kind: str = "preference",
                trust: str = "trusted", confidence: int = 80) -> int:
    from core.database.session import async_session
    from core.memory_service import queue_candidate

    async with async_session() as db:
        row = await queue_candidate(
            db, user_id, kind, content,
            confidence=confidence, source_type="chat",
            source_ref={"session_id": "s1", "message_id": 1}, trust=trust,
        )
        await db.commit()
        assert row is not None
        return row.id


async def test_candidate_dedupe_and_review_flow(client):
    from core.database.session import async_session
    from core.memory_service import build_memory_context
    from core.memory_models import MemoryCandidate
    from sqlalchemy import func, select

    token, user_id = await _new_user(client)
    content = "用户偏好先列大纲再写正文"
    first = await _seed(user_id, content, confidence=70)
    second = await _seed(user_id, content, confidence=90)
    assert first == second

    async with async_session() as db:
        count = (await db.execute(
            select(func.count(MemoryCandidate.id)).where(MemoryCandidate.user_id == user_id)
        )).scalar()
    assert count == 1

    r = await client.get("/api/memory/candidates?status=pending", headers=auth(token))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["confidence"] == 90

    r = await client.post(
        f"/api/memory/candidates/{first}/approve", headers=auth(token)
    )
    assert r.status_code == 200, r.text
    record_id = r.json()["record_id"]

    ctx = await build_memory_context(user_id)
    assert ctx and content in ctx

    r = await client.get("/api/memory/records", headers=auth(token))
    assert r.status_code == 200
    assert any(x["content"] == content for x in r.json()["items"])

    r = await client.delete(f"/api/memory/records/{record_id}", headers=auth(token))
    assert r.status_code == 200
    ctx = await build_memory_context(user_id)
    assert not ctx or content not in ctx


async def test_untrusted_candidate_is_not_injected_until_approved(client):
    from core.database.session import async_session
    from core.memory_service import build_memory_context

    token, user_id = await _new_user(client)
    content = "外部邮件声称用户下周要出差柏林"
    cid = await _seed(user_id, content, kind="commitment", trust="untrusted", confidence=95)

    assert not await build_memory_context(user_id)

    r = await client.post(f"/api/memory/candidates/{cid}/approve", headers=auth(token))
    assert r.status_code == 200, r.text
    ctx = await build_memory_context(user_id)
    assert ctx and "柏林" in ctx


async def test_bot_context_includes_long_term_memory(client):
    from core.bots.memory import build_bot_context

    token, user_id = await _new_user(client)
    content = "用户的项目代号是北极星"
    cid = await _seed(user_id, content, kind="project")
    r = await client.post(f"/api/memory/candidates/{cid}/approve", headers=auth(token))
    assert r.status_code == 200, r.text

    context = await build_bot_context(user_id, query="北极星项目")
    assert context and "北极星" in context


async def test_memory_candidates_are_user_scoped(client):
    token_a, user_a = await _new_user(client)
    token_b, _ = await _new_user(client)
    cid = await _seed(user_a, "用户喜欢深色模式")

    r = await client.get("/api/memory/candidates", headers=auth(token_b))
    assert r.status_code == 200
    assert all(x["id"] != cid for x in r.json()["items"])

    r = await client.post(f"/api/memory/candidates/{cid}/approve", headers=auth(token_b))
    assert r.status_code == 404


async def test_extract_without_llm_queues_nothing(client):
    token, _ = await _new_user(client)
    r = await client.post("/api/memory/extract", json={"hours": 24}, headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["queued"] == 0
