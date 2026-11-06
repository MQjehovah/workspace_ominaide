"""Activity recorder middleware — auto-records all mutating API operations."""
import re
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from core.auth.jwt import decode_access_token


def _derive_event_type(method: str, path: str) -> str:
    """Derive event_type from HTTP method and path.
    e.g. POST /api/notes → note.created, DELETE /api/todo/items/5 → todo.deleted
    """
    # Strip leading /api/ or /plugins/
    p = re.sub(r'^/(?:api/)?(?:plugins/)?', '', path)
    # Remove IDs and trailing slashes
    p = re.sub(r'/\d+(/|$)', r'\1', p).rstrip('/')
    # Take first two path segments as entity
    parts = p.split('/')
    if len(parts) >= 2:
        entity = parts[0]
        action = parts[1]
    else:
        entity = parts[0] if parts else 'unknown'
        action = ''

    verb_map = {'POST': 'created', 'PUT': 'updated', 'PATCH': 'updated', 'DELETE': 'deleted'}
    verb = verb_map.get(method, 'unknown')

    if action in ('created', 'updated', 'deleted', 'move', 'toggle', 'read', 'star'):
        verb = action
        entity = parts[0] if parts else 'unknown'
    elif action and action != entity:
        entity = f"{entity}.{action}"

    return f"{entity}.{verb}"


def _make_summary(method: str, path: str, event_type: str) -> str:
    """Generate a human-readable summary from the HTTP method and path."""
    # Strip /api/ prefix
    p = re.sub(r'^/(?:api/)?(?:plugins/)?', '', path)
    # Remove IDs
    p = re.sub(r'/\d+', '/{id}', p).rstrip('/')

    labels = {
        'post': '创建', 'put': '修改', 'patch': '修改', 'delete': '删除',
    }
    verb = labels.get(method.lower(), method)
    suffix = path.rstrip('/')

    if 'read' in path.lower():
        verb = '标记已读'

    special = {
        'bots.created': '创建 Bot',
        'bots.updated': '修改 Bot',
        'bots.deleted': '删除 Bot',
        'bots.routines.created': '创建 Bot 例行任务',
        'bots.routines.updated': '修改 Bot 例行任务',
        'bots.routines.deleted': '删除 Bot 例行任务',
        'bots.runs.created': '启动 Bot 运行',
        'bots.memories.created': '添加 Bot 记忆',
        'bots.memories.deleted': '删除 Bot 记忆',
        'automation.from-template.created': '从模板创建自动化任务',
        'mcp.servers.created': '添加 MCP 服务',
        'mcp.servers.updated': '修改 MCP 服务',
        'mcp.servers.deleted': '删除 MCP 服务',
        'runs.cancel.created': '取消 Bot 运行',
        'projects.created': '创建项目',
        'projects.deleted': '删除项目',
        'projects.scan.created': '扫描项目',
        'projects.runs.created': '启动项目任务',
        'device.briefing.created': '触发简报',
        'device.tts.created': '语音播报',
        'device.gesture.created': '手势控制',
        'memory.candidates.created': '审核记忆候选',
    }
    if event_type in special:
        if event_type == 'bots.routines.created' and suffix.endswith('/run'):
            return '运行 Bot 例行任务'
        if event_type == 'mcp.servers.created' and suffix.endswith('/connect'):
            return '连接 MCP 服务'
        if event_type == 'mcp.servers.created' and suffix.endswith('/disconnect'):
            return '断开 MCP 服务'
        return special[event_type]

    # Fall back to the route path: enough context for the agent without
    # repeating the event type in both the title and the type column.
    return f"{verb} {p}" if p else verb


SKIP_PATHS = (
    '/health', '/api/auth', '/api/chat', '/api/remote', '/ws',
    '/api/rss',             # rss plugin records its own events
    '/api/notifications',   # notification read markers are high-frequency noise
    '/api/sync',            # sync operations
    '/api/files',           # file plugin records its own events
    '/api/plugins/notes',   # notes plugin records its own events
    '/api/plugins/todo',    # todo plugin records its own events
    '/api/plugins/mail',    # mail plugin records its own events
    '/api/schedule',        # schedule plugin records its own events
    '/api/music',           # music plugin records its own events
    '/api/search',          # search is a read operation
    '/api/activities',      # activity reporting is itself an event
    '/api/device',          # device polling/gestures are high-frequency
    '/api/mcp/call',        # MCP router records the tool name itself
    '/api/approvals',       # approvals router records the decision itself
    '/api/memory/candidates',  # memory router records approve/reject itself
)


def _is_skipped(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + '/') for prefix in SKIP_PATHS)


def _entity_ref(path: str) -> tuple[str | None, int | None]:
    p = re.sub(r'^/(?:api/)?(?:plugins/)?', '', path)
    parts = [part for part in p.split('/') if part]
    entity_type = parts[0] if parts else None
    match = re.search(r'/(\d+)(?=/|$)', path)
    entity_id = int(match.group(1)) if match else None
    return entity_type, entity_id


class ActivityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only record mutating operations
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return await call_next(request)

        path = request.url.path
        if _is_skipped(path):
            return await call_next(request)

        # Try to get user_id from token
        user_id = None
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            payload = decode_access_token(auth[7:])
            if payload:
                user_id = int(payload.get('sub', 0))

        # Let the request through
        response = await call_next(request)

        # Record activity
        if user_id and response.status_code < 400:
            event_type = _derive_event_type(request.method, path)
            summary = _make_summary(request.method, path, event_type)
            entity_type, entity_id = _entity_ref(path)
            details = {
                "method": request.method,
                "path": path,
                "status": response.status_code,
            }
            query = {
                str(key): str(value)[:200]
                for key, value in list(request.query_params.items())[:10]
            }
            if query:
                details["query"] = query
            try:
                from core.database.session import async_session
                from core.events.bus import record_event
                async with async_session() as db:
                    await record_event(
                        db=db,
                        user_id=user_id,
                        event_type=event_type,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        summary=summary,
                        details=details,
                    )
                    await db.commit()
            except Exception:
                pass

        return response
