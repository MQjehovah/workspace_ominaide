from conftest import auth


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_users_list_requires_auth(client):
    r = await client.get("/api/auth/users")
    assert r.status_code == 401


async def test_admin_can_list_users(client, admin_token):
    r = await client.get("/api/auth/users", headers=auth(admin_token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_non_admin_cannot_list_users(client, user_token):
    r = await client.get("/api/auth/users", headers=auth(user_token))
    assert r.status_code == 403


async def test_non_admin_cannot_toggle_user(client, user_token, admin_token):
    users = (await client.get("/api/auth/users", headers=auth(admin_token))).json()
    target = users[0]
    r = await client.put(f"/api/auth/users/{target['id']}/toggle-active",
                         json={"is_active": False}, headers=auth(user_token))
    assert r.status_code == 403


async def test_me_requires_valid_token(client, admin_token):
    r = await client.get("/api/auth/me", headers=auth(admin_token))
    assert r.status_code == 200
    assert "username" in r.json()


async def test_me_rejects_garbage_token(client):
    r = await client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


async def test_disabled_user_cannot_login(client, admin_token):
    # Register a user, disable them, then verify login is rejected.
    import random
    import string
    suffix = "".join(random.choices(string.ascii_lowercase, k=6))
    username = f"disabled_{suffix}"
    email = f"{username}@example.com"
    r = await client.post("/api/auth/register", json={"username": username, "email": email, "password": "testpass123"})
    assert r.status_code in (200, 201)
    # Find and disable via admin
    users = (await client.get("/api/auth/users", headers=auth(admin_token))).json()
    target = next(u for u in users if u["username"] == username)
    r = await client.put(f"/api/auth/users/{target['id']}/toggle-active",
                         json={"is_active": False}, headers=auth(admin_token))
    assert r.status_code == 200
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 401
