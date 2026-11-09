"""Desktop application release artifacts and update feed."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from core.auth.dependencies import get_current_admin
from core.config.settings import settings

router = APIRouter(prefix="/api/desktop/releases", tags=["desktop-releases"])


def _root() -> Path:
    root = Path(settings.desktop_releases_dir or "/data/desktop-releases").expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_file(filename: str) -> Path:
    name = Path(filename).name
    if not name or name in {".", ".."}:
        raise HTTPException(404, detail="Release file not found")
    target = (_root() / name).resolve()
    if not str(target).startswith(str(_root().resolve()) + "/") and target != _root().resolve():
        raise HTTPException(404, detail="Release file not found")
    return target


@router.get("/latest")
async def latest_release():
    root = _root()
    candidates = sorted(
        (p for p in root.iterdir() if p.is_file() and p.suffix in {".yml", ".yaml"}),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return {
        "files": [p.name for p in root.iterdir() if p.is_file()],
        "feeds": [p.name for p in candidates],
    }


@router.get("/{filename:path}")
async def download_release(filename: str):
    target = _safe_file(filename)
    if not target.is_file():
        raise HTTPException(404, detail="Release file not found")
    return FileResponse(target, filename=target.name)


@router.post("/upload")
async def upload_release(
    file: UploadFile = File(...),
    _admin: dict = Depends(get_current_admin),
):
    name = Path(file.filename or "").name
    if not name:
        raise HTTPException(422, detail="filename required")
    root = _root()
    target = root / name
    try:
        with target.open("wb") as out:
            await file.seek(0)
            shutil.copyfileobj(file.file, out)
    finally:
        await file.close()
    return {"ok": True, "filename": name, "size": target.stat().st_size}
