import secrets
import time
import sys
from fastapi import WebSocket

# 已连接的设备: device_id → WebSocket
_connections: dict[str, WebSocket] = {}

# 设备信息: device_id → { user_id, name, ts }
_devices: dict[str, dict] = {}

# 配对码: code → { device_id, password, expire_ts }
_pairs: dict[str, dict] = {}

# 配对关系: pair_code → { host_id, viewer_id, connected }  (viewer 查配对码后建立)
_pairings: dict[str, dict] = {}

# 待定 Viewer 连接: target_id → list[WebSocket]  (Host 回复时转发用)
_pending_viewers: dict[str, list[WebSocket]] = {}


def _log(msg: str):
    print(f"[remote] {msg}", flush=True, file=sys.stderr)


# ─── 连接管理 ───

async def connect(ws: WebSocket):
    """接受 WS 连接，等待后续 join 消息"""
    await ws.accept()


async def disconnect(ws: WebSocket):
    """设备断开连接 → 清理在线状态和配对"""
    dead = [did for did, w in _connections.items() if w is ws]
    clean_pending_viewer(ws)
    for did in dead:
        _log(f"disconnect device={did}")
        _connections.pop(did, None)
        _devices.pop(did, None)
        # 清理相关配对
        for code, p in list(_pairs.items()):
            if p["device_id"] == did:
                _pairs.pop(code, None)
        for code, pr in list(_pairings.items()):
            if pr["host_id"] == did or pr.get("viewer_id") == did:
                _pairings.pop(code, None)


async def handle_join(ws: WebSocket, device_id: str, name: str, user_id: int):
    """设备注册在线"""
    _connections[device_id] = ws
    _devices[device_id] = {"user_id": user_id, "name": name, "ts": time.time()}
    _log(f"join device={device_id} name={name} user={user_id}")


def get_online_device(device_id: str) -> WebSocket | None:
    """获取设备连接"""
    return _connections.get(device_id)


def get_own_device_ws(user_id: int, device_id: str) -> WebSocket | None:
    """获取同账号下指定设备的连接"""
    info = _devices.get(device_id)
    if info and info["user_id"] == user_id:
        return _connections.get(device_id)
    return None


# ─── 配对管理 ───

def create_pair(device_id: str, password: str = "") -> tuple[str, str]:
    """生成配对码 + 密码"""
    while True:
        code = ''.join(secrets.choice('0123456789') for _ in range(6))
        if code not in _pairs:
            break
    pw = password or ''.join(secrets.choice('0123456789') for _ in range(6))
    _pairs[code] = {"device_id": device_id, "password": pw, "expire_ts": time.time() + 300}
    _log(f"pair created code={code} device={device_id}")
    return code, pw


def verify_pair(code: str, password: str) -> str | None:
    """验证配对码 + 密码，返回 host device_id"""
    p = _pairs.get(code)
    if not p:
        return None
    if time.time() > p["expire_ts"]:
        _pairs.pop(code, None)
        return None
    if p["password"] and p["password"] != password:
        return None
    return p["device_id"]


def bind_pairing(code: str, host_id: str, viewer_id: str):
    """建立配对关系"""
    _pairings[code] = {"host_id": host_id, "viewer_id": viewer_id}
    _pairs.pop(code, None)  # 配对码用完即销毁
    _log(f"pairing bound code={code} host={host_id} viewer={viewer_id}")


def get_peer(ws: WebSocket) -> WebSocket | None:
    """找到配对的对方的连接"""
    for code, pr in _pairings.items():
        if _connections.get(pr["host_id"]) is ws:
            return _connections.get(pr["viewer_id"])
        if _connections.get(pr["viewer_id"]) is ws:
            return _connections.get(pr["host_id"])
    return None


def get_host_ws_by_code(code: str) -> WebSocket | None:
    """通过配对码找到 Host 连接（供配对前转发消息用）"""
    p = _pairs.get(code)
    if not p:
        return None
    return _connections.get(p["device_id"])


def get_own_devices(user_id: int) -> list[dict]:
    """同账号设备列表（排除自己）"""
    now = time.time()
    return [{"device_id": did, "name": info["name"], "room_id": did}
            for did, info in _devices.items()
            if info["user_id"] == user_id and now - info["ts"] < 90]


# ─── Viewer 临时路由 ───

def register_pending_viewer(target_id: str, viewer_ws: WebSocket):
    """注册 Viewer 连接，Host 回复时转发用"""
    _pending_viewers.setdefault(target_id, []).append(viewer_ws)
    _log(f"register pending viewer target={target_id}")


def clean_pending_viewer(ws: WebSocket):
    """清理 Viewer 连接"""
    for tid, viewers in list(_pending_viewers.items()):
        _pending_viewers[tid] = [v for v in viewers if v is not ws]
        if not _pending_viewers[tid]:
            del _pending_viewers[tid]


async def forward_to_pending_viewers(target_id: str, message: dict, exclude_ws: WebSocket | None = None) -> bool:
    """转发消息给所有待定 Viewer"""
    viewers = _pending_viewers.get(target_id, [])
    sent = False
    for viewer_ws in viewers:
        if viewer_ws is exclude_ws:
            continue
        try:
            await viewer_ws.send_json(message)
            sent = True
        except Exception:
            pass
    return sent


# ─── 消息转发 ───

async def forward(ws: WebSocket, message: dict) -> bool:
    """转发消息给配对的对方。返回是否成功"""
    peer = get_peer(ws)
    if not peer:
        return False
    try:
        await peer.send_json(message)
        return True
    except Exception:
        return False


async def forward_to_device(device_id: str, message: dict, exclude_ws: WebSocket | None = None) -> bool:
    """按设备 ID 转发消息（用于 Viewer → Host 场景）"""
    peer_ws = _connections.get(device_id)
    if not peer_ws or peer_ws is exclude_ws:
        return False
    try:
        await peer_ws.send_json(message)
        return True
    except Exception:
        return False
