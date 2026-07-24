import secrets
import time
import sys
from fastapi import WebSocket

_connections: dict[str, WebSocket] = {}
_devices: dict[str, dict] = {}
_pairs: dict[str, dict] = {}


def _log(msg: str):
    print(f"[remote] {msg}", flush=True, file=sys.stderr)


async def connect(ws: WebSocket):
    await ws.accept()


async def disconnect(ws: WebSocket):
    dead = [did for did, w in _connections.items() if w is ws]
    for did in dead:
        _log(f"disconnect device={did}")
        _connections.pop(did, None)
        _devices.pop(did, None)
        for code, p in list(_pairs.items()):
            if p["device_id"] == did:
                _pairs.pop(code, None)


async def handle_join(ws: WebSocket, device_id: str, name: str, user_id: int):
    _connections[device_id] = ws
    _devices[device_id] = {"user_id": user_id, "name": name, "ts": time.time()}
    _log(f"join device={device_id} name={name} user={user_id}")


def create_pair(device_id: str, password: str = "") -> tuple[str, str]:
    while True:
        code = ''.join(secrets.choice('0123456789') for _ in range(6))
        if code not in _pairs:
            break
    pw = password or ''.join(secrets.choice('0123456789') for _ in range(6))
    _pairs[code] = {"device_id": device_id, "password": pw, "expire_ts": time.time() + 300}
    _log(f"pair created code={code} device={device_id}")
    return code, pw


def verify_pair(code: str, password: str) -> str | None:
    p = _pairs.get(code)
    if not p:
        return None
    if time.time() > p["expire_ts"]:
        _pairs.pop(code, None)
        return None
    if p["password"] and p["password"] != password:
        return None
    return p["device_id"]


def get_own_devices(user_id: int) -> list[dict]:
    now = time.time()
    return [{"device_id": did, "name": info["name"]}
            for did, info in _devices.items()
            if info["user_id"] == user_id and now - info["ts"] < 90]


async def forward_to_device(target_device_id: str, message: dict) -> bool:
    peer_ws = _connections.get(target_device_id)
    if not peer_ws:
        return False
    try:
        await peer_ws.send_json(message)
        return True
    except Exception:
        return False
