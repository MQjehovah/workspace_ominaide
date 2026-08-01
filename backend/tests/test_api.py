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


async def test_mail_event_report_and_mcp(client, admin_token):
    """Mail events can be reported, deduplicated, and queried via MCP."""
    payload = {
        "account_id": "acc1",
        "uid": 1001,
        "subject": "紧急测试邮件",
        "from_address": "noreply@example.com",
        "date": "2026-08-01 10:00:00",
        "preview": "请优先处理",
        "content": "这是紧急邮件内容",
        "important": True,
    }
    r = await client.post("/api/plugins/mail/events", json=payload, headers=auth(admin_token))
    assert r.status_code == 201, r.text
    # Dedupe: same uid should return existing, not a new row
    r2 = await client.post("/api/plugins/mail/events", json=payload, headers=auth(admin_token))
    assert r2.status_code == 201
    assert r2.json()["id"] == r.json()["id"]
    # List events
    r3 = await client.get("/api/plugins/mail/events", headers=auth(admin_token))
    assert r3.status_code == 200
    assert any(e["subject"] == "紧急测试邮件" for e in r3.json())
    # MCP tool available
    r4 = await client.get("/api/mcp/tools", headers=auth(admin_token))
    names = {t["name"] for t in r4.json()["tools"]}
    assert "list_recent_emails" in names
