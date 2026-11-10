"""Projects are folders; git repositories are independent children."""

from conftest import auth
from core.config.settings import settings


async def _create_project(client, token, tmp_path) -> dict:
    response = await client.post(
        "/api/projects",
        headers=auth(token),
        json={
            "name": "workspace_ai",
            "path": str(tmp_path / "workspace_ai"),
            "description": "AI workspace",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_create_project_with_independent_git_projects(
    client, admin_token, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "coding_workspace_root", str(tmp_path))
    project = await _create_project(client, admin_token, tmp_path)
    assert project["name"] == "workspace_ai"
    assert project["git_projects"] == []
    assert "is_git" not in project
    assert "repo_url" not in project

    for name, path in (
        ("gateway", "gateway"),
        ("rag", "rag"),
        ("market", "market"),
        ("agent", "agent"),
    ):
        response = await client.post(
            f"/api/projects/{project['id']}/git-projects",
            headers=auth(admin_token),
            json={
                "name": name,
                "url": f"https://github.com/MQjehovah/{name}.git",
                "relative_path": path,
                "clone": False,
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["relative_path"] == path
        assert response.json()["status"] == "pending"

    detail = await client.get(
        f"/api/projects/{project['id']}", headers=auth(admin_token)
    )
    assert detail.status_code == 200, detail.text
    assert [item["name"] for item in detail.json()["git_projects"]] == [
        "gateway",
        "rag",
        "market",
        "agent",
    ]


async def test_git_project_relative_path_cannot_escape(
    client, admin_token, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "coding_workspace_root", str(tmp_path))
    project = await _create_project(client, admin_token, tmp_path)

    response = await client.post(
        f"/api/projects/{project['id']}/git-projects",
        headers=auth(admin_token),
        json={
            "name": "escape",
            "url": "https://github.com/a/b.git",
            "relative_path": "../escape",
            "clone": False,
        },
    )
    assert response.status_code == 422
    assert "相对路径" in response.json()["detail"]
