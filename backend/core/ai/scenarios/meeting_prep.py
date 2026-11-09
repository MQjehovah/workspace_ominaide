"""Meeting preparation scenario."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from core.ai.context import (
    dingtalk_items,
    mail_items,
    schedule_items,
    source_items,
    todo_items,
)
from core.ai.llm import llm_json
from core.ai.scenarios._time import parse_dt


async def meeting_prep(
    user_id: int,
    *,
    title: str = "",
    start: str | None = None,
    attendees: list[str] | None = None,
    query: str | None = None,
    bot=None,
    extra_system: str | None = None,
) -> dict:
    attendees = [a for a in (attendees or []) if str(a).strip()]
    keyword = (query or title or "").strip()
    start_dt = parse_dt(start)
    window_start = (start_dt or datetime.now()) - timedelta(days=1)
    window_end = (start_dt or datetime.now()) + timedelta(days=1)

    context: list[dict] = []
    events = await schedule_items(
        user_id, start=window_start, end=window_end, limit=10,
    )
    for event in events:
        context.append({
            "source": "schedule",
            "title": event["title"],
            "snippet": event.get("summary") or "",
            "time": event.get("time"),
            "link": "/schedule",
        })

    if keyword:
        mail = await mail_items(user_id, limit=8, query=keyword)
        for item in mail:
            context.append({
                "source": "mail",
                "title": item["title"],
                "snippet": item.get("summary") or "",
                "time": item.get("time"),
                "link": "/mail",
            })
        todos = await todo_items(user_id, limit=6, query=keyword)
        for item in todos:
            context.append({
                "source": "todo",
                "title": item["title"],
                "snippet": item.get("summary") or "",
                "time": item.get("time"),
                "link": "/dashboard",
            })
        news = await source_items(user_id, limit=5, query=keyword)
        for item in news:
            context.append({
                "source": "sources",
                "title": item["title"],
                "snippet": item.get("summary") or "",
                "time": item.get("time"),
                "link": "/sources",
            })

        dingtalk, dingtalk_status = await dingtalk_items(user_id, query=keyword, limit=8)
        for item in dingtalk:
            context.append({
                "source": "dingtalk",
                "title": item["title"],
                "snippet": item.get("summary") or "",
                "time": item.get("time"),
                "link": "/mcp",
            })
    else:
        dingtalk_status = "skipped"

    try:
        from core.memory_service import list_records

        records = await list_records(user_id, keyword, 5) if keyword else []
        for record in records:
            context.append({
                "source": "memory",
                "title": f"[{record.kind}] {record.content[:80]}",
                "snippet": record.content,
                "time": None,
                "link": "/memory",
            })
    except Exception:
        pass

    seen: set[tuple[str, str]] = set()
    deduped = []
    for item in context:
        key = (item["source"], item["title"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    agenda = [
        "对齐会议目标与预期产出",
        "回顾上次进展和未决事项",
        "讨论关键议题并形成结论",
        "明确下一步、负责人和截止时间",
    ]
    if attendees:
        agenda.insert(1, f"确认参会人分工：{'、'.join(attendees[:6])}")

    questions = [
        "这次会议必须做出的决定是什么？",
        "还有哪些信息缺失会影响判断？",
        "会后 24 小时内谁负责推进什么？",
    ]
    risks = [
        item["title"] for item in deduped
        if item["source"] in ("todo", "mail") and ("逾期" in item["title"] or "截止" in item["title"])
    ][:3]

    enriched = await llm_json(
        "负责会前准备。基于给定材料输出中文会议准备，"
        "不要编造材料里没有的人名或数字。"
        '只返回 JSON: {"summary": "2-3 句背景与目标", '
        '"agenda": ["议程项"], "questions": ["要问的问题"], "risks": ["风险或未决事项"]}。',
        json.dumps({
            "title": title,
            "start": start,
            "attendees": attendees,
            "context": deduped,
        }, ensure_ascii=False),
        bot=bot,
        extra_system=extra_system,
    )
    summary = f"为「{title or '本次会议'}」准备的会前简报，共找到 {len(deduped)} 条相关材料。"
    if enriched:
        if isinstance(enriched.get("summary"), str) and enriched["summary"].strip():
            summary = enriched["summary"].strip()
        if isinstance(enriched.get("agenda"), list) and enriched["agenda"]:
            agenda = [str(x) for x in enriched["agenda"] if str(x).strip()]
        if isinstance(enriched.get("questions"), list) and enriched["questions"]:
            questions = [str(x) for x in enriched["questions"] if str(x).strip()]
        if isinstance(enriched.get("risks"), list) and enriched["risks"]:
            risks = [str(x) for x in enriched["risks"] if str(x).strip()]

    return {
        "title": title or "会议准备",
        "start": start,
        "attendees": attendees,
        "summary": summary,
        "agenda": agenda,
        "questions": questions,
        "risks": risks,
        "context": deduped,
        "sources": {"dingtalk": dingtalk_status},
    }
