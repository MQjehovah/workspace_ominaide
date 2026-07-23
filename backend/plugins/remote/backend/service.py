import secrets
import time
from fastapi import WebSocket

_online: dict[str, dict] = {}
_pairs: dict[str, dict] = {}
_rooms: dict[str, set] = {}


def register_device(user_id: int, device_id: str, name: str, room_id: str):
    _online[device_id] = {"user_id": user_id, "room_id": room_id, "name": name, "ts": time.time()}


def unregister_device(device_id: str):
    _online.pop(device_id, None)


def _sweep_stale():
    now = time.time()
    for d in [k for k, v in _online.items() if now - v["ts"] >= 90]:
        _online.pop(d, None)


def heartbeat(device_id: str, user_id: int | None = None, name: str | None = None, room_id: str | None = None):
    if device_id in _online:
        _online[device_id]['ts'] = time.time()
    elif user_id and name and room_id:
        _online[device_id] = {"user_id": user_id, "room_id": room_id, "name": name, "ts": time.time()}


def list_devices(user_id: int):
    _sweep_stale()
    now = time.time()
    return [{"device_id": d, "name": v["name"], "room_id": v["room_id"]}
            for d, v in _online.items() if v["user_id"] == user_id and now - v["ts"] < 90]


def clear_user_devices(user_id: int, device_id: str | None = None):
    if device_id:
        _online.pop(device_id, None)
    else:
        for d in [k for k, v in _online.items() if v["user_id"] == user_id]:
            _online.pop(d, None)


def create_pair(user_id: int, device_id: str, room_id: str, ttl: int = 300):
    while True:
        code = ''.join(secrets.choice('0123456789') for _ in range(6))
        if code not in _pairs:
            break
    _pairs[code] = {"room_id": room_id, "user_id": user_id, "device_id": device_id, "expire_ts": time.time() + ttl}
    return code


def consume_pair(code: str):
    v = _pairs.get(code)
    if not v:
        return None
    if time.time() > v["expire_ts"]:
        _pairs.pop(code, None)
        return None
    room_id = v["room_id"]
    _pairs.pop(code, None)
    return room_id


async def room_join(room_id: str, ws: WebSocket):
    _rooms.setdefault(room_id, set()).add(ws)


async def room_leave(room_id: str, ws: WebSocket):
    if room_id in _rooms:
        _rooms[room_id].discard(ws)
        if not _rooms[room_id]:
            del _rooms[room_id]


async def room_broadcast(room_id: str, ws: WebSocket, message: dict):
    dead = []
    for peer in list(_rooms.get(room_id, ())):
        if peer is ws:
            continue
        try:
            await peer.send_json(message)
        except Exception:
            dead.append(peer)
    for peer in dead:
        _rooms.get(room_id, set()).discard(peer)
