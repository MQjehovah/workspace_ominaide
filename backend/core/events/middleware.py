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
    """Generate human-readable summary from HTTP method and path."""
    # Strip /api/ prefix
    p = re.sub(r'^/(?:api/)?(?:plugins/)?', '', path)
    # Remove IDs
    p = re.sub(r'/\d+', '/{id}', p).rstrip('/')

    labels = {
        'post': '创建', 'put': '修改', 'patch': '修改', 'delete': '删除',
    }
    verb = labels.get(method.lower(), method)

    parts = p.split('/')
    if len(parts) >= 1:
        entity_name = parts[0]
    else:
        entity_name = ''

    if 'read' in path.lower():
        verb = '标记已读'

    return f"{verb} {entity_name}: {p}" if entity_name else f"{verb}"


SKIP_PATHS = (
    '/health', '/auth/', '/api/chat', '/api/remote', '/ws/',
    '/api/rss/entries/',    # rss read/star markers
    '/api/notifications/',  # notification read markers
    '/api/sync/',           # sync operations
    '/api/files/',          # file operations
    '/api/plugins/notes/',  # notes plugin records own events
    '/api/plugins/schedule/',  # schedule plugin records own events
    '/api/plugins/rss/',    # rss (un)subscribe records own events
    '/api/plugins/todo/',   # todo plugin records own events
    '/api/plugins/music/',  # music playlist records own events
)


class ActivityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only record mutating operations
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(s) for s in SKIP_PATHS):
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
            try:
                from core.database.session import async_session
                from core.events.bus import record_event
                async with async_session() as db:
                    await record_event(
                        db=db,
                        user_id=user_id,
                        event_type=event_type,
                        entity_type=path.split('/')[2] if len(path.split('/')) > 2 else None,
                        summary=summary,
                    )
                    await db.commit()
            except Exception:
                pass

        return response
