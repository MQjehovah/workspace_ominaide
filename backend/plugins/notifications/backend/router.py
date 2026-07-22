from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from core.auth.jwt import decode_access_token
from plugins.notifications.backend.schemas import NotificationResponse
from plugins.notifications.backend import service

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
ws_router = APIRouter(tags=["notifications"])


class WSManager:
    def __init__(self):
        self.connections: dict[int, set[WebSocket]] = {}

    async def connect(self, user_id: int, ws: WebSocket):
        self.connections.setdefault(user_id, set()).add(ws)

    async def disconnect(self, user_id: int, ws: WebSocket):
        self.connections.get(user_id, set()).discard(ws)

    async def notify_user(self, user_id: int, data: dict):
        for ws in list(self.connections.get(user_id, set())):
            try:
                await ws.send_json(data)
            except Exception:
                self.connections.get(user_id, set()).discard(ws)


ws_manager = WSManager()


@ws_router.websocket("/ws/notifications")
async def notification_ws(websocket: WebSocket):
    token = websocket.query_params.get("token")
    payload = decode_access_token(token) if token else None
    if not payload:
        await websocket.close(code=4001)
        return
    user_id = int(payload["sub"])
    await websocket.accept()
    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(user_id, websocket)


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    unread: bool = False, limit: int = 50,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_notifications(db, user["id"], unread, limit)


@router.get("/unread-count")
async def unread_count(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"count": await service.count_unread(db, user["id"])}


@router.put("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await service.mark_read(db, user["id"], notification_id)
    if not ok:
        raise HTTPException(404, detail="Not found")
    return {"message": "Read"}


@router.put("/read-all")
async def mark_all_read(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await service.mark_all_read(db, user["id"])
    return {"message": "All read"}
