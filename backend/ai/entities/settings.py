"""Per-user switches for automatic graph extraction."""

from __future__ import annotations

import json
from datetime import datetime

from core.auth.domain.models import UserProfile
from core.database.session import async_session

DEFAULT_SETTINGS = {
    "auto_extract": False,
    "auto_relations": False,
    "last_extract_at": None,
    "last_relation_at": None,
}


def _loads(value):
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


async def get_entity_settings(user_id: int) -> dict:
    async with async_session() as db:
        profile = await db.get(UserProfile, user_id)
    prefs = _loads(profile.preferences) if profile is not None else {}
    values = prefs.get("entity_graph") if isinstance(prefs, dict) else {}
    return {**DEFAULT_SETTINGS, **(values or {})}


async def update_entity_settings(user_id: int, values: dict) -> dict:
    async with async_session() as db:
        profile = await db.get(UserProfile, user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)
            db.add(profile)
            await db.flush()
        prefs = _loads(profile.preferences)
        current = {**DEFAULT_SETTINGS, **(prefs.get("entity_graph") or {})}
        for key in ("auto_extract", "auto_relations"):
            if key in values and values[key] is not None:
                current[key] = bool(values[key])
        prefs["entity_graph"] = current
        profile.preferences = json.dumps(prefs, ensure_ascii=False)
        await db.commit()
    return current


async def auto_extract_enabled(user_id: int) -> bool:
    return bool((await get_entity_settings(user_id)).get("auto_extract"))


async def auto_relations_enabled(user_id: int) -> bool:
    return bool((await get_entity_settings(user_id)).get("auto_relations"))


async def mark_run(user_id: int, key: str) -> None:
    if key not in ("last_extract_at", "last_relation_at"):
        return
    async with async_session() as db:
        profile = await db.get(UserProfile, user_id)
        if profile is None:
            return
        prefs = _loads(profile.preferences)
        current = {**DEFAULT_SETTINGS, **(prefs.get("entity_graph") or {})}
        current[key] = datetime.utcnow().isoformat(timespec="seconds")
        prefs["entity_graph"] = current
        profile.preferences = json.dumps(prefs, ensure_ascii=False)
        await db.commit()
