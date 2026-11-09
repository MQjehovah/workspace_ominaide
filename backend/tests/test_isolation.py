"""Regression tests for the application-level multi-user boundary (L0)."""

import inspect
import random
import string
import tempfile

from conftest import auth


async def _new_user(client):
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"iso_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "testpass123",
        },
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "testpass123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def _me(client, token):
    return (await client.get("/api/auth/me", headers=auth(token))).json()


def _use_tmp_workspace(tmp_path, monkeypatch):
    from core.config.settings import settings

    monkeypatch.setattr(settings, "workspace_root", str(tmp_path))
    monkeypatch.setattr(settings, "coding_workspace_root", "")


async def test_projects_are_scoped_per_user(client, tmp_path, monkeypatch):
    _use_tmp_workspace(tmp_path, monkeypatch)

    token_a, uid_a = await _new_user(client)
    token_b, uid_b = await _new_user(client)

    from core.paths import ensure_user_workspace, projects_root

    ensure_user_workspace(uid_a)
    ensure_user_workspace(uid_b)
    project_a = projects_root(uid_a) / "proj-a"
    project_a.mkdir(parents=True, exist_ok=True)

    r = await client.post(
        "/api/projects",
        json={"name": "A", "path": str(project_a), "is_git": False},
        headers=auth(token_a),
    )
    assert r.status_code == 200, r.text
    project_id = r.json()["id"]

    # A sees it, B does not.
    r = await client.get("/api/projects", headers=auth(token_a))
    assert any(p["id"] == project_id for p in r.json())
    r = await client.get("/api/projects", headers=auth(token_b))
    assert all(p["id"] != project_id for p in r.json())

    # B cannot read, update or delete A's project.
    assert (await client.get(
        f"/api/projects/{project_id}", headers=auth(token_b)
    )).status_code == 404
    assert (await client.patch(
        f"/api/projects/{project_id}", json={"name": "hacked"}, headers=auth(token_b)
    )).status_code == 404
    assert (await client.delete(
        f"/api/projects/{project_id}", headers=auth(token_b)
    )).status_code == 404

    # B cannot register A's directory as its own project.
    r = await client.post(
        "/api/projects",
        json={"name": "escape", "path": str(project_a), "is_git": False},
        headers=auth(token_b),
    )
    assert r.status_code == 422, r.text


async def test_project_path_traversal_is_rejected(tmp_path, monkeypatch):
    _use_tmp_workspace(tmp_path, monkeypatch)

    from core.paths import ensure_user_workspace, projects_root
    from plugins.projects.backend import service
    from plugins.projects.backend.schemas import ProjectCreate

    ensure_user_workspace(1)
    ensure_user_workspace(2)
    other = projects_root(1) / "other"
    other.mkdir(parents=True, exist_ok=True)

    try:
        await service.create_project(
            2,
            ProjectCreate(name="escape", path=str(other), is_git=False),
        )
    except ValueError as exc:
        assert "项目不在工作区内" in str(exc)
    else:  # pragma: no cover - failure path
        raise AssertionError("cross-user project path was accepted")


def test_dingtalk_env_is_per_user(tmp_path, monkeypatch):
    _use_tmp_workspace(tmp_path, monkeypatch)

    from plugins.dingtalk.backend.paths import dingtalk_env

    env1 = dingtalk_env(11)
    env2 = dingtalk_env(12)
    assert env1["DWS_CONFIG_DIR"] != env2["DWS_CONFIG_DIR"]
    assert env1["HOME"] != env2["HOME"]
    assert env1["DWS_CONFIG_DIR"] == str(tmp_path / "11" / "dingtalk" / ".dws")
    assert env2["DWS_CONFIG_DIR"] == str(tmp_path / "12" / "dingtalk" / ".dws")


async def test_admin_jobs_and_metrics_are_scoped(client, admin_token):
    admin_id = (await _me(client, admin_token))["id"]
    _, user_b = await _new_user(client)

    from core.database.session import async_session
    from core.jobs.models import BackgroundJob
    from core.observability.models import RequestTrace

    async with async_session() as db:
        db.add(BackgroundJob(user_id=admin_id, kind="test.admin", status="queued"))
        db.add(BackgroundJob(user_id=user_b, kind="test.other", status="queued"))
        db.add(RequestTrace(
            trace_id="admin-trace", user_id=admin_id, kind="request",
            name="admin-only", status="ok", duration_ms=1,
        ))
        db.add(RequestTrace(
            trace_id="other-trace", user_id=user_b, kind="request",
            name="other-only", status="ok", duration_ms=1,
        ))
        await db.commit()

    r = await client.get("/api/jobs", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert all(item["user_id"] == admin_id for item in r.json()["items"])

    r = await client.get("/api/metrics", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    names = {row["name"] for row in r.json()["slowest"]}
    assert "other-only" not in names


async def test_non_admin_cannot_create_stdio_mcp(client, admin_token):
    token_b, _ = await _new_user(client)

    r = await client.post(
        "/api/mcp/servers",
        json={
            "name": "bad",
            "slug": "bad-stdio",
            "transport": "stdio",
            "command": "sh",
            "args": ["-c", "echo no"],
        },
        headers=auth(token_b),
    )
    assert r.status_code == 403, r.text


async def test_non_admin_cannot_connect_existing_stdio(client, admin_token):
    token_b, user_b = await _new_user(client)
    from core.database.session import async_session
    from core.mcp_hub.models import McpServer

    async with async_session() as db:
        row = McpServer(
            user_id=user_b,
            slug=f"legacy-{user_b}",
            name="legacy stdio",
            transport="stdio",
            command="sh",
            args=["-c", "echo no"],
            scope="backend",
            enabled=True,
            auto_start=False,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        server_id = row.id

    r = await client.post(
        f"/api/mcp/servers/{server_id}/connect", headers=auth(token_b)
    )
    assert r.status_code == 502
    assert "stdio" in r.text


async def test_shell_tool_is_admin_only(client, admin_token):
    token_b, user_b = await _new_user(client)
    admin_id = (await _me(client, admin_token))["id"]

    from core.ai.mcp.tools.system import run_shell

    workdir = tempfile.gettempdir()
    denied = await run_shell(user_b, {"command": "echo no", "cwd": workdir})
    assert denied.isError
    assert "管理员" in denied.content[0].text

    allowed = await run_shell(admin_id, {"command": "echo ok", "cwd": workdir})
    assert not allowed.isError, allowed.content[0].text
