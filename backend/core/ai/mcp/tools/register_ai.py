"""Register MCP tools for schedule, notifications, RSS plugins."""
from core.ai.mcp.registry import tool_registry
from core.ai.mcp.core import MCPTool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import async_session


async def list_schedule_events(user_id: int, args: dict) -> dict:
    """List schedule events within a date range."""
    from datetime import datetime, timedelta
    start = args.get("start") or datetime.utcnow().isoformat()
    end = args.get("end") or (datetime.utcnow() + timedelta(days=30)).isoformat()
    async with async_session() as db:
        from plugins.schedule.backend.models import Event
        q = select(Event).where(Event.user_id == user_id, Event.start_time >= start, Event.start_time <= end).order_by(Event.start_time).limit(20)
        r = await db.execute(q)
        evts = r.scalars().all()
        return {"events": [{"id": e.id, "title": e.title, "start_time": str(e.start_time), "end_time": str(e.end_time) if e.end_time else None} for e in evts]}


async def create_schedule_event(user_id: int, args: dict) -> dict:
    """Create a schedule/calendar event. Use this to turn natural-language requests into calendar events."""
    from datetime import datetime, timedelta
    title = args.get("title")
    start = args.get("start_time")
    if not title or not start:
        return {"error": "title and start_time are required"}
    try:
        start_dt = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
    except ValueError:
        return {"error": "start_time must be an ISO datetime string, e.g. 2026-08-02T15:00:00"}
    start_dt = start_dt.replace(tzinfo=None)
    end = args.get("end_time")
    end_dt = datetime.fromisoformat(str(end).replace("Z", "+00:00")).replace(tzinfo=None) if end else None
    notes = args.get("notes")
    remind_before = int(args.get("remind_before", 10) or 0)

    from plugins.schedule.backend.schemas import EventCreate
    from plugins.schedule.backend.service import create_event
    req = EventCreate(
        title=title,
        start_time=start_dt,
        end_time=end_dt or (start_dt + timedelta(hours=1)),
        notes=notes,
        remind_before=remind_before,
    )
    async with async_session() as db:
        ev = await create_event(db, user_id, req)
        await db.commit()
        return {"id": ev.id, "title": ev.title, "start_time": str(ev.start_time), "remind_before": ev.remind_before}


async def list_recent_emails(user_id: int, args: dict) -> dict:
    """List recent emails reported by the user's mail client. Returns subject, sender and preview."""
    limit = min(int(args.get("limit", 10)), 50)
    only_important = bool(args.get("important", False))
    async with async_session() as db:
        from plugins.mail.backend.models import MailEvent
        q = select(MailEvent).where(MailEvent.user_id == user_id)
        if only_important:
            q = q.where(MailEvent.important == True)
        q = q.order_by(MailEvent.created_at.desc()).limit(limit)
        r = await db.execute(q)
        events = r.scalars().all()
        return {"emails": [{
            "id": e.id,
            "subject": e.subject,
            "from": e.from_address,
            "date": e.date or (str(e.created_at) if e.created_at else ""),
            "preview": (e.preview or "")[:300],
            "important": bool(e.important),
        } for e in events]}


async def search_articles(user_id: int, args: dict) -> dict:
    q = args.get("q", "")
    if not q: return {"items": []}
    async with async_session() as db:
        from plugins.rss.backend.models import Entry, Feed
        from sqlalchemy import or_
        cond = [Feed.user_id == user_id, or_(Entry.title.ilike(f"%{q}%"), Entry.summary.ilike(f"%{q}%"))]
        base = select(Entry).join(Feed).where(*cond).order_by(Entry.published.desc()).limit(10)
        r = await db.execute(base)
        items = r.scalars().all()
        return {"items": [{"title": i.title, "summary": i.summary[:200] if i.summary else "", "published": str(i.published) if i.published else ""} for i in items]}


async def list_notifications(user_id: int, args: dict) -> dict:
    """List recent notifications for the user."""
    limit = args.get("limit", 10)
    unread = args.get("unread", False)
    async with async_session() as db:
        from plugins.notifications.backend.models import Notification
        q = select(Notification).where(Notification.user_id == user_id)
        if unread: q = q.where(Notification.read == False)
        q = q.order_by(Notification.created_at.desc()).limit(limit)
        r = await db.execute(q)
        ns = r.scalars().all()
        return {"notifications": [{"id": n.id, "title": n.title, "body": n.body, "created_at": str(n.created_at)} for n in ns]}


async def get_unread_count(user_id: int, args: dict) -> dict:
    """Get the number of unread notifications."""
    async with async_session() as db:
        from plugins.notifications.backend.models import Notification
        from sqlalchemy import func
        r = await db.execute(select(func.count(Notification.id)).where(Notification.user_id == user_id, Notification.read == False))
        return {"unread_count": r.scalar() or 0}


async def get_user_info(user_id: int, args: dict) -> dict:
    """Get current user information."""
    async with async_session() as db:
        from core.auth.domain.models import User
        r = await db.execute(select(User).where(User.id == user_id))
        u = r.scalar_one_or_none()
        if not u: return {"error": "User not found"}
        return {"username": u.username, "email": u.email, "created_at": str(u.created_at) if u.created_at else ""}


async def unified_search_tool(user_id: int, args: dict) -> dict:
    q = args.get("q", "")
    if not q:
        return {"results": []}
    from core.ai.embeddings import generate_embedding
    from qdrant_client import QdrantClient
    from core.config.settings import settings
    host = settings.qdrant_url.replace("http://", "").split(":")[0]
    port = int(settings.qdrant_url.split(":")[-1])
    client = QdrantClient(host=host, port=port)
    vector = await generate_embedding(q)
    if vector is None:
        return {"results": []}
    filter_cond = {"must": [{"key": "user_id", "match": {"value": user_id}}]}
    types = args.get("types")
    if types:
        filter_cond["must"].append({"key": "source_type", "match": {"any": types}})
    results = client.search(collection_name="omnidocs", query_vector=vector, limit=10, query_filter=filter_cond)
    return {"results": [{"type": p.payload.get("source_type"), "title": p.payload.get("title"), "snippet": p.payload.get("content", "")[:200], "score": p.score} for p in results]}


def register_ai_tools():
    tool_registry.register(MCPTool(name="list_schedule_events", description="List upcoming schedule/calendar events within a date range. Returns event titles and times.", inputSchema={"type":"object","properties":{"start":{"type":"string","description":"Start date ISO format"},"end":{"type":"string","description":"End date ISO format"}}}), list_schedule_events)
    tool_registry.register(MCPTool(name="list_recent_emails", description="List recent emails received by the user. Returns subject, sender and preview. Use important=true to filter for important mail.", inputSchema={"type":"object","properties":{"limit":{"type":"integer","description":"Max results"},"important":{"type":"boolean","description":"Only important emails"}}}), list_recent_emails)
    tool_registry.register(MCPTool(name="create_schedule_event", description="Create a schedule/calendar event. Use this to turn natural-language requests like '明天下午3点开会' into calendar events.", inputSchema={"type":"object","properties":{"title":{"type":"string","description":"Event title"},"start_time":{"type":"string","description":"Start time ISO format, e.g. 2026-08-02T15:00:00"},"end_time":{"type":"string","description":"Optional end time ISO format"},"notes":{"type":"string","description":"Optional notes"},"remind_before":{"type":"integer","description":"Minutes before to remind, default 10"}},"required":["title","start_time"]}), create_schedule_event)
    tool_registry.register(MCPTool(name="search_articles", description="Search RSS feed articles by keyword. Returns matching article titles and summaries.", inputSchema={"type":"object","properties":{"q":{"type":"string","description":"Search keyword"}},"required":["q"]}), search_articles)
    tool_registry.register(MCPTool(name="list_notifications", description="List recent notifications. Use unread=true to see only unread.", inputSchema={"type":"object","properties":{"limit":{"type":"integer","description":"Max results"},"unread":{"type":"boolean","description":"Only unread"}}}), list_notifications)
    tool_registry.register(MCPTool(name="get_unread_count", description="Get the number of unread notifications.", inputSchema={"type":"object","properties":{}}), get_unread_count)
    tool_registry.register(MCPTool(name="get_user_info", description="Get info about the currently logged-in user.", inputSchema={"type":"object","properties":{}}), get_user_info)
    tool_registry.register(MCPTool(name="unified_search", description="Search across all your data (files, notes, articles, events) with a natural language query. Use this as the primary search tool.", inputSchema={"type":"object","properties":{"q":{"type":"string","description":"Natural language search query"},"types":{"type":"array","items":{"type":"string"},"description":"Optional: filter by type (file, note, rss_entry, event)"}},"required":["q"]}), unified_search_tool)
