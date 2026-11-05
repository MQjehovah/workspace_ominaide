"""Cross-device settings sync (user-scoped key/value documents)."""
from conftest import auth


async def _new_user(client) -> tuple[str, int]:
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"sync_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def test_settings_sync_roundtrip(client):
    token, _ = await _new_user(client)
    assert (await client.get("/api/sync/settings/desktop")).status_code == 401

    r = await client.put(
        "/api/sync/settings/desktop/shortcut",
        json={"value": {"toggle": "Ctrl+Shift+Space", "quickCapture": "Ctrl+Shift+N"}, "device_id": "dev-a"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["device_id"] == "dev-a"

    r = await client.get("/api/sync/settings/desktop", headers=auth(token))
    assert r.status_code == 200, r.text
    items = {x["key"]: x for x in r.json()["items"]}
    assert items["shortcut"]["value"]["quickCapture"] == "Ctrl+Shift+N"

    # Overwrite from another device.
    r = await client.put(
        "/api/sync/settings/desktop/shortcut",
        json={"value": {"toggle": "Ctrl+Alt+Space"}, "device_id": "dev-b"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["device_id"] == "dev-b"

    r = await client.get("/api/sync/settings/desktop", headers=auth(token))
    items = {x["key"]: x for x in r.json()["items"]}
    assert items["shortcut"]["value"]["toggle"] == "Ctrl+Alt+Space"
    assert len(items) == 1


async def test_settings_are_user_scoped(client):
    token_a, _ = await _new_user(client)
    token_b, _ = await _new_user(client)

    await client.put(
        "/api/sync/settings/desktop/disabledPlugins",
        json={"value": ["mail"], "device_id": "dev-a"},
        headers=auth(token_a),
    )
    r = await client.get("/api/sync/settings/desktop", headers=auth(token_b))
    assert r.status_code == 200
    assert r.json()["items"] == []
