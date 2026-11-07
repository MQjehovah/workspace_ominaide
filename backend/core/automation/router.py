from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from core.auth.dependencies import get_current_user
from core.automation.dsl import compile_spec, spec_from_routine
from core.automation.executor import execute_automation
from core.automation.models import AutomationRun
from core.bots import routines as routine_service
from core.database.session import async_session

router = APIRouter(prefix="/api/automation", tags=["automation"])
alias_router = APIRouter(prefix="/api/automations", tags=["automation"])


class ValidateRequest(BaseModel):
    spec: dict
    name: str | None = None


class FromTemplateRequest(BaseModel):
    bot_id: int
    template_key: str


class ParseRequest(BaseModel):
    text: str


TEMPLATES = [
    {
        "key": "daily_digest",
        "name": "每天汇总未读",
        "description": "每天 9 点让助手整理邮件和钉钉未读。",
        "trigger_type": "cron",
        "cron_expr": "0 9 * * *",
        "event_type": None,
        "prompt": "整理今天的未读邮件和钉钉消息，给出重点和待办建议。",
        "spec": {
            "name": "每天汇总未读",
            "trigger": {"type": "schedule", "cron": "0 9 * * *"},
            "match": "all",
            "conditions": [],
            "actions": [{"type": "agent", "params": {"prompt": "整理今天的未读邮件和钉钉消息，给出重点和待办建议。"}}],
        },
    },
    {
        "key": "important_mail",
        "name": "重要邮件提醒",
        "description": "收到重要邮件时创建待办并通知。",
        "trigger_type": "event",
        "cron_expr": None,
        "event_type": "mail.received",
        "prompt": None,
        "spec": {
            "name": "重要邮件提醒",
            "trigger": {"type": "event", "event_type": "mail.received"},
            "match": "all",
            "conditions": [{"field": "event.details.important", "op": "eq", "value": True}],
            "actions": [
                {"type": "todo", "params": {"title": "跟进重要邮件"}},
                {"type": "notify", "params": {"title": "重要邮件", "body": "收到一封重要邮件"}},
            ],
        },
    },
    {
        "key": "weekly_review",
        "name": "每周复盘",
        "description": "每周五生成一份工作复盘。",
        "trigger_type": "cron",
        "cron_expr": "0 18 * * 5",
        "event_type": None,
        "prompt": "生成本周工作复盘：完成事项、未完成事项、下周建议。",
        "spec": {
            "name": "每周复盘",
            "trigger": {"type": "schedule", "cron": "0 18 * * 5"},
            "match": "all",
            "conditions": [],
            "actions": [{"type": "agent", "params": {"prompt": "生成本周工作复盘：完成事项、未完成事项、下周建议。"}}],
        },
    },
]


def _template(key: str) -> dict | None:
    return next((t for t in TEMPLATES if t["key"] == key), None)


@router.get("/templates")
async def automation_templates(user: dict = Depends(get_current_user)):
    return {"templates": TEMPLATES}


@alias_router.get("/templates")
async def automation_templates_alias(user: dict = Depends(get_current_user)):
    return {"templates": TEMPLATES}


@router.post("/validate")
async def validate_automation(
    req: ValidateRequest, user: dict = Depends(get_current_user)
):
    data = dict(req.spec or {})
    if req.name:
        data.setdefault("name", req.name)
    return compile_spec(data)


@alias_router.post("/validate")
async def validate_automation_alias(
    req: ValidateRequest, user: dict = Depends(get_current_user)
):
    return await validate_automation(req, user)


@router.post("/from-template")
async def create_from_template(
    req: FromTemplateRequest, user: dict = Depends(get_current_user)
):
    template = _template(req.template_key)
    if template is None:
        raise HTTPException(status_code=404, detail="template not found")
    try:
        routine = await routine_service.create_routine(
            user["id"], req.bot_id, template["name"],
            spec=template["spec"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"message": "created", "routine_id": routine.id}


async def _parse_with_llm(text: str) -> dict | None:
    from core.config.settings import settings

    if not settings.llm_api_key:
        return None
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "把用户的一句话自动化需求解析为 JSON："
                        "{\"name\":\"\",\"trigger_type\":\"cron|event|manual\","
                        "\"cron_expr\":null,\"event_type\":null,\"prompt\":\"\",\"explanation\":\"\"}。"
                        "只返回 JSON。cron 使用 5 段表达式。"
                    ),
                },
                {"role": "user", "content": text[:2000]},
            ],
            temperature=0.1,
        )
        raw = resp.choices[0].message.content or "{}"
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return None
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


@router.post("/parse")
async def parse_natural_language(
    req: ParseRequest, user: dict = Depends(get_current_user)
):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="text is required")
    draft = await _parse_with_llm(text)
    if not draft:
        draft = {
            "name": text[:40],
            "trigger_type": "manual",
            "cron_expr": None,
            "event_type": None,
            "prompt": text,
            "explanation": "未配置 LLM 或解析失败，已保存为手动自动化",
        }
    draft.setdefault("name", text[:40])
    draft.setdefault("trigger_type", "manual")
    draft.setdefault("prompt", text)
    return {"draft": draft}


@router.post("/routines/{routine_id}/dry-run")
async def dry_run(routine_id: int, user: dict = Depends(get_current_user)):
    routine = await routine_service.get_routine(user["id"], routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    result = await execute_automation(routine.id, "manual", manual={}, dry_run=True)
    spec = result.get("spec") or spec_from_routine(routine)
    next_runs: list[str] = []
    if spec.get("trigger", {}).get("type") == "schedule":
        from core.bots.routines import next_run

        when = datetime.now()
        for _ in range(3):
            when = next_run(spec["trigger"]["cron"], when)
            next_runs.append(when.isoformat(sep=" ", timespec="minutes"))
    actions = spec.get("actions") or []
    return {
        "trigger": spec.get("trigger"),
        "schedule": {"next_runs": next_runs},
        "prompt": next((a.get("params", {}).get("prompt") for a in actions if a.get("type") == "agent"), ""),
        "plan": json.dumps(actions, ensure_ascii=False, indent=2),
        "matched": result.get("matched"),
        "conditions": result.get("conditions"),
    }


@router.get("/routines/{routine_id}/runs")
async def routine_runs(
    routine_id: int,
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    routine = await routine_service.get_routine(user["id"], routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    rows = await routine_service.list_routine_runs(user["id"], routine_id, limit)
    return [
        {
            "id": row.id,
            "status": row.status,
            "trigger": row.trigger_type,
            "created_at": row.created_at,
            "output": json.dumps(row.action_results, ensure_ascii=False)[:1000]
            if row.action_results else None,
            "error": row.error,
        }
        for row in rows
    ]


@router.get("/routines/{routine_id}/stats")
async def routine_stats(
    routine_id: int,
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(get_current_user),
):
    routine = await routine_service.get_routine(user["id"], routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    since = datetime.now() - timedelta(days=days)
    async with async_session() as db:
        rows = (await db.execute(
            select(AutomationRun.status, func.count(AutomationRun.id))
            .where(
                AutomationRun.user_id == user["id"],
                AutomationRun.routine_id == routine_id,
                AutomationRun.created_at >= since,
            )
            .group_by(AutomationRun.status)
        )).all()
    by_status = {str(status): int(count) for status, count in rows}
    return {"days": days, "total": sum(by_status.values()), "by_status": by_status}
