from conftest import auth


async def test_mcp_router_mounted(client):
    """MCP tools router must be reachable."""
    r = await client.get("/api/mcp/tools")
    assert r.status_code == 200
    tools = r.json().get("tools", [])
    names = {t.get("name") for t in tools}
    assert "search_files" in names
    assert "unified_search" in names
    assert "list_schedule_events" in names
    assert "create_schedule_event" in names
    # Removed tools must NOT be present
    assert "list_workspaces" not in names
    assert "get_daily_briefing" not in names


async def test_search_router_mounted(client, admin_token):
    r = await client.post("/api/search", json={"q": "test", "top_k": 5}, headers=auth(admin_token))
    assert r.status_code == 200
    assert "results" in r.json()


async def test_activities_router_mounted_requires_auth(client):
    r = await client.get("/api/activities")
    assert r.status_code == 401


async def test_activities_router_works_with_auth(client, admin_token):
    r = await client.get("/api/activities", headers=auth(admin_token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_files_list_requires_auth(client):
    r = await client.get("/api/files")
    assert r.status_code == 401


async def test_chat_history_endpoints(client, admin_token):
    r = await client.get("/api/chat/history", headers=auth(admin_token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_sync_folders_requires_auth(client):
    r = await client.get("/api/sync/folders")
    assert r.status_code == 401


async def test_mail_password_encrypted(client, admin_token):
    """Mail account passwords must not be stored as plaintext."""
    r = await client.post("/api/plugins/mail/accounts", json={
        "name": "Test",
        "email": "t@test.local",
        "imap_host": "imap.test.local",
        "imap_port": 993,
        "imap_tls": True,
        "smtp_host": "smtp.test.local",
        "smtp_port": 465,
        "smtp_tls": True,
        "username": "t@test.local",
        "password": "super-secret-password",
    }, headers=auth(admin_token))
    assert r.status_code == 201, r.text
    # Response returns decrypted password to the owner
    assert r.json()["password"] == "super-secret-password"
    # The DB must not store plaintext
    import sqlite3
    conn = sqlite3.connect("test_app.db")
    rows = conn.execute(
        "SELECT password FROM plugin_mail_accounts WHERE email='t@test.local'"
    ).fetchall()
    conn.close()
    stored = rows[0][0]
    assert "super-secret-password" not in stored
    assert stored.startswith("enc:")
