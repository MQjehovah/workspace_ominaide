from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.minio.client import ensure_buckets
    from core.plugin.registry import discover_plugins
    await ensure_buckets()
    await discover_plugins(app)
    yield
    from core.database.redis import close_redis
    await close_redis()


app = FastAPI(title="OmniAide API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from domains.auth.router import router as auth_router
app.include_router(auth_router)

from core.plugin.router import router as plugin_router
app.include_router(plugin_router)

from domains.file.router import router as file_router
app.include_router(file_router)

from domains.workspace.router import router as workspace_router
app.include_router(workspace_router)

from domains.sync.router import router as sync_router
app.include_router(sync_router)


@app.websocket("/ws/sync/{workspace_id}")
async def sync_websocket(websocket: WebSocket, workspace_id: int):
    from core.auth.jwt import decode_access_token
    token = websocket.query_params.get("token")
    payload = decode_access_token(token) if token else None
    if not payload:
        await websocket.close(code=4001)
        return

    user_id = int(payload["sub"])

    from core.database.session import async_session
    from domains.workspace.service import get_workspace as get_ws

    async with async_session() as db:
        ws = await get_ws(db, user_id, workspace_id)
        if not ws:
            await websocket.close(code=4003)
            return

        from domains.sync.websocket_manager import manager
        await manager.connect(websocket, user_id, workspace_id)
        try:
            while True:
                data = await websocket.receive_json()
                if data.get("type") == "sync_ack":
                    from domains.sync.service import mark_synced
                    await mark_synced(db, data.get("event_id"))
                    await db.commit()
                elif data.get("type") == "conflict":
                    from domains.sync.service import mark_conflicted
                    await mark_conflicted(db, data.get("event_id"))
                    await db.commit()
        except WebSocketDisconnect:
            manager.disconnect(websocket, user_id, workspace_id)


@app.get("/health")
async def health():
    return {"status": "ok"}
