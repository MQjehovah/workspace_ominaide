from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.minio.client import ensure_buckets
    await ensure_buckets()
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


@app.get("/health")
async def health():
    return {"status": "ok"}
