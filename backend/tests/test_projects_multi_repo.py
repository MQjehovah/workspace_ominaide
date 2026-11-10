"""Project workspaces may contain multiple independent git repositories."""

from pathlib import Path

from conftest import auth
from core.config.settings import settings


async def test_create_multi_repo_project(client, admin_token, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "coding_workspace_root", str(tmp_path))
    target = tmp_path / "workspace_ai"

    response = await client.post(
        "/api/projects",
        headers=auth(admin_token),
        json={
            "name": "workspace_ai",
            "path": str(target),
            "clone": False,
            "repos": [
                {"name": "gateway", "url": "https://github.com/MQjehovah/gateway.git"},
                {"name": "rag", "url": "https://github.com/MQjehovah/rag.git"},
                {"name": "market", "url": "https://github.com/MQjehovah/market.git"},
                {"name": "agent", "url": "https://github.com/MQjehovah/agent.git"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    project = response.json()
    assert project["name"] == "workspace_ai"
    assert project["is_git"] is True
    assert [repo["name"] for repo in project["repos"]] == [
        "gateway",
        "rag",
        "market",
        "agent",
    ]
    assert all(repo["status"] == "pending" for repo in project["repos"])
    assert target.is_dir()

    listed = await client.get("/api/projects", headers=auth(admin_token))
    assert listed.status_code == 200, listed.text
    entry = next(item for item in listed.json() if item["id"] == project["id"])
    assert len(entry["repos"]) == 4


async def test_multi_repo_path_cannot_escape_project(client, admin_token, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "coding_workspace_root", str(tmp_path))

    response = await client.post(
        "/api/projects",
        headers=auth(admin_token),
        json={
            "name": "bad",
            "path": str(tmp_path / "bad"),
            "clone": False,
            "repos": [
                {"name": "escape", "path": "../escape", "url": "https://github.com/a/b.git"}
            ],
        },
    )
    assert response.status_code == 422
    assert "相对路径" in response.json()["detail"]
