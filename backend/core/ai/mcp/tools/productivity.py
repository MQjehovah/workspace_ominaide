"""Productivity agent tools: schedule, notes, weather.

Closes the biggest voice-assistant gaps — before this, the agent could not
create schedule events or notes, and had no weather source for the morning
briefing. All tools operate on the user's own data via the existing services.
"""
from datetime import datetime, timedelta

from core.ai.mcp.core import MCPTool, MCPCallResponse, MCPContent
from core.config.settings import settings
from core.timeutil import parse_datetime


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


def _err(text: str) -> MCPCallResponse:
    return MCPCallResponse(isError=True, content=[MCPContent(text=text)])


# ---------------- 日程 ----------------

async def create_event_tool(user_id: int, args: dict) -> MCPCallResponse:
    """创建日程。args: title, start(ISO 或 "YYYY-MM-DD HH:MM"), remind_before(分钟), hours(持续小时,默认1)"""
    title = (args.get("title") or "").strip()
    start_raw = (args.get("start") or "").strip()
    if not title or not start_raw:
        return _err("title 和 start 必填")
    try:
        start = parse_datetime(start_raw)
    except ValueError:
        return _err(f"start 时间格式不对: {start_raw}（例 2026-10-26 15:00）")
    try:
        hours = float(args.get("hours") or 1)
        remind = int(args.get("remind_before") or 0)
        from plugins.schedule.backend.schemas import EventCreate
        from plugins.schedule.backend import service as schedule_service
        from core.database.session import async_session

        async with async_session() as db:
            ev = await schedule_service.create_event(db, user_id, EventCreate(
                title=title,
                start_time=start,
                end_time=start + timedelta(hours=hours) if hours > 0 else None,
                remind_before=max(remind, 0),
            ))
            await db.commit()
        return _ok(f"已创建日程「{title}」{start.strftime('%m-%d %H:%M')}"
                   + (f"，提前 {remind} 分钟提醒" if remind else ""))
    except Exception as e:
        return _err(f"创建失败: {e}")


async def list_events_tool(user_id: int, args: dict) -> MCPCallResponse:
    """查询日程。args: days=往后几天（默认 3）、all=false 只看今天"""
    days = min(int(args.get("days") or 3), 30)
    try:
        from plugins.schedule.backend import service as schedule_service
        from core.database.session import async_session

        now = datetime.now()
        async with async_session() as db:
            events = await schedule_service.list_events(db, user_id, start=now)
        events = [e for e in events if e.start_time <= now + timedelta(days=days)][:15]
        if not events:
            return _ok(f"接下来 {days} 天没有日程。")
        lines = [f"接下来 {days} 天的日程："]
        for e in events:
            mark = " ← 进行中" if e.start_time <= now else ""
            lines.append(f"- {e.start_time.strftime('%m-%d %H:%M')} {e.title}{mark}")
        return _ok("\n".join(lines))
    except Exception as e:
        return _err(f"查询失败: {e}")


# ---------------- 笔记 ----------------

async def create_note_tool(user_id: int, args: dict) -> MCPCallResponse:
    """记一条笔记（语音速记）。args: content(必填), title(可选,默认取内容前12字)"""
    content = (args.get("content") or "").strip()
    if not content:
        return _err("content 必填")
    title = (args.get("title") or "").strip() or content[:12]
    try:
        from plugins.notes.backend.schemas import NoteCreate
        from plugins.notes.backend import service as notes_service
        from core.database.session import async_session

        async with async_session() as db:
            note = await notes_service.create_note(db, user_id, NoteCreate(
                title=title, content=content))
            await db.commit()
        return _ok(f"已记入笔记「{note.title}」")
    except Exception as e:
        return _err(f"记笔记失败: {e}")


async def search_notes_tool(user_id: int, args: dict) -> MCPCallResponse:
    """搜索笔记。args: query(必填), limit(默认5)"""
    query = (args.get("query") or "").strip()
    if not query:
        return _err("query 必填")
    try:
        from plugins.notes.backend import service as notes_service
        from core.database.session import async_session

        async with async_session() as db:
            notes = await notes_service.search_notes(db, user_id, query)
        if not notes:
            return _ok(f"没有找到包含「{query}」的笔记。")
        lines = [f"找到 {len(notes)} 条："]
        for n in notes[:5]:
            snippet = " ".join((n.content or "").split())[:100]
            lines.append(f"- 《{n.title}》{('：' + snippet) if snippet else ''}")
        return _ok("\n".join(lines))
    except Exception as e:
        return _err(f"搜索失败: {e}")


# ---------------- 天气 ----------------

async def get_weather_tool(user_id: int, args: dict) -> MCPCallResponse:
    """当前天气 + 今日概况（Open-Meteo，需配置 weather_lat/lon）"""
    if not settings.weather_lat or not settings.weather_lon:
        return _ok("未配置天气位置（settings 里填 weather_lat/weather_lon）。")
    try:
        import httpx
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={settings.weather_lat}&longitude={settings.weather_lon}"
            "&current=temperature_2m,weather_code,wind_speed_10m"
            "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            "&timezone=auto&forecast_days=1"
        )
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url)
            d = r.json()
        cur, daily = d["current"], d["daily"]
        lines = [
            f"当前 {round(cur['temperature_2m'])}°C {WMO.get(cur['weather_code'], '未知')}，"
            f"风速 {round(cur['wind_speed_10m'])}km/h",
            f"今日 {round(daily['temperature_2m_min'][0])}~{round(daily['temperature_2m_max'][0])}°C，"
            f"降水概率 {daily['precipitation_probability_max'][0]}%",
        ]
        if daily["precipitation_probability_max"][0] >= 50:
            lines.append("降水概率较高，出门记得带伞。")
        return _ok("\n".join(lines))
    except Exception as e:
        return _err(f"天气查询失败: {e}")


WMO = {0: "晴", 1: "基本晴", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
       51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨", 61: "小雨", 63: "中雨", 65: "大雨",
       66: "冻雨", 67: "冻雨", 71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
       80: "阵雨", 81: "阵雨", 82: "强阵雨", 85: "阵雪", 86: "阵雪",
       95: "雷雨", 96: "雷雨伴冰雹", 99: "雷雨伴冰雹"}


TOOLS = [
    (MCPTool(
        name="create_event",
        description="为用户创建日程。用户说\"帮我约/提醒我…\"时调用。时间解析成 YYYY-MM-DD HH:MM（相对时间如\"明天下午三点\"换算成具体时间）。",
        inputSchema={"type": "object", "properties": {
            "title": {"type": "string"},
            "start": {"type": "string", "description": "开始时间 YYYY-MM-DD HH:MM"},
            "hours": {"type": "number", "description": "持续小时数，默认 1"},
            "remind_before": {"type": "integer", "description": "提前提醒分钟数，默认 0"},
        }, "required": ["title", "start"]},
    ), create_event_tool),
    (MCPTool(
        name="list_events",
        description="查询用户未来的日程安排。",
        inputSchema={"type": "object", "properties": {
            "days": {"type": "integer", "description": "往后看几天，默认 3"},
        }},
    ), list_events_tool),
    (MCPTool(
        name="create_note",
        description="帮用户记一条笔记（速记/日记/想法）。用户说\"记一下/记个笔记\"时调用。",
        inputSchema={"type": "object", "properties": {
            "content": {"type": "string", "description": "笔记内容"},
            "title": {"type": "string", "description": "标题，可省略"},
        }, "required": ["content"]},
    ), create_note_tool),
    (MCPTool(
        name="search_notes",
        description="按关键词搜索用户的笔记。",
        inputSchema={"type": "object", "properties": {
            "query": {"type": "string"}, "limit": {"type": "integer"},
        }, "required": ["query"]},
    ), search_notes_tool),
    (MCPTool(
        name="get_weather",
        description="查询当前天气与今日概况（温度/降水概率/带伞建议）。用户问天气、或生成晨报时调用。",
        inputSchema={"type": "object", "properties": {}},
    ), get_weather_tool),
]
