"""Home Assistant REST 客户端（device 插件专用）。

配置走 Settings（环境变量 / .env）：
  HA_BASE_URL  例 http://192.168.2.10:8123
  HA_TOKEN     HA 个人访问令牌（用户中心 → 安全 → 长期访问令牌）
"""
import logging

import httpx

from core.config.settings import settings

log = logging.getLogger(__name__)

TIMEOUT = 6.0


def ha_configured() -> bool:
    return bool(settings.ha_base_url and settings.ha_token)


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
                headers={"Authorization": f"Bearer {settings.ha_token}"},
                json=body,
            )
        if r.status_code in (200, 201):
            return {"ok": True, "detail": "ok"}
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
                headers={"Authorization": f"Bearer {settings.ha_token}"},
            )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.warning("HA get_state failed: %s", e)
    return None
