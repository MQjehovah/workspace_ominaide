import asyncio
import json
import secrets
import time
from pathlib import Path

from core.config.settings import settings
from core.wschannel.hub import host_channel

from plugins.vibecoding.backend.service import CHANNEL, hub
from plugins.vibecoding.backend import workspace

MAX_TOOL_RESULT_CHARS = 20_000

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories under the project. Paths are relative to the project root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path, default '.'"},
                    "depth": {"type": "number", "description": "Recursion depth 1-4, default 2"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 text file. Use offset/limit for large files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path"},
                    "offset": {"type": "number", "description": "Start line offset, default 0"},
                    "limit": {"type": "number", "description": "Max lines, default 400"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with the given content. Parent directories are created automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path"},
                    "content": {"type": "string", "description": "Full file content"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace an exact string in a file. Use replace_all to change every occurrence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path"},
                    "old_string": {"type": "string", "description": "Exact text to replace"},
                    "new_string": {"type": "string", "description": "Replacement text"},
                    "replace_all": {"type": "boolean", "description": "Replace all occurrences, default false"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_text",
            "description": "Search text files in the project with a regular expression. Returns file path, line number and line text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regular expression"},
                    "path": {"type": "string", "description": "Relative directory to search, default '.'"},
                    "include": {"type": "string", "description": "Optional file suffix filter, e.g. '.ts,.vue'"},
                    "max_results": {"type": "number", "description": "Max matches, default 50"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command in the project directory and return stdout/stderr/exit code. Use for builds, tests and git.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command line to run"},
                    "cwd": {"type": "string", "description": "Relative working directory, default '.'"},
                    "timeout_ms": {"type": "number", "description": "Timeout in ms, default 120000"},
                },
                "required": ["command"],
            },
        },
    },
]

_TASKS: dict[str, asyncio.Task] = {}
_CANCEL: set[str] = set()


def new_task_id() -> str:
    return f"t-{int(time.time() * 1000):x}-{secrets.token_hex(3)}"


def is_server_task(task_id: str | None) -> bool:
    return bool(task_id) and (task_id in _TASKS or task_id in _CANCEL)


def cancel_server_task(task_id: str | None) -> bool:
    if not task_id:
        return False
    _CANCEL.add(task_id)
    task = _TASKS.get(task_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def _emit(user_id: int, task_id: str, event: str, data: dict):
    ts = int(time.time() * 1000)
    msg = {"type": "task.event", "task_id": task_id, "event": event, "data": data, "ts": ts}
    try:
        hub.note_task_event(user_id, "server", msg)
    except Exception:
        pass
    await host_channel.broadcast_to_viewers(
        user_id,
        CHANNEL,
        {"type": "task.event", "device_id": "server", "task_id": task_id,
         "event": event, "data": data, "ts": ts},
    )
    if event in ("started", "done", "failed"):
        try:
            await hub.push_device_status(user_id)
        except Exception:
            pass


async def _load_developer(user_id: int) -> dict | None:
    try:
        from sqlalchemy import select
        from core.auth.domain.models import UserProfile
        from core.database.session import async_session
        async with async_session() as db:
            result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
            profile = result.scalar_one_or_none()
            if profile and profile.developer:
                return json.loads(profile.developer)
    except Exception:
        pass
    return None


def _system_prompt(project: str, developer: dict | None) -> str:
    lines = [
        "你是 OmniAide 内置的编程 Agent，运行在用户自己的后端服务器上，当前为全自动模式。",
        f"项目根目录：{project}",
        "",
        "工作方式：",
        "1. 先理解项目结构与相关代码，再动手修改；优先读取现有实现而不是猜测。",
        "2. 使用工具真正完成工作，不要只输出计划或伪代码。",
        "3. 所有路径都使用相对项目根目录的路径；不要访问项目根目录以外的位置。",
        "4. 修改后尽量运行构建、测试或最小验证命令确认没有破坏。",
        "5. 不要执行格式化磁盘、关机、删除项目根目录等破坏性命令。",
        "6. 完成后用中文简要说明改了什么、验证结果，以及仍需用户注意的事项。",
        "",
        "可用工具：list_dir / read_file / write_file / edit_file / search_text / run_command。",
    ]
    if developer:
        perms = developer.get("permissions") if isinstance(developer.get("permissions"), list) else []
        lines += ["", "【开发者档案】"]
        if developer.get("github_username"):
            lines.append(f"GitHub 用户名：{developer['github_username']}")
        if developer.get("github_email"):
            lines.append(f"Git 提交邮箱：{developer['github_email']}")
        if developer.get("default_branch"):
            lines.append(f"默认分支：{developer['default_branch']}")
        if developer.get("workspace_roots"):
            lines.append(f"工作区根目录：{', '.join(developer['workspace_roots'])}")
        if developer.get("commit_style"):
            lines.append(f"提交信息规范：{developer['commit_style']}")
        lines.append(f"允许的代码操作：{', '.join(perms) if perms else '仅读取与修改'}")
        if "push" in perms:
            lines.append(
                "推送使用 SSH（/root/.ssh/id_rsa）。remote 为 https 时改用 git@github.com:<owner>/<repo>.git；"
                "禁止 force push；除非用户明确要求，优先新建分支推送，不要直接推 main/master。"
            )
        else:
            lines.append("不要执行 git commit 或 git push。")
        if developer.get("notes"):
            lines.append(f"补充说明：{developer['notes']}")
    else:
        lines.append("")
        lines.append("未配置开发者档案：只允许读取和修改文件，不要执行 git commit 或 git push。")
    return "\n".join(lines)


def _assistant_message(msg) -> dict:
    message: dict = {"role": "assistant", "content": msg.content or None}
    reasoning = getattr(msg, "reasoning_content", None)
    if reasoning:
        message["reasoning_content"] = reasoning
    if msg.tool_calls:
        message["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]
    return message


async def _run_task(user_id: int, task_id: str, project: str, instruction: str, source: str):
    started = time.time()
    developer = await _load_developer(user_id)
    perms = developer.get("permissions", []) if developer else []
    allow_push = isinstance(perms, list) and "push" in perms
    allow_commit = isinstance(perms, list) and "commit" in perms
    identity = {
        "name": (developer or {}).get("github_username"),
        "email": (developer or {}).get("github_email"),
    }
    project_name = Path(project).name

    try:
        await _emit(user_id, task_id, "started", {
            "tool": "omniaide",
            "project": project,
            "project_name": project_name,
            "input": instruction[:500],
            "source": source,
            "engine": "server",
        })
        await _emit(user_id, task_id, "milestone", {"stage": "executing"})

        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        messages: list[dict] = [
            {"role": "system", "content": _system_prompt(project, developer)},
            {"role": "user", "content": instruction},
        ]
        final = ""
        last_text = ""
        max_turns = min(max(settings.coding_max_turns, 1), 80)

        for _turn in range(max_turns):
            if task_id in _CANCEL:
                await _emit(user_id, task_id, "milestone", {"stage": "cancelled"})
                await _emit(user_id, task_id, "done", {
                    "code": 0, "duration_ms": int((time.time() - started) * 1000),
                    "output": last_text or "已取消",
                })
                return

            response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                tools=TOOLS,
                temperature=0.2,
            )
            message = response.choices[0].message
            content = (message.content or "").strip()
            if content:
                last_text = content
                await _emit(user_id, task_id, "output", {"chunk": content + "\n"})

            if not message.tool_calls:
                final = content
                break

            messages.append(_assistant_message(message))
            for call in message.tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                await _emit(user_id, task_id, "tool", {"name": name, "detail": _describe(name, args)})
                result = await workspace.execute_tool(
                    project, name, args,
                    allow_push=allow_push, allow_commit=allow_commit, identity=identity,
                )
                if name in ("write_file", "edit_file") and not result.get("error"):
                    await _emit(user_id, task_id, "file", {"path": str(args.get("path") or ""), "action": "modified"})
                text = json.dumps(result, ensure_ascii=False, default=str)
                if len(text) > MAX_TOOL_RESULT_CHARS:
                    text = text[:MAX_TOOL_RESULT_CHARS] + "\n...[truncated]"
                messages.append({"role": "tool", "tool_call_id": call.id, "content": text})

        duration = int((time.time() - started) * 1000)
        if not final:
            final = last_text or "已达到最大步数，未生成最终总结。"
        await _emit(user_id, task_id, "done", {
            "code": 0,
            "duration_ms": duration,
            "output": final[:MAX_TOOL_RESULT_CHARS],
        })
    except asyncio.CancelledError:
        await _emit(user_id, task_id, "milestone", {"stage": "cancelled"})
        await _emit(user_id, task_id, "done", {
            "code": 0,
            "duration_ms": int((time.time() - started) * 1000),
            "output": "已取消",
        })
    except Exception as e:
        await _emit(user_id, task_id, "failed", {
            "error": str(e),
            "duration_ms": int((time.time() - started) * 1000),
            "code": -1,
        })


def _describe(name: str, args: dict) -> str:
    if name == "run_command":
        return str(args.get("command") or "")[:160]
    if name in ("read_file", "write_file", "edit_file"):
        return str(args.get("path") or "")
    if name == "list_dir":
        return str(args.get("path") or ".")
    if name == "search_text":
        return f"{args.get('pattern', '')} in {args.get('path', '.')}"
    return json.dumps(args, ensure_ascii=False)[:160]


async def start_server_task(user_id: int, task_id: str | None, project: str | None,
                            instruction: str | None, source: str = "api") -> str:
    task_id = task_id or new_task_id()
    if not project or not instruction:
        await _emit(user_id, task_id, "failed", {"error": "缺少 project/input", "duration_ms": 0, "code": -1})
        return task_id

    root = Path(project).expanduser().resolve()
    workspace_root = Path(settings.coding_workspace_root).expanduser().resolve()
    if root != workspace_root and workspace_root not in root.parents:
        await _emit(user_id, task_id, "failed", {
            "error": f"项目不在工作区内：{project}", "duration_ms": 0, "code": -1,
        })
        return task_id
    if not root.exists() or not root.is_dir():
        await _emit(user_id, task_id, "failed", {
            "error": f"项目目录不存在：{project}", "duration_ms": 0, "code": -1,
        })
        return task_id
    if task_id in _TASKS:
        return task_id

    _CANCEL.discard(task_id)
    task = asyncio.create_task(_run_task(user_id, task_id, str(root), instruction, source))
    _TASKS[task_id] = task
    task.add_done_callback(lambda _t: _TASKS.pop(task_id, None))
    return task_id
