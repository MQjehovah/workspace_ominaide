import asyncio
import json
import logging
import secrets
import time
from pathlib import Path

from core.config.settings import settings
from core.wschannel.hub import host_channel

from plugins.vibecoding.backend import delivery, store, workspace
from plugins.vibecoding.backend.context import build_project_context
from plugins.vibecoding.backend.service import CHANNEL, hub

log = logging.getLogger("uvicorn")

MAX_TOOL_RESULT_CHARS = 20_000
MAX_EVENT_BUFFER = 800

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
            "description": "Run a shell command in the project directory and return stdout/stderr/exit code. Use for builds and tests.",
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
_RECORDERS: dict[str, "TaskRecorder"] = {}


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


class TaskRecorder:
    """Buffers task events/messages and flushes them to `coding_tasks`.

    Persistence must never be able to break a running task, so every write is
    best-effort: failures are logged and swallowed.
    """

    def __init__(self, task_id: str, user_id: int):
        self.task_id = task_id
        self.user_id = user_id
        self.events: list[dict] = []
        self.messages: list[dict] | None = None
        self.status = "running"
        self.code = None
        self.duration_ms = None
        self.turns = 0
        self.output: str | None = None
        self.error: str | None = None
        self.branch: str | None = None
        self.commit_sha: str | None = None
        self.pr_url: str | None = None
        self.ended_ts: int | None = None
        self._lock = asyncio.Lock()
        self._dirty = False
        self._last_flush = 0.0
        self._since_flush = 0

    def set_messages(self, messages: list[dict]) -> None:
        self.messages = list(messages)

    def set_turns(self, turns: int) -> None:
        self.turns = turns

    def set_delivery(self, summary: dict | None) -> None:
        if not summary:
            return
        self.branch = summary.get("branch") or self.branch
        self.commit_sha = summary.get("commit") or self.commit_sha
        self.pr_url = summary.get("pr_url") or self.pr_url

    async def record(self, event: str, data: dict) -> None:
        now = int(time.time() * 1000)
        self.events.append({"ts": now, "event": event, "data": data})
        if len(self.events) > MAX_EVENT_BUFFER:
            self.events = self.events[-MAX_EVENT_BUFFER:]
        self._dirty = True
        self._since_flush += 1

        if event == "started":
            self.status = "running"
        elif event == "done":
            self.status = "done"
            self.ended_ts = now
            self.code = data.get("code")
            self.duration_ms = data.get("duration_ms")
            self.output = str(data.get("output") or "")[:40_000]
        elif event == "failed":
            self.status = "failed"
            self.ended_ts = now
            self.code = data.get("code")
            self.duration_ms = data.get("duration_ms")
            self.error = str(data.get("error") or "")[:4000]
        elif event == "milestone" and data.get("stage") == "cancelled":
            self.status = "cancelled"
            self.ended_ts = now

        if event in ("started", "done", "failed", "delivery") or self._since_flush >= 20 \
                or time.monotonic() - self._last_flush > 2:
            await self.flush()

    async def flush(self, force: bool = False) -> None:
        if not self._dirty and not force:
            return
        async with self._lock:
            fields = {
                "events": self.events,
                "status": self.status,
                "turns": self.turns,
                "branch": self.branch,
                "commit_sha": self.commit_sha,
                "pr_url": self.pr_url,
            }
            if self.messages is not None:
                fields["messages"] = self.messages
            if self.output is not None:
                fields["output"] = self.output
            if self.error is not None:
                fields["error"] = self.error
            if self.code is not None:
                fields["code"] = self.code
            if self.duration_ms is not None:
                fields["duration_ms"] = self.duration_ms
            if self.ended_ts is not None:
                fields["ended_ts"] = self.ended_ts
            try:
                await store.update_task(self.task_id, **fields)
                self._dirty = False
                self._since_flush = 0
                self._last_flush = time.monotonic()
            except Exception as e:  # pragma: no cover - best effort
                log.warning("[coding] failed to persist task %s: %s", self.task_id, e)


async def _emit(user_id: int, task_id: str, event: str, data: dict):
    ts = int(time.time() * 1000)
    msg = {"type": "task.event", "task_id": task_id, "event": event, "data": data, "ts": ts}

    recorder = _RECORDERS.get(task_id)
    if recorder is not None:
        await recorder.record(event, data)

    try:
        hub.note_task_event(user_id, "server", msg)
    except Exception:
        pass
    try:
        await host_channel.broadcast_to_viewers(
            user_id,
            CHANNEL,
            {"type": "task.event", "device_id": "server", "task_id": task_id,
             "event": event, "data": data, "ts": ts},
        )
    except Exception as e:
        log.debug("[coding] broadcast failed for %s: %s", task_id, e)
    if event in ("started", "done", "failed"):
        try:
            await hub.push_device_status(user_id)
        except Exception:
            pass


async def _finalize(task_id: str):
    recorder = _RECORDERS.pop(task_id, None)
    if recorder is not None:
        try:
            await recorder.flush(force=True)
        except Exception:
            pass
    _CANCEL.discard(task_id)


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


def _system_prompt(project: str, developer: dict | None, context: str = "",
                   auto_deliver: bool = False) -> str:
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

    if context.strip():
        lines += ["", "【项目快照】（自动生成，可能不是最新，动手前以实际文件为准）", context.strip()]

    if auto_deliver:
        lines += [
            "",
            "【交付方式】",
            "本次任务启用自动交付：完成后系统会统一执行验证、创建分支、提交并推送。",
            "因此不要自行执行 git commit 或 git push，也不要把改动留在特殊状态（rebase/merge 中）。",
            "如果项目有测试命令，请自行运行并通过；系统随后还会再验证一次。",
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
        if "push" in perms and not auto_deliver:
            lines.append(
                "推送使用 SSH。remote 为 https 时改用 git@github.com:<owner>/<repo>.git；"
                "禁止 force push；除非用户明确要求，优先新建分支推送，不要直接推 main/master。"
            )
        elif not auto_deliver:
            lines.append("不要执行 git commit 或 git push。")
        if developer.get("notes"):
            lines.append(f"补充说明：{developer['notes']}")
    elif not auto_deliver:
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


async def _llm_call(client, messages: list[dict]):
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return await asyncio.wait_for(
                client.chat.completions.create(
                    model=settings.llm_model,
                    messages=messages,
                    tools=TOOLS,
                    temperature=0.2,
                ),
                timeout=240,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            last_error = e
            if attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))
    raise last_error or RuntimeError("LLM call failed")


def _delivery_line(summary: dict | None) -> str:
    if not summary:
        return ""
    if summary.get("skipped"):
        return ""
    branch = summary.get("branch")
    commit = summary.get("commit")
    parts = []
    if branch:
        parts.append(f"分支 {branch}")
    if commit:
        parts.append(f"提交 {commit}")
    if summary.get("pushed"):
        parts.append("已推送")
    elif summary.get("push_error"):
        parts.append("推送失败")
    if summary.get("pr_url"):
        parts.append(f"PR {summary['pr_url']}")
    return "交付：" + "，".join(parts) if parts else ""


async def _run_task(user_id: int, task_id: str, project: str, instruction: str, source: str,
                    seed_messages: list[dict] | None = None):
    started = time.time()
    developer = await _load_developer(user_id)
    perms = developer.get("permissions", []) if developer else []
    allow_commit = isinstance(perms, list) and "commit" in perms
    allow_push = isinstance(perms, list) and "push" in perms and settings.coding_auto_push
    auto_deliver = bool(settings.coding_auto_deliver)
    # Delivery owns git when enabled; the model must not race it.
    tool_commit = allow_commit and not auto_deliver
    tool_push = allow_push and not auto_deliver
    identity = {
        "name": (developer or {}).get("github_username"),
        "email": (developer or {}).get("github_email"),
    }
    ssh_key = (developer or {}).get("ssh_key_path")
    project_name = Path(project).name
    recorder = _RECORDERS.get(task_id)
    turns_used = 0
    messages: list[dict] | None = None

    try:
        await _emit(user_id, task_id, "started", {
            "tool": "omniaide",
            "project": project,
            "project_name": project_name,
            "input": instruction[:500],
            "source": source,
            "engine": "server",
            "auto_deliver": auto_deliver,
        })
        await _emit(user_id, task_id, "milestone", {"stage": "context"})

        context = ""
        try:
            context = await build_project_context(project, settings.coding_context_max_chars)
        except Exception as e:
            log.debug("[coding] context build failed: %s", e)

        await _emit(user_id, task_id, "milestone", {
            "stage": "executing",
            "context_chars": len(context),
            "turns": 0,
        })

        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

        system = _system_prompt(project, developer, context, auto_deliver=auto_deliver)
        if seed_messages:
            messages = [dict(m) for m in seed_messages]
            if messages and messages[0].get("role") == "system":
                messages[0] = {"role": "system", "content": system}
            else:
                messages.insert(0, {"role": "system", "content": system})
            messages.append({"role": "user", "content": instruction})
        else:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": instruction},
            ]

        if recorder is not None:
            recorder.set_messages(messages)

        final = ""
        last_text = ""
        max_turns = min(max(settings.coding_max_turns, 1), 80)
        cancelled = False

        for turn in range(max_turns):
            if task_id in _CANCEL:
                cancelled = True
                break

            turns_used = turn + 1
            response = await _llm_call(client, messages)
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
                    allow_push=tool_push, allow_commit=tool_commit,
                    identity=identity, ssh_key=ssh_key,
                )
                if name in ("write_file", "edit_file") and not result.get("error"):
                    await _emit(user_id, task_id, "file", {"path": str(args.get("path") or ""), "action": "modified"})
                text = json.dumps(result, ensure_ascii=False, default=str)
                if len(text) > MAX_TOOL_RESULT_CHARS:
                    text = text[:MAX_TOOL_RESULT_CHARS] + "\n...[truncated]"
                messages.append({"role": "tool", "tool_call_id": call.id, "content": text})

            if recorder is not None:
                recorder.set_messages(messages)
                recorder.set_turns(turns_used)
                await recorder.flush()

        if cancelled or task_id in _CANCEL:
            if recorder is not None:
                recorder.set_messages(messages)
                recorder.set_turns(turns_used)
            await _emit(user_id, task_id, "milestone", {"stage": "cancelled"})
            await _emit(user_id, task_id, "done", {
                "code": 0,
                "duration_ms": int((time.time() - started) * 1000),
                "output": last_text or "已取消",
                "turns": turns_used,
            })
            return

        delivery_summary = None
        if auto_deliver and not allow_commit:
            await _emit(user_id, task_id, "delivery", {
                "stage": "skipped",
                "ok": False,
                "detail": "开发者档案未授予 commit 权限，改动仅保留在工作区",
            })
        if auto_deliver and allow_commit:
            async def on_delivery(stage: str, ok, detail: str = "", extra: dict | None = None):
                await _emit(user_id, task_id, "delivery", {
                    "stage": stage,
                    "ok": ok,
                    "detail": detail,
                    **(extra or {}),
                })

            delivery_summary = await delivery.deliver(
                project,
                instruction,
                developer=developer,
                allow_commit=allow_commit,
                allow_push=allow_push,
                verify_command=settings.coding_verify_command,
                branch_prefix=settings.coding_branch_prefix,
                timeout_ms=settings.coding_command_timeout_ms,
                emit=on_delivery,
            )
            if recorder is not None:
                recorder.set_delivery(delivery_summary)

        duration = int((time.time() - started) * 1000)
        if not final:
            final = last_text or "已达到最大步数，未生成最终总结。"
        line = _delivery_line(delivery_summary)
        if line:
            final = f"{final}\n\n---\n{line}"

        if recorder is not None:
            recorder.set_messages(messages)
            recorder.set_turns(turns_used)

        payload = {
            "code": 0,
            "duration_ms": duration,
            "output": final[:MAX_TOOL_RESULT_CHARS],
            "turns": turns_used,
        }
        if delivery_summary:
            payload["delivery"] = {
                k: v for k, v in delivery_summary.items() if k != "verify"
            }
        await _emit(user_id, task_id, "done", payload)
    except asyncio.CancelledError:
        await _emit(user_id, task_id, "milestone", {"stage": "cancelled"})
        await _emit(user_id, task_id, "done", {
            "code": 0,
            "duration_ms": int((time.time() - started) * 1000),
            "output": "已取消",
            "turns": turns_used,
        })
    except Exception as e:
        log.exception("[coding] task %s failed", task_id)
        await _emit(user_id, task_id, "failed", {
            "error": str(e),
            "duration_ms": int((time.time() - started) * 1000),
            "code": -1,
            "turns": turns_used,
        })
    finally:
        if recorder is not None:
            recorder.set_turns(turns_used)
            if messages:
                recorder.set_messages(messages)


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
                            instruction: str | None, source: str = "api", *,
                            seed_messages: list[dict] | None = None,
                            parent_id: str | None = None) -> str:
    task_id = task_id or new_task_id()
    project = (project or "").strip()
    instruction = instruction or ""
    project_name = Path(project).name if project else None

    recorder = TaskRecorder(task_id, user_id)
    _RECORDERS[task_id] = recorder

    try:
        await store.create_task(
            user_id, task_id, project, instruction, source,
            project_name=project_name, parent_id=parent_id,
        )
    except Exception as e:
        log.warning("[coding] cannot persist task %s: %s", task_id, e)

    async def fail(reason: str):
        await _emit(user_id, task_id, "failed", {"error": reason, "duration_ms": 0, "code": -1})
        _RECORDERS.pop(task_id, None)
        await recorder.flush(force=True)

    if not project or not instruction.strip():
        await fail("缺少 project/input")
        return task_id

    root = Path(project).expanduser().resolve()
    workspace_root = Path(settings.coding_workspace_root).expanduser().resolve()
    if root != workspace_root and workspace_root not in root.parents:
        await fail(f"项目不在工作区内：{project}")
        return task_id
    if not root.exists() or not root.is_dir():
        await fail(f"项目目录不存在：{project}")
        return task_id
    if task_id in _TASKS:
        return task_id

    _CANCEL.discard(task_id)
    task = asyncio.create_task(
        _run_task(user_id, task_id, str(root), instruction, source, seed_messages)
    )
    _TASKS[task_id] = task

    def _done(_t: asyncio.Task, tid: str = task_id):
        _TASKS.pop(tid, None)
        try:
            asyncio.get_running_loop().create_task(_finalize(tid))
        except RuntimeError:
            pass

    task.add_done_callback(_done)
    return task_id
