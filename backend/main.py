from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.minio.client import ensure_buckets
    from core.plugin.registry import discover_plugins
    await ensure_buckets()
    await discover_plugins(app)
    yield


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


@app.get("/health")
async def health():
    return {"status": "ok"}
