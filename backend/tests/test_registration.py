"""Registration mode and admin-created users."""

import random
import string

from conftest import auth


def _suffix():
    return "".join(random.choices(string.ascii_lowercase, k=8))


async def test_public_registration_is_closed(client, monkeypatch):
    from core.config.settings import settings

    monkeypatch.setattr(settings, "allow_registration", False)
    suffix = _suffix()
    r = await client.post(
        "/api/auth/register",
        json={
            "username": f"closed_{suffix}",
            "email": f"closed_{suffix}@example.com",
            "password": "testpass123",
        },
    )
    assert r.status_code == 403


async def test_admin_can_create_user(client, admin_token):
    suffix = _suffix()
    r = await client.post(
        "/api/auth/users",
        json={
            "username": f"created_{suffix}",
            "email": f"created_{suffix}@example.com",
            "password": "testpass123",
        },
        headers=auth(admin_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["username"] == f"created_{suffix}"
    assert r.json()["is_admin"] is False


async def test_non_admin_cannot_create_user(client, user_token):
    suffix = _suffix()
    r = await client.post(
        "/api/auth/users",
        json={
            "username": f"nope_{suffix}",
            "email": f"nope_{suffix}@example.com",
            "password": "testpass123",
        },
        headers=auth(user_token),
    )
    assert r.status_code == 403


async def test_refresh_rejects_disabled_user(client, admin_token):
    suffix = _suffix()
    username = f"refresh_{suffix}"
    r = await client.post(
        "/api/auth/users",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "testpass123",
        },
        headers=auth(admin_token),
    )
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]

    r = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "testpass123"},
    )
    assert r.status_code == 200, r.text
    refresh = r.json()["refresh_token"]

    r = await client.put(
        f"/api/auth/users/{user_id}/toggle-active",
        json={"is_active": False},
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text

    r = await client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401
