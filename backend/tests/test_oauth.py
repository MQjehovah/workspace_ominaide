"""External authorization plugin: account storage and Google tool gating."""

import random
import string

from conftest import auth


async def _new_user(client):
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"conn_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "testpass123",
        },
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "testpass123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def test_oauth_providers_and_config_gate(client):
    token, _ = await _new_user(client)

    r = await client.get("/api/oauth", headers=auth(token))
    assert r.status_code == 200, r.text
    providers = {item["key"]: item for item in r.json()["providers"]}
    assert "google" in providers
    assert providers["google"]["configured"] is False

    r = await client.post(
        "/api/oauth/start",
        json={"provider": "google"},
        headers=auth(token),
    )
    assert r.status_code == 400, r.text


async def test_oauth_account_store_and_disconnect(client):
    token, user_id = await _new_user(client)
    from datetime import datetime, timedelta

    from plugins.oauth.backend import service

    row = await service.save_account(
        user_id,
        "google",
        "google-user-1",
        email="me@example.com",
        name="Me",
        access_token="access",
        refresh_token="refresh",
        scopes=["gmail.readonly"],
        expires_at=datetime.now() + timedelta(hours=1),
    )
    assert row.id

    r = await client.get("/api/oauth", headers=auth(token))
    providers = {item["key"]: item for item in r.json()["providers"]}
    accounts = providers["google"]["accounts"]
    assert accounts and accounts[0]["email"] == "me@example.com"
    assert "access" not in str(accounts)

    r = await client.delete(
        f"/api/oauth/{row.id}", headers=auth(token)
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/oauth", headers=auth(token))
    assert r.json()["providers"][0]["accounts"] == []


async def test_google_tool_requires_account(client):
    token, _ = await _new_user(client)

    r = await client.post(
        "/api/mcp/call",
        json={
            "name": "google_gmail_search",
            "arguments": {"query": "is:unread"},
        },
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["isError"] is True
    assert "还没有连接" in r.json()["content"][0]["text"]
