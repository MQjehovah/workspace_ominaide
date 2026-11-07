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


async def test_vibecoding_devices_endpoint_lists_empty_when_offline(client):
    token = await _new_user(client)
    r = await client.get("/api/vibecoding/devices", headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json() == []
