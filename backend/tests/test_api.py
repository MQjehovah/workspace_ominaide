from conftest import auth


async def test_mcp_router_mounted(client, admin_token):
    """MCP tools router must be reachable."""
    r = await client.get("/api/mcp/tools", headers=auth(admin_token))
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


async def test_mcp_call_activity_records_tool_name(client, admin_token):
    r = await client.post(
        "/api/mcp/call",
        json={"name": "get_user_info", "arguments": {}},
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text

    r = await client.get(
        "/api/activities",
        params={"event_type": "mcp.tool.called", "limit": 5},
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert rows
    assert rows[0]["summary"].startswith("get_user_info")
    assert rows[0]["details"]["tool"] == "get_user_info"


async def test_files_list_requires_auth(client):
    r = await client.get("/api/files")
    assert r.status_code == 401


async def test_chat_history_endpoints(client, admin_token):
    r = await client.get("/api/chat/history", headers=auth(admin_token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_config_package_exports_settings():
    from core.config import settings

    assert hasattr(settings, "memory_layer_enabled")


async def test_schedule_accepts_aware_datetimes(client, admin_token):
    """Frontend sends UTC (Z) ranges; DB columns are naive local wall time."""
    r = await client.post(
        "/api/schedule",
        json={
            "title": "TZ 测试日程",
            "start_time": "2026-11-05T09:00:00+08:00",
            "end_time": "2026-11-05T10:00:00+08:00",
        },
        headers=auth(admin_token),
    )
    assert r.status_code in (200, 201), r.text
    event_id = r.json()["id"]

    r = await client.get(
        "/api/activities",
        params={"event_type": "schedule.created", "limit": 10},
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text
    created = [e for e in r.json() if e.get("entity_id") == event_id]
    assert created
    assert created[0]["details"]["title"] == "TZ 测试日程"
    assert created[0]["details"]["start_time"]

    r = await client.get(
        "/api/schedule?start=2026-11-04T16:00:00Z&end=2026-11-05T16:00:00Z",
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text
    assert any(e["id"] == event_id for e in r.json())

    r = await client.delete(f"/api/schedule/{event_id}", headers=auth(admin_token))
    assert r.status_code == 200


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
    account_id = r.json()["id"]
    # Passwords are never included in account list/create responses.
    assert "password" not in r.json()
    # The owner can fetch it explicitly when a legacy client needs IMAP.
    r = await client.get(
        f"/api/plugins/mail/accounts/{account_id}/secret", headers=auth(admin_token)
    )
    assert r.status_code == 200, r.text
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


async def test_projects_requires_auth(client):
    r = await client.get("/api/projects")
    assert r.status_code == 401


async def test_coding_tools_registered(client, admin_token):
    r = await client.get("/api/mcp/tools", headers=auth(admin_token))
    names = {t["name"] for t in r.json()["tools"]}
    assert "delegate_coding" in names
    assert "list_coding_projects" in names
    assert "list_coding_runs" in names
    assert "get_coding_run" in names
    assert "dispatch_coding_task" not in names
    assert "ha_list_entities" in names
    assert "ha_toggle" in names
    assert "web_search" in names
    assert "fetch_url" in names
    assert "todo_update" in names
    assert "event_delete" in names
    assert "note_delete" in names
    assert "file_delete" in names
    assert "routine_create" in names
    assert "sources_add" in names
    assert "send_email" in names
    assert "read_file_content" in names
    assert "project_delete" in names
    assert "run_shell" in names
    assert "create_event" not in names
    assert "list_events" not in names
    assert "get_unread_notifications" not in names


async def test_project_service_crud(tmp_path, monkeypatch):
    from core.config.settings import settings

    monkeypatch.setattr(settings, "coding_workspace_root", str(tmp_path))
    repo = tmp_path / "demo"
    repo.mkdir()

    from plugins.projects.backend import service
    from plugins.projects.backend.schemas import ProjectCreate, ProjectUpdate

    project = await service.create_project(
        1, ProjectCreate(name="Demo", path=str(repo), is_git=False)
    )
    assert project.path == str(repo.resolve())
    assert any(p.id == project.id for p in await service.list_projects(1))

    updated = await service.update_project(
        1, project.id, ProjectUpdate(name="Demo 2")
    )
    assert updated is not None and updated.name == "Demo 2"
    assert await service.delete_project(1, project.id)
    assert not any(p.id == project.id for p in await service.list_projects(1))
    assert not repo.exists()


async def test_project_default_path_and_git_fields(tmp_path, monkeypatch):
    from core.config.settings import settings

    monkeypatch.setattr(settings, "coding_workspace_root", str(tmp_path))
    defaulted_dir = tmp_path / "Defaulted"
    defaulted_dir.mkdir()
    git_dir = tmp_path / "GitDemo"
    git_dir.mkdir()

    from plugins.projects.backend import service
    from plugins.projects.backend.schemas import ProjectCreate

    project = await service.create_project(
        1, ProjectCreate(name="Defaulted", path="", is_git=False)
    )
    assert project.path == str(defaulted_dir.resolve())
    assert project.default_branch is None
    assert await service.delete_project(1, project.id)

    try:
        await service.create_project(
            1,
            ProjectCreate(name="GitDemo", path=str(git_dir), is_git=True, repo_url=""),
        )
    except ValueError as e:
        assert "仓库地址" in str(e)
    else:
        raise AssertionError("git project without repo_url must be rejected")

    project = await service.create_project(
        1,
        ProjectCreate(
            name="GitDemo",
            path=str(git_dir),
            is_git=True,
            repo_url="git@example.com:demo/repo.git",
        ),
    )
    assert project.default_branch == "master"
    assert await service.delete_project(1, project.id)


async def test_coding_project_context_snapshot(tmp_path):
    from core.coding.context import build_project_context

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
    from core.coding.delivery import deliver

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
    assert summary["branch"].startswith("feature/")
    assert summary["pushed"] is False
    assert "commit" in stages and "sensitive_skipped" in stages

    branch = _git_out(repo, "rev-parse", "--abbrev-ref", "HEAD")
    assert branch.startswith("feature/")
    assert "fix:" in _git_out(repo, "log", "-1", "--format=%s")
    changed = _git_out(repo, "show", "--name-only", "--format=", "HEAD")
    assert "a.txt" in changed
    assert ".env" not in changed


async def test_delivery_stops_when_verify_fails(tmp_path):
    from core.coding.delivery import deliver

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



def test_git_gate_blocks_push_and_commit_by_default():
    from core.coding.workspace import git_policy_violation

    blocked = [
        "git push",
        "git -C . push origin main",
        'sh -c "git push origin main"',
        "bash -lc 'git push --force'",
        "env GIT_TRACE=1 git push origin master",
        "sudo git push",
        "git -c user.name=x push",
        "git commit -m test",
        "sh -c 'git commit -am wip'",
    ]
    for command in blocked:
        assert git_policy_violation(command, allow_commit=False, allow_push=False), command


def test_git_gate_blocks_force_and_protected_branch_even_when_allowed():
    from core.coding.workspace import git_policy_violation

    # push is permitted, but never destructive and never straight to main.
    assert git_policy_violation("git push --force origin feature", allow_commit=True, allow_push=True)
    assert git_policy_violation("git push -f origin feature", allow_commit=True, allow_push=True)
    assert git_policy_violation("git push origin main", allow_commit=True, allow_push=True)
    assert git_policy_violation("git push origin HEAD:master", allow_commit=True, allow_push=True)
    assert git_policy_violation("git push origin refs/heads/main", allow_commit=True, allow_push=True)
    assert git_policy_violation("git push origin +agent/fix", allow_commit=True, allow_push=True)
    assert git_policy_violation("git push --delete origin agent/x", allow_commit=True, allow_push=True)
    # Feature branch push and plain commit stay allowed.
    assert git_policy_violation("git push -u origin agent/fix", allow_commit=True, allow_push=True) is None
    assert git_policy_violation("git commit -m 'fix: x'", allow_commit=True, allow_push=True) is None


def test_git_gate_allows_read_only_and_non_git_commands():
    from core.coding.workspace import git_policy_violation

    for command in [
        "git status",
        "git -C sub log --oneline -5",
        "git diff --stat",
        "pytest -q",
        "npm run build",
        "python -m pytest",
    ]:
        assert git_policy_violation(command, allow_commit=False, allow_push=False) is None, command


def test_git_gate_blocks_alias_override():
    from core.coding.workspace import git_policy_violation

    assert git_policy_violation(
        "git -c alias.p=push p origin main", allow_commit=True, allow_push=False
    )


def test_sensitive_reference_detection():
    from core.coding.workspace import contains_sensitive_reference

    for command in [
        "cat .env",
        "cat backend/.env",
        "head -5 ./.env.local",
        "cat /root/.ssh/id_rsa",
        "ls ~/.ssh",
        "grep SECRET .env",
        "docker run --env-file=.env img",
        "DB=.env ./start.sh",
    ]:
        assert contains_sensitive_reference(command), command
    for command in [
        "cat .env.example",
        "pytest -q",
        "git status",
        "ls src",
    ]:
        assert not contains_sensitive_reference(command), command


def test_sandbox_env_excludes_backend_secrets(monkeypatch):
    from core.coding import workspace

    monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
    monkeypatch.setenv("LLM_API_KEY", "sk-secret")
    monkeypatch.setenv("JWT_SECRET", "jwt-secret")
    env = workspace.sandbox_env({"name": "tester", "email": "t@example.com"})

    assert "DATABASE_URL" not in env
    assert "LLM_API_KEY" not in env
    assert "JWT_SECRET" not in env
    assert env["HOME"] == workspace.settings.coding_sandbox_home
    assert env["GIT_AUTHOR_NAME"] == "tester"
    assert env["GIT_AUTHOR_EMAIL"] == "t@example.com"


async def test_run_command_fails_closed_without_sandbox_user(tmp_path, monkeypatch):
    from core.coding import workspace

    monkeypatch.setattr(workspace, "_euid", lambda: 0)
    monkeypatch.setattr(workspace.settings, "coding_sandbox_enabled", True)
    monkeypatch.setattr(workspace, "sandbox_identity", lambda: None)

    result = await workspace.run_command(str(tmp_path), {"command": "id"})
    assert "error" in result
    assert "refusing" in result["error"]


async def test_run_command_rejects_gated_git_and_reports_sandbox(tmp_path):
    from core.coding import workspace

    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    denied = await workspace.run_command(str(tmp_path), {"command": "git push origin main"})
    assert "error" in denied

    denied_commit = await workspace.run_command(str(tmp_path), {"command": "git commit -am wip"})
    assert "error" in denied_commit

    secret = await workspace.run_command(str(tmp_path), {"command": "cat .env"})
    assert "error" in secret

    ok = await workspace.run_command(str(tmp_path), {"command": "git --version"})
    assert ok.get("code") == 0
    assert "sandbox" in ok


async def test_delivery_ignores_repo_hooks_and_restores_config(tmp_path):
    import os

    from core.coding.delivery import deliver

    repo = tmp_path / "repo"
    repo.mkdir()
    await _init_repo(repo)
    marker = repo / "hook-ran.txt"
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    hook = hooks / "pre-commit"
    hook.write_text(f"#!/bin/sh\ntouch '{marker.as_posix()}'\n", encoding="utf-8")
    if hasattr(os, "chmod"):
        os.chmod(hook, 0o755)

    config = repo / ".git" / "config"
    original = config.read_text(encoding="utf-8")

    (repo / "a.txt").write_text("hooked\n", encoding="utf-8")
    summary = await deliver(
        str(repo), "改 a.txt",
        developer={"github_username": "tester", "github_email": "t@example.com", "default_branch": "main"},
        allow_commit=True, allow_push=False,
    )
    assert summary["ok"] is True
    assert not marker.exists(), "repo hook must not run as root during delivery"
    assert config.read_text(encoding="utf-8") == original


async def test_delivery_rejects_exec_remote(tmp_path):
    from core.coding.delivery import deliver

    repo = tmp_path / "repo"
    repo.mkdir()
    await _init_repo(repo)
    import subprocess

    subprocess.run(["git", "remote", "add", "origin", "ext::sh -c touch-pwned"], cwd=repo, check=True)
    (repo / "a.txt").write_text("x\n", encoding="utf-8")

    summary = await deliver(
        str(repo), "改 a.txt",
        developer={"github_username": "tester", "github_email": "t@example.com", "default_branch": "main"},
        allow_commit=True, allow_push=True,
    )
    assert summary["ok"] is False
    assert summary["stage"] == "repo"
    assert "ext:" in summary["detail"]


async def test_delivery_rejects_symlinked_git_dir(tmp_path):
    import os

    from core.coding.delivery import deliver

    repo = tmp_path / "repo"
    repo.mkdir()
    await _init_repo(repo)
    real = tmp_path / "real-git"
    (repo / ".git").rename(real)
    try:
        os.symlink(real, repo / ".git", target_is_directory=True)
    except (OSError, NotImplementedError):
        return  # Windows without developer mode

    (repo / "a.txt").write_text("x\n", encoding="utf-8")
    summary = await deliver(
        str(repo), "改 a.txt",
        developer={"github_username": "tester", "github_email": "t@example.com", "default_branch": "main"},
        allow_commit=True, allow_push=False,
    )
    assert summary["ok"] is False
    assert summary["stage"] == "repo"


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
