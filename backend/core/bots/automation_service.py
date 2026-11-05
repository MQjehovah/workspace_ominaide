"""Automation center services: templates, natural-language rules, dry runs and logs."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from sqlalchemy import func, select

from core.bots import routines as routine_service
from core.bots.models import Bot, BotApproval, BotRoutine, BotRun
from core.bots.routine_templates import get_template, list_templates
from core.config.settings import settings
from core.database.session import async_session

_EVENT_HINTS = [
    (("上传", "文件"), "file.uploaded"),
    (("邮件",), "mail.received"),
    (("文章", "RSS", "订阅", "资讯"), "article.new"),
    (("完成", "待办"), "todo.completed"),
    (("创建", "日程"), "schedule.created"),
]

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 3 - 1, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _to_int(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    if value in _CN_DIGITS:
        return _CN_DIGITS[value]
    return None


def _extract_time(text: str) -> tuple[int, int] | None:
    """Return (hour, minute) from phrases like 8:30 / 早上八点 / 下午 3 点."""
    m = re.search(r"(\d{1,2}|[零一二两三四五六七八九十]{1,3})\s*[:：点时]\s*(\d{1,2}|[零一二两三四五六七八九十]{1,3})?", text)
    if not m:
        return None
    hour = _to_int(m.group(1))
    minute = _to_int(m.group(2)) if m.group(2) else 0
    if hour is None or minute is None:
        return None
    if any(x in text for x in ("下午", "晚上", "傍晚")) and hour < 12:
        hour += 12
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _weekday(text: str) -> str | None:
    m = re.search(r"周([一二三四五六日天])", text)
    if m:
        return {"一": "1", "二": "2", "三": "3", "四": "4",
                "五": "5", "六": "6", "日": "0", "天": "0"}[m.group(1)]
    return None


def parse_rule_locally(text: str) -> dict:
    """Deterministic parser used when the LLM is unavailable or returns junk."""
    text = (text or "").strip()
    lowered = text.lower()

    for words, event_type in _EVENT_HINTS:
        if all(w in text or w.lower() in lowered for w in words):
            name = text[:30] or event_type
            return {
                "name": name,
                "trigger_type": "event",
                "cron_expr": None,
                "event_type": event_type,
                "event_filter": None,
                "prompt": text,
                "explanation": f"检测到事件触发：{event_type}",
            }

    hm = _extract_time(text) or (9, 0)
    hour, minute = hm
    dow = _weekday(text)

    if "每小时" in text:
        return {
            "name": text[:30] or "每小时任务",
            "trigger_type": "cron",
            "cron_expr": "0 * * * *",
            "event_type": None,
            "event_filter": None,
            "prompt": text,
            "explanation": "每小时执行一次",
        }

    if "工作日" in text or "每个工作日" in text:
        cron = f"{minute} {hour} * * 1-5"
        explanation = f"工作日 {hour:02d}:{minute:02d} 执行"
    elif dow is not None:
        cron = f"{minute} {hour} * * {dow}"
        explanation = f"每周 {dow} 的 {hour:02d}:{minute:02d} 执行"
    elif "每天" in text or "每日" in text:
        cron = f"{minute} {hour} * * *"
        explanation = f"每天 {hour:02d}:{minute:02d} 执行"
    elif "每周" in text:
        cron = f"{minute} {hour} * * 1"
        explanation = f"每周一 {hour:02d}:{minute:02d} 执行"
    else:
        cron = f"{minute} {hour} * * *"
        explanation = f"按每天 {hour:02d}:{minute:02d} 执行"

    routine_service.parse_cron(cron)  # validate
    return {
        "name": text[:30] or "自动任务",
        "trigger_type": "cron",
        "cron_expr": cron,
        "event_type": None,
        "event_filter": None,
        "prompt": text,
        "explanation": explanation,
    }


async def parse_rule(text: str) -> dict:
    """Turn a natural-language sentence into a routine draft (no DB write)."""
    text = (text or "").strip()
    if not text:
        raise ValueError("请描述这条自动化要做什么")
    if not settings.llm_api_key:
        return parse_rule_locally(text)

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": (
                    "你是自动化规则解析器。把用户的一句话转换成一条 Bot 例程。"
                    f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}。"
                    "可用事件类型：file.uploaded, mail.received, article.new, todo.completed, "
                    "schedule.created, note.created, file.trashed。"
                    "cron 使用标准 5 段式（分 时 日 月 周）。只返回 JSON: "
                    '{"name":"简短名称","trigger_type":"cron|event|manual",'
                    '"cron_expr":"分 时 日 月 周 或 null","event_type":"事件类型或 null",'
                    '"event_filter":{},"prompt":"触发时交给 Bot 的完整任务描述",'
                    '"explanation":"一句中文说明何时触发"}。不要输出其他内容。'
                )},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
        )
        raw = resp.choices[0].message.content or ""
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return parse_rule_locally(text)
        data = json.loads(m.group(0))
        trigger_type = str(data.get("trigger_type") or "cron").lower()
        if trigger_type not in ("cron", "event", "manual"):
            return parse_rule_locally(text)
        cron_expr = data.get("cron_expr") or None
        event_type = data.get("event_type") or None
        if trigger_type == "cron":
            if not cron_expr:
                return parse_rule_locally(text)
            routine_service.parse_cron(cron_expr)
        if trigger_type == "event" and not event_type:
            return parse_rule_locally(text)
        return {
            "name": str(data.get("name") or text[:30])[:120],
            "trigger_type": trigger_type,
            "cron_expr": cron_expr if trigger_type == "cron" else None,
            "event_type": event_type if trigger_type == "event" else None,
            "event_filter": data.get("event_filter") or None,
            "prompt": str(data.get("prompt") or text),
            "explanation": str(data.get("explanation") or ""),
        }
    except Exception as e:
        print(f"[automation] parse llm error: {e}")
        return parse_rule_locally(text)


async def create_from_template(user_id: int, bot_id: int, template_key: str, overrides: dict | None = None) -> BotRoutine:
    template = get_template(template_key)
    if template is None:
        raise ValueError("模板不存在")
    data = {**template, **(overrides or {})}
    return await routine_service.create_routine(
        user_id,
        bot_id,
        data.get("name") or template["name"],
        trigger_type=data.get("trigger_type") or "cron",
        cron_expr=data.get("cron_expr"),
        event_type=data.get("event_type"),
        event_filter=data.get("event_filter"),
        prompt=data.get("prompt"),
        enabled=bool(data.get("enabled", True)),
    )


def _next_runs(cron_expr: str, count: int = 3) -> list[str]:
    out: list[str] = []
    cursor = datetime.now()
    for _ in range(count):
        cursor = routine_service.next_run(cron_expr, cursor)
        out.append(cursor.strftime("%Y-%m-%d %H:%M"))
    return out


async def dry_run(user_id: int, routine_id: int) -> dict:
    """Preview what a routine will do without creating a run or calling tools."""
    routine = await routine_service.get_routine(user_id, routine_id)
    if routine is None:
        raise ValueError("例程不存在")

    if routine.trigger_type == "cron":
        schedule = {"type": "cron", "expr": routine.cron_expr, "next_runs": _next_runs(routine.cron_expr)}
        trigger_text = f"按 cron「{routine.cron_expr}」触发"
    elif routine.trigger_type == "event":
        schedule = {"type": "event", "event_type": routine.event_type, "filter": routine.event_filter}
        trigger_text = f"当事件 {routine.event_type} 满足 {routine.event_filter or '任意'} 时触发"
    else:
        schedule = {"type": "manual"}
        trigger_text = "仅手动触发"

    prompt = routine.prompt or routine.name
    plan = ""
    if settings.llm_api_key:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
            resp = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": (
                        "这是一次【试运行】。你只能输出执行计划，绝对不能调用工具、读取文件、"
                        "发送消息或修改任何数据。用 3-6 条中文短句描述触发后将按什么步骤执行，"
                        "并指出可能需要的工具和风险。不要执行。"
                    )},
                    {"role": "user", "content": f"触发条件：{trigger_text}\n任务：{prompt}"},
                ],
                temperature=0.2,
            )
            plan = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            print(f"[automation] dry-run llm error: {e}")

    if not plan:
        plan = (
            f"试运行（不执行）：{trigger_text}。\n"
            f"Bot 将执行：{prompt}\n"
            "如需真实执行，请点「立即运行」或等待触发时间。"
        )

    return {
        "routine_id": routine.id,
        "name": routine.name,
        "enabled": bool(routine.enabled),
        "schedule": schedule,
        "trigger": trigger_text,
        "prompt": prompt,
        "plan": plan,
        "dry_run": True,
    }


async def list_routine_runs(user_id: int, routine_id: int, limit: int = 20) -> list[BotRun]:
    async with async_session() as db:
        rows = await db.execute(
            select(BotRun).where(
                BotRun.user_id == user_id,
                BotRun.routine_id == routine_id,
            ).order_by(BotRun.id.desc()).limit(max(1, min(limit, 200)))
        )
        return list(rows.scalars().all())


async def routine_stats(user_id: int, routine_id: int, days: int = 30) -> dict:
    since = datetime.utcnow() - timedelta(days=max(1, days))
    async with async_session() as db:
        total = (await db.execute(
            select(func.count(BotRun.id)).where(
                BotRun.user_id == user_id,
                BotRun.routine_id == routine_id,
                BotRun.created_at >= since,
            )
        )).scalar() or 0
        rows = (await db.execute(
            select(BotRun.status, func.count(BotRun.id)).where(
                BotRun.user_id == user_id,
                BotRun.routine_id == routine_id,
                BotRun.created_at >= since,
            ).group_by(BotRun.status)
        )).all()
    return {"days": days, "total": total, "by_status": {s: c for s, c in rows}}


async def overview(user_id: int) -> dict:
    since = datetime.utcnow() - timedelta(days=7)
    async with async_session() as db:
        routines_total = (await db.execute(
            select(func.count(BotRoutine.id)).where(BotRoutine.user_id == user_id)
        )).scalar() or 0
        routines_enabled = (await db.execute(
            select(func.count(BotRoutine.id)).where(
                BotRoutine.user_id == user_id, BotRoutine.enabled == True
            )
        )).scalar() or 0
        run_rows = (await db.execute(
            select(BotRun.status, func.count(BotRun.id)).where(
                BotRun.user_id == user_id, BotRun.created_at >= since
            ).group_by(BotRun.status)
        )).all()
        pending_approvals = (await db.execute(
            select(func.count(BotApproval.id)).where(
                BotApproval.user_id == user_id, BotApproval.status == "pending"
            )
        )).scalar() or 0
        recent = list((await db.execute(
            select(BotRun).where(
                BotRun.user_id == user_id,
                BotRun.routine_id != None,
                BotRun.created_at >= since,
            ).order_by(BotRun.id.desc()).limit(10)
        )).scalars().all())
    return {
        "routines_total": routines_total,
        "routines_enabled": routines_enabled,
        "runs_7d": sum(c for _, c in run_rows),
        "runs_by_status": {s: c for s, c in run_rows},
        "pending_approvals": pending_approvals,
        "recent_runs": [
            {
                "id": r.id,
                "routine_id": r.routine_id,
                "status": r.status,
                "trigger": r.trigger,
                "created_at": r.created_at,
            }
            for r in recent
        ],
    }
