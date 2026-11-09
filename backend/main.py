import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from core.activities.middleware import ActivityMiddleware
from core.config.settings import settings as app_settings
from core.logging import configure_logging, get_logger
from core.observability.context import get_trace_id

configure_logging()
log = get_logger("omniaide")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.minio.client import ensure_buckets
    from core.plugin.registry import discover_plugins
    from core.ai.mcp.tools.register_core import register_core_tools
    from core.ai.mcp.tools.register_ai import register_ai_tools
    from core.events.bus import worker_loop
    from core.events.workers import register_workers
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
    import core.activities.models  # noqa
    import plugins.notifications.backend.models  # noqa
    import plugins.chat.backend.models  # noqa
    import core.coding.models  # noqa
    import plugins.projects.backend.models  # noqa
    import plugins.schedule.backend.models  # noqa
    import core.bots.models  # noqa
    import core.automation.models  # noqa
    import core.captures.models  # noqa
    import core.people.models  # noqa
    import core.meetings.models  # noqa
    import core.skills.models  # noqa
    import core.observability.models  # noqa
    import core.jobs.models  # noqa
    import core.graph.models  # noqa
    import core.ai.insight_models  # noqa
    import core.mcp_hub.models  # noqa
    import core.wschannel.models  # noqa
    import plugins.oauth.backend.models  # noqa
    import plugins.dingtalk.backend.models  # noqa
    import core.insights.models  # noqa
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
    from core.auth.domain.cleanup import register_cleanup_handlers
    register_cleanup_handlers()
    from core.captures.service import register_capture_handlers
    register_capture_handlers()
    from core.scheduler import scheduler as periodic_scheduler
    from core.jobs.service import start_workers as start_jobs_workers
    start_jobs_workers()
    await ensure_buckets()
    await discover_plugins(app)
    from core.insights.jobs import JOBS as INSIGHT_JOBS
    from core.skills.jobs import JOBS as BRIEF_JOBS

    for job in [*BRIEF_JOBS, *INSIGHT_JOBS]:
        periodic_scheduler.register(job)
    periodic_scheduler.start()
    register_core_tools()
    register_ai_tools()

    from core.mcp_hub.hub import mcp_hub

    await mcp_hub.startup()

    from core.bots.runner import recover_runs
    from core.meetings.service import recover_pending_jobs

    await recover_runs()
    await recover_pending_jobs()
    routine_task = asyncio.create_task(routine_loop())
    from core.ai.clients import warm_voice_clients
    warm_task = asyncio.create_task(warm_voice_clients())
    yield
    await periodic_scheduler.stop()
    await mcp_hub.shutdown()
    warm_task.cancel()
    routine_task.cancel()
    worker_task.cancel()
    from core.jobs.service import stop_workers
    await stop_workers()
    try: await warm_task
    except asyncio.CancelledError: pass
    try: await routine_task
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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("unhandled error %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "request_id": get_trace_id()},
    )

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

from core.observability.middleware import TraceMiddleware
app.add_middleware(TraceMiddleware)

from core.auth.domain.router import router as auth_router
app.include_router(auth_router)

from core.captures.router import router as captures_router
app.include_router(captures_router)

from core.people.router import router as people_router
app.include_router(people_router)

from core.wschannel import router as host_channel_router
app.include_router(host_channel_router)

from core.plugin.router import router as plugin_router
app.include_router(plugin_router)

from core.plugin.marketplace import router as marketplace_router
app.include_router(marketplace_router)

# All business plugins now have a manifest and are mounted by
# core.plugin.registry.discover_plugins during startup.

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

from core.insights.router import router as activity_insights_router
app.include_router(activity_insights_router)

from core.ai.insights_router import router as insights_router
app.include_router(insights_router)

from core.memory_router import router as memory_router
app.include_router(memory_router)

from core.observability.router import router as metrics_router
app.include_router(metrics_router)

from core.jobs.router import router as jobs_router
app.include_router(jobs_router)

from core.graph.router import router as graph_router, context_router
app.include_router(graph_router)
app.include_router(context_router)

from core.agent.router import router as agent_router
app.include_router(agent_router)

from core.meetings.router import router as meetings_router
app.include_router(meetings_router)

from core.workbench.router import router as workbench_router
app.include_router(workbench_router)

from core.skills.router import router as skills_router, bots_router as bot_skills_router
app.include_router(skills_router)
app.include_router(bot_skills_router)

from core.activities.router import router as activities_router
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
