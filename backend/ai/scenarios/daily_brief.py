"""Daily brief scenario: deterministic fallback plus optional LLM narrative."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from ai.context import build_context
from ai.llm import llm_json
from ai.scenarios._time import parse_dt


async def daily_brief(
    user_id: int,
    day: date | None = None,
    *,
    bot=None,
    extra_system: str | None = None,
) -> dict:
    """Generate today's short brief plus workbench quick prompts."""
    day = day or date.today()
    now = datetime.now()
    is_today = day == date.today()
    context = await build_context(
        user_id,
        now=now,
        day=datetime.combine(day, datetime.min.time()),
        horizon_hours=24,
    )

    events = context["events"]
    todos = context["todos"]
    due_today = [
        t for t in todos
        if t["meta"].get("due")
        and parse_dt(t["meta"]["due"])
        and (is_today and parse_dt(t["meta"]["due"]) < now.replace(hour=23, minute=59, second=59)
             or not is_today and parse_dt(t["meta"]["due"]) >= datetime.combine(day, datetime.min.time())
             and parse_dt(t["meta"]["due"]) < datetime.combine(day, datetime.min.time()) + timedelta(days=1))
    ]
    overdue = [
        t for t in todos
        if t["meta"].get("due") and parse_dt(t["meta"]["due"]) and parse_dt(t["meta"]["due"]) < now
    ]

    mail = context["unread_mail"]
    news = context["news"]
    dingtalk = context["dingtalk"]
    memory_lines = context["memory"]

    summary = _fallback_brief_summary(day, events, due_today, overdue, mail, news, dingtalk)
    prompts = _fallback_prompts(
        events, overdue, due_today, mail, dingtalk, news,
        context["recent_notes"], context["recent_files"], context["recent_projects"],
    )

    enriched = await llm_json(
        "根据当天数据写 2-4 句中文简报，先讲最重要的冲突或截止，再讲日程与需要回复的人，不编造数据。"
        "同时给出 3 个工作台快捷建议。"
        '只返回 JSON: {"summary": "...", "prompts": ["...", "...", "..."]}。'
        "prompts 每条 6-14 个中文字符，动词开头、可直接执行，不要编号或解释。",
        json.dumps({
            "day": day.isoformat(),
            "events": events,
            "todos": due_today,
            "overdue": overdue,
            "mail": mail,
            "news": news,
            "dingtalk": dingtalk,
            "memory": memory_lines,
            "recent_notes": context["recent_notes"],
            "recent_files": context["recent_files"],
            "recent_projects": context["recent_projects"],
        }, ensure_ascii=False, default=str),
        bot=bot,
        extra_system=extra_system,
    )
    if enriched:
        if isinstance(enriched.get("summary"), str) and enriched["summary"].strip():
            summary = enriched["summary"].strip()
        candidates = enriched.get("prompts")
        if isinstance(candidates, list):
            clean = []
            for value in candidates:
                text = " ".join(str(value or "").split())[:24]
                if text and text not in clean:
                    clean.append(text)
            if clean:
                prompts = clean[:3]

    return {
        "day": day.isoformat(),
        "generated_at": datetime.now().isoformat(),
        "summary": summary,
        "prompts": prompts[:3],
    }


def _fallback_brief_summary(
    day: date, events: list[dict], due_today: list[dict], overdue: list[dict],
    mail: list[dict], news: list[dict], dingtalk: list[dict],
) -> str:
    bits: list[str] = []
    if overdue:
        bits.append(f"有 {len(overdue)} 项已经逾期，先处理「{overdue[0]['title']}」")
    if events:
        bits.append(f"今天 {len(events)} 个日程，第一个是 {events[0]['time'][11:16] if events[0].get('time') else ''}「{events[0]['title']}」")
    if due_today:
        bits.append(f"{len(due_today)} 项待办今天到期")
    if mail:
        bits.append(f"{len(mail)} 封未读邮件")
    if dingtalk:
        bits.append(f"{len(dingtalk)} 个钉钉会话未读")
    if news:
        bits.append(f"{len(news)} 条新资讯")
    if not bits:
        return f"{day.isoformat()} 没有需要特别处理的事项，适合推进长期任务。"
    return "；".join(bits) + "。"


def _fallback_prompts(
    events: list[dict], overdue: list[dict], due_today: list[dict],
    mail: list[dict], dingtalk: list[dict], news: list[dict],
    notes: list[dict], files: list[dict], projects: list[dict],
) -> list[str]:
    prompts: list[str] = []
    if overdue:
        prompts.append(f"处理逾期事项：{overdue[0]['title']}")
    if events:
        prompts.append(f"准备 {events[0]['title']}")
    if mail:
        prompts.append(f"回复 {mail[0].get('from') or '重要邮件'}：{mail[0]['title']}")
    if dingtalk:
        prompts.append(f"查看钉钉未读：{dingtalk[0]['title']}")
    if news:
        prompts.append("看看今天的资讯")
    if notes:
        prompts.append(f"继续编辑「{str(notes[0].get('title') or '')[:10]}」")
    if files:
        prompts.append("整理最近文件")
    if projects:
        prompts.append(f"推进项目「{str(projects[0].get('name') or '')[:8]}」")
    if not prompts and due_today:
        prompts.append(f"推进今天到期的待办：{due_today[0]['title']}")
    return prompts[:3]
