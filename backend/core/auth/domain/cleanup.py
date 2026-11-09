"""Delete a user's runtime data, storage and database rows.

This is intentionally explicit and idempotent. It runs as a background job so a
large file tree or object store does not block the admin request.
"""

from __future__ import annotations

import asyncio
import shutil

from sqlalchemy import delete, select, update

from core.auth.domain.models import User
from ai.bots.models import Bot, Approval, BotMemory, BotRoutine, Run, RunStep
from ai.skills.models import BotSkill
from ai.automation.models import AutomationRun
from core.database.session import async_session
from core.logging import get_logger
from ai.mcp_hub.models import McpServer, McpTool
from app.objects.models import BusinessComment
from core.paths import is_within, user_root, workspace_root
from plugins.files.backend.models import File
from plugins.music.backend.models import Playlist, PlaylistItem
from plugins.sources.backend.models import ContentItem, ContentSource

logger = get_logger(__name__)


async def _user_exists(user_id: int) -> bool:
    async with async_session() as db:
        return (
            await db.execute(select(User.id).where(User.id == user_id))
        ).scalar_one_or_none() is not None


async def _stop_runtime(user_id: int) -> None:
    """Cancel work that could write data while deletion is in progress."""
    # Active bot/coding runs poll the DB for cancellation.
    try:
        from ai.bots.runner import cancel_run

        async with async_session() as db:
            run_ids = list((await db.execute(
                select(Run.id).where(
                    Run.user_id == user_id,
                    Run.status.notin_(("done", "failed", "cancelled")),
                )
            )).scalars().all())
        for run_id in run_ids:
            try:
                await cancel_run(user_id, run_id)
            except Exception as exc:
                logger.warning("cancel run %s failed: %s", run_id, exc)
    except Exception as exc:
        logger.warning("cancel runs failed: %s", exc)

    # Cancel queued/running jobs owned by the user.
    try:
        from core.jobs.models import BackgroundJob

        async with async_session() as db:
            await db.execute(
                update(BackgroundJob)
                .where(
                    BackgroundJob.user_id == user_id,
                    BackgroundJob.status.in_(("queued", "running")),
                )
                .values(status="cancelled", locked_at=None)
            )
            await db.commit()
    except Exception as exc:
        logger.warning("cancel jobs failed: %s", exc)

    # Stop MCP child processes and remove their tools from the registry.
    try:
        from ai.mcp_hub.hub import mcp_hub

        async with async_session() as db:
            server_ids = list((await db.execute(
                select(McpServer.id).where(McpServer.user_id == user_id)
            )).scalars().all())
        for server_id in server_ids:
            try:
                await mcp_hub.disconnect_server(server_id)
            except Exception as exc:
                logger.warning("disconnect mcp %s failed: %s", server_id, exc)
    except Exception as exc:
        logger.warning("disconnect mcps failed: %s", exc)

    # Stop a pending DingTalk device-flow login process.
    try:
        from plugins.dingtalk.backend.service import cancel_login

        cancel_login(user_id)
    except Exception as exc:
        logger.debug("cancel dingtalk login for user %s failed: %s", user_id, exc)


async def _collect_file_keys(user_id: int) -> set[tuple[str, str]]:
    async with async_session() as db:
        rows = (await db.execute(
            select(File.bucket, File.object_key).where(File.user_id == user_id)
        )).all()
    return {(str(bucket), str(key)) for bucket, key in rows if bucket and key}


def _remove_minio_objects(user_id: int, file_keys: set[tuple[str, str]]) -> list[str]:
    """Best-effort object cleanup. Returns a list of error strings."""
    errors: list[str] = []
    try:
        from core.minio import client as minio_module

        client = minio_module.minio_client
        if client is None:
            return ["minio unavailable"]
    except Exception as exc:
        return [f"minio init: {exc}"]

    buckets = {
        "user-files", "music", "videos", "documents", "thumbnails",
        *(bucket for bucket, _ in file_keys),
    }
    keys = set(file_keys)
    prefixes = (f"{user_id}/", f"folder:{user_id}/")
    for bucket in buckets:
        for prefix in prefixes:
            try:
                for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
                    name = getattr(obj, "object_name", None)
                    if name:
                        keys.add((bucket, str(name)))
            except Exception as exc:
                errors.append(f"list {bucket}/{prefix}: {str(exc)[:200]}")
    for bucket, key in keys:
        try:
            client.remove_object(bucket, key)
        except Exception as exc:
            errors.append(f"remove {bucket}/{key}: {str(exc)[:200]}")
    return errors[:20]


async def _delete_storage(user_id: int, file_keys: set[tuple[str, str]]) -> list[str]:
    try:
        return await asyncio.to_thread(_remove_minio_objects, user_id, file_keys)
    except Exception as exc:
        return [f"minio cleanup: {str(exc)[:200]}"]


async def _delete_workspace(user_id: int) -> bool:
    target = user_root(user_id)
    root = workspace_root().resolve()
    try:
        resolved = target.resolve()
    except OSError:
        resolved = target
    # Never follow a symlink or delete outside the workspace root.
    if target.is_symlink() or not is_within(root, resolved):
        raise RuntimeError(f"拒绝删除工作区外路径: {target}")
    if not target.exists():
        return False
    await asyncio.to_thread(shutil.rmtree, target, True)
    return True


async def _delete_embeddings(user_id: int) -> int:
    """Delete pgvector rows that live outside ``Base.metadata``.

    The table is created lazily by ``vector_store`` and older deployments may
    not have it, so a missing table must not abort user cleanup.
    """
    from core.database.session import engine
    from sqlalchemy import text

    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text("DELETE FROM embeddings WHERE user_id = :uid"),
                {"uid": user_id},
            )
            return int(result.rowcount or 0)
    except Exception as exc:
        logger.debug("embeddings cleanup skipped for user %s: %s", user_id, exc)
        return 0


async def _delete_db_rows(user_id: int) -> None:
    from core.database.base import Base

    async with async_session() as db:
        # Break self/optional references before deleting parents.
        await db.execute(
            update(Run)
            .where(Run.user_id == user_id)
            .values(parent_run_id=None, routine_id=None)
        )
        await db.execute(
            update(BusinessComment)
            .where(BusinessComment.user_id == user_id)
            .values(parent_id=None)
        )

        # Bot ownership graph. These rows all carry user_id, but deleting them
        # explicitly keeps the order safe even if a child table was added
        # without a cascade or the generic loop changes.
        await db.execute(
            delete(Approval).where(Approval.user_id == user_id)
        )
        await db.execute(
            delete(AutomationRun).where(AutomationRun.user_id == user_id)
        )
        await db.execute(
            delete(RunStep).where(
                RunStep.run_id.in_(
                    select(Run.id).where(Run.user_id == user_id)
                )
            )
        )
        await db.execute(delete(BotSkill).where(BotSkill.user_id == user_id))
        await db.execute(delete(BotMemory).where(BotMemory.user_id == user_id))
        await db.execute(delete(BotRoutine).where(BotRoutine.user_id == user_id))
        await db.execute(delete(Run).where(Run.user_id == user_id))
        await db.execute(delete(Bot).where(Bot.user_id == user_id))
        await db.execute(
            delete(McpTool).where(
                McpTool.server_id.in_(
                    select(McpServer.id).where(McpServer.user_id == user_id)
                )
            )
        )
        await db.execute(
            delete(PlaylistItem).where(
                PlaylistItem.playlist_id.in_(
                    select(Playlist.id).where(Playlist.user_id == user_id)
                )
            )
        )
        await db.execute(
            delete(PlaylistItem).where(
                PlaylistItem.file_id.in_(
                    select(File.id).where(File.user_id == user_id)
                )
            )
        )
        await db.execute(
            delete(ContentItem).where(
                ContentItem.source_id.in_(
                    select(ContentSource.id).where(ContentSource.user_id == user_id)
                )
            )
        )

        # Everything that has a direct user_id. Reverse dependency order means
        # children go before their parents.
        for table in reversed(Base.metadata.sorted_tables):
            if "user_id" in table.c:
                await db.execute(
                    delete(table).where(table.c.user_id == user_id)
                )

        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def delete_user_data(user_id: int) -> dict:
    """Delete one user's data. Safe to call again after a partial failure."""
    user_id = int(user_id)
    exists = await _user_exists(user_id)
    result: dict = {
        "user_id": user_id,
        "found": exists,
        "workspace_deleted": False,
        "objects_seen": 0,
        "storage_errors": [],
        "already_deleted": not exists,
    }

    file_keys: set[tuple[str, str]] = set()
    if exists:
        await _stop_runtime(user_id)
        file_keys = await _collect_file_keys(user_id)

    result["objects_seen"] = len(file_keys)
    result["storage_errors"] = await _delete_storage(user_id, file_keys)
    result["workspace_deleted"] = await _delete_workspace(user_id)

    if exists:
        result["embeddings_deleted"] = await _delete_embeddings(user_id)
        await _delete_db_rows(user_id)

    return result


async def _handle_admin_user_delete(job) -> dict:
    payload = job.payload or {}
    target_user_id = payload.get("target_user_id")
    if target_user_id is None:
        raise ValueError("target_user_id 缺失")
    result = await delete_user_data(int(target_user_id))
    logger.info(
        "job %s deleted user %s: workspace=%s objects=%s embeddings=%s errors=%s",
        job.id, target_user_id, result["workspace_deleted"],
        result["objects_seen"], result.get("embeddings_deleted", 0),
        len(result["storage_errors"]),
    )
    return result


def register_cleanup_handlers() -> None:
    from core.jobs.service import register_handler

    register_handler("admin.user_delete", _handle_admin_user_delete)
