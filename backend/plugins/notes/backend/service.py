from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from plugins.notes.backend.models import PluginNote
from plugins.notes.backend.schemas import NoteCreate, NoteUpdate


async def create_note(db: AsyncSession, user_id: int, req: NoteCreate) -> PluginNote:
    note = PluginNote(
        user_id=user_id,
        title=req.title,
        content=req.content,
        parent_id=req.parent_id,
        is_folder=1 if req.is_folder else 0,
        icon=req.icon,
    )
    db.add(note)
    await db.flush()
    await db.refresh(note)
    return note


async def get_notes(
    db: AsyncSession, user_id: int, parent_id: int | None = None
) -> list[PluginNote]:
    query = select(PluginNote).where(PluginNote.user_id == user_id)
    if parent_id is not None:
        query = query.where(PluginNote.parent_id == parent_id)
    else:
        query = query.where(PluginNote.parent_id.is_(None))
    query = query.order_by(PluginNote.sort_order, PluginNote.updated_at.desc())
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
    if req.title is not None: note.title = req.title
    if req.content is not None: note.content = req.content
    if req.parent_id is not None: note.parent_id = req.parent_id
    if req.is_folder is not None: note.is_folder = 1 if req.is_folder else 0
    if req.icon is not None: note.icon = req.icon
    if req.sort_order is not None: note.sort_order = req.sort_order
    await db.flush()
    await db.refresh(note)
    return note


async def delete_note(db: AsyncSession, user_id: int, note_id: int):
    note = await get_note(db, user_id, note_id)
    if not note:
        raise ValueError("Note not found")
    # Delete children
    children = await db.execute(
        select(PluginNote).where(PluginNote.parent_id == note_id)
    )
    for child in children.scalars().all():
        await db.delete(child)
    await db.delete(note)
    await db.flush()


async def get_tree(db: AsyncSession, user_id: int) -> list[dict]:
    """Get full note tree structure."""
    result = await db.execute(
        select(PluginNote).where(PluginNote.user_id == user_id).order_by(PluginNote.sort_order, PluginNote.updated_at.desc())
    )
    all_notes = list(result.scalars().all())
    notes_dict = {n.id: {
        "id": n.id, "title": n.title, "parent_id": n.parent_id,
        "is_folder": bool(n.is_folder), "icon": n.icon,
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
    note = await get_note(db, user_id, note_id)
    if not note:
        raise ValueError("Note not found")
    note.parent_id = parent_id
    if sort_order is not None:
        note.sort_order = sort_order
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
        PluginNote.title.ilike(f"%{query}%")
    ).order_by(PluginNote.updated_at.desc()).limit(20)
    result = await db.execute(q)
    return list(result.scalars().all())
