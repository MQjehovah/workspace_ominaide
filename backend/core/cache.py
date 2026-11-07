"""Small async cache with Redis and process-local fallback.

Keys must be namespaced by the caller, e.g. ``workbench:suggestions:1``.
The fallback keeps the application usable when Redis is unavailable.
"""

from __future__ import annotations

import json
import time

_memory: dict[str, tuple[float, str]] = {}


async def get_json(key: str):
    try:
        from core.database.redis import get_redis

        redis = await get_redis()
        raw = await redis.get(key)
        if raw is not None:
            return json.loads(raw)
    except Exception:
        pass
    cached = _memory.get(key)
    if cached is None:
        return None
    expires, raw = cached
    if expires and expires < time.monotonic():
        _memory.pop(key, None)
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def set_json(key: str, value, ttl_seconds: int = 60) -> None:
    raw = json.dumps(value, ensure_ascii=False, default=str)
    _memory[key] = (time.monotonic() + ttl_seconds, raw)
    try:
        from core.database.redis import get_redis

        redis = await get_redis()
        await redis.set(key, raw, ex=max(1, int(ttl_seconds)))
    except Exception:
        pass


async def delete(key: str) -> None:
    _memory.pop(key, None)
    try:
        from core.database.redis import get_redis

        redis = await get_redis()
        await redis.delete(key)
    except Exception:
        pass
