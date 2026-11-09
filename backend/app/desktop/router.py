"""Desktop application releases, update feeds and platform-specific artifacts."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from core.auth.dependencies import get_current_admin
from core.config.settings import settings

router = APIRouter(prefix="/api/desktop/releases", tags=["desktop-releases"])

PLATFORM_FEEDS = {
    "mac": "latest-mac.yml",
    "windows": "latest.yml",
    "linux": "latest-linux.yml",
}
PLATFORM_LABELS = {
    "mac": "macOS",
    "windows": "Windows",
    "linux": "Linux",
}


def _root(platform: str | None = None) -> Path:
    root = Path(settings.desktop_releases_dir or "/data/desktop-releases").expanduser()
    if platform:
        root = root / platform
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve(base: Path, filename: str) -> Path:
    name = filename.replace("\\", "/").lstrip("/")
    if not name:
        raise HTTPException(404, detail="Release file not found")
    base_resolved = base.resolve()
    target = (base_resolved / name).resolve()
    if target != base_resolved and base_resolved not in target.parents:
        raise HTTPException(404, detail="Release file not found")
    return target


def _feed_version(feed: Path) -> str | None:
    if not feed.is_file():
        return None
    for line in feed.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = re.match(r"^version:\s*(.+?)\s*$", line)
        if match:
            return match.group(1).strip("'\"")
    return None


def _file_info(path: Path, base: Path) -> dict:
    stat = path.stat()
    return {
        "name": path.relative_to(base).as_posix(),
        "size": stat.st_size,
        "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def _summary(platform: str) -> dict:
    base = _root(platform)
    files = sorted(
        (_file_info(path, base) for path in base.rglob("*") if path.is_file()),
        key=lambda item: item["updated_at"],
        reverse=True,
    )
    feed_name = PLATFORM_FEEDS[platform]
    feed = base / feed_name
    return {
        "platform": platform,
        "label": PLATFORM_LABELS[platform],
        "version": _feed_version(feed),
        "feed": feed_name,
        "feed_url": f"/desktop/releases/{platform}/{feed_name}",
        "has_feed": feed.is_file(),
        "files": files,
        "total_size": sum(item["size"] for item in files),
    }


def _prefix_legacy_feed(text: str, platform: str) -> str:
    """Rewrite relative artifact URLs for the legacy root feed.

    Older desktop builds read latest-mac.yml from /api/desktop/releases. Point
    those downloads at the platform subdirectory so artifacts stay in one place.
    """
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        key = None
        if stripped.startswith("- url:"):
            key = "- url:"
        elif stripped.startswith("path:"):
            key = "path:"
        if key:
            prefix, _, value = line.partition(key)
            value = value.strip().strip("'\"")
            if value and "://" not in value and "/" not in value:
                line = f"{prefix}{key} {platform}/{value}"
        lines.append(line)
    return "\n".join(lines) + "\n"


@router.get("/platforms")
async def list_platforms():
    return {"platforms": [_summary(platform) for platform in PLATFORM_FEEDS]}


@router.get("/latest")
async def latest_release_legacy():
    """Legacy root feed listing kept for desktop builds before 1.1.2."""
    root = _root()
    feeds = sorted(
        (path.name for path in root.iterdir() if path.is_file() and path.suffix in {".yml", ".yaml"}),
    )
    return {
        "files": sorted(path.name for path in root.iterdir() if path.is_file()),
        "feeds": feeds,
    }


@router.get("/{platform}/latest")
async def latest_release(platform: str):
    if platform not in PLATFORM_FEEDS:
        raise HTTPException(404, detail="Unknown platform")
    return _summary(platform)


@router.post("/upload")
async def upload_release(
    platform: str = Query(...),
    file: UploadFile = File(...),
    _admin: dict = Depends(get_current_admin),
):
    if platform not in PLATFORM_FEEDS:
        raise HTTPException(422, detail="Unsupported platform")
    name = Path(file.filename or "").name
    if not name:
        raise HTTPException(422, detail="filename required")

    base = _root(platform)
    target = base / name
    try:
        with target.open("wb") as out:
            shutil.copyfileobj(file.file, out)
    finally:
        await file.close()

    feed_name = PLATFORM_FEEDS[platform]
    if name == feed_name:
        # Keep the canonical feed inside the platform directory and mirror a
        # legacy copy at the root with platform-prefixed artifact URLs.
        text = target.read_text(encoding="utf-8", errors="ignore")
        (_root() / name).write_text(_prefix_legacy_feed(text, platform), encoding="utf-8")

    return {
        "ok": True,
        "platform": platform,
        "filename": name,
        "size": target.stat().st_size,
    }


@router.delete("/{platform}/{filename:path}")
async def delete_release(
    platform: str,
    filename: str,
    _admin: dict = Depends(get_current_admin),
):
    if platform not in PLATFORM_FEEDS:
        raise HTTPException(404, detail="Unknown platform")
    base = _root(platform)
    target = _resolve(base, filename)
    if not target.is_file():
        raise HTTPException(404, detail="Release file not found")
    target.unlink()

    if target.name == PLATFORM_FEEDS[platform]:
        legacy = _root() / target.name
        if legacy.is_file():
            legacy.unlink()

    return {"ok": True, "platform": platform, "filename": filename}


@router.get("/{platform}/{filename:path}")
async def download_release(platform: str, filename: str):
    if platform not in PLATFORM_FEEDS:
        raise HTTPException(404, detail="Unknown platform")
    target = _resolve(_root(platform), filename)
    if not target.is_file():
        raise HTTPException(404, detail="Release file not found")
    return FileResponse(target, filename=target.name)


@router.get("/{filename:path}")
async def download_release_legacy(filename: str):
    """Serve legacy root artifacts, including platform-prefixed download paths."""
    target = _resolve(_root(), filename)
    if not target.is_file():
        raise HTTPException(404, detail="Release file not found")
    return FileResponse(target, filename=target.name)
