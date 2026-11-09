"""MCP tool handlers for the Device plugin (Home Assistant control).

注册进 OmniAide 的 MCP 工具中心后，两条链路共用：
  1. 智能助手设备的手势上报（device router 查映射 → 调这里）
  2. AI 对话的 function calling（"开灯"/"客厅什么温度"）
"""

import json

from ai.mcp.core import MCPCallResponse, MCPContent
from ai.mcp.tools.plugin_tools import register_plugin_tool_handler

from . import ha


def _resp(payload: dict, is_error: bool = False) -> MCPCallResponse:
    return MCPCallResponse(isError=is_error,
                           content=[MCPContent(text=json.dumps(payload, ensure_ascii=False))])


async def ha_call_service(user_id: int, args: dict) -> MCPCallResponse:
    """Call a Home Assistant service (domain/service/entity_id)."""
    domain = (args.get("domain") or "").strip()
    service = (args.get("service") or "").strip()
    entity_id = (args.get("entity_id") or "").strip() or None
    if not domain or not service:
        return _resp({"ok": False, "detail": "domain and service are required"}, True)
    if not ha.ha_configured():
        return _resp({"ok": False, "detail": "HA not configured (HA_BASE_URL / HA_TOKEN)"}, True)
    # HA 2024+ rejects domain-wide service calls with an empty body (400).
    # "all" is the documented way to target every entity of the domain.
    if entity_id is None and service in ("turn_on", "turn_off", "toggle") \
            and domain in ha.DOMAIN_WIDE_SERVICES:
        entity_id = "all"
    if entity_id and entity_id != "all" and await ha.get_state(entity_id) is None:
        return _resp({"ok": False, "detail": f"entity not found: {entity_id}; call ha_list_entities first"}, True)
    result = await ha.call_service(domain, service, entity_id, args.get("data") or {})
    return _resp(result, not result["ok"])


async def ha_list_entities(user_id: int, args: dict) -> MCPCallResponse:
    """List Home Assistant entities with optional domain/name filtering."""
    try:
        limit = int(args.get("limit") or 80)
    except (TypeError, ValueError):
        limit = 80
    result = await ha.list_entities(
        domain=(args.get("domain") or "").strip() or None,
        query=(args.get("query") or "").strip() or None,
        limit=limit,
    )
    return _resp(result, not result["ok"])


async def ha_get_state(user_id: int, args: dict) -> MCPCallResponse:
    """Get the state of a Home Assistant entity."""
    entity_id = (args.get("entity_id") or "").strip()
    if not entity_id:
        return _resp({"ok": False, "detail": "entity_id is required"}, True)
    if not ha.ha_configured():
        return _resp({"ok": False, "detail": "HA not configured (HA_BASE_URL / HA_TOKEN)"}, True)
    st = await ha.get_state(entity_id)
    if st is None:
        return _resp({"ok": False, "detail": f"entity not found: {entity_id}; call ha_list_entities first"}, True)
    return _resp({"ok": True, "entity_id": st.get("entity_id"),
                  "state": st.get("state"),
                  "friendly_name": (st.get("attributes") or {}).get("friendly_name", "")})


async def ha_toggle(user_id: int, args: dict) -> MCPCallResponse:
    """Toggle a switch/light/input_boolean/fan entity (shorthand)."""
    entity_id = (args.get("entity_id") or "").strip()
    if not entity_id:
        return _resp({"ok": False, "detail": "entity_id is required"}, True)
    if not ha.ha_configured():
        return _resp({"ok": False, "detail": "HA not configured (HA_BASE_URL / HA_TOKEN)"}, True)
    state = await ha.get_state(entity_id)
    if state is None:
        return _resp({"ok": False, "detail": f"entity not found: {entity_id}; call ha_list_entities first"}, True)
    domain = entity_id.split(".")[0]
    service = "toggle" if domain != "script" else "turn_on"
    result = await ha.call_service(domain, service, entity_id)
    result["entity_id"] = entity_id
    result["friendly_name"] = (state.get("attributes") or {}).get("friendly_name", "")
    result["state_before"] = state.get("state")
    return _resp(result, not result["ok"])


async def set_device_timer(user_id: int, args: dict) -> MCPCallResponse:
    """Start a local countdown timer on the user's hardware assistant."""
    try:
        seconds = int(args.get("seconds") or 0)
    except Exception:
        seconds = 0
    if seconds < 1 or seconds > 24 * 3600:
        return _resp({"ok": False, "detail": "seconds must be 1..86400"}, True)
    label = (args.get("label") or "计时器").strip()[:40]
    from .events import publish_device_event
    await publish_device_event(user_id, "timer", {
        "seconds": seconds,
        "title": label,
    })
    mins = seconds // 60
    human = f"{mins} 分钟" if mins and seconds % 60 == 0 else f"{seconds} 秒"
    return _resp({"ok": True, "detail": f"已开始 {human} {label}"})


async def play_device_music(user_id: int, args: dict) -> MCPCallResponse:
    """Ask the hardware assistant to start playing audio files/playlist."""
    try:
        playlist_id = int(args.get("playlist_id") or 0)
    except Exception:
        playlist_id = 0
    from .events import publish_device_event
    await publish_device_event(user_id, "music_play", {
        "playlist_id": playlist_id,
        "title": (args.get("title") or "音乐").strip()[:60],
    })
    return _resp({"ok": True, "detail": "已发送播放指令"})


async def device_music_control(user_id: int, args: dict) -> MCPCallResponse:
    """Control hardware music playback: play / stop / next."""
    action = (args.get("action") or "stop").strip().lower()
    if action not in ("play", "stop", "next"):
        return _resp({"ok": False, "detail": "action must be play/stop/next"}, True)
    from .events import publish_device_event
    await publish_device_event(user_id, "music_control", {"action": action})
    return _resp({"ok": True, "detail": f"音乐控制: {action}"})


register_plugin_tool_handler("ha_call_service", ha_call_service)
register_plugin_tool_handler("ha_list_entities", ha_list_entities)
register_plugin_tool_handler("ha_get_state", ha_get_state)
register_plugin_tool_handler("ha_toggle", ha_toggle)
register_plugin_tool_handler("set_device_timer", set_device_timer)
register_plugin_tool_handler("play_device_music", play_device_music)
register_plugin_tool_handler("device_music_control", device_music_control)
