"""Home Assistant REST 客户端（device 插件专用）。

配置走 Settings（环境变量 / .env）：
  HA_BASE_URL  例 http://192.168.2.10:8123
  HA_TOKEN     HA 个人访问令牌（用户中心 → 安全 → 长期访问令牌）
"""
import logging
from collections import Counter

import httpx

from core.config.settings import settings

log = logging.getLogger(__name__)

TIMEOUT = 6.0
CONTROL_DOMAINS = {
    "light", "switch", "climate", "cover", "fan", "media_player",
    "scene", "script", "input_boolean", "lock", "vacuum", "humidifier",
    "water_heater", "button", "number", "select",
}

# Domains where "entity_id: all" is a valid target for turn_on/turn_off/toggle.
DOMAIN_WIDE_SERVICES = {
    "light", "switch", "fan", "input_boolean", "media_player",
    "climate", "cover", "humidifier", "water_heater", "vacuum",
}


def ha_configured() -> bool:
    return bool(settings.ha_base_url and settings.ha_token)


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.ha_token}"}


async def list_entities(
    domain: str | None = None,
    query: str | None = None,
    limit: int = 80,
) -> dict:
    """List HA entities, optionally filtered by domain or name/entity keyword."""
    if not ha_configured():
        return {"ok": False, "detail": "HA not configured (HA_BASE_URL / HA_TOKEN)"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{settings.ha_base_url.rstrip('/')}/api/states",
                headers=_headers(),
            )
        if r.status_code != 200:
            return {"ok": False, "detail": f"HTTP {r.status_code}"}
        states = r.json()
    except Exception as e:
        log.warning("HA list_entities failed: %s", e)
        return {"ok": False, "detail": str(e)[:200]}

    domain = (domain or "").strip().lower() or None
    query = (query or "").strip().lower() or None

    items = []
    for state in states:
        entity_id = state.get("entity_id") or ""
        if not entity_id:
            continue
        entity_domain = entity_id.split(".", 1)[0]
        if domain and entity_domain != domain:
            continue
        attrs = state.get("attributes") or {}
        name = attrs.get("friendly_name") or entity_id
        haystack = f"{entity_id} {name}".lower()
        if query and query not in haystack:
            continue
        items.append({
            "entity_id": entity_id,
            "name": name,
            "state": state.get("state"),
            "domain": entity_domain,
        })

    domains = Counter(
        (s.get("entity_id") or "").split(".", 1)[0] for s in states
    )
    items.sort(key=lambda x: (
        0 if x["domain"] in CONTROL_DOMAINS else 1,
        x["domain"],
        x["entity_id"],
    ))
    return {
        "ok": True,
        "total": len(states),
        "matched": len(items),
        "domains": dict(domains.most_common()),
        "entities": items[: min(max(limit, 1), 200)],
    }



async def call_service(domain: str, service: str, entity_id: str | None = None,
                       data: dict | None = None) -> dict:
    """调用 HA 服务。返回 {"ok": bool, "detail": str}。"""
    if not ha_configured():
        return {"ok": False, "detail": "HA not configured (HA_BASE_URL / HA_TOKEN)"}
    url = f"{settings.ha_base_url.rstrip('/')}/api/services/{domain}/{service}"
    body = dict(data or {})
    if entity_id:
        body["entity_id"] = entity_id
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                url,
                headers=_headers(),
                json=body,
            )
        if r.status_code in (200, 201):
            changed = 0
            try:
                payload = r.json()
                if isinstance(payload, list):
                    changed = len(payload)
            except Exception:
                payload = None
            detail = "ok" if changed else "ok (no state change reported)"
            return {"ok": True, "detail": detail, "changed": changed}
        log.warning("HA %s/%s -> %s: %s", domain, service, r.status_code, r.text[:200])
        return {"ok": False, "detail": f"HTTP {r.status_code}"}
    except Exception as e:  # 网络错误不让设备端等太久
        log.warning("HA call failed: %s", e)
        return {"ok": False, "detail": str(e)[:120]}


async def get_state(entity_id: str) -> dict | None:
    """读取单个实体状态，失败返回 None。"""
    if not ha_configured():
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{settings.ha_base_url.rstrip('/')}/api/states/{entity_id}",
                headers=_headers(),
            )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.warning("HA get_state failed: %s", e)
    return None
