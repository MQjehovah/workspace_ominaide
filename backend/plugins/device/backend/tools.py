"""MCP tool handlers for the Device plugin (Home Assistant control).

注册进 OmniAide 的 MCP 工具中心后，两条链路共用：
  1. 智能助手设备的手势上报（device router 查映射 → 调这里）
  2. AI 对话的 function calling（"开灯"/"客厅什么温度"）
"""

import json

from core.ai.mcp.core import MCPCallResponse, MCPContent
from core.ai.mcp.tools.plugin_tools import register_plugin_tool_handler

from . import ha


def _resp(payload: dict, is_error: bool = False) -> MCPCallResponse:
    return MCPCallResponse(isError=is_error,
                           content=[MCPContent(text=json.dumps(payload, ensure_ascii=False))])


async def ha_call_service(user_id: int, args: dict) -> MCPCallResponse:
    """Call a Home Assistant service (domain/service/entity_id)."""
    domain = args.get("domain", "")
    service = args.get("service", "")
    if not domain or not service:
        return _resp({"ok": False, "detail": "domain and service are required"}, True)
    result = await ha.call_service(domain, service,
                                   args.get("entity_id"), args.get("data") or {})
    return _resp(result, not result["ok"])


async def ha_get_state(user_id: int, args: dict) -> MCPCallResponse:
    """Get the state of a Home Assistant entity."""
    entity_id = args.get("entity_id", "")
    if not entity_id:
        return _resp({"ok": False, "detail": "entity_id is required"}, True)
    st = await ha.get_state(entity_id)
    if st is None:
        return _resp({"ok": False, "detail": "entity not found or HA not configured"}, True)
    return _resp({"ok": True, "entity_id": st.get("entity_id"),
                  "state": st.get("state"),
                  "friendly_name": (st.get("attributes") or {}).get("friendly_name", "")})


async def ha_toggle(user_id: int, args: dict) -> MCPCallResponse:
    """Toggle a switch/light/input_boolean/fan entity (shorthand)."""
    entity_id = args.get("entity_id", "")
    if not entity_id:
        return _resp({"ok": False, "detail": "entity_id is required"}, True)
    domain = entity_id.split(".")[0]
    service = "toggle" if domain != "script" else "turn_on"
    result = await ha.call_service(domain, service, entity_id)
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


register_plugin_tool_handler("ha_call_service", ha_call_service)
register_plugin_tool_handler("ha_get_state", ha_get_state)
register_plugin_tool_handler("ha_toggle", ha_toggle)
register_plugin_tool_handler("set_device_timer", set_device_timer)
