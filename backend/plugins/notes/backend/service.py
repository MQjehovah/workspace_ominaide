import asyncio
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from core.ai.indexer import index_content
from plugins.notes.backend.models import PluginNote
from plugins.notes.backend.schemas import NoteCreate, NoteUpdate
from plugins.notes.backend.content_text import note_content_to_text
from plugins.notes.backend.rag import index_note_rag, delete_note_rag


def _index_text(content: str | None) -> str:
    """Convert stored content (JSON/markdown/html) to readable text for AI indexing."""
    return note_content_to_text(content)


# Bulk imports can queue hundreds of notes at once. Without a cap every note
# opens its own DB session in the background and exhausts the connection pool.
_INDEX_SEMAPHORE = asyncio.Semaphore(2)


async def _run_index(coro) -> None:
    async with _INDEX_SEMAPHORE:
        try:
            await coro
        except Exception:
            pass


def _schedule_rag_index(user_id: int, note: PluginNote) -> None:
    """Index chunks/terms in the background; never blocks the save request."""
    if note.is_folder:
        return
    asyncio.create_task(_run_index(index_note_rag(
        user_id, note.id, note.title, note.content
    )))


async def create_note(db: AsyncSession, user_id: int, req: NoteCreate,
                      *, defer_index: bool = False) -> PluginNote:
    if req.parent_id is not None:
        parent = await db.get(PluginNote, req.parent_id)
        if not parent or parent.user_id != user_id:
            raise ValueError("Parent note not found")
    # Assign next sort_order among siblings so order is stable (new notes go last).
    sib_query = select(func.coalesce(func.max(PluginNote.sort_order), -1)).where(
        PluginNote.user_id == user_id,
        PluginNote.parent_id.is_(None) if req.parent_id is None else PluginNote.parent_id == req.parent_id,
    )
    sib_result = await db.execute(sib_query)
    max_order = sib_result.scalar() or -1

    note = PluginNote(
        user_id=user_id,
        title=req.title,
        content=req.content,
        parent_id=req.parent_id,
        is_folder=1 if req.is_folder else 0,
        icon=req.icon,
        sort_order=max_order + 1,
    )
    db.add(note)
    await db.flush()
    await db.refresh(note)

    if not note.is_folder and not defer_index:
        asyncio.create_task(_run_index(index_content(
            user_id=user_id,
            source_type='note',
            source_id=note.id,
            title=note.title,
            content=_index_text(note.content),
            metadata={"link": f"/notes/{note.id}"},
        )))
        _schedule_rag_index(user_id, note)

    return note


async def get_notes(
    db: AsyncSession, user_id: int, parent_id: int | None = None
) -> list[PluginNote]:
    query = select(PluginNote).where(PluginNote.user_id == user_id)
    if parent_id is not None:
        query = query.where(PluginNote.parent_id == parent_id)
    else:
        query = query.where(PluginNote.parent_id.is_(None))
    query = query.order_by(PluginNote.sort_order, PluginNote.id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_note(db: AsyncSession, user_id: int, note_id: int) -> PluginNote | None:
    result = await db.execute(
        select(PluginNote).where(PluginNote.id == note_id, PluginNote.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_note(
    db: AsyncSession, user_id: int, note_id: int, req: NoteUpdate
) -> PluginNote:
    note = await get_note(db, user_id, note_id)
    if not note:
        raise ValueError("Note not found")
    # Snapshot previous state before applying changes (page history)
    if not note.is_folder and (req.content is not None or req.title is not None):
        changed = (req.content is not None and (req.content or "") != (note.content or "")) or \
                  (req.title is not None and (req.title or "") != (note.title or ""))
        if changed:
            await snapshot_version(db, user_id, note_id, note)
    if req.title is not None: note.title = req.title
    if req.content is not None: note.content = req.content
    if req.parent_id is not None: note.parent_id = req.parent_id
    if req.is_folder is not None: note.is_folder = 1 if req.is_folder else 0
    if req.icon is not None: note.icon = req.icon
    if req.sort_order is not None: note.sort_order = req.sort_order
    await db.flush()
    await db.refresh(note)

    if not note.is_folder:
        asyncio.create_task(_run_index(index_content(
            user_id=user_id,
            source_type='note',
            source_id=note.id,
            title=note.title,
            content=_index_text(note.content),
            metadata={"link": f"/notes/{note.id}"},
        )))
        _schedule_rag_index(user_id, note)

    return note


async def snapshot_version(db: AsyncSession, user_id: int, note_id: int, note: PluginNote):
    """Save a snapshot of the note's current state as a new version."""
    from plugins.notes.backend.models import NoteVersion
    from sqlalchemy import func
    r = await db.execute(
        select(func.coalesce(func.max(NoteVersion.version), 0)).where(NoteVersion.note_id == note_id)
    )
    next_version = (r.scalar() or 0) + 1
    db.add(NoteVersion(
        note_id=note_id,
        user_id=user_id,
        title=note.title,
        content=note.content,
        version=next_version,
    ))
    # keep last 50 versions
    r2 = await db.execute(
        select(NoteVersion.id).where(NoteVersion.note_id == note_id).order_by(NoteVersion.version.desc()).offset(50)
    )
    for old_id in r2.scalars().all():
        old = await db.get(NoteVersion, old_id)
        if old:
            await db.delete(old)


async def list_versions(db: AsyncSession, user_id: int, note_id: int) -> list[dict]:
    from plugins.notes.backend.models import NoteVersion
    note = await get_note(db, user_id, note_id)
    if not note:
        raise ValueError("Note not found")
    r = await db.execute(
        select(NoteVersion).where(NoteVersion.note_id == note_id).order_by(NoteVersion.version.desc()).limit(50)
    )
    vs = r.scalars().all()
    return [{
        "id": v.id,
        "version": v.version,
        "title": v.title or note.title,
        "created_at": str(v.created_at),
    } for v in vs]


async def get_version(db: AsyncSession, user_id: int, note_id: int, version_id: int) -> dict:
    from plugins.notes.backend.models import NoteVersion
    note = await get_note(db, user_id, note_id)
    if not note:
        raise ValueError("Note not found")
    r = await db.execute(
        select(NoteVersion).where(NoteVersion.id == version_id, NoteVersion.note_id == note_id)
    )
    v = r.scalar_one_or_none()
    if not v:
        raise ValueError("Version not found")
    return {"id": v.id, "version": v.version, "title": v.title or note.title, "content": v.content or "", "created_at": str(v.created_at)}


async def restore_version(db: AsyncSession, user_id: int, note_id: int, version_id: int) -> PluginNote:
    """Restore note content to a previous version (creates a new version snapshot of current state first)."""
    note = await get_note(db, user_id, note_id)
    if not note:
        raise ValueError("Note not found")
    v = await get_version(db, user_id, note_id, version_id)
    await snapshot_version(db, user_id, note_id, note)
    note.title = v["title"] or note.title
    note.content = v["content"]
    await db.flush()
    await db.refresh(note)
    if not note.is_folder:
        asyncio.create_task(_run_index(index_content(
            user_id=user_id,
            source_type='note',
            source_id=note.id,
            title=note.title,
            content=_index_text(note.content),
            metadata={"link": f"/notes/{note.id}"},
        )))
        _schedule_rag_index(user_id, note)
    return note


async def delete_note(db: AsyncSession, user_id: int, note_id: int):
    note = await get_note(db, user_id, note_id)
    if not note:
        raise ValueError("Note not found")

    # Collect the whole subtree so RAG chunks/terms don't outlive their notes.
    all_ids: list[int] = [note.id]
    frontier = [note.id]
    while frontier:
        children = await db.execute(
            select(PluginNote).where(PluginNote.parent_id.in_(frontier))
        )
        rows = list(children.scalars().all())
        frontier = [c.id for c in rows]
        all_ids.extend(frontier)

    from plugins.notes.backend.models import NoteVersion
    from sqlalchemy import delete as _delete
    await db.execute(_delete(NoteVersion).where(NoteVersion.note_id.in_(all_ids)))
    await delete_note_rag(db, all_ids)
    # Delete deepest children first: the self-referential FK has no ON DELETE
    # CASCADE, so removing a parent before its children violates the constraint.
    for nid in reversed(all_ids):
        obj = await db.get(PluginNote, nid)
        if obj:
            await db.delete(obj)
            await db.flush()
    try:
        from core.ai import vector_store

        for nid in all_ids:
            await vector_store.delete_source(user_id, "note", nid)
    except Exception:
        pass


async def get_tree(db: AsyncSession, user_id: int) -> list[dict]:
    """Get full note tree structure."""
    result = await db.execute(
        select(PluginNote).where(PluginNote.user_id == user_id).order_by(PluginNote.sort_order, PluginNote.id)
    )
    all_notes = list(result.scalars().all())
    notes_dict = {n.id: {
        "id": n.id, "title": n.title, "parent_id": n.parent_id,
        "is_folder": bool(n.is_folder), "icon": n.icon,
        "sort_order": n.sort_order or 0,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
        "children": [],
    } for n in all_notes}
    roots = []
    for note_id, note in notes_dict.items():
        parent_id = note["parent_id"]
        if parent_id and parent_id in notes_dict:
            notes_dict[parent_id]["children"].append(note)
        else:
            roots.append(note)
    return roots


async def move_note(db: AsyncSession, user_id: int, note_id: int, parent_id: int | None, sort_order: int | None = None):
    """Move/reorder a note; sort_order is the target index among siblings."""
    note = await get_note(db, user_id, note_id)
    if not note:
        raise ValueError("Note not found")
    if parent_id == note.id:
        raise ValueError("Cannot move a note into itself")

    if parent_id is not None:
        parent = await get_note(db, user_id, parent_id)
        if not parent:
            raise ValueError("Target note not found")
        # Any note can be a tree parent; only prevent cycles.
        frontier = [note.id]
        seen = {note.id}
        while frontier:
            rows = await db.execute(
                select(PluginNote).where(PluginNote.parent_id.in_(frontier))
            )
            children = list(rows.scalars().all())
            frontier = [c.id for c in children if c.id not in seen]
            seen.update(frontier)
            if parent_id in seen:
                raise ValueError("Cannot move a note into its descendant")

    old_parent = note.parent_id
    if old_parent != parent_id:
        old_q = select(PluginNote).where(
            PluginNote.user_id == user_id,
            PluginNote.id != note_id,
            PluginNote.parent_id.is_(None) if old_parent is None else PluginNote.parent_id == old_parent,
        ).order_by(PluginNote.sort_order, PluginNote.id)
        old_siblings = list((await db.execute(old_q)).scalars().all())
        for i, item in enumerate(old_siblings):
            item.sort_order = i

    new_q = select(PluginNote).where(
        PluginNote.user_id == user_id,
        PluginNote.id != note_id,
        PluginNote.parent_id.is_(None) if parent_id is None else PluginNote.parent_id == parent_id,
    ).order_by(PluginNote.sort_order, PluginNote.id)
    siblings = list((await db.execute(new_q)).scalars().all())
    index = len(siblings) if sort_order is None else max(0, min(int(sort_order), len(siblings)))
    ordered = siblings[:index] + [note] + siblings[index:]
    note.parent_id = parent_id
    for i, item in enumerate(ordered):
        item.sort_order = i

    await db.flush()
    await db.refresh(note)
    return note


async def search_notes(
    db: AsyncSession, user_id: int, query: str
) -> list[PluginNote]:
    q = select(PluginNote).where(
        PluginNote.user_id == user_id,
        PluginNote.is_folder == 0,
    ).where(
        or_(
            PluginNote.title.ilike(f"%{query}%"),
            PluginNote.content.ilike(f"%{query}%"),
        )
    ).order_by(PluginNote.updated_at.desc()).limit(20)
    result = await db.execute(q)
    return list(result.scalars().all())
