"""Tools that execute on the user's desktop computer, not on the server."""

from __future__ import annotations

import json
from pathlib import Path

from ai.mcp.core import MCPCallResponse, MCPContent, MCPTool
from core.config.settings import settings
from core.wschannel import local_tools


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


def _err(text: str) -> MCPCallResponse:
    return MCPCallResponse(isError=True, content=[MCPContent(text=text)])


async def list_local_machines(user_id: int, args: dict) -> MCPCallResponse:
    machines = local_tools.machines(user_id)
    if not machines:
        return _ok(
            "当前没有在线的本地机器。请先打开 OmniAide 桌面端并登录，"
            "然后重试。"
        )
    lines = ["在线本地机器："]
    for item in machines:
        lines.append(f"- {item['name']} · machine_id={item['machine_id']}")
    lines.append("")
    lines.append("调用 local_* 工具时可用 machine_id 指定本地机器；只有一台本地机器在线时可省略。")
    return _ok("\n".join(lines))


def _resolve_machine(user_id: int, args: dict) -> str:
    return local_tools.resolve_machine(
        user_id,
        machine_id=str(args.get("machine_id") or "").strip() or None,
        machine=str(args.get("machine") or "").strip() or None,
    )


async def _call(
    user_id: int,
    args: dict,
    tool: str,
    payload: dict,
    *,
    timeout: int = 120,
) -> tuple[str | None, dict | None, str | None]:
    """Return ``(machine_id, result, error)``."""
    try:
        machine_id = _resolve_machine(user_id, args)
    except local_tools.LocalMachineError as exc:
        return None, None, str(exc)
    try:
        response = await local_tools.call_local(
            user_id,
            machine_id,
            tool,
            payload,
            timeout_seconds=timeout,
        )
    except local_tools.LocalMachineError as exc:
        return machine_id, None, str(exc)
    if not response.get("ok"):
        return machine_id, None, str(response.get("error") or "未知错误")
    return machine_id, response.get("result") or {}, None


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
    machine_id, payload, error = await _call(
        user_id,
        args,
        "shell",
        {"command": command, "cwd": cwd, "timeout_seconds": timeout},
        timeout=timeout,
    )
    if error or payload is None:
        name = local_tools.host_channel.machine_name(machine_id) if machine_id else ""
        return _err(f"本地命令执行失败（{name or '未连接本地机器'}）：{error}")

    limit = settings.local_shell_max_output_chars
    stdout = str(payload.get("stdout") or "")[:limit].strip()
    stderr = str(payload.get("stderr") or "")[: min(limit, 8000)].strip()
    machine_name = local_tools.host_channel.machine_name(machine_id or "")
    lines = [
        f"本地机器：{machine_name} ({machine_id})",
        f"cwd：{payload.get('cwd') or cwd or '~'}",
        f"退出码：{payload.get('exit_code')}"
        + ("（超时）" if payload.get("timed_out") else ""),
    ]
    if stdout:
        lines.append(f"\nstdout:\n{stdout}")
    if stderr:
        lines.append(f"\nstderr:\n{stderr}")
    return _ok("\n".join(lines))


async def local_shell_start(user_id: int, args: dict) -> MCPCallResponse:
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
        machine_id = _resolve_machine(user_id, args)
        job = await local_tools.start_job(
            user_id,
            machine_id,
            command,
            cwd=str(args.get("cwd") or "").strip() or None,
            timeout_seconds=timeout,
        )
    except local_tools.LocalMachineError as exc:
        return _err(str(exc))

    machine_name = local_tools.host_channel.machine_name(machine_id)
    return _ok(
        f"已在本地机器启动任务。\n"
        f"job_id：{job.job_id}\n"
        f"机器：{machine_name} ({machine_id})\n"
        f"目录：{job.cwd or '~'}\n"
        f"用 local_shell_wait(job_id=\"{job.job_id}\") 读取输出，"
        f"用 local_shell_cancel 取消。"
    )


async def local_shell_wait(user_id: int, args: dict) -> MCPCallResponse:
    job_id = str(args.get("job_id") or "").strip()
    if not job_id:
        return _err("job_id 必填")
    try:
        cursor = int(args.get("cursor") or 0)
    except (TypeError, ValueError):
        cursor = 0
    try:
        wait_seconds = int(args.get("wait_seconds") or 60)
    except (TypeError, ValueError):
        wait_seconds = 60

    try:
        job, events, next_cursor = await local_tools.wait_job(
            user_id,
            job_id,
            cursor=cursor,
            wait_seconds=wait_seconds,
        )
    except local_tools.LocalMachineError as exc:
        return _err(str(exc))

    stdout = "".join(text for stream, text in events if stream == "stdout")
    stderr = "".join(text for stream, text in events if stream == "stderr")
    machine_name = local_tools.host_channel.machine_name(job.machine_id)
    lines = [
        f"job_id：{job.job_id}",
        f"机器：{machine_name} ({job.machine_id})",
        f"状态：{job.status}",
    ]
    if job.status in ("done", "cancelled"):
        lines.append(
            f"退出码：{job.exit_code}"
            + ("（超时）" if job.timed_out else "")
            + ("（已取消）" if job.cancelled else "")
        )
    if stdout:
        lines.append(f"\nstdout:\n{stdout}")
    if stderr:
        lines.append(f"\nstderr:\n{stderr}")
    if not stdout and not stderr:
        lines.append("（暂无新输出）")
    lines.append(f"\nnext_cursor：{next_cursor}")
    if job.truncated:
        lines.append("（输出已截断）")
    return _ok("\n".join(lines))


async def local_shell_cancel(user_id: int, args: dict) -> MCPCallResponse:
    job_id = str(args.get("job_id") or "").strip()
    if not job_id:
        return _err("job_id 必填")
    try:
        job = await local_tools.cancel_job(user_id, job_id)
    except local_tools.LocalMachineError as exc:
        return _err(str(exc))
    return _ok(f"已请求取消 {job_id}，当前状态：{job.status}")


async def local_mcp_search(user_id: int, args: dict) -> MCPCallResponse:
    query = str(args.get("query") or "").strip()
    if not query:
        return _err("query 必填，例如 filesystem / browser / git")
    try:
        limit = int(args.get("limit") or 10)
    except (TypeError, ValueError):
        limit = 10
    limit = min(max(limit, 1), 30)
    try:
        machine_id = _resolve_machine(user_id, args)
        response = await local_tools.call_local(
            user_id,
            machine_id,
            "mcp_search",
            {"query": query, "limit": limit},
            timeout_seconds=60,
        )
    except local_tools.LocalMachineError as exc:
        return _err(str(exc))
    if not response.get("ok"):
        return _err(str(response.get("error") or "读取本地 MCP 失败"))
    payload = response.get("result") or {}
    tools = payload.get("tools") if isinstance(payload, dict) else []
    machine_name = local_tools.host_channel.machine_name(machine_id)
    lines = [
        f"本地机器：{machine_name} ({machine_id})",
        f"搜索：{query}",
    ]
    if not tools:
        lines.append("没有匹配的本地 MCP 工具。")
        return _ok("\n".join(lines))
    by_server: dict[str, list] = {}
    names: dict[str, str] = {}
    for item in tools:
        server_id = str(item.get("server_id") or "")
        if not server_id:
            continue
        by_server.setdefault(server_id, []).append(item)
        names[server_id] = str(item.get("server_name") or server_id)
    for server_id, items in by_server.items():
        lines.append(f"\n服务器：{names.get(server_id, server_id)} (server_id={server_id})")
        for item in items:
            lines.append(f"- {item.get('name')}: {item.get('description') or ''}")
            schema = item.get("input_schema")
            if isinstance(schema, dict):
                lines.append(
                    "  schema: "
                    + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))[:1200]
                )
    lines.append(
        "\n调用方式：local_mcp_call(server_id, tool, arguments, machine_id)"
    )
    return _ok("\n".join(lines))


async def local_mcp_call(user_id: int, args: dict) -> MCPCallResponse:
    server_id = str(args.get("server_id") or "").strip()
    tool_name = str(args.get("tool") or "").strip()
    if not server_id or not tool_name:
        return _err("server_id 和 tool 必填")
    arguments = args.get("arguments")
    if not isinstance(arguments, dict):
        arguments = args.get("args") if isinstance(args.get("args"), dict) else {}
    try:
        machine_id = _resolve_machine(user_id, args)
        response = await local_tools.call_local(
            user_id,
            machine_id,
            "mcp_call",
            {
                "server_id": server_id,
                "tool": tool_name,
                "arguments": arguments,
            },
            timeout_seconds=120,
        )
    except local_tools.LocalMachineError as exc:
        return _err(str(exc))
    if not response.get("ok"):
        return _err(str(response.get("error") or "本地 MCP 调用失败"))
    payload = response.get("result") or {}
    content = payload.get("content") if isinstance(payload, dict) else None
    if isinstance(content, str):
        text = content
    else:
        text = json.dumps(content, ensure_ascii=False)
    if payload.get("is_error"):
        return _err(text or "本地 MCP 工具执行出错")
    return _ok(text or "(本地 MCP 返回空结果)")


async def local_list_dir(user_id: int, args: dict) -> MCPCallResponse:
    path = str(args.get("path") or "").strip()
    if not path:
        return _err("path 必填，例如 ~/projects")

    machine_id, payload, error = await _call(
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
    machine_name = local_tools.host_channel.machine_name(machine_id or "")
    lines = [
        f"本地机器：{machine_name} ({machine_id})",
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

    machine_id, payload, error = await _call(
        user_id,
        args,
        "read_file",
        {"path": path, "max_bytes": max_bytes},
    )
    if error or payload is None:
        return _err(f"读取文件失败：{error}")

    machine_name = local_tools.host_channel.machine_name(machine_id or "")
    lines = [
        f"本地机器：{machine_name} ({machine_id})",
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

    machine_id, payload, error = await _call(
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

    machine_name = local_tools.host_channel.machine_name(machine_id or "")
    action = "创建" if payload.get("created") else "覆盖"
    return _ok(
        f"本地机器：{machine_name} ({machine_id})\n"
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

    machine_id, payload, error = await _call(
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
    machine_name = local_tools.host_channel.machine_name(machine_id or "")
    lines = [
        f"本地机器：{machine_name} ({machine_id})",
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


def _is_server_project_path(user_id: int, path: str) -> bool:
    """Server-side project paths must not be sent to a desktop machine."""
    raw = str(path or "").strip()
    if not raw.startswith("/"):
        return False
    if raw == "/data/workspace" or raw.startswith("/data/workspace/"):
        return True
    try:
        from core.paths import projects_root

        root = projects_root(user_id).resolve()
        target = Path(raw).expanduser().resolve()
        return target == root or root in target.parents
    except Exception:
        return False


async def local_file(user_id: int, args: dict) -> MCPCallResponse:
    """One local filesystem entry point for list/read/write/grep."""
    op = str(args.get("op") or "").strip().lower()
    if _is_server_project_path(user_id, str(args.get("path") or "")):
        return _err(
            "这是服务端项目路径，不是本地机器路径。"
            "分析服务端项目请用 project_file；local_file 只用于用户设备上的文件。"
            "设备端路径请使用 ~ 或该设备自己的绝对路径。"
        )
    if op in ("list", "ls", "dir"):
        return await local_list_dir(user_id, args)
    if op in ("read", "cat"):
        return await local_read_file(user_id, args)
    if op in ("write", "save"):
        return await local_write_file(user_id, args)
    if op in ("grep", "search"):
        return await local_grep(user_id, args)
    return _err("op 必须是 list / read / write / grep")


TOOLS = [
    (
        MCPTool(
            name="list_local_machines",
            description=(
                "列出当前在线的本地机器（OmniAide 桌面端）。"
                "多台本地机器在线时，用返回的 machine_id 指定 local_* 工具在哪台本地机器执行。"
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        list_local_machines,
    ),
    (
        MCPTool(
            name="local_shell",
            description=(
                "在用户自己的本地机器（Mac/Windows）上执行 shell 命令，适合访问本机文件、"
                "localhost、局域网/VPN 资源或本机已安装的 CLI。命令默认需要在桌面端"
                "逐条批准。多台本地机器在线时用 machine_id 指定；可先调用 "
                "list_local_machines 查看。不要在服务器上执行同样的命令时使用本工具。"
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
                    "machine_id": {
                        "type": "string",
                        "description": "本地机器 ID；只有一台本地机器在线时可省略",
                    },
                    "machine": {
                        "type": "string",
                        "description": "本地机器名称（主机名）；与 machine_id 二选一",
                    },
                },
                "required": ["command"],
            },
        ),
        local_shell,
    ),
    (
        MCPTool(
            name="local_shell_start",
            description=(
                "在本地机器上启动一个长命令并立即返回 job_id。适合构建、测试、下载、"
                "长时间脚本。之后用 local_shell_wait 读取输出，用 local_shell_cancel 取消。"
                "启动前桌面端会审批一次。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                    "cwd": {"type": "string", "description": "执行目录，默认用户主目录"},
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "超时秒数，默认 600，最大 3600",
                    },
                    "machine_id": {"type": "string", "description": "本地机器 ID"},
                    "machine": {"type": "string", "description": "本地机器名称"},
                },
                "required": ["command"],
            },
        ),
        local_shell_start,
    ),
    (
        MCPTool(
            name="local_shell_wait",
            description=(
                "读取 local_shell_start 任务的增量输出。传回上一次的 next_cursor，"
                "最多等待 wait_seconds 秒。任务完成时返回退出码。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "local_shell_start 返回的 job_id"},
                    "cursor": {
                        "type": "integer",
                        "description": "上次返回的 next_cursor，默认 0",
                    },
                    "wait_seconds": {
                        "type": "integer",
                        "description": "等待秒数，默认 60，最大 300；长任务建议用 300 减少轮次",
                    },
                },
                "required": ["job_id"],
            },
        ),
        local_shell_wait,
    ),
    (
        MCPTool(
            name="local_shell_cancel",
            description="取消 local_shell_start 启动的本地任务，会杀掉进程组。",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "任务 ID"},
                },
                "required": ["job_id"],
            },
        ),
        local_shell_cancel,
    ),
    (
        MCPTool(
            name="local_mcp_search",
            description=(
                "搜索指定本地机器上的 MCP 工具及参数 schema。"
                "用 query 关键词（如 filesystem、browser、git）检索，"
                "再用 local_mcp_call 调用匹配的工具。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "limit": {
                        "type": "integer",
                        "description": "最多返回数量，默认 10，最大 30",
                    },
                    "machine_id": {"type": "string", "description": "本地机器 ID"},
                    "machine": {"type": "string", "description": "本地机器名称"},
                },
                "required": ["query"],
            },
        ),
        local_mcp_search,
    ),
    (
        MCPTool(
            name="local_mcp_call",
            description=(
                "调用本地机器上的 MCP 工具。先调用 local_mcp_search 获取 server_id、"
                "工具名和参数 schema。调用会需要审批。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "server_id": {"type": "string", "description": "MCP 服务器 ID"},
                    "tool": {"type": "string", "description": "工具名"},
                    "arguments": {
                        "type": "object",
                        "description": "工具参数 JSON",
                    },
                    "machine_id": {"type": "string", "description": "本地机器 ID"},
                    "machine": {"type": "string", "description": "本地机器名称"},
                },
                "required": ["server_id", "tool"],
            },
        ),
        local_mcp_call,
    ),
    (
        MCPTool(
            name="local_list_dir",
            description=(
                "列出用户本地机器上某个目录的内容。路径支持 ~ 和绝对路径；"
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
                    "machine_id": {"type": "string", "description": "本地机器 ID"},
                    "machine": {"type": "string", "description": "本地机器名称"},
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
                "读取用户本地机器上的文本文件。默认最多读取 200KB，"
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
                    "machine_id": {"type": "string", "description": "本地机器 ID"},
                    "machine": {"type": "string", "description": "本地机器名称"},
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
                "在用户本地机器上创建或覆盖文本文件。默认不覆盖已有文件；"
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
                    "machine_id": {"type": "string", "description": "本地机器 ID"},
                    "machine": {"type": "string", "description": "本地机器名称"},
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
                "在用户本地机器的目录里搜索文本，返回 路径:行号: 内容。"
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
                    "machine_id": {"type": "string", "description": "本地机器 ID"},
                    "machine": {"type": "string", "description": "本地机器名称"},
                },
                "required": ["pattern", "path"],
            },
        ),
        local_grep,
    ),
    (
        MCPTool(
            name="local_file",
            description=(
                "在用户本地机器上操作文件。op=list 列目录，op=read 读文本，"
                "op=write 写文件，op=grep 在目录中搜索文本。"
                "只用于用户设备上的文件；服务端项目路径请用 project_file。"
                "写入默认需要桌面端确认。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "op": {
                        "type": "string",
                        "enum": ["list", "read", "write", "grep"],
                        "description": "操作类型",
                    },
                    "path": {
                        "type": "string",
                        "description": "文件或目录路径，支持 ~ 和绝对路径",
                    },
                    "content": {
                        "type": "string",
                        "description": "op=write 时的文本内容",
                    },
                    "include_hidden": {
                        "type": "boolean",
                        "description": "op=list 时是否包含隐藏文件",
                    },
                    "max_bytes": {
                        "type": "integer",
                        "description": "op=read 时最多读取的字节数，默认 200000",
                    },
                    "create_dirs": {
                        "type": "boolean",
                        "description": "op=write 时是否自动创建父目录",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "op=write 时是否允许覆盖已有文件",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "op=grep 时的正则表达式",
                    },
                    "glob": {
                        "type": "string",
                        "description": "op=grep 时的文件名过滤，例如 *.ts",
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": "op=grep 时是否区分大小写，默认 true",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "op=grep 时最多返回条数，默认 100",
                    },
                    "machine_id": {
                        "type": "string",
                        "description": "本地机器 ID；只有一台在线时可省略",
                    },
                    "machine": {
                        "type": "string",
                        "description": "本地机器名称；与 machine_id 二选一",
                    },
                },
                "required": ["op", "path"],
            },
        ),
        local_file,
    ),
]

# Local tools are injected by the desktop node, not builtin tools.
for _tool, _handler in TOOLS:
    _tool.source = "local"
