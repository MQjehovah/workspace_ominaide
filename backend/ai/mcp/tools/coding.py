"""Coding capability tools exposed to every Bot.

The coding runtime lives in ``ai.coding``; this module only creates child
Runs and lists projects/runs. It deliberately has no dependency on a business
plugin.
"""
from pathlib import Path

from sqlalchemy import select

from ai.mcp.core import MCPCallResponse, MCPContent, MCPTool
from core.config.settings import settings
from core.paths import projects_root


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


def _err(text: str) -> MCPCallResponse:
    return MCPCallResponse(isError=True, content=[MCPContent(text=text)])


def _resolve_project(user_id: int, project: str) -> Path:
    root = projects_root(user_id)
    path = Path(project).expanduser().resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"项目不在工作区内：{project}")
    if not path.exists() or not path.is_dir():
        raise ValueError(f"项目目录不存在：{project}")
    return path


async def delegate_coding(user_id: int, args: dict) -> MCPCallResponse:
    from ai.bots.context import get_current_bot_id, get_current_run_id
    from ai.bots.registry import get_active_bot, get_or_create_default_bot
    from ai.coding.service import create_coding_run

    project = (args.get("project") or "").strip()
    instruction = (args.get("instruction") or "").strip()
    branch = (args.get("branch") or "").strip() or None
    if not project or not instruction:
        return _err("project 和 instruction 必填")
    try:
        _resolve_project(user_id, project)
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
                f"完成后可用 get_coding_run(run_id={run.id}) 读取完整产出。",
            ]
        )
    )


async def list_coding_projects(user_id: int, args: dict) -> MCPCallResponse:
    from ai.coding.workspace import list_projects

    projects = list_projects(str(projects_root(user_id)))
    if not projects:
        return _ok("工作区内没有可用的项目。")
    lines = ["可用项目："]
    for p in projects:
        lines.append(f"- {p['name']}  {p['path']}  ({p.get('type', 'project')})")
    return _ok("\n".join(lines))


async def list_coding_runs(user_id: int, args: dict) -> MCPCallResponse:
    from ai.bots.models import Run
    from core.database.session import async_session

    limit = min(int(args.get("limit") or 10), 50)
    async with async_session() as db:
        rows = list(
            (
                await db.execute(
                    select(Run)
                    .where(Run.user_id == user_id, Run.trigger == "coding")
                    .order_by(Run.id.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
    if not rows:
        return _ok("还没有 Coding Run。")
    lines = ["最近的 Coding Run："]
    for run in rows:
        meta = run.meta or {}
        preview = (run.output or run.error or "").replace("\n", " ")[:80]
        lines.append(
            f"- #{run.id} [{run.status}] {meta.get('project_path') or '-'} · "
            f"{meta.get('branch') or '-'} · {(run.input or '')[:60]}"
            + (f" · 产出：{preview}" if preview else "")
        )
    lines.append("需要完整产出时调用 get_coding_run(run_id)。")
    return _ok("\n".join(lines))


async def get_coding_run(user_id: int, args: dict) -> MCPCallResponse:
    """Read one Coding Run's full output, error and steps."""
    from ai.bots.models import Run, RunStep
    from core.database.session import async_session

    try:
        run_id = int(args.get("run_id") or 0)
    except (TypeError, ValueError):
        run_id = 0
    if not run_id:
        return _err("run_id 必填")

    async with async_session() as db:
        run = (
            await db.execute(
                select(Run).where(
                    Run.id == run_id,
                    Run.user_id == user_id,
                    Run.trigger == "coding",
                )
            )
        ).scalar_one_or_none()
        if run is None:
            return _err(f"Coding Run #{run_id} 不存在")
        steps = list(
            (
                await db.execute(
                    select(RunStep)
                    .where(RunStep.run_id == run_id)
                    .order_by(RunStep.seq.asc())
                )
            ).scalars().all()
        )

    meta = run.meta or {}
    lines = [
        f"# Coding Run #{run.id}",
        f"状态：{run.status}",
        f"会话：{run.session_id or '-'}",
        f"项目：{meta.get('project_path') or '-'}",
        f"分支：{meta.get('branch') or '-'}",
        f"引擎：{run.agent or meta.get('engine') or '-'}",
        f"任务：{run.input or '-'}",
    ]
    if run.output:
        lines.append(f"\n## 产出\n{run.output[:12000]}")
    if run.error:
        lines.append(f"\n## 错误\n{run.error[:4000]}")
    if steps:
        lines.append("\n## 步骤")
        for step in steps[-40:]:
            detail = (step.result or "").replace("\n", " ")[:180]
            lines.append(
                f"- [{step.seq}] {step.type} {step.tool_name or ''} "
                f"{step.status or ''} {detail}".rstrip()
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
                        "description": "项目绝对路径，位于当前用户的 projects 目录下",
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
            description="列出最近的 Coding Run（状态、项目、分支、任务摘要和产出预览）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "返回条数，默认 10"},
                },
            },
        ),
        list_coding_runs,
    ),
    (
        MCPTool(
            name="get_coding_run",
            description=(
                "读取某个 Coding Run 的完整产出、错误和步骤。"
                "用户问“Run #5 结果是什么/改了什么/为什么失败”时使用；先用 list_coding_runs 找 run_id。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "run_id": {"type": "integer", "description": "Coding Run 编号，例如 5"},
                },
                "required": ["run_id"],
            },
        ),
        get_coding_run,
    ),
]
