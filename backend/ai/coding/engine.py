"""Built-in coding agent engine.

This is the replaceable Agent implementation used by coding Runs. It edits the
workspace through the sandboxed workspace tools, then hands git delivery to
``ai.coding.delivery`` so branch/verify/commit policy stays in one place.
"""
import json
import logging
from pathlib import Path

from openai import AsyncOpenAI

from ai.coding import delivery, workspace
from ai.coding.context import build_project_context
from ai.coding.prompts import TOOLS, coding_system_prompt
from core.config.settings import settings
from core.paths import projects_root

log = logging.getLogger("uvicorn")
MAX_TOOL_RESULT_CHARS = 20_000


async def _load_developer(user_id: int) -> dict | None:
    try:
        from sqlalchemy import select

        from core.auth.domain.models import UserProfile
        from core.database.session import async_session

        async with async_session() as db:
            profile = (
                await db.execute(
                    select(UserProfile).where(UserProfile.user_id == user_id)
                )
            ).scalar_one_or_none()
            if profile and profile.developer:
                return json.loads(profile.developer)
    except Exception:
        pass
    return None


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
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return message


def _delivery_line(summary: dict | None) -> str:
    if not summary:
        return ""
    if summary.get("skipped"):
        return f"交付：跳过（{summary.get('detail') or summary.get('reason') or '无改动'}）"
    parts = []
    if summary.get("branch"):
        parts.append(f"分支 {summary['branch']}")
    if summary.get("commit"):
        parts.append(f"提交 {summary['commit']}")
    if summary.get("pushed"):
        parts.append("已推送")
    elif summary.get("push_error"):
        parts.append("推送失败")
    elif summary.get("push_skipped"):
        parts.append("未推送")
    if summary.get("pr_url"):
        parts.append(f"PR {summary['pr_url']}")
    return "交付：" + "，".join(parts) if parts else ""


def _resolve_project(user_id: int, project: str) -> Path:
    root = projects_root(user_id)
    path = Path(project).expanduser().resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"项目不在工作区内：{project}")
    if not path.exists() or not path.is_dir():
        raise ValueError(f"项目目录不存在：{project}")
    return path


async def run_coding(run, bot, coding_run, *, on_event, is_cancelled) -> dict:
    """Execute one coding run and return ``{status, output, error}``."""
    try:
        project = _resolve_project(run.user_id, coding_run.project_path or "")
    except Exception as e:
        return {"status": "failed", "output": None, "error": str(e)}

    developer = await _load_developer(run.user_id)
    perms = developer.get("permissions", []) if developer else []
    allow_commit = isinstance(perms, list) and "commit" in perms
    allow_push = isinstance(perms, list) and "push" in perms and settings.coding_auto_push
    identity = {
        "name": (developer or {}).get("github_username"),
        "email": (developer or {}).get("github_email"),
    }
    ssh_key = (developer or {}).get("ssh_key_path")

    checkpoint = run.checkpoint or {}
    messages = checkpoint.get("messages")
    if not messages:
        context = ""
        try:
            context = await build_project_context(
                str(project), settings.coding_context_max_chars
            )
        except Exception as e:
            log.debug("[coding] context build failed: %s", e)
        messages = [
            {
                "role": "system",
                "content": coding_system_prompt(
                    str(project), developer, context, branch=coding_run.branch
                ),
            },
            {"role": "user", "content": run.input or ""},
        ]

    client = AsyncOpenAI(
        api_key=settings.llm_api_key, base_url=settings.llm_base_url
    )
    model = (bot.model or settings.llm_model) if bot is not None else settings.llm_model
    max_turns = min(
        int((bot.max_turns if bot is not None else 0) or settings.coding_max_turns),
        100,
    )

    final = ""
    last_text = ""
    for _turn in range(max_turns):
        if await is_cancelled():
            await on_event("checkpoint", {"messages": messages})
            return {"status": "cancelled", "output": last_text or None, "error": None}

        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                temperature=0.2,
            )
        except Exception as e:
            await on_event("checkpoint", {"messages": messages})
            return {"status": "failed", "output": last_text or None, "error": f"LLM error: {e}"}

        msg = resp.choices[0].message
        if msg.content:
            last_text = msg.content
            await on_event("partial", {"content": msg.content})

        if not msg.tool_calls:
            final = msg.content or last_text
            break

        messages.append(_assistant_message(msg))
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = await workspace.execute_tool(
                str(project),
                tc.function.name,
                args,
                allow_push=False,
                allow_commit=False,
                identity=identity,
                ssh_key=ssh_key,
            )
            text = json.dumps(result, ensure_ascii=False, default=str)[:MAX_TOOL_RESULT_CHARS]
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": text}
            )
            await on_event(
                "step",
                {
                    "name": tc.function.name,
                    "arguments": args,
                    "result": text,
                    "status": "error" if result.get("error") else "ok",
                },
            )
        await on_event("checkpoint", {"messages": messages})

    if not final:
        await on_event("checkpoint", {"messages": messages})
        return {
            "status": "failed",
            "output": last_text or None,
            "error": f"reached max turns ({max_turns})",
        }

    summary = None
    if allow_commit:
        async def on_delivery(stage: str, ok, detail: str = "", extra: dict | None = None):
            await on_event("delivery", {"stage": stage, "ok": ok, "detail": detail})

        summary = await delivery.deliver(
            str(project),
            run.input or "",
            developer=developer,
            allow_commit=allow_commit,
            allow_push=allow_push,
            verify_command=(developer or {}).get("verify_command")
            or settings.coding_verify_command,
            branch_prefix=settings.coding_branch_prefix,
            branch=coding_run.branch,
            allow_protected_push=bool(coding_run.branch),
            timeout_ms=settings.coding_command_timeout_ms,
            emit=on_delivery,
        )

    line = _delivery_line(summary)
    output = f"{final}\n\n---\n{line}" if line else final
    await on_event("checkpoint", {"messages": messages})
    return {"status": "done", "output": output, "error": None}
