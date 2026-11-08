"""Regression coverage for profile + connected devices endpoints."""

import random
import string

from conftest import auth


async def _new_user(client):
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"device_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "testpass123",
        },
    )
    assert r.status_code in (200, 201), r.text
    r = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "testpass123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def test_profile_endpoint_returns_200(client):
    token = await _new_user(client)
    r = await client.get("/api/auth/profile", headers=auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"]
    assert "name" in body


async def test_me_exposes_admin_flag(client):
    token = await _new_user(client)
    r = await client.get("/api/auth/me", headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["is_admin"] is False


async def test_vibecoding_machines_endpoint_lists_empty_when_offline(client):
    token = await _new_user(client)
    r = await client.get("/api/vibecoding/machines", headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json() == []


async def test_machine_rename_persists(client):
    from core.auth.jwt import decode_access_token
    from core.wschannel import machines as machine_service

    token = await _new_user(client)
    user_id = int(decode_access_token(token)["sub"])

    display = await machine_service.register(
        user_id, "machine-test-1", "mac-mini.local"
    )
    assert display == "mac-mini.local"

    r = await client.get("/api/vibecoding/machines", headers=auth(token))
    assert r.status_code == 200, r.text
    first = next(
        item for item in r.json() if item["machine_id"] == "machine-test-1"
    )
    assert first["name"] == "mac-mini.local"
    assert first["default_name"] == "mac-mini.local"
    assert first["online"] is False

    r = await client.put(
        "/api/vibecoding/machines/machine-test-1",
        json={"name": "Mac mini"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Mac mini"

    r = await client.get("/api/vibecoding/machines", headers=auth(token))
    custom = next(
        item for item in r.json() if item["machine_id"] == "machine-test-1"
    )
    assert custom["name"] == "Mac mini"
    assert custom["default_name"] == "mac-mini.local"

    # Empty name restores the hostname-derived default.
    r = await client.put(
        "/api/vibecoding/machines/machine-test-1",
        json={"name": ""},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "mac-mini.local"
