import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from core.events.middleware import ActivityMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.minio.client import ensure_buckets
    from core.plugin.registry import discover_plugins
    from core.ai.mcp.tools.register_core import register_core_tools
    from core.ai.mcp.tools.register_ai import register_ai_tools
    from core.events.bus import worker_loop
    from core.events.workers import register_workers
    from core.ai.scheduler import scheduler_loop
    from core.database.session import engine
    from core.database.base import Base

    # Ensure all tables exist
    import core.plugin.models  # noqa
    import core.auth.domain.models  # noqa
    import plugins.files.backend.models  # noqa
    import plugins.sync.backend.models  # noqa
    import plugins.todo.backend.models  # noqa
    import plugins.notes.backend.models  # noqa
    import plugins.mail.backend.models  # noqa
    import plugins.music.backend.models  # noqa
    import core.events.models  # noqa
    import plugins.notifications.backend.models  # noqa
    import plugins.chat.backend.models  # noqa
    import core.coding.models  # noqa
    import plugins.projects.backend.models  # noqa
    import core.bots.models  # noqa
    import core.skills.models  # noqa
    import core.ai.insight_models  # noqa
    import core.mcp_hub.models  # noqa
    import core.memory_models  # noqa
    import plugins.sources.backend.models  # noqa
    import core.objects.models  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from core.database.migrations import ensure_schema_migrations
    await ensure_schema_migrations()

    # Every user gets a default ``main`` bot. Existing rows stay readable.
    from core.bots.registry import seed_default_bots
    from core.bots.routines import register_event_handler, routine_loop

    await seed_default_bots()
    register_event_handler()

    register_workers()
    worker_task = asyncio.create_task(worker_loop())
    scheduler_task = asyncio.create_task(scheduler_loop())
    await ensure_buckets()
    await discover_plugins(app)
    register_core_tools()
    register_ai_tools()

    from core.mcp_hub.hub import mcp_hub

    await mcp_hub.startup()

    from core.bots.runner import recover_runs

    await recover_runs()
    routine_task = asyncio.create_task(routine_loop())
    yield
    await mcp_hub.shutdown()
    routine_task.cancel()
    scheduler_task.cancel()
    worker_task.cancel()
    try: await routine_task
    except asyncio.CancelledError: pass
    try: await scheduler_task
    except asyncio.CancelledError: pass
    try: await worker_task
    except asyncio.CancelledError: pass
    from core.database.redis import close_redis
    await close_redis()


from core.responses import UTCJSONResponse

app = FastAPI(
    title="OmniAide API",
    version="0.1.0",
    lifespan=lifespan,
    default_response_class=UTCJSONResponse,
)

from core.config.settings import settings as app_settings

_origins = app_settings.cors_origins_list
_allow_all = "*" in _origins


@app.middleware("http")
async def cors_middleware(request, call_next):
    """Reliable CORS: add headers to all responses and short-circuit OPTIONS."""
    origin = request.headers.get("origin", "")
    allow = "*" if _allow_all else (origin if origin in _origins else "")
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": allow or "*",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,PATCH,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Max-Age": "600",
        }
        return Response(status_code=204, headers=headers)
    response = await call_next(request)
    if allow:
        response.headers["Access-Control-Allow-Origin"] = allow
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,PATCH,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    return response


app.add_middleware(ActivityMiddleware)

from core.auth.domain.router import router as auth_router
app.include_router(auth_router)

from core.wschannel import router as host_channel_router
app.include_router(host_channel_router)

from core.plugin.router import router as plugin_router
app.include_router(plugin_router)

from core.plugin.marketplace import router as marketplace_router
app.include_router(marketplace_router)

# Manifest-backed plugins (files / sync / todo / notes / mail / sources / device)
# are mounted once by core.plugin.registry.discover_plugins during startup.
# Only modules without a manifest are included manually here.

from plugins.music.backend.router import router as music_router
app.include_router(music_router)

from plugins.remote.backend.router import router as remote_router
from plugins.remote.backend.router import ws_router as remote_ws_router
app.include_router(remote_router)
app.include_router(remote_ws_router)

from plugins.chat.backend.router import router as chat_router
app.include_router(chat_router)

from plugins.schedule.backend.router import router as schedule_router
app.include_router(schedule_router)

from plugins.projects.backend.router import router as projects_router
app.include_router(projects_router)

from plugins.notifications.backend.router import router as notifications_router
app.include_router(notifications_router)

# Manifest-backed plugins (files / sync / todo / notes / mail / sources / device)
# are mounted once by core.plugin.registry.discover_plugins during startup.
# Only modules without a manifest are included manually here.

from core.ai.mcp.router import router as mcp_router
app.include_router(mcp_router)

from core.mcp_hub.router import router as mcp_hub_router
app.include_router(mcp_hub_router)

from core.bots.router import router as bots_router
from core.bots.router import runs_router, approvals_router
app.include_router(bots_router)
app.include_router(runs_router)
app.include_router(approvals_router)

from core.bots.automation_router import router as automation_router
app.include_router(automation_router)

from core.ai.search_router import router as search_router
app.include_router(search_router)

from core.ai.insights_router import router as insights_router
app.include_router(insights_router)

from core.memory_router import router as memory_router
app.include_router(memory_router)

from core.inbox.router import router as inbox_router
app.include_router(inbox_router)

from core.skills.router import router as skills_router, bots_router as bot_skills_router
app.include_router(skills_router)
app.include_router(bot_skills_router)

from core.events.router import router as activities_router
app.include_router(activities_router)

from core.objects.router import router as objects_router
app.include_router(objects_router)


@app.websocket("/ws/sync/{folder_id}")
async def sync_websocket(websocket: WebSocket, folder_id: int):
    from core.auth.jwt import decode_access_token
    token = websocket.query_params.get("token")
    payload = decode_access_token(token) if token else None
    if not payload:
        await websocket.close(code=4001)
        return

    user_id = int(payload["sub"])

    from core.database.session import async_session
    from sqlalchemy import select
    from plugins.sync.backend.models import SyncFolder

    async with async_session() as db:
        result = await db.execute(
            select(SyncFolder).where(SyncFolder.id == folder_id, SyncFolder.user_id == user_id)
        )
        folder = result.scalar_one_or_none()
        if not folder:
            await websocket.close(code=4003)
            return

        from plugins.sync.backend.websocket_manager import manager
        await manager.connect(websocket, user_id, folder_id)
        try:
            while True:
                data = await websocket.receive_json()
                if data.get("type") == "sync_ack":
                    from plugins.sync.backend.service import mark_synced
                    await mark_synced(db, user_id, data.get("event_id"))
                    await db.commit()
                elif data.get("type") == "conflict":
                    from plugins.sync.backend.service import mark_conflicted
                    await mark_conflicted(db, user_id, data.get("event_id"))
                    await db.commit()
        except WebSocketDisconnect:
            manager.disconnect(websocket, user_id, folder_id)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
