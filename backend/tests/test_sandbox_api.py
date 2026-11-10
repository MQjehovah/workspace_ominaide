"""Sandbox facade: auth, ownership and forwarding."""

import pytest

from ai.sandbox import router as sandbox_router


class FakeSandboxClient:
    base_url = "http://sandbox-runner:8010"
    token = "runner-token"
    timeout = 30

    def __init__(self):
        self.created = None
        self.workspaces = {
            "ws-1": {
                "id": "ws-1",
                "owner_id": "1",
                "template": "omniaide-base",
                "name": "demo",
                "project_path": "/data/workspace/1/projects/demo",
                "status": "ready",
                "created_at": 1.0,
                "last_used_at": 1.0,
                "ttl_seconds": 1800,
            }
        }

    async def list_templates(self):
        return [{"id": "omniaide-base", "name": "Base", "image": "img"}]

    async def list_workspaces(self, owner_id):
        return [ws for ws in self.workspaces.values() if ws["owner_id"] == owner_id]

    async def create_workspace(self, **kwargs):
        self.created = kwargs
        workspace = {
            "id": "ws-new",
            "owner_id": kwargs["owner_id"],
            "template": kwargs["template"],
            "name": kwargs.get("name") or "new",
            "project_path": kwargs["project_path"],
            "status": "creating",
            "created_at": 1.0,
            "last_used_at": 1.0,
            "ttl_seconds": 1800,
        }
        self.workspaces["ws-new"] = workspace
        return workspace

    async def get_workspace(self, workspace_id):
        from ai.coding.sandbox_client import SandboxError

        if workspace_id not in self.workspaces:
            raise SandboxError("workspace not found")
        return self.workspaces[workspace_id]

    async def start_workspace(self, workspace_id):
        return self.workspaces[workspace_id]

    async def stop_workspace(self, workspace_id):
        return self.workspaces[workspace_id]

    async def delete_workspace(self, workspace_id):
        return {"deleted": True}

    async def logs(self, workspace_id, tail=200):
        return {"logs": ""}


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def test_list_sandbox_templates(client, admin_token, monkeypatch):
    fake = FakeSandboxClient()
    monkeypatch.setattr(sandbox_router, "get_client", lambda: fake)

    response = await client.get("/api/sandbox/templates", headers=_auth(admin_token))
    assert response.status_code == 200
    assert response.json()[0]["id"] == "omniaide-base"


async def test_create_workspace_uses_current_user(client, admin_token, monkeypatch):
    fake = FakeSandboxClient()
    monkeypatch.setattr(sandbox_router, "get_client", lambda: fake)

    response = await client.post(
        "/api/sandbox/workspaces",
        headers=_auth(admin_token),
        json={"template": "omniaide-base", "name": "demo"},
    )
    assert response.status_code == 201
    assert fake.created["owner_id"]
    assert response.json()["proxy_base"].startswith("/api/sandbox/workspaces/")


async def test_workspace_ownership_is_enforced(client, admin_token, monkeypatch):
    fake = FakeSandboxClient()
    fake.workspaces["ws-1"]["owner_id"] = "999"
    monkeypatch.setattr(sandbox_router, "get_client", lambda: fake)

    response = await client.get("/api/sandbox/workspaces/ws-1", headers=_auth(admin_token))
    assert response.status_code == 404
