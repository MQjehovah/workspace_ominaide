"""File sync routes now live inside the files plugin."""

import random
import string

from conftest import auth


async def _new_user(client):
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"sync_{suffix}"
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


async def test_sync_folders_are_served_by_files_plugin(client):
    token = await _new_user(client)

    r = await client.post(
        "/api/sync/folders",
        json={"server_path": "/docs/", "local_path": "C:/docs"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    folder = r.json()
    assert folder["server_path"] == "/docs/"

    r = await client.get("/api/sync/folders", headers=auth(token))
    assert r.status_code == 200, r.text
    assert [item["id"] for item in r.json()["folders"]] == [folder["id"]]

    r = await client.put(
        f"/api/sync/folders/{folder['id']}",
        json={"enabled": False},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False
