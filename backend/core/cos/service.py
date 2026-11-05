"""Chief-of-Staff services: triage, briefs, meeting prep and reply drafts.

All generation is deterministic-first. When an LLM key is configured the same
payload is enriched with a short narrative; without one the user still gets a
complete, usable result.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta

from sqlalchemy import or_, select

from core.config.settings import settings
from core.database.session import async_session
from core.cos import collectors


async def _llm_json(system: str, prompt: str, max_chars: int = 8000) -> dict | None:
    if not settings.llm_api_key:
        return None
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt[:max_chars]},
            ],
            temperature=0.3,
        )
        raw = resp.choices[0].message.content or ""
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return None
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception as e:
        print(f"[cos] llm error: {e}")
        return None


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


async def _all_triage_items(user_id: int, days: int) -> tuple[list[dict], dict]:
    now = datetime.now()
    since = now - timedelta(days=max(1, days))
    end = now + timedelta(days=2)

    mail = await collectors.mail_items(user_id, since=since, limit=30)
    todos = await collectors.todo_items(user_id, limit=30)
    events = await collectors.schedule_items(user_id, start=now - timedelta(hours=2), end=end, limit=20)
    rss = await collectors.rss_items(user_id, since=since, limit=20)
    dingtalk, dingtalk_status = await collectors.dingtalk_items(user_id, limit=15)

    items = [*mail, *todos, *events, *rss, *dingtalk]
    return items, {"dingtalk": dingtalk_status}


async def triage(user_id: int, days: int = 3) -> dict:
    items, sources = await _all_triage_items(user_id, days)
    groups = collectors.group_items(items)
    return {
        "generated_at": datetime.now().isoformat(),
        "window_days": days,
        "counts": {
            "total": len(items),
            **{key: len(value) for key, value in groups.items()},
        },
        "sources": sources,
        "groups": groups,
    }


async def daily_brief(user_id: int, day: date | None = None) -> dict:
    day = day or date.today()
    start, end = _day_bounds(day)
    now = datetime.now()

    events = await collectors.schedule_items(user_id, start=start, end=end, limit=20)
    todos = await collectors.todo_items(user_id, limit=20)
    mail = await collectors.mail_items(
        user_id, since=now - timedelta(days=2), limit=8, unread_only=True,
    )
    news = await collectors.rss_items(user_id, since=now - timedelta(hours=36), limit=5)
    dingtalk, dingtalk_status = await collectors.dingtalk_items(user_id, limit=8)

    due_today = [
        t for t in todos
        if t["meta"].get("due") and _parse_dt(t["meta"]["due"]) and _parse_dt(t["meta"]["due"]) < end
    ]
    overdue = [
        t for t in todos
        if t["meta"].get("due") and _parse_dt(t["meta"]["due"]) and _parse_dt(t["meta"]["due"]) < now
    ]

    memory_lines: list[str] = []
    try:
        from core.memory_service import list_records

        records = await list_records(user_id, "", 6)
        memory_lines = [r.content for r in records[:5]]
    except Exception:
        pass

    summary = _fallback_brief_summary(day, events, due_today, overdue, mail, news, dingtalk)
    enriched = await _llm_json(
        "你是用户的幕僚长。基于当天数据写 2-4 句中文晨报，"
        "先讲最重要的冲突或截止，再讲日程与需要回复的人，不编造数据。"
        '只返回 JSON: {"summary": "...", "focus": ["今天最该做的 1-3 件事"]}。',
        json.dumps({
            "day": day.isoformat(),
            "events": events,
            "todos": due_today,
            "overdue": overdue,
            "mail": mail,
            "news": news,
            "dingtalk": dingtalk,
            "memory": memory_lines,
        }, ensure_ascii=False),
    )
    focus: list[str] = []
    if enriched and isinstance(enriched.get("summary"), str) and enriched["summary"].strip():
        summary = enriched["summary"].strip()
        focus = [str(x) for x in (enriched.get("focus") or []) if str(x).strip()]
    if not focus:
        focus = _fallback_focus(events, overdue, due_today, mail, dingtalk)

    sections = [
        {"key": "schedule", "title": "今日日程", "items": events},
        {"key": "todos", "title": "待办与截止", "items": due_today or todos[:8]},
        {"key": "mail", "title": "需要处理的邮件", "items": mail},
        {"key": "dingtalk", "title": "钉钉未读", "items": dingtalk},
        {"key": "news", "title": "值得一看", "items": news},
        {"key": "memory", "title": "长期记忆提醒", "items": [
            {"id": f"memory:{i}", "title": line, "source": "memory", "summary": ""}
            for i, line in enumerate(memory_lines)
        ]},
    ]
    return {
        "day": day.isoformat(),
        "generated_at": datetime.now().isoformat(),
        "summary": summary,
        "focus": focus,
        "sections": sections,
        "sources": {"dingtalk": dingtalk_status},
        "stats": {
            "schedule_count": len(events),
            "todo_due_count": len(due_today),
            "todo_overdue_count": len(overdue),
            "mail_count": len(mail),
            "news_count": len(news),
            "dingtalk_count": len(dingtalk),
        },
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


def _fallback_focus(
    events: list[dict], overdue: list[dict], due_today: list[dict],
    mail: list[dict], dingtalk: list[dict],
) -> list[str]:
    focus: list[str] = []
    if overdue:
        focus.append(f"处理逾期事项：{overdue[0]['title']}")
    if events:
        focus.append(f"准备 {events[0]['title']}")
    if mail:
        focus.append(f"回复 {mail[0].get('from') or '重要邮件'}：{mail[0]['title']}")
    if dingtalk:
        focus.append(f"查看钉钉未读：{dingtalk[0]['title']}")
    if not focus and due_today:
        focus.append(f"推进今天到期的待办：{due_today[0]['title']}")
    return focus[:3]


async def meeting_prep(
    user_id: int,
    *,
    title: str = "",
    start: str | None = None,
    attendees: list[str] | None = None,
    query: str | None = None,
) -> dict:
    attendees = [a for a in (attendees or []) if str(a).strip()]
    keyword = (query or title or "").strip()
    start_dt = _parse_dt(start)
    window_start = (start_dt or datetime.now()) - timedelta(days=1)
    window_end = (start_dt or datetime.now()) + timedelta(days=1)

    context: list[dict] = []
    events = await collectors.schedule_items(
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
        mail = await collectors.mail_items(user_id, limit=8, query=keyword)
        for item in mail:
            context.append({
                "source": "mail",
                "title": item["title"],
                "snippet": item.get("summary") or "",
                "time": item.get("time"),
                "link": "/mail",
            })
        todos = await collectors.todo_items(user_id, limit=6, query=keyword)
        for item in todos:
            context.append({
                "source": "todo",
                "title": item["title"],
                "snippet": item.get("summary") or "",
                "time": item.get("time"),
                "link": "/dashboard",
            })
        news = await collectors.rss_items(user_id, limit=5, query=keyword)
        for item in news:
            context.append({
                "source": "rss",
                "title": item["title"],
                "snippet": item.get("summary") or "",
                "time": item.get("time"),
                "link": "/rss",
            })

        dingtalk, dingtalk_status = await collectors.dingtalk_items(user_id, query=keyword, limit=8)
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
                "link": "/about",
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

    enriched = await _llm_json(
        "你是用户的幕僚长，负责会前准备。基于给定材料输出中文会议准备，"
        "不要编造材料里没有的人名或数字。"
        '只返回 JSON: {"summary": "2-3 句背景与目标", '
        '"agenda": ["议程项"], "questions": ["要问的问题"], "risks": ["风险或未决事项"]}。',
        json.dumps({
            "title": title,
            "start": start,
            "attendees": attendees,
            "context": deduped,
        }, ensure_ascii=False),
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


async def weekly_review(user_id: int, weeks: int = 1) -> dict:
    from core.ai.daily_insights import get_recent_insights
    from plugins.mail.backend.models import MailMessage
    from plugins.schedule.backend.models import Event
    from plugins.todo.backend.models import PluginTodoItem

    days = max(7, weeks * 7)
    today = date.today()
    start_day = today - timedelta(days=days - 1)
    start_dt, _ = _day_bounds(start_day)
    _, end_dt = _day_bounds(today)

    insights = [
        row for row in await get_recent_insights(user_id, days)
        if row.day >= start_day
    ]

    async with async_session() as db:
        done = list((await db.execute(
            select(PluginTodoItem).where(
                PluginTodoItem.user_id == user_id,
                PluginTodoItem.status == "done",
                PluginTodoItem.updated_at >= start_dt,
            ).order_by(PluginTodoItem.updated_at.desc()).limit(50)
        )).scalars().all())
        pending = list((await db.execute(
            select(PluginTodoItem).where(
                PluginTodoItem.user_id == user_id,
                PluginTodoItem.status == "pending",
            ).order_by(PluginTodoItem.due_date).limit(50)
        )).scalars().all())
        next_events = list((await db.execute(
            select(Event).where(
                Event.user_id == user_id,
                Event.start_time >= datetime.now(),
                Event.start_time < datetime.now() + timedelta(days=7),
            ).order_by(Event.start_time).limit(20)
        )).scalars().all())
        important_mail = list((await db.execute(
            select(MailMessage).where(
                MailMessage.user_id == user_id,
                MailMessage.important == True,  # noqa: E712
                or_(MailMessage.date >= start_dt, MailMessage.created_at >= start_dt),
            ).limit(30)
        )).scalars().all())

    wins: list[str] = []
    for row in insights:
        wins.extend(str(x) for x in (row.highlights or []) if str(x).strip())
    wins.extend(t.title for t in done[:8])
    wins = list(dict.fromkeys(wins))[:10]

    overdue = [
        t.title for t in pending
        if t.due_date and t.due_date < datetime.now()
    ][:5]
    next_week = [
        f"{(e.start_time.strftime('%m-%d %H:%M') if e.start_time else '')} {e.title}"
        for e in next_events
    ]

    insight_text = "；".join(row.summary for row in insights if row.summary)
    summary = (
        f"本周完成 {len(done)} 项待办，还有 {len(pending)} 项待推进。"
        + (f" 回顾：{insight_text}" if insight_text else "")
        + (f" 逾期：{'、'.join(overdue)}。" if overdue else "")
    )[:1200]

    enriched = await _llm_json(
        "你是用户的幕僚长。基于本周数据写一份中文周报，"
        "包括成果、进行中、风险、下周重点。不要编造。"
        '只返回 JSON: {"summary": "3-5 句总结", "wins": ["成果"], '
        '"in_progress": ["进行中"], "risks": ["风险"], "next_week": ["下周重点"]}。',
        json.dumps({
            "period": [start_day.isoformat(), today.isoformat()],
            "insights": [
                {"day": row.day.isoformat(), "summary": row.summary,
                 "highlights": row.highlights, "patterns": row.patterns}
                for row in insights
            ],
            "todos_done": [t.title for t in done],
            "todos_pending": [t.title for t in pending],
            "events_next_week": next_week,
            "important_mail": [m.subject for m in important_mail],
        }, ensure_ascii=False),
    )
    if enriched:
        if isinstance(enriched.get("summary"), str) and enriched["summary"].strip():
            summary = enriched["summary"].strip()
        if isinstance(enriched.get("wins"), list) and enriched["wins"]:
            wins = [str(x) for x in enriched["wins"] if str(x).strip()]
        if isinstance(enriched.get("risks"), list) and enriched["risks"]:
            overdue = [str(x) for x in enriched["risks"] if str(x).strip()]
        if isinstance(enriched.get("next_week"), list) and enriched["next_week"]:
            next_week = [str(x) for x in enriched["next_week"] if str(x).strip()]

    return {
        "period": {"start": start_day.isoformat(), "end": today.isoformat()},
        "summary": summary,
        "wins": wins,
        "in_progress": [t.title for t in pending[:8]],
        "risks": overdue,
        "next_week": next_week,
        "stats": {
            "insight_days": len(insights),
            "todos_done": len(done),
            "todos_pending": len(pending),
            "events_next_week": len(next_events),
            "important_mail": len(important_mail),
        },
    }


_TONES = {
    "professional": "专业、简洁、有礼貌",
    "friendly": "友好、自然、有人情味",
    "concise": "非常简短，直接说结论和下一步",
}


async def draft_reply(
    user_id: int,
    *,
    source: str = "mail",
    message_id: int | None = None,
    message: str | None = None,
    subject: str | None = None,
    tone: str = "professional",
    instructions: str | None = None,
) -> dict | None:
    original_subject = subject or ""
    original_body = (message or "").strip()
    from_address = ""

    if source == "mail":
        from plugins.mail.backend.models import MailMessage

        if not message_id:
            return None
        async with async_session() as db:
            row = (await db.execute(
                select(MailMessage).where(
                    MailMessage.id == message_id,
                    MailMessage.user_id == user_id,
                )
            )).scalar_one_or_none()
        if row is None:
            return None
        original_subject = row.subject or original_subject
        original_body = (row.content or row.preview or "").strip()
        from_address = row.from_address or ""

    if not original_body and not original_subject:
        return None

    tone_text = _TONES.get(tone, _TONES["professional"])
    base_subject = original_subject.strip()
    reply_subject = base_subject if base_subject.lower().startswith("re:") else f"Re: {base_subject}".strip()

    fallback = _fallback_reply(original_subject, original_body, tone)
    enriched = await _llm_json(
        f"你是用户的助理，代写一封{'' if source == 'mail' else '消息'}回复草稿。语气：{tone_text}。"
        "只写草稿，不要声称已经发送，也不要编造承诺或日期。"
        '只返回 JSON: {"subject": "邮件主题", "body": "回复正文"}。',
        json.dumps({
            "channel": source,
            "from": from_address,
            "subject": original_subject,
            "message": original_body[:4000],
            "instructions": instructions or "",
        }, ensure_ascii=False),
    )
    body = fallback
    if enriched and isinstance(enriched.get("body"), str) and enriched["body"].strip():
        body = enriched["body"].strip()
        if isinstance(enriched.get("subject"), str) and enriched["subject"].strip():
            reply_subject = enriched["subject"].strip()

    return {
        "source": source,
        "message_id": message_id,
        "to": from_address,
        "subject": reply_subject,
        "body": body,
        "tone": tone,
        "sent": False,
        "note": "这是草稿，尚未发送。确认后再通过邮件或钉钉发送。",
    }


def _fallback_reply(subject: str, body: str, tone: str) -> str:
    topic = f"「{subject}」" if subject else "你提到的事项"
    snippet = " ".join(body.split())[:120]
    if tone == "concise":
        return f"收到，关于{topic}我会尽快确认并回复下一步。"
    if tone == "friendly":
        return (
            f"你好！\n\n看到了关于{topic}的消息。"
            + (f"（{snippet}……）\n\n" if snippet else "\n\n")
            + "我先核对一下相关细节，确认后马上同步进展。有新的信息也欢迎随时告诉我。\n\n谢谢！"
        )
    return (
        f"你好，\n\n收到关于{topic}的消息，核心信息已了解。"
        + (f"\n\n原文要点：{snippet}……\n" if snippet else "\n")
        + "\n我会尽快确认相关细节，并同步后续进展。如需我优先处理某一部分，请直接说明。\n\n谢谢！"
    )
