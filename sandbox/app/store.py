"""Small SQLite metadata store for workspaces.

Container state itself lives in Docker. This table only keeps the metadata that
Docker labels cannot update cheaply, such as last-used time and setup logs.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from app.models import Workspace


class WorkspaceStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    template TEXT NOT NULL,
                    name TEXT NOT NULL,
                    project_path TEXT NOT NULL,
                    container_id TEXT,
                    env_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_used_at REAL NOT NULL,
                    ttl_seconds INTEGER NOT NULL,
                    error TEXT,
                    setup_log TEXT
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id)"
            )
            self._conn.commit()

    def create(self, workspace: Workspace) -> Workspace:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO workspaces (
                    id, owner_id, template, name, project_path, container_id,
                    env_json, status, created_at, last_used_at, ttl_seconds, error, setup_log
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workspace.id,
                    workspace.owner_id,
                    workspace.template,
                    workspace.name,
                    workspace.project_path,
                    workspace.container_id,
                    json.dumps(workspace.env, ensure_ascii=False),
                    workspace.status,
                    workspace.created_at,
                    workspace.last_used_at,
                    workspace.ttl_seconds,
                    workspace.error,
                    workspace.setup_log,
                ),
            )
            self._conn.commit()
        return workspace

    def get(self, workspace_id: str) -> Workspace | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
            ).fetchone()
        return _row_to_workspace(row) if row else None

    def list(self, owner_id: str | None = None) -> list[Workspace]:
        with self._lock:
            if owner_id:
                rows = self._conn.execute(
                    "SELECT * FROM workspaces WHERE owner_id = ? ORDER BY created_at DESC",
                    (owner_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM workspaces ORDER BY created_at DESC"
                ).fetchall()
        return [_row_to_workspace(row) for row in rows]

    def update(self, workspace_id: str, **fields: Any) -> Workspace | None:
        allowed = {
            "container_id",
            "status",
            "error",
            "setup_log",
            "last_used_at",
            "ttl_seconds",
            "name",
            "env_json",
        }
        data = {key: value for key, value in fields.items() if key in allowed}
        if not data:
            return self.get(workspace_id)
        assignments = ", ".join(f"{key} = ?" for key in data)
        values = list(data.values()) + [workspace_id]
        with self._lock:
            self._conn.execute(
                f"UPDATE workspaces SET {assignments} WHERE id = ?", values
            )
            self._conn.commit()
        return self.get(workspace_id)

    def touch(self, workspace_id: str) -> None:
        self.update(workspace_id, last_used_at=time.time())

    def delete(self, workspace_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
            self._conn.commit()

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM workspaces").fetchone()
        return int(row["n"]) if row else 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _row_to_workspace(row: sqlite3.Row) -> Workspace:
    return Workspace(
        id=row["id"],
        owner_id=row["owner_id"],
        template=row["template"],
        name=row["name"],
        project_path=row["project_path"],
        container_id=row["container_id"],
        env=json.loads(row["env_json"] or "{}"),
        status=row["status"],
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        ttl_seconds=row["ttl_seconds"],
        error=row["error"],
        setup_log=row["setup_log"],
    )
