from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from plugins.todo.backend.models import PluginTodoItem
from plugins.todo.backend.schemas import TodoCreate, TodoUpdate


async def create_todo(db: AsyncSession, user_id: int, req: TodoCreate) -> PluginTodoItem:
    todo = PluginTodoItem(
        user_id=user_id,
        title=req.title,
        description=req.description,
        priority=req.priority,
        due_date=datetime.fromisoformat(req.due_date) if req.due_date else None,
        tags=req.tags,
    )
    db.add(todo)
    await db.flush()
    return todo


async def get_todos(
    db: AsyncSession, user_id: int, status: str | None = None, page: int = 1, page_size: int = 50
) -> tuple[list[PluginTodoItem], int]:
    query = select(PluginTodoItem).where(PluginTodoItem.user_id == user_id)

    if status:
        query = query.where(PluginTodoItem.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(PluginTodoItem.priority.desc(), PluginTodoItem.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    return list(result.scalars().all()), total


async def get_todo(db: AsyncSession, user_id: int, todo_id: int) -> PluginTodoItem | None:
    result = await db.execute(
        select(PluginTodoItem).where(
            PluginTodoItem.id == todo_id,
            PluginTodoItem.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def update_todo(db: AsyncSession, user_id: int, todo_id: int, req: TodoUpdate) -> PluginTodoItem:
    todo = await get_todo(db, user_id, todo_id)
    if not todo:
        raise ValueError("Todo not found")

    if req.title is not None:
        todo.title = req.title
    if req.description is not None:
        todo.description = req.description
    if req.status is not None:
        todo.status = req.status
    if req.priority is not None:
        todo.priority = req.priority
    if req.due_date is not None:
        todo.due_date = datetime.fromisoformat(req.due_date) if req.due_date else None
    if req.tags is not None:
        todo.tags = req.tags

    await db.flush()
    return todo


async def delete_todo(db: AsyncSession, user_id: int, todo_id: int):
    todo = await get_todo(db, user_id, todo_id)
    if not todo:
        raise ValueError("Todo not found")
    await db.delete(todo)
    await db.flush()
