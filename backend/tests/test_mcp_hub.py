"""Unified MCP hub: CRUD, discovery, namespacing, policy and audit."""
import sys
from pathlib import Path

from conftest import auth

FAKE = str(Path(__file__).parent / "fake_mcp_server.py")


async def _new_user(client) -> tuple[str, int]:
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"mcp_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def _make_admin(user_id: int) -> None:
    """Only admins may register stdio MCP servers (arbitrary command execution)."""
    from sqlalchemy import select

    from core.auth.domain.models import User
    from core.database.session import async_session

    async with async_session() as db:
        row = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
        row.is_admin = True
        await db.commit()


async def _add_fake(client, token: str, slug: str) -> dict:
    r = await client.post(
        "/api/mcp/servers",
        json={
            "name": "Fake MCP",
            "slug": slug,
            "transport": "stdio",
            "command": sys.executable,
            "args": [FAKE],
            "enabled": True,
            "auto_start": True,
            "risk_default": "read",
        },
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_mcp_hub_discovers_namespaces_and_calls(client):
    token, user_id = await _new_user(client)
    await _make_admin(user_id)
    server = await _add_fake(client, token, "fake")

    r = await client.get("/api/mcp/servers", headers=auth(token))
    assert r.status_code == 200, r.text
    row = next(s for s in r.json()["servers"] if s["id"] == server["id"])
    assert row["last_status"] == "connected"
    assert row["tools_count"] == 2

    r = await client.get("/api/mcp/tools", headers=auth(token))
    assert r.status_code == 200, r.text
    tools = {t["name"]: t for t in r.json()["tools"]}
    assert "fake__echo" in tools
    assert tools["fake__echo"]["source"] == "mcp"
    assert tools["fake__echo"]["server"] == "fake"

    r = await client.post(
        "/api/mcp/call",
        json={"name": "fake__echo", "arguments": {"text": "hello"}},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert "echo:hello" in r.json()["content"][0]["text"]
    assert r.json()["isError"] is False

    r = await client.get("/api/mcp/calls", headers=auth(token))
    assert r.status_code == 200, r.text
    calls = r.json()["calls"]
    assert calls and calls[0]["tool_name"] == "fake__echo"
    assert calls[0]["status"] == "ok"


async def test_disabling_server_removes_tools(client):
    token, user_id = await _new_user(client)
    await _make_admin(user_id)
    server = await _add_fake(client, token, "fake2")

    r = await client.patch(
        f"/api/mcp/servers/{server['id']}", json={"enabled": False}, headers=auth(token)
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/mcp/tools", headers=auth(token))
    names = {t["name"] for t in r.json()["tools"]}
    assert "fake2__echo" not in names

    r = await client.post(
        "/api/mcp/call", json={"name": "fake2__echo", "arguments": {"text": "x"}},
        headers=auth(token),
    )
    assert r.status_code == 200
    assert r.json()["isError"] is True


async def test_mcp_servers_are_user_scoped(client):
    token_a, user_a = await _new_user(client)
    await _make_admin(user_a)
    token_b, _ = await _new_user(client)
    await _add_fake(client, token_a, "fake3")

    r = await client.get("/api/mcp/tools", headers=auth(token_b))
    names = {t["name"] for t in r.json()["tools"]}
    assert "fake3__echo" not in names

    r = await client.post(
        "/api/mcp/call", json={"name": "fake3__echo", "arguments": {"text": "x"}},
        headers=auth(token_b),
    )
    assert r.status_code == 200
    assert r.json()["isError"] is True


async def test_mcp_templates_are_available(client):
    token, _ = await _new_user(client)
    r = await client.get("/api/mcp/templates", headers=auth(token))
    assert r.status_code == 200, r.text
    keys = {t["key"] for t in r.json()["templates"]}
    assert {"home-assistant", "playwright"} <= keys
    assert "dingtalk" not in keys
