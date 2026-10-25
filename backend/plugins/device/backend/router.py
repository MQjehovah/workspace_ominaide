"""device 插件路由：智能助手等硬件设备接入网关。

- POST /api/device/auth     设备登录（同账号密码，签发 90 天长效 token）
- GET  /api/device/brief    设备聚合摘要（待办 + 今日日程），一次请求拿全
- POST /api/device/gesture  手势事件上报 → 按映射调 Home Assistant
- GET  /api/device/gestures 查看手势映射
- PUT  /api/device/gestures 修改手势映射
"""
import asyncio
import os
import tempfile
import time as _time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.auth.domain.service import login as auth_login
from core.auth.jwt import create_access_token
from core.config.settings import settings
from core.database.session import get_db
from plugins.todo.backend import service as todo_service
from plugins.schedule.backend import service as schedule_service

from . import gesture_store
from . import ha
from .events import device_events

router = APIRouter(prefix="/api/device", tags=["device"])

DEVICE_TOKEN_DAYS = 90
BRIEF_TODO_LIMIT = 8
BRIEF_EVENT_LIMIT = 3


def _ffmpeg_exe() -> str:
    """Prefer the static ffmpeg bundled by imageio-ffmpeg (no system apt)."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


# ---------------- auth ----------------

class DeviceLoginRequest(BaseModel):
    username: str
    password: str


class GestureReport(BaseModel):
    gesture: str  # flip | shake | double_tap | pickup


class DevicePush(BaseModel):
    title: str
    body: str | None = None
    kind: str = "notification"


@router.post("/auth")
async def device_auth(req: DeviceLoginRequest, db: AsyncSession = Depends(get_db)):
    """设备端登录：验证账号密码后签发 90 天长效 token（免频繁刷新）。

    JWT sub 必须是数字用户 ID（get_current_user 按 int(sub) 查库）。
    """
    from sqlalchemy import select
    from core.auth.domain.models import User as UserModel

    try:
        await auth_login(db, req.username, req.password)   # 验密码
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    row = (await db.execute(
        select(UserModel).where(UserModel.username == req.username))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=401, detail="user not found")
    token = create_access_token(
        {"sub": str(row.id)},
        expires_delta=timedelta(days=DEVICE_TOKEN_DAYS),
    )
    return {"access_token": token, "token_type": "bearer",
            "expires_in_days": DEVICE_TOKEN_DAYS, "user_id": row.id}


# ---------------- brief ----------------

@router.get("/brief")
async def device_brief(user: dict = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """设备聚合摘要：未完成待办 + 即将开始的日程。设备每分钟轮询一次即可。"""
    uid = user["id"]
    todos, _total = await todo_service.get_todos(db, uid, status="pending",
                                                 page=1, page_size=BRIEF_TODO_LIMIT)
    now = datetime.now()
    events = await schedule_service.list_events(db, uid, start=now)
    events = events[:BRIEF_EVENT_LIMIT]

    weather = await _current_weather()
    return {
        "todos": [{"id": t.id, "title": t.title, "priority": t.priority} for t in todos],
        "events": [{"id": e.id,
                    "title": e.title,
                    "start": e.start_time.strftime("%m-%d %H:%M")} for e in events],
        "server_time": now.strftime("%Y-%m-%d %H:%M"),
        **({"weather": weather} if weather else {}),
    }


# ---------------- music (device playback) ----------------

@router.get("/music/tracks")
async def device_music_tracks(
    playlist_id: int = Query(0),
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return audio tracks for the device; playlist_id=0 means all audio files."""
    from sqlalchemy import select
    from plugins.files.backend.models import File

    uid = user["id"]
    if playlist_id:
        from plugins.music.backend.models import Playlist, PlaylistItem
        pl = (await db.execute(
            select(Playlist).where(Playlist.id == playlist_id, Playlist.user_id == uid)
        )).scalar_one_or_none()
        if not pl:
            raise HTTPException(status_code=404, detail="Playlist not found")
        rows = await db.execute(
            select(File)
            .join(PlaylistItem, PlaylistItem.file_id == File.id)
            .where(
                PlaylistItem.playlist_id == playlist_id,
                File.user_id == uid,
                File.status == "active",
            )
            .order_by(PlaylistItem.position)
            .limit(limit)
        )
    else:
        rows = await db.execute(
            select(File)
            .where(
                File.user_id == uid,
                File.status == "active",
                File.mime_type.like("audio/%"),
            )
            .order_by(File.created_at.desc())
            .limit(limit)
        )
    files = list(rows.scalars().all())
    return {"tracks": [
        {"id": f.id, "name": f.original_name, "mime": f.mime_type}
        for f in files
    ]}


@router.get("/music/{file_id}.pcm")
async def device_music_pcm(
    file_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transcode any audio file to raw s16le 24kHz mono for the device."""
    from core.minio.client import minio_client
    from plugins.files.backend import service as file_service

    if not minio_client:
        raise HTTPException(status_code=503, detail="MinIO unavailable")
    record = await file_service.get_file(db, user["id"], file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    if not (record.mime_type or "").startswith("audio/"):
        raise HTTPException(status_code=400, detail="Not an audio file")

    def _download() -> str:
        obj = minio_client.get_object(record.bucket, record.object_key)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".media")
        try:
            while True:
                chunk = obj.read(1024 * 1024)
                if not chunk:
                    break
                tmp.write(chunk)
        finally:
            tmp.close()
        return tmp.name

    try:
        src_path = await asyncio.to_thread(_download)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"download failed: {e}")

    out_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pcm")
    out_path = out_tmp.name
    out_tmp.close()

    def _cleanup():
        for path in (src_path, out_path):
            try:
                os.unlink(path)
            except OSError:
                pass

    try:
        proc = await asyncio.create_subprocess_exec(
            _ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            "-i", src_path, "-vn", "-f", "s16le", "-acodec", "pcm_s16le",
            "-ac", "1", "-ar", "16000", out_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        _cleanup()
        raise HTTPException(status_code=503, detail="ffmpeg not installed")

    await proc.wait()
    if proc.returncode != 0:
        _cleanup()
        raise HTTPException(status_code=502, detail="audio transcode failed")

    # FileResponse gives Content-Length (not chunked). HTTPClient on the device
    # then reads raw s16le bytes without HTTP chunk framing mixed into the PCM.
    return FileResponse(
        out_path,
        media_type="application/octet-stream",
        headers={
            "X-Audio-Rate": "16000",
            "X-Audio-Channels": "1",
            "Cache-Control": "no-store",
        },
        background=BackgroundTask(_cleanup),
    )


# ---------------- realtime events (long-poll) ----------------

@router.get("/events")
async def device_events_poll(
    since: int = Query(0),
    wait: int = Query(25, ge=0, le=30),
    user: dict = Depends(get_current_user),
):
    """Long-poll device events (notifications, reminders, commands).

    The device keeps the last event id and calls this endpoint with a 25s wait.
    ``since=-1`` is a cursor sync: return no replay, just the current last id
    (used on boot so old notifications don't fire again).
    """
    uid = user["id"]
    if since < 0:
        return {"events": [], "last_id": device_events.last_id(uid),
                "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    events = device_events.since(uid, since)
    if not events and wait > 0:
        events = await device_events.wait(uid, since, wait)
    last_id = events[-1]["id"] if events else since
    return {
        "events": events,
        "last_id": last_id,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.post("/push")
async def device_push(
    req: DevicePush,
    user: dict = Depends(get_current_user),
):
    """Push a short message to the user's hardware assistant (web/mobile -> device)."""
    from .events import publish_device_event
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="title is required")
    event = await publish_device_event(user["id"], req.kind or "notification", {
        "title": req.title.strip()[:120],
        "body": (req.body or "").strip()[:400],
    })
    return {"ok": True, "event": event}


# ---------------- weather（Open-Meteo，无 key，30min 缓存） ----------------

_weather_cache = {"t": 0.0, "data": None}


async def _current_weather() -> dict | None:
    if not settings.weather_lat or not settings.weather_lon:
        return None
    if _time.time() - _weather_cache["t"] > 1800:
        try:
            import httpx
            url = (
                "https://api.open-meteo.com/v1/forecast"
                f"?latitude={settings.weather_lat}&longitude={settings.weather_lon}"
                "&current=temperature_2m,weather_code"
            )
            async with httpx.AsyncClient(timeout=6) as client:
                r = await client.get(url)
                cur = r.json()["current"]
            _weather_cache["data"] = {
                "temp": round(cur["temperature_2m"]),
                "code": cur["weather_code"],
            }
            _weather_cache["t"] = _time.time()
        except Exception as e:
            print(f"[device] weather error: {e}")
    return _weather_cache["data"]


# ---------------- firmware OTA ----------------

@router.get("/firmware/latest")
async def firmware_latest(user: dict = Depends(get_current_user)):
    """设备固件版本检查。目录里放 version.txt + firmware.bin 即启用。"""
    d = Path(settings.device_firmware_dir)
    ver_file, bin_file = d / "version.txt", d / "firmware.bin"
    if not (ver_file.exists() and bin_file.exists()):
        return {"available": False}
    return {
        "available": True,
        "version": ver_file.read_text(encoding="utf-8").strip(),
        "size": bin_file.stat().st_size,
    }


@router.get("/firmware/download")
async def firmware_download(user: dict = Depends(get_current_user)):
    d = Path(settings.device_firmware_dir)
    bin_file = d / "firmware.bin"
    if not bin_file.exists():
        raise HTTPException(status_code=404, detail="firmware not published")
    version = ""
    if (d / "version.txt").exists():
        version = (d / "version.txt").read_text(encoding="utf-8").strip()
    return FileResponse(
        bin_file,
        media_type="application/octet-stream",
        headers={"X-Firmware-Version": version},
    )


# ---------------- gestures ----------------

@router.get("/gestures")
async def get_gestures(user: dict = Depends(get_current_user)):
    return {"gestures": gesture_store.get_gestures(),
            "ha_configured": ha.ha_configured()}


@router.put("/gestures")
async def put_gestures(payload: dict, user: dict = Depends(get_current_user)):
    if not isinstance(payload, dict) or not payload.get("gestures"):
        raise HTTPException(status_code=400, detail="missing gestures")
    saved = gesture_store.set_gestures(payload["gestures"])
    return {"gestures": saved, "ha_configured": ha.ha_configured()}


@router.post("/gesture")
async def report_gesture(req: GestureReport, user: dict = Depends(get_current_user)):
    """设备手势上报 → 查映射 → 经 MCP 工具中心执行（与 AI 对话同一条工具链）。"""
    action = gesture_store.get_action(req.gesture)
    if not action:
        return {"ok": False, "detail": f"no action bound to '{req.gesture}'"}

    from core.ai.mcp.tools.plugin_tools import get_plugin_handler
    handler = get_plugin_handler(action.get("tool", ""))
    if handler is None:
        return {"ok": False, "detail": f"MCP tool '{action.get('tool')}' not registered"}

    resp = await handler(user["id"], action.get("args") or {})
    ok = not resp.isError
    text = resp.content[0].text if resp.content else ""
    label = action.get("label", req.gesture)
    return {"ok": ok, "detail": ("" if ok else text[:120]),
            "label": label}
