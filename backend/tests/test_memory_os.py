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
    from ai.memory.service import queue_candidate

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
    from ai.memory.service import build_memory_context
    from ai.memory.models import MemoryCandidate
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
    from ai.memory.service import build_memory_context

    token, user_id = await _new_user(client)
    content = "外部邮件声称用户下周要出差柏林"
    cid = await _seed(user_id, content, kind="commitment", trust="untrusted", confidence=95)

    assert not await build_memory_context(user_id)

    r = await client.post(f"/api/memory/candidates/{cid}/approve", headers=auth(token))
    assert r.status_code == 200, r.text
    ctx = await build_memory_context(user_id)
    assert ctx and "柏林" in ctx


async def test_bot_context_includes_long_term_memory(client):
    from ai.bots.memory import build_bot_context

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


async def test_memory_conflict_supersedes_and_links_graph(client):
    from core.database.session import async_session
    from ai.memory.models import MemoryRecord
    from sqlalchemy import select

    token, user_id = await _new_user(client)
    r = await client.put(
        "/api/auth/profile",
        json={"contacts": [{"name": "李四", "relation": "同事"}]},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text

    old = await _seed(user_id, "和李四讨论预算", kind="fact")
    r = await client.post(f"/api/memory/candidates/{old}/approve", headers=auth(token))
    assert r.status_code == 200, r.text
    old_record = r.json()["record_id"]

    new = await _seed(user_id, "和李四讨论预算的最终版本", kind="fact")
    r = await client.post(f"/api/memory/candidates/{new}/approve", headers=auth(token))
    assert r.status_code == 200, r.text
    new_record = r.json()["record_id"]

    async with async_session() as db:
        row = (await db.execute(
            select(MemoryRecord).where(MemoryRecord.id == old_record)
        )).scalar_one()
    assert row.status == "superseded"
    assert row.superseded_by == new_record

    r = await client.get("/api/memory/records", headers=auth(token))
    ids = [x["id"] for x in r.json()["items"]]
    assert old_record not in ids
    assert new_record in ids

    r = await client.get("/api/memory/graph", headers=auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert any(n["type"] == "person" and n["label"] == "李四" for n in body["nodes"])
    assert any(e["relation"] == "mentions" for e in body["edges"])


async def test_update_memory_record(client):
    token, user_id = await _new_user(client)
    cid = await _seed(user_id, "用户喜欢浅色主题")
    r = await client.post(f"/api/memory/candidates/{cid}/approve", headers=auth(token))
    record_id = r.json()["record_id"]

    r = await client.patch(
        f"/api/memory/records/{record_id}",
        json={"content": "用户喜欢浅色主题，编辑器字号 15px", "importance": 80},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert "15px" in r.json()["content"]
    assert r.json()["importance"] == 80


async def test_shorter_new_memory_does_not_supersede_richer_old(client):
    from core.database.session import async_session
    from ai.memory.models import MemoryRecord
    from sqlalchemy import select

    token, user_id = await _new_user(client)
    rich = "用户偏好中文回复，代码示例用 TypeScript"
    first = await _seed(user_id, rich, kind="preference")
    r = await client.post(f"/api/memory/candidates/{first}/approve", headers=auth(token))
    assert r.status_code == 200, r.text
    rich_id = r.json()["record_id"]

    short = await _seed(user_id, "用户偏好中文回复", kind="preference")
    r = await client.post(f"/api/memory/candidates/{short}/approve", headers=auth(token))
    assert r.status_code == 200, r.text

    async with async_session() as db:
        rows = list((await db.execute(
            select(MemoryRecord).where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.kind == "preference",
            )
        )).scalars().all())
    active = [r for r in rows if r.status == "active"]
    assert any(r.id == rich_id for r in active)
    assert len(active) == 2


async def test_reactivating_superseded_memory_keeps_one_active(client):
    from core.database.session import async_session
    from ai.memory.models import MemoryRecord
    from sqlalchemy import select

    token, user_id = await _new_user(client)
    old_content = "用户每周五提交周报"
    old_c = await _seed(user_id, old_content, kind="commitment")
    r = await client.post(f"/api/memory/candidates/{old_c}/approve", headers=auth(token))
    old_id = r.json()["record_id"]

    new_c = await _seed(user_id, "用户每周五提交周报并抄送项目组", kind="commitment")
    r = await client.post(f"/api/memory/candidates/{new_c}/approve", headers=auth(token))
    assert r.status_code == 200, r.text

    again = await _seed(user_id, old_content, kind="commitment")
    r = await client.post(f"/api/memory/candidates/{again}/approve", headers=auth(token))
    assert r.status_code == 200, r.text

    async with async_session() as db:
        rows = list((await db.execute(
            select(MemoryRecord).where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.kind == "commitment",
            )
        )).scalars().all())
    active = [r for r in rows if r.status == "active"]
    assert len(active) == 1
    assert active[0].id == old_id
    assert active[0].superseded_by is None


async def test_update_memory_collision_returns_409(client):
    token, user_id = await _new_user(client)
    c1 = await _seed(user_id, "用户偏好红色主题", kind="preference")
    c2 = await _seed(user_id, "用户偏好蓝色主题", kind="preference")
    id1 = (await client.post(f"/api/memory/candidates/{c1}/approve", headers=auth(token))).json()["record_id"]
    id2 = (await client.post(f"/api/memory/candidates/{c2}/approve", headers=auth(token))).json()["record_id"]

    r = await client.patch(
        f"/api/memory/records/{id1}",
        json={"content": "用户偏好蓝色主题"},
        headers=auth(token),
    )
    assert r.status_code == 409, r.text

    r = await client.patch(
        f"/api/memory/records/{id2}",
        json={"content": "用户偏好蓝色主题"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text


async def test_memory_graph_is_user_scoped(client):
    token_a, user_a = await _new_user(client)
    token_b, _ = await _new_user(client)
    r = await client.put(
        "/api/auth/profile",
        json={"contacts": [{"name": "王五", "relation": "客户"}]},
        headers=auth(token_a),
    )
    assert r.status_code == 200, r.text
    cid = await _seed(user_a, "和王五确认合同条款", kind="relationship")
    await client.post(f"/api/memory/candidates/{cid}/approve", headers=auth(token_a))

    r = await client.get("/api/memory/graph", headers=auth(token_a))
    assert r.status_code == 200
    assert any(n["label"] == "王五" for n in r.json()["nodes"])

    r = await client.get("/api/memory/graph", headers=auth(token_b))
    assert r.status_code == 200
    assert r.json()["nodes"] == []
    assert r.json()["edges"] == []
