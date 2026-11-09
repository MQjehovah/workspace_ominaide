"""Goal workspace: structured DB items plus an exportable view."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime

from sqlalchemy import select

from ai.cognition.models import Goal, Task, Workspace, WorkspaceArtifact, WorkspaceItem
from core.database.session import async_session


async def ensure_workspace(user_id: int, goal_id: int, bot_id: int | None = None) -> Workspace | None:
    async with async_session() as db:
        goal = (await db.execute(
            select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
        )).scalar_one_or_none()
        if goal is None:
            return None
        row = (await db.execute(
            select(Workspace).where(
                Workspace.user_id == user_id,
                Workspace.goal_id == goal_id,
            )
        )).scalar_one_or_none()
        if row is None:
            row = Workspace(user_id=user_id, bot_id=bot_id or goal.bot_id, goal_id=goal_id)
            db.add(row)
            await db.flush()
            goal.workspace_id = row.id
        elif goal.workspace_id != row.id:
            goal.workspace_id = row.id
        await db.commit()
        await db.refresh(row)
        return row


async def workspace_view(user_id: int, workspace_id: int) -> dict | None:
    async with async_session() as db:
        row = (await db.execute(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.user_id == user_id,
            )
        )).scalar_one_or_none()
        if row is None:
            return None
        items = list((await db.execute(
            select(WorkspaceItem)
            .where(WorkspaceItem.workspace_id == workspace_id)
            .order_by(WorkspaceItem.id)
        )).scalars().all())
        artifacts = list((await db.execute(
            select(WorkspaceArtifact)
            .where(WorkspaceArtifact.workspace_id == workspace_id)
            .order_by(WorkspaceArtifact.id)
        )).scalars().all())
        return {
            "id": row.id,
            "user_id": row.user_id,
            "bot_id": row.bot_id,
            "goal_id": row.goal_id,
            "status": row.status,
            "items": [
                {
                    "id": item.id,
                    "type": item.type,
                    "key": item.key,
                    "content": item.content,
                    "source": item.source,
                    "confidence": item.confidence,
                    "created_by": item.created_by,
                    "created_at": item.created_at,
                }
                for item in items
            ],
            "artifacts": [
                {
                    "id": art.id,
                    "file_id": art.file_id,
                    "kind": art.kind,
                    "created_at": art.created_at,
                }
                for art in artifacts
            ],
        }


async def add_item(
    user_id: int,
    workspace_id: int,
    *,
    type: str = "fact",
    key: str | None = None,
    content=None,
    source: str | None = None,
    confidence: float = 0.5,
    created_by: str | None = None,
) -> dict | None:
    async with async_session() as db:
        workspace = (await db.execute(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.user_id == user_id,
            )
        )).scalar_one_or_none()
        if workspace is None:
            return None
        row = WorkspaceItem(
            workspace_id=workspace_id,
            type=type[:24],
            key=key[:120] if key else None,
            content=content,
            source=source,
            confidence=float(confidence),
            created_by=created_by,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return {
            "id": row.id,
            "type": row.type,
            "key": row.key,
            "content": row.content,
            "source": row.source,
            "confidence": row.confidence,
            "created_by": row.created_by,
        }


async def update_item(
    user_id: int,
    workspace_id: int,
    item_id: int,
    **values,
) -> dict | None:
    async with async_session() as db:
        workspace = (await db.execute(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.user_id == user_id,
            )
        )).scalar_one_or_none()
        if workspace is None:
            return None
        row = (await db.execute(
            select(WorkspaceItem).where(
                WorkspaceItem.id == item_id,
                WorkspaceItem.workspace_id == workspace_id,
            )
        )).scalar_one_or_none()
        if row is None:
            return None
        for key, value in values.items():
            if hasattr(row, key):
                setattr(row, key, value)
        await db.commit()
        await db.refresh(row)
        return {
            "id": row.id,
            "type": row.type,
            "key": row.key,
            "content": row.content,
            "source": row.source,
            "confidence": row.confidence,
            "created_by": row.created_by,
        }


async def delete_item(user_id: int, workspace_id: int, item_id: int) -> bool:
    async with async_session() as db:
        workspace = (await db.execute(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.user_id == user_id,
            )
        )).scalar_one_or_none()
        if workspace is None:
            return False
        row = (await db.execute(
            select(WorkspaceItem).where(
                WorkspaceItem.id == item_id,
                WorkspaceItem.workspace_id == workspace_id,
            )
        )).scalar_one_or_none()
        if row is None:
            return False
        await db.delete(row)
        await db.commit()
        return True


async def add_artifact(
    user_id: int,
    workspace_id: int,
    *,
    file_id: int | None = None,
    kind: str = "draft",
) -> dict | None:
    async with async_session() as db:
        workspace = (await db.execute(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.user_id == user_id,
            )
        )).scalar_one_or_none()
        if workspace is None:
            return None
        row = WorkspaceArtifact(
            workspace_id=workspace_id,
            file_id=file_id,
            kind=kind[:24],
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return {"id": row.id, "file_id": row.file_id, "kind": row.kind}


async def export_zip(user_id: int, workspace_id: int) -> bytes | None:
    view = await workspace_view(user_id, workspace_id)
    if view is None:
        return None

    async with async_session() as db:
        goal = (await db.execute(
            select(Goal).where(Goal.id == view["goal_id"], Goal.user_id == user_id)
        )).scalar_one_or_none()
        tasks = list((await db.execute(
            select(Task).where(Task.goal_id == view["goal_id"]).order_by(Task.sort_order, Task.id)
        )).scalars().all())

    goal_md = ""
    plan = {}
    if goal is not None:
        goal_md = (
            f"# {goal.title}\n\n"
            f"- 状态：{goal.status}\n"
            f"- 优先级：{goal.priority}\n"
            f"- 截止：{goal.due_at.isoformat() if goal.due_at else '未设置'}\n\n"
            f"{goal.description or ''}\n\n"
            f"## 成功标准\n```json\n{json.dumps(goal.success_criteria, ensure_ascii=False, indent=2, default=str)}\n```\n"
        )
        plan = {
            "goal_id": goal.id,
            "title": goal.title,
            "status": goal.status,
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "agent_profile_key": t.agent_profile_key,
                    "depends_on": t.depends_on,
                    "acceptance": t.acceptance,
                }
                for t in tasks
            ],
        }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("goal.md", goal_md or "# Workspace\n")
        zf.writestr("plan.json", json.dumps(plan, ensure_ascii=False, indent=2, default=str))
        items = "\n".join(
            json.dumps(item, ensure_ascii=False, default=str) for item in view["items"]
        )
        zf.writestr("items.jsonl", items + ("\n" if items else ""))
        zf.writestr(
            "artifacts.json",
            json.dumps(view["artifacts"], ensure_ascii=False, indent=2, default=str),
        )
        zf.writestr(
            "README.md",
            f"导出时间：{datetime.now().isoformat(timespec='seconds')}\n\n"
            "这是工作区的只读导出，不是数据源。\n",
        )
    return buf.getvalue()
