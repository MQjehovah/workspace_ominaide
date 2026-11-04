"""Coding capability tools exposed to every Bot.

The coding runtime lives in ``core.coding``; this module only creates child
Runs and lists projects/runs. It deliberately has no dependency on a business
plugin.
"""
from pathlib import Path

from sqlalchemy import select

from core.ai.mcp.core import MCPCallResponse, MCPContent, MCPTool
from core.config.settings import settings


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


def _err(text: str) -> MCPCallResponse:
    return MCPCallResponse(isError=True, content=[MCPContent(text=text)])


def _resolve_project(project: str) -> Path:
    root = Path(settings.coding_workspace_root).expanduser().resolve()
    path = Path(project).expanduser().resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"项目不在工作区内：{project}")
    if not path.exists() or not path.is_dir():
        raise ValueError(f"项目目录不存在：{project}")
    return path


async def delegate_coding(user_id: int, args: dict) -> MCPCallResponse:
    from core.bots.context import get_current_bot_id, get_current_run_id
    from core.bots.registry import get_active_bot, get_or_create_default_bot
    from core.coding.service import create_coding_run

    project = (args.get("project") or "").strip()
    instruction = (args.get("instruction") or "").strip()
    branch = (args.get("branch") or "").strip() or None
    if not project or not instruction:
        return _err("project 和 instruction 必填")
    try:
        _resolve_project(project)
    except ValueError as e:
        return _err(str(e))

    bot_id = get_current_bot_id()
    bot = (
        await get_active_bot(user_id, bot_id)
        if bot_id is not None
        else await get_or_create_default_bot(user_id)
    )
    run = await create_coding_run(
        user_id,
        bot,
        project,
        instruction,
        branch=branch,
        parent_run_id=get_current_run_id(),
    )
    return _ok(
        "\n".join(
            [
                f"已创建 Coding Run #{run.id}。",
                f"项目：{project}",
                f"分支：{branch or '自动创建 feature/*'}",
                f"状态：{run.status}",
                f"进度：/api/runs/{run.id}/stream",
            ]
        )
    )


async def list_coding_projects(user_id: int, args: dict) -> MCPCallResponse:
    from core.coding.workspace import list_projects

    projects = list_projects(settings.coding_workspace_root)
    if not projects:
        return _ok("工作区内没有可用的项目。")
    lines = ["可用项目："]
    for p in projects:
        lines.append(f"- {p['name']}  {p['path']}  ({p.get('type', 'project')})")
    return _ok("\n".join(lines))


async def list_coding_runs(user_id: int, args: dict) -> MCPCallResponse:
    from core.bots.models import BotRun
    from core.coding.models import CodingRun
    from core.database.session import async_session

    limit = min(int(args.get("limit") or 10), 50)
    async with async_session() as db:
        rows = list(
            (
                await db.execute(
                    select(BotRun)
                    .join(CodingRun, CodingRun.run_id == BotRun.id)
                    .where(BotRun.user_id == user_id)
                    .order_by(BotRun.id.desc())
                    .limit(limit)
                )
            ).scalars().all()
        )
    if not rows:
        return _ok("还没有 Coding Run。")
    lines = ["最近的 Coding Run："]
    for r in rows:
        lines.append(
            f"- #{r.id} [{r.status}] {r.project or '-'} · {r.branch or '-'} · {(r.input or '')[:60]}"
        )
    return _ok("\n".join(lines))


TOOLS = [
    (
        MCPTool(
            name="delegate_coding",
            description=(
                "把代码修改任务交给 Coding Agent。它会读取/修改项目文件、运行构建测试，"
                "并在完成后按策略提交到 feature/* 分支；用户明确要求时才传 branch=master。"
                "先用 list_coding_projects 找项目路径。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {
                        "type": "string",
                        "description": "项目绝对路径，例如 /workspace/workspace_ominaide",
                    },
                    "instruction": {
                        "type": "string",
                        "description": "详细开发任务，用自然语言描述",
                    },
                    "branch": {
                        "type": "string",
                        "description": "可选。用户明确要求直接在 master 改动时传 master；否则留空，自动创建 feature/*。",
                    },
                },
                "required": ["project", "instruction"],
            },
        ),
        delegate_coding,
    ),
    (
        MCPTool(
            name="list_coding_projects",
            description="列出工作区内可用的代码项目（项目名 + 路径）。",
            inputSchema={"type": "object", "properties": {}},
        ),
        list_coding_projects,
    ),
    (
        MCPTool(
            name="list_coding_runs",
            description="列出最近的 Coding Run（状态、项目、分支、任务摘要）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "返回条数，默认 10"},
                },
            },
        ),
        list_coding_runs,
    ),
]
