"""CRUD for generic business-object comments and materials."""

from __future__ import annotations

from core.logging import get_logger
log = get_logger(__name__)

import asyncio
from datetime import datetime

from sqlalchemy import select

from core.database.session import async_session
from core.objects.models import BusinessComment
from core.objects.registry import OBJECT_TYPES, resolve_object

COMMENT_KINDS = {"comment", "note", "material", "ai_summary"}


class ObjectCommentError(ValueError):
    pass


def comment_out(row: BusinessComment) -> dict:
    return {
        "id": row.id,
        "object_type": row.object_type,
        "object_id": row.object_id,
        "parent_id": row.parent_id,
        "root_id": row.root_id,
        "kind": row.kind,
        "title": row.title,
        "content": row.content,
        "author": row.author,
        "session_id": row.session_id,
        "message_id": row.message_id,
        "metadata": row.meta or {},
        "deleted": row.deleted_at is not None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def list_comments(
    user_id: int,
    object_type: str,
    object_id: int,
    *,
    include_deleted: bool = False,
    limit: int = 300,
) -> list[BusinessComment]:
    async with async_session() as db:
        q = select(BusinessComment).where(
            BusinessComment.user_id == user_id,
            BusinessComment.object_type == object_type,
            BusinessComment.object_id == object_id,
        )
        if not include_deleted:
            q = q.where(BusinessComment.deleted_at.is_(None))
        q = q.order_by(BusinessComment.created_at, BusinessComment.id).limit(max(1, min(limit, 500)))
        return list((await db.execute(q)).scalars().all())


async def create_comment(
    user_id: int,
    object_type: str,
    object_id: int,
    *,
    content: str,
    kind: str = "comment",
    title: str | None = None,
    author: str = "user",
    parent_id: int | None = None,
    session_id: str | None = None,
    message_id: int | None = None,
    metadata: dict | None = None,
) -> dict:
    content = (content or "").strip()
    if not content:
        raise ObjectCommentError("评论内容不能为空")
    if len(content) > 20000:
        raise ObjectCommentError("评论内容不能超过 20000 字")
    kind = kind if kind in COMMENT_KINDS else "comment"
    obj = await resolve_object(user_id, object_type, object_id)
    if obj is None:
        raise ObjectCommentError("对象不存在或无权限")

    async with async_session() as db:
        parent = None
        if parent_id:
            parent = (await db.execute(
                select(BusinessComment).where(
                    BusinessComment.id == int(parent_id),
                    BusinessComment.user_id == user_id,
                    BusinessComment.object_type == object_type,
                    BusinessComment.object_id == object_id,
                    BusinessComment.deleted_at.is_(None),
                )
            )).scalar_one_or_none()
            if parent is None:
                raise ObjectCommentError("要回复的评论不存在")

        row = BusinessComment(
            user_id=user_id,
            object_type=object_type,
            object_id=object_id,
            parent_id=parent.id if parent else None,
            root_id=(parent.root_id or parent.id) if parent else None,
            kind=kind,
            title=(title or "").strip()[:300] or None,
            content=content,
            author="assistant" if author == "assistant" else "user",
            session_id=session_id,
            message_id=message_id,
            meta=metadata or None,
        )
        db.add(row)
        await db.flush()
        if row.root_id is None:
            row.root_id = row.id
            await db.flush()
        await db.refresh(row)

        try:
            from core.events.bus import record_event

            action = "replied" if parent else "created"
            await record_event(
                db, user_id, f"object.comment.{action}", object_type, object_id,
                f"{'回复' if parent else '评论'} {OBJECT_TYPES.get(object_type, object_type)}: {obj['title'][:60]}",
                {
                    "object_type": object_type,
                    "object_id": object_id,
                    "object_title": obj["title"],
                    "comment_id": row.id,
                    "parent_id": row.parent_id,
                    "kind": row.kind,
                    "author": row.author,
                    "title": row.title,
                    "preview": content[:500],
                    "session_id": session_id,
                    "link": obj.get("url"),
                },
            )
            await db.commit()
        except Exception as e:
            log.warning(f"[objects] comment event failed: {e}")
            await db.commit()

    _index_comment(user_id, row, obj)
    return comment_out(row)


async def update_comment(
    user_id: int,
    comment_id: int,
    *,
    content: str | None = None,
    title: str | None = None,
) -> dict | None:
    async with async_session() as db:
        row = (await db.execute(
            select(BusinessComment).where(
                BusinessComment.id == comment_id,
                BusinessComment.user_id == user_id,
                BusinessComment.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if row is None:
            return None
        if content is not None:
            content = content.strip()
            if not content:
                raise ObjectCommentError("评论内容不能为空")
            row.content = content[:20000]
        if title is not None:
            row.title = title.strip()[:300] or None
        row.updated_at = datetime.now()
        await db.flush()
        await db.refresh(row)
        try:
            from core.events.bus import record_event

            await record_event(
                db, user_id, "object.comment.updated", row.object_type, row.object_id,
                f"修改评论 #{row.id}",
                {"comment_id": row.id, "object_type": row.object_type,
                 "object_id": row.object_id, "preview": row.content[:500]},
            )
            await db.commit()
        except Exception:
            await db.commit()

    obj = await resolve_object(user_id, row.object_type, row.object_id)
    if obj is not None:
        _index_comment(user_id, row, obj)
    return comment_out(row)


async def delete_comment(user_id: int, comment_id: int) -> bool:
    async with async_session() as db:
        row = (await db.execute(
            select(BusinessComment).where(
                BusinessComment.id == comment_id,
                BusinessComment.user_id == user_id,
                BusinessComment.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if row is None:
            return False
        row.deleted_at = datetime.now()
        try:
            from core.events.bus import record_event

            await record_event(
                db, user_id, "object.comment.deleted", row.object_type, row.object_id,
                f"删除评论 #{row.id}",
                {"comment_id": row.id, "object_type": row.object_type,
                 "object_id": row.object_id, "preview": (row.content or "")[:300]},
            )
        except Exception:
            pass
        await db.commit()

    try:
        from core.ai import vector_store

        await vector_store.delete_source(user_id, "object_comment", comment_id)
    except Exception:
        pass
    return True


def _index_comment(user_id: int, row: BusinessComment, obj: dict) -> None:
    """Best-effort RAG indexing so the agent can recall saved materials."""
    try:
        from core.ai.indexer import index_content

        title = f"{obj['title']} - {row.title or row.kind}"
        asyncio.create_task(index_content(
            user_id=user_id,
            source_type="object_comment",
            source_id=row.id,
            title=title[:200],
            content=(row.content or "")[:8000],
            metadata={
                "object_type": row.object_type,
                "object_id": row.object_id,
                "object_title": obj["title"],
                "kind": row.kind,
                "author": row.author,
                "link": obj.get("url"),
                "session_id": row.session_id,
            },
        ))
    except Exception as e:
        log.warning(f"[objects] comment indexing failed: {e}")
