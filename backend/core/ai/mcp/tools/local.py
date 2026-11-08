"""Tools that execute on the user's desktop computer, not on the server."""

from __future__ import annotations

from core.ai.mcp.core import MCPCallResponse, MCPContent, MCPTool
from core.config.settings import settings
from core.wschannel import local_tools


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


def _err(text: str) -> MCPCallResponse:
    return MCPCallResponse(isError=True, content=[MCPContent(text=text)])


async def list_local_devices(user_id: int, args: dict) -> MCPCallResponse:
    devices = local_tools.devices(user_id)
    if not devices:
        return _ok(
            "当前没有在线的桌面设备。请先打开 OmniAide 桌面端并登录，"
            "然后重试。"
        )
    lines = ["在线桌面设备："]
    for item in devices:
        lines.append(f"- {item['name']} · device_id={item['device_id']}")
    lines.append("")
    lines.append("调用 local_shell 时可用 device_id 指定设备；只有一台在线时可省略。")
    return _ok("\n".join(lines))


async def local_shell(user_id: int, args: dict) -> MCPCallResponse:
    if not settings.local_shell_enabled:
        return _err("本地 shell 工具已被禁用")

    command = str(args.get("command") or "").strip()
    if not command:
        return _err("command 必填")

    try:
        timeout = int(args.get("timeout_seconds") or settings.local_shell_timeout_seconds)
    except (TypeError, ValueError):
        timeout = settings.local_shell_timeout_seconds
    timeout = min(max(timeout, 1), 3600)

    try:
        device_id = local_tools.resolve_device(
            user_id,
            device_id=str(args.get("device_id") or "").strip() or None,
            device=str(args.get("device") or "").strip() or None,
        )
    except local_tools.LocalDeviceError as exc:
        return _err(str(exc))

    cwd = str(args.get("cwd") or "").strip() or None
    try:
        result = await local_tools.call_local(
            user_id,
            device_id,
            "shell",
            {
                "command": command,
                "cwd": cwd,
                "timeout_seconds": timeout,
            },
            timeout_seconds=timeout,
        )
    except local_tools.LocalDeviceError as exc:
        return _err(str(exc))

    if not result.get("ok"):
        device_name = local_tools.host_channel.device_name(device_id)
        return _err(
            f"本地命令执行失败（{device_name}）：{result.get('error') or '未知错误'}"
        )

    payload = result.get("result") or {}
    limit = settings.local_shell_max_output_chars
    stdout = str(payload.get("stdout") or "")[:limit].strip()
    stderr = str(payload.get("stderr") or "")[: min(limit, 8000)].strip()
    exit_code = payload.get("exit_code")
    timed_out = bool(payload.get("timed_out"))
    device_name = local_tools.host_channel.device_name(device_id)

    lines = [
        f"设备：{device_name} ({device_id})",
        f"cwd：{payload.get('cwd') or cwd or '~'}",
        f"退出码：{exit_code}" + ("（超时）" if timed_out else ""),
    ]
    if stdout:
        lines.append(f"\nstdout:\n{stdout}")
    if stderr:
        lines.append(f"\nstderr:\n{stderr}")
    return _ok("\n".join(lines))


TOOLS = [
    (
        MCPTool(
            name="list_local_devices",
            description=(
                "列出当前在线的桌面执行设备（OmniAide 桌面端）。"
                "多台电脑在线时，用返回的 device_id 指定 local_shell 在哪台执行。"
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        list_local_devices,
    ),
    (
        MCPTool(
            name="local_shell",
            description=(
                "在用户自己的电脑（Mac/Windows）上执行 shell 命令，适合访问本机文件、"
                "localhost、局域网/VPN 资源或本机已安装的 CLI。命令默认需要在桌面端"
                "逐条批准。多台设备在线时用 device_id 指定；可先调用 "
                "list_local_devices 查看。不要在服务器上执行同样的命令时使用本工具。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                    "cwd": {
                        "type": "string",
                        "description": "本地执行目录，默认用户主目录",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "超时秒数，默认 600，最大 3600",
                    },
                    "device_id": {
                        "type": "string",
                        "description": "桌面设备 ID；只有一台在线时可省略",
                    },
                    "device": {
                        "type": "string",
                        "description": "桌面设备名称（主机名）；与 device_id 二选一",
                    },
                },
                "required": ["command"],
            },
        ),
        local_shell,
    ),
]
