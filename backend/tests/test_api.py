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


async def test_coding_task_requires_auth(client):
    r = await client.post("/api/vibecoding/tasks", json={"project": "E:/x", "input": "y"})
    assert r.status_code == 401


async def test_coding_dispatch_without_desktop(client, admin_token):
    r = await client.post(
        "/api/vibecoding/tasks",
        json={"project": "E:/x", "input": "y", "tool": "opencode"},
        headers=auth(admin_token),
    )
    assert r.status_code == 409


async def test_coding_dispatch_server_engine(client, admin_token):
    r = await client.post(
        "/api/vibecoding/tasks",
        json={"project": "/workspace/missing", "input": "y"},
        headers=auth(admin_token),
    )
    assert r.status_code == 200
    assert r.json().get("engine") == "server"
    assert r.json().get("task_id")


async def test_coding_projects_endpoint(client, admin_token):
    r = await client.get("/api/vibecoding/projects", headers=auth(admin_token))
    assert r.status_code == 200
    assert "projects" in r.json()
    assert r.json()["tools"].get("omniaide") is True


async def test_coding_tools_registered(client, admin_token):
    r = await client.get("/api/mcp/tools", headers=auth(admin_token))
    names = {t["name"] for t in r.json()["tools"]}
    assert "dispatch_coding_task" in names
    assert "list_coding_projects" in names
    assert "continue_coding_task" in names
    assert "list_coding_tasks" in names


async def test_coding_history_requires_auth(client):
    r = await client.get("/api/vibecoding/tasks")
    assert r.status_code == 401


async def test_coding_task_failure_is_persisted(client, admin_token):
    """A task that fails validation must still land in durable history."""
    r = await client.post(
        "/api/vibecoding/tasks",
        json={"project": "/workspace/definitely-missing", "input": "x"},
        headers=auth(admin_token),
    )
    assert r.status_code == 200
    task_id = r.json()["task_id"]

    detail = await client.get(f"/api/vibecoding/tasks/{task_id}", headers=auth(admin_token))
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["task_id"] == task_id
    assert body["status"] == "failed"
    assert body["error"]
    assert body["events"]

    listing = await client.get("/api/vibecoding/tasks?limit=50", headers=auth(admin_token))
    assert any(t["task_id"] == task_id for t in listing.json()["tasks"])

    # A failed task has no stored conversation, so continuing it is rejected.
    cont = await client.post(
        f"/api/vibecoding/tasks/{task_id}/continue",
        json={"input": "再来一次"},
        headers=auth(admin_token),
    )
    assert cont.status_code == 409


async def test_coding_task_detail_is_user_scoped(client, admin_token, user_token):
    r = await client.post(
        "/api/vibecoding/tasks",
        json={"project": "/workspace/definitely-missing", "input": "x"},
        headers=auth(admin_token),
    )
    task_id = r.json()["task_id"]
    other = await client.get(f"/api/vibecoding/tasks/{task_id}", headers=auth(user_token))
    assert other.status_code == 404


async def test_coding_project_context_snapshot(tmp_path):
    from plugins.vibecoding.backend.context import build_project_context

    (tmp_path / "AGENTS.md").write_text("Run pytest before committing.", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("x = 1\n", encoding="utf-8")

    text = await build_project_context(str(tmp_path))
    assert "AGENTS.md" in text
    assert "src/" in text
    assert "main.py" in text


async def _init_repo(path):
    import subprocess

    def run(*args):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)

    run("init", "-b", "main")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")
    (path / "a.txt").write_text("one\n", encoding="utf-8")
    run("add", "-A")
    run("commit", "-m", "init")


def _git_out(path, *args) -> str:
    import subprocess

    out = subprocess.run(["git", *args], cwd=path, capture_output=True)
    stdout = out.stdout
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    return stdout.strip()


async def test_delivery_branches_commits_and_skips_sensitive(tmp_path):
    from plugins.vibecoding.backend.delivery import deliver

    repo = tmp_path / "repo"
    repo.mkdir()
    await _init_repo(repo)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    (repo / ".env").write_text("SECRET=1\n", encoding="utf-8")

    stages = []

    async def emit(stage, ok, detail="", extra=None):
        stages.append(stage)

    summary = await deliver(
        str(repo), "修复 a.txt 的内容",
        developer={"github_username": "tester", "github_email": "t@example.com", "default_branch": "main"},
        allow_commit=True, allow_push=False, verify_command="", emit=emit,
    )
    assert summary["ok"] is True
    assert summary["branch"].startswith("agent/")
    assert summary["pushed"] is False
    assert "commit" in stages and "sensitive_skipped" in stages

    branch = _git_out(repo, "rev-parse", "--abbrev-ref", "HEAD")
    assert branch.startswith("agent/")
    assert "fix:" in _git_out(repo, "log", "-1", "--format=%s")
    changed = _git_out(repo, "show", "--name-only", "--format=", "HEAD")
    assert "a.txt" in changed
    assert ".env" not in changed


async def test_delivery_stops_when_verify_fails(tmp_path):
    from plugins.vibecoding.backend.delivery import deliver

    repo = tmp_path / "repo"
    repo.mkdir()
    await _init_repo(repo)
    head_before = _git_out(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("broken\n", encoding="utf-8")

    summary = await deliver(
        str(repo), "改坏它",
        developer={"github_username": "tester", "github_email": "t@example.com", "default_branch": "main"},
        allow_commit=True, allow_push=False, verify_command="exit 3",
    )
    assert summary["ok"] is False
    assert summary["stage"] == "verify"
    assert _git_out(repo, "rev-parse", "HEAD") == head_before



async def test_activity_post_and_list(client, admin_token):
    """Client-reported activity events can be posted and listed."""
    payload = {
        "event_type": "app.used",
        "entity_type": "app",
        "summary": "使用 Code 15 分钟",
        "details": {"app": "Code", "title": "workspace", "minutes": 15},
    }
    r = await client.post("/api/activities", json=payload, headers=auth(admin_token))
    assert r.status_code == 201, r.text
    assert r.json()["event_type"] == "app.used"
    assert r.json()["details"]["minutes"] == 15
    # Listed back
    r2 = await client.get("/api/activities?event_type=app.used", headers=auth(admin_token))
    assert r2.status_code == 200
    assert any(a["event_type"] == "app.used" for a in r2.json())
