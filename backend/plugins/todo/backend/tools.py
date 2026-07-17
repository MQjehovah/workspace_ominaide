"""MCP tool handlers for the Todo plugin."""

import json
from domains.mcp.core import MCPCallResponse, MCPContent
from domains.mcp.tools.plugin_tools import register_plugin_tool_handler


async def create_todo_item(user_id: int, args: dict) -> MCPCallResponse:
    """Create a new todo item via MCP."""
    title = args.get("title", "")
    if not title:
        return MCPCallResponse(isError=True, content=[MCPContent(text="title is required")])

    priority = args.get("priority", 0)
    description = args.get("description", "")

    from core.database.session import async_session
    from plugins.todo.backend.models import PluginTodoItem

    async with async_session() as db:
        todo = PluginTodoItem(
            user_id=user_id,
            title=title,
            description=description,
            priority=priority,
        )
        db.add(todo)
        await db.flush()
        await db.commit()

        result = {
            "id": todo.id,
            "title": todo.title,
            "priority": todo.priority,
            "status": todo.status,
            "created_at": todo.created_at.isoformat() if todo.created_at else None,
        }

    return MCPCallResponse(content=[MCPContent(text=json.dumps(result, ensure_ascii=False, default=str))])


async def list_todo_items(user_id: int, args: dict) -> MCPCallResponse:
    """List todo items via MCP."""
    status = args.get("status")

    from core.database.session import async_session
    from sqlalchemy import select
    from plugins.todo.backend.models import PluginTodoItem

    async with async_session() as db:
        q = select(PluginTodoItem).where(PluginTodoItem.user_id == user_id)
        if status:
            q = q.where(PluginTodoItem.status == status)
        q = q.order_by(PluginTodoItem.priority.desc(), PluginTodoItem.created_at.desc())
        result = await db.execute(q)
        todos = list(result.scalars().all())

    results = [
        {
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in todos
    ]

    return MCPCallResponse(content=[MCPContent(text=json.dumps(results, ensure_ascii=False, default=str))])


register_plugin_tool_handler("create_todo_item", create_todo_item)
register_plugin_tool_handler("list_todo_items", list_todo_items)
