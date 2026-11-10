"""Built-in coding agent loop.

Independent Coding Agent execution: it reasons over the project, edits the
workspace through sandboxed tools, can search/run shared Agent Skills, and
returns a final answer. Git verification, commit and push are intentionally not
part of this loop.
"""
import json
from ai.llm.usage import tracked_create
import logging
from pathlib import Path

from openai import AsyncOpenAI

from ai.coding import workspace
from ai.coding.context import build_project_context
from ai.coding.prompts import TOOLS, coding_system_prompt
from ai.context_window import compact_context
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


def _resolve_project(user_id: int, project: str) -> Path:
    root = projects_root(user_id)
    path = Path(project).expanduser().resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"项目不在工作区内：{project}")
    if not path.exists() or not path.is_dir():
        raise ValueError(f"项目目录不存在：{project}")
    return path


def _mcp_text(result) -> str:
    parts = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    if parts:
        return "\n".join(parts)
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        return str(result)


async def _execute_tool(run, project, name, args, identity, ssh_key):
    """Run a coding tool. Skills are shared with the chat agent."""
    if name == "skill_search":
        from ai.mcp.tools.skills import skill_search

        result = await skill_search(run.user_id, args)
        return _mcp_text(result), bool(getattr(result, "isError", False))
    if name == "skill_call":
        from ai.mcp.tools.skills import skill_call

        result = await skill_call(run.user_id, args)
        return _mcp_text(result), bool(getattr(result, "isError", False))
    result = await workspace.execute_tool(
        str(project),
        name,
        args,
        allow_push=False,
        allow_commit=False,
        identity=identity,
        ssh_key=ssh_key,
    )
    text = json.dumps(result, ensure_ascii=False, default=str)[:MAX_TOOL_RESULT_CHARS]
    return text, bool(result.get("error"))


async def run_coding(run, bot, coding_run, *, on_event, is_cancelled) -> dict:
    """Execute one coding run and return ``{status, output, error}``."""
    try:
        project = _resolve_project(run.user_id, coding_run.project_path or "")
    except Exception as e:
        return {"status": "failed", "output": None, "error": str(e)}

    developer = await _load_developer(run.user_id)
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
        from ai.context_builder import ContextBuilder

        builder = ContextBuilder()
        builder.section(
            "coding_agent",
            coding_system_prompt(
                str(project), developer, context, branch=coding_run.branch
            ),
            priority=100,
            required=True,
        )
        try:
            from ai.skills.runtime import build_skill_context

            skill_ctx = await build_skill_context(bot)
            if skill_ctx:
                builder.section("skills", skill_ctx, priority=50, max_chars=4000)
        except Exception as e:
            log.debug("[coding] skill context failed: %s", e)
        session_id = getattr(coding_run, "session_id", None)
        if session_id:
            try:
                from core.sessions.service import list_messages

                history = await list_messages(run.user_id, session_id, limit=20)
                builder.history([
                    {"role": item["role"], "content": item["content"]}
                    for item in history
                    if item.get("run_id") != run.id and item.get("kind") == "text"
                ])
            except Exception as e:
                log.debug("[coding] session history failed: %s", e)
        builder.user(run.input or "")
        messages = await builder.build()

    client = AsyncOpenAI(
        api_key=settings.coding_api_key or settings.llm_api_key,
        base_url=settings.coding_base_url or settings.llm_base_url,
    )
    model = settings.coding_model or (
        (bot.model if bot is not None else "") or settings.llm_model
    )
    temperature = settings.coding_temperature
    # Coding runs get their own budget. Chat bots default to 60 turns, which
    # is too small for repository-wide investigation and implementation.
    max_turns = min(
        max(
            int(settings.coding_max_turns or 60),
            int((bot.max_turns if bot is not None else 0) or 0),
        ),
        150,
    )

    final = ""
    last_text = ""
    budget_exhausted = False
    budget_warned = False
    for _turn in range(max_turns):
        if await is_cancelled():
            await on_event("checkpoint", {"messages": messages})
            return {"status": "cancelled", "output": last_text or None, "error": None}

        compacted = await compact_context(messages, client=client, model=model)
        if compacted is not messages:
            messages = compacted
            await on_event("checkpoint", {"messages": messages})

        remaining = max_turns - _turn
        if remaining <= 2 and not budget_warned:
            budget_warned = True
            messages.append({
                "role": "system",
                "content": (
                    "本次运行即将达到轮次上限。不要再调用任何工具，"
                    "立即用中文输出阶段性总结：已经完成了什么、发现了什么、"
                    "还有哪些未完成，以及建议的下一步。"
                ),
            })
        force_final = remaining <= 2

        try:
            resp = await tracked_create(client, 
                model=model,
                messages=messages,
                tools=None if force_final else TOOLS,
                temperature=temperature,
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
            budget_exhausted = force_final
            break

        if force_final:
            final = msg.content or last_text
            budget_exhausted = True
            break

        messages.append(_assistant_message(msg))
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            text, is_error = await _execute_tool(
                run, project, tc.function.name, args, identity, ssh_key
            )
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": text}
            )
            await on_event(
                "step",
                {
                    "name": tc.function.name,
                    "arguments": args,
                    "result": text,
                    "status": "error" if is_error else "ok",
                },
            )
        await on_event("checkpoint", {"messages": messages})

    if not final:
        final = last_text or ""
        budget_exhausted = True

    if not final:
        await on_event("checkpoint", {"messages": messages})
        return {
            "status": "failed",
            "output": None,
            "error": f"reached max turns ({max_turns})",
        }

    if budget_exhausted:
        await on_event("checkpoint", {"messages": messages})
        note = (
            f"（已达到单次运行轮次上限 {max_turns}，以下为阶段性结果。"
            "本次未自动提交或推送，建议确认后继续。）"
        )
        return {"status": "done", "output": f"{note}\n\n{final}", "error": None}

    await on_event("checkpoint", {"messages": messages})
    return {"status": "done", "output": final, "error": None}
