"""Sync event wiring and single-route registration."""
from collections import Counter

from conftest import auth


async def _new_user(client) -> tuple[str, int]:
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"synevt_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def test_file_change_publishes_sync_event(client):
    token, _ = await _new_user(client)

    r = await client.post(
        "/api/sync/folders",
        json={"server_path": "/", "local_path": "C:/tmp/omniaide-sync-test"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    folder_id = r.json()["id"]

    r = await client.post(
        "/api/files/folder",
        json={"name": "同步测试目录", "parent_path": "/"},
        headers=auth(token),
    )
    assert r.status_code in (200, 201), r.text

    r = await client.get(
        f"/api/sync/events?sync_folder_id={folder_id}", headers=auth(token)
    )
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    assert any(
        e["event_type"] == "created" and e["file_path"] == "/同步测试目录"
        for e in events
    )


async def test_manifest_plugins_are_mounted_once(client):
    import main

    await client.get("/health")
    keys = [
        (route.path, tuple(sorted(route.methods)))
        for route in main.app.routes
        if getattr(route, "path", "").startswith("/api/") and getattr(route, "methods", None)
    ]
    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    assert duplicates == [], f"duplicate API routes: {duplicates[:10]}"
