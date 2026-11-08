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
    lines.append("调用 local_* 工具时可用 device_id 指定设备；只有一台在线时可省略。")
    return _ok("\n".join(lines))


def _resolve_device(user_id: int, args: dict) -> str:
    return local_tools.resolve_device(
        user_id,
        device_id=str(args.get("device_id") or "").strip() or None,
        device=str(args.get("device") or "").strip() or None,
    )


async def _call(
    user_id: int,
    args: dict,
    tool: str,
    payload: dict,
    *,
    timeout: int = 120,
) -> tuple[str | None, dict | None, str | None]:
    """Return ``(device_id, result, error)``."""
    try:
        device_id = _resolve_device(user_id, args)
    except local_tools.LocalDeviceError as exc:
        return None, None, str(exc)
    try:
        response = await local_tools.call_local(
            user_id,
            device_id,
            tool,
            payload,
            timeout_seconds=timeout,
        )
    except local_tools.LocalDeviceError as exc:
        return device_id, None, str(exc)
    if not response.get("ok"):
        return device_id, None, str(response.get("error") or "未知错误")
    return device_id, response.get("result") or {}, None


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

    cwd = str(args.get("cwd") or "").strip() or None
    device_id, payload, error = await _call(
        user_id,
        args,
        "shell",
        {"command": command, "cwd": cwd, "timeout_seconds": timeout},
        timeout=timeout,
    )
    if error or payload is None:
        name = local_tools.host_channel.device_name(device_id) if device_id else ""
        return _err(f"本地命令执行失败（{name or '未连接设备'}）：{error}")

    limit = settings.local_shell_max_output_chars
    stdout = str(payload.get("stdout") or "")[:limit].strip()
    stderr = str(payload.get("stderr") or "")[: min(limit, 8000)].strip()
    device_name = local_tools.host_channel.device_name(device_id or "")
    lines = [
        f"设备：{device_name} ({device_id})",
        f"cwd：{payload.get('cwd') or cwd or '~'}",
        f"退出码：{payload.get('exit_code')}"
        + ("（超时）" if payload.get("timed_out") else ""),
    ]
    if stdout:
        lines.append(f"\nstdout:\n{stdout}")
    if stderr:
        lines.append(f"\nstderr:\n{stderr}")
    return _ok("\n".join(lines))


async def local_list_dir(user_id: int, args: dict) -> MCPCallResponse:
    path = str(args.get("path") or "").strip()
    if not path:
        return _err("path 必填，例如 ~/projects")

    device_id, payload, error = await _call(
        user_id,
        args,
        "list_dir",
        {
            "path": path,
            "include_hidden": bool(args.get("include_hidden")),
        },
    )
    if error or payload is None:
        return _err(f"列目录失败：{error}")

    entries = payload.get("entries") or []
    device_name = local_tools.host_channel.device_name(device_id or "")
    lines = [
        f"设备：{device_name} ({device_id})",
        f"目录：{payload.get('path') or path}",
        f"共 {len(entries)} 项",
    ]
    for item in entries[:500]:
        kind = "dir" if item.get("type") == "dir" else "file"
        size = item.get("size")
        size_text = f" {size}B" if isinstance(size, int) and kind == "file" else ""
        lines.append(f"- [{kind}] {item.get('name')}{size_text}")
    if payload.get("truncated"):
        lines.append("...（已截断）")
    return _ok("\n".join(lines))


async def local_read_file(user_id: int, args: dict) -> MCPCallResponse:
    path = str(args.get("path") or "").strip()
    if not path:
        return _err("path 必填")

    try:
        max_bytes = int(args.get("max_bytes") or 200_000)
    except (TypeError, ValueError):
        max_bytes = 200_000
    max_bytes = min(max(max_bytes, 1), 2_000_000)

    device_id, payload, error = await _call(
        user_id,
        args,
        "read_file",
        {"path": path, "max_bytes": max_bytes},
    )
    if error or payload is None:
        return _err(f"读取文件失败：{error}")

    device_name = local_tools.host_channel.device_name(device_id or "")
    lines = [
        f"设备：{device_name} ({device_id})",
        f"文件：{payload.get('path') or path}",
        f"大小：{payload.get('size', 0)}B",
    ]
    if payload.get("binary"):
        lines.append("这是二进制文件，未返回内容。")
        return _ok("\n".join(lines))
    content = str(payload.get("content") or "")
    if payload.get("truncated"):
        lines.append(f"（只读取了前 {max_bytes} 字节）")
    lines.append("")
    lines.append(content)
    return _ok("\n".join(lines))


async def local_write_file(user_id: int, args: dict) -> MCPCallResponse:
    path = str(args.get("path") or "").strip()
    if not path:
        return _err("path 必填")
    content = args.get("content")
    if not isinstance(content, str):
        return _err("content 必须是字符串")

    device_id, payload, error = await _call(
        user_id,
        args,
        "write_file",
        {
            "path": path,
            "content": content,
            "create_dirs": bool(args.get("create_dirs", True)),
            "overwrite": bool(args.get("overwrite")),
        },
    )
    if error or payload is None:
        return _err(f"写入文件失败：{error}")

    device_name = local_tools.host_channel.device_name(device_id or "")
    action = "创建" if payload.get("created") else "覆盖"
    return _ok(
        f"设备：{device_name} ({device_id})\n"
        f"已{action}：{payload.get('path') or path}\n"
        f"写入：{payload.get('bytes', len(content.encode('utf-8')))} 字节"
    )


async def local_grep(user_id: int, args: dict) -> MCPCallResponse:
    pattern = str(args.get("pattern") or "").strip()
    path = str(args.get("path") or "").strip()
    if not pattern:
        return _err("pattern 必填")
    if not path:
        return _err("path 必填")

    try:
        max_results = int(args.get("max_results") or 100)
    except (TypeError, ValueError):
        max_results = 100
    max_results = min(max(max_results, 1), 500)

    device_id, payload, error = await _call(
        user_id,
        args,
        "grep",
        {
            "pattern": pattern,
            "path": path,
            "glob": str(args.get("glob") or "").strip() or None,
            "case_sensitive": bool(args.get("case_sensitive", True)),
            "max_results": max_results,
        },
        timeout=300,
    )
    if error or payload is None:
        return _err(f"搜索失败：{error}")

    matches = payload.get("matches") or []
    device_name = local_tools.host_channel.device_name(device_id or "")
    lines = [
        f"设备：{device_name} ({device_id})",
        f"路径：{payload.get('path') or path}",
        f"匹配：{len(matches)} 条",
    ]
    for item in matches:
        lines.append(
            f"{item.get('path')}:{item.get('line')}: {item.get('text')}"
        )
    if payload.get("truncated"):
        lines.append("...（结果已截断）")
    return _ok("\n".join(lines))


TOOLS = [
    (
        MCPTool(
            name="list_local_devices",
            description=(
                "列出当前在线的桌面执行设备（OmniAide 桌面端）。"
                "多台电脑在线时，用返回的 device_id 指定 local_* 工具在哪台执行。"
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
    (
        MCPTool(
            name="local_list_dir",
            description=(
                "列出用户电脑上某个目录的内容。路径支持 ~ 和绝对路径；"
                "相对路径按用户主目录解析。默认需要在桌面端确认。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径，例如 ~/Downloads"},
                    "include_hidden": {
                        "type": "boolean",
                        "description": "是否包含隐藏文件，默认 false",
                    },
                    "device_id": {"type": "string", "description": "桌面设备 ID"},
                    "device": {"type": "string", "description": "桌面设备名称"},
                },
                "required": ["path"],
            },
        ),
        local_list_dir,
    ),
    (
        MCPTool(
            name="local_read_file",
            description=(
                "读取用户电脑上的文本文件。默认最多读取 200KB，"
                "二进制文件只返回元信息。路径支持 ~ 和绝对路径。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "max_bytes": {
                        "type": "integer",
                        "description": "最多读取字节数，默认 200000，最大 2000000",
                    },
                    "device_id": {"type": "string", "description": "桌面设备 ID"},
                    "device": {"type": "string", "description": "桌面设备名称"},
                },
                "required": ["path"],
            },
        ),
        local_read_file,
    ),
    (
        MCPTool(
            name="local_write_file",
            description=(
                "在用户电脑上创建或覆盖文本文件。默认不覆盖已有文件；"
                "需要修改已有文件时传 overwrite=true（桌面端会确认）。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "写入的文本内容"},
                    "create_dirs": {
                        "type": "boolean",
                        "description": "父目录不存在时自动创建，默认 true",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "是否覆盖已有文件，默认 false",
                    },
                    "device_id": {"type": "string", "description": "桌面设备 ID"},
                    "device": {"type": "string", "description": "桌面设备名称"},
                },
                "required": ["path", "content"],
            },
        ),
        local_write_file,
    ),
    (
        MCPTool(
            name="local_grep",
            description=(
                "在用户电脑的目录里搜索文本，返回 路径:行号: 内容。"
                "适合在本机项目/日志中查找，避免用 shell 拼 grep 命令。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "正则表达式"},
                    "path": {"type": "string", "description": "搜索目录"},
                    "glob": {
                        "type": "string",
                        "description": "文件名过滤，例如 *.ts 或 *.log",
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": "是否区分大小写，默认 true",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最多返回条数，默认 100，最大 500",
                    },
                    "device_id": {"type": "string", "description": "桌面设备 ID"},
                    "device": {"type": "string", "description": "桌面设备名称"},
                },
                "required": ["pattern", "path"],
            },
        ),
        local_grep,
    ),
]
