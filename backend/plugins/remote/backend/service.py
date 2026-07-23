import secrets
import time
import sys
from fastapi import WebSocket

_online: dict[str, dict] = {}
_pairs: dict[str, dict] = {}
_rooms: dict[str, set] = {}


def _log(msg: str):
    print(f"[remote] {msg}", flush=True, file=sys.stderr)


def register_device(user_id: int, device_id: str, name: str, room_id: str):
    _online[device_id] = {"user_id": user_id, "room_id": room_id, "name": name, "ts": time.time()}
    _log(f"register device={device_id} name={name} user={user_id} room={room_id}")


def unregister_device(device_id: str):
    _online.pop(device_id, None)
    _log(f"unregister device={device_id}")


def _sweep_stale():
    now = time.time()
    stale = [d for d, v in _online.items() if now - v["ts"] >= 90]
    for d in stale:
        _log(f"sweep stale device={d} age={now - _online[d]['ts']:.0f}s")
        _online.pop(d, None)


def heartbeat(device_id: str, user_id: int | None = None, name: str | None = None, room_id: str | None = None):
    if device_id in _online:
        _online[device_id]['ts'] = time.time()
        _log(f"heartbeat device={device_id} ts={_online[device_id]['ts']:.0f}")
    elif user_id and name and room_id:
        _online[device_id] = {"user_id": user_id, "room_id": room_id, "name": name, "ts": time.time()}
        _log(f"heartbeat re-register device={device_id} name={name} user={user_id}")
    else:
        _log(f"heartbeat MISS device={device_id} (not found, no re-register data)")


def list_devices(user_id: int):
    _sweep_stale()
    now = time.time()
    result = [{"device_id": d, "name": v["name"], "room_id": v["room_id"]}
              for d, v in _online.items() if v["user_id"] == user_id and now - v["ts"] < 90]
    _log(f"list_devices user={user_id} count={len(result)} online_keys={list(_online.keys())}")
    return result


def debug_state() -> dict:
    """Return copy of _online state for debugging."""
    return {k: {kk: vv for kk, vv in v.items() if kk != "ts"} | {"ts_age": time.time() - v["ts"]}
            for k, v in _online.items()}


def clear_user_devices(user_id: int, device_id: str | None = None):
    if device_id:
        _log(f"clear_user_devices device={device_id} user={user_id}")
        _online.pop(device_id, None)
    else:
        removed = [d for d, v in _online.items() if v["user_id"] == user_id]
        _log(f"clear_user_devices ALL user={user_id} devices={removed}")
        for d in removed:
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
