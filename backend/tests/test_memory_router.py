"""Memory/profile API tests (SQLite path returns an empty entity graph)."""
from conftest import auth


async def _new_user(client) -> tuple[str, int]:
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"mem_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def test_memory_profile_returns_learned_preferences(client):
    token, user_id = await _new_user(client)
    assert (await client.get("/api/memory/profile")).status_code == 401

    r = await client.put(
        "/api/auth/profile",
        json={
            "name": "张三",
            "role": "技术负责人",
            "company": "示例公司",
            "contacts": [{"name": "李四", "relation": "同事"}],
            "projects": [{"name": "Q3 项目", "deadline": "2026-12-31"}],
        },
        headers=auth(token),
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/memory/profile", headers=auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == user_id
    assert body["name"] == "张三"
    assert body["role"] == "技术负责人"
    assert body["contacts"][0]["name"] == "李四"
    assert body["projects"][0]["name"] == "Q3 项目"
    assert isinstance(body["preferences"], dict)


async def test_entity_graph_degrades_gracefully_on_sqlite(client):
    token, _ = await _new_user(client)
    r = await client.get("/api/memory/entities", headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []
    assert r.json()["supported"] is False

    r = await client.delete("/api/memory/entities/ent_x_1", headers=auth(token))
    assert r.status_code == 404
