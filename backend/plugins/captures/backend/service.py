"""Quick capture ingestion and analysis."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from core.ai.indexer import index_content
from plugins.captures.backend.models import QuickCapture
from core.config.settings import settings
from core.database.session import async_session
from core.logging import get_logger

log = get_logger(__name__)
MAX_BYTES = 2 * 1024 * 1024


def _clean(text: str, limit: int = 12000) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:limit]


def _validate_url(url: str) -> str:
    from core.ai.mcp.tools.web import _validate_url as validate

    return validate(url)


async def _fetch_article(url: str) -> tuple[str, str, str]:
    """Fetch a public page with redirect re-validation."""
    current = _validate_url(url)
    for _ in range(4):
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=20,
            headers={"User-Agent": "OmniAide/1.0"},
        ) as client:
            resp = await client.get(current)
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("location")
            if not location:
                raise ValueError("redirect without location")
            current = _validate_url(urljoin(current, location))
            continue
        if resp.status_code >= 400:
            raise ValueError(f"HTTP {resp.status_code}")
        ctype = (resp.headers.get("content-type") or "").lower()
        if ctype and not any(t in ctype for t in ("text/html", "text/plain", "application/xhtml")):
            raise ValueError(f"unsupported content type: {ctype}")
        raw = resp.content[:MAX_BYTES]
        text = raw.decode(resp.encoding or "utf-8", errors="replace")
        if "html" in ctype or not ctype:
            soup = BeautifulSoup(text, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "svg", "iframe"]):
                tag.decompose()
            body = soup.body or soup
            content = body.get_text("\n", strip=True)
        else:
            title, content = "", text
        return title, _clean(content), current
    raise ValueError("too many redirects")


async def _llm_analyze(title: str, content: str) -> dict:
    if not settings.llm_api_key:
        return {}
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是个人知识库的采集分析器。只返回 JSON："
                        "{\"title\":\"...\",\"summary\":\"...\",\"key_points\":[\"...\"],"
                        "\"tags\":[\"...\"],\"people\":[\"...\"],"
                        "\"suggested_actions\":[{\"type\":\"todo|event|note\",\"title\":\"...\"}]}。"
                        "summary 不超过 300 字，key_points 最多 5 条，tags 最多 8 个，people 只提取人名。"
                    ),
                },
                {"role": "user", "content": f"标题：{title}\n\n正文：{content[:10000]}"},
            ],
            temperature=0.1,
        )
        raw = resp.choices[0].message.content or "{}"
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return {}
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log.warning("capture llm analysis failed: %s", exc)
        return {}


async def _file_text(file_id: int) -> str:
    try:
        from plugins.files.backend.models import File
        from core.database.session import async_session
        from core.minio.client import minio_client

        if minio_client is None:
            return ""
        async with async_session() as db:
            row = await db.get(File, file_id)
        if row is None or (row.size or 0) > 20 * 1024 * 1024:
            return ""
        data = await asyncio.to_thread(
            lambda: minio_client.get_object(row.bucket, row.object_key).read()
        )
        from plugins.notes.backend.importers import extract_document

        _title, text = extract_document(row.original_name or "capture.txt", data)
        return _clean(text)
    except Exception as exc:
        log.debug("capture file extract failed id=%s: %s", file_id, exc)
        return ""


async def analyze_capture(capture_id: int) -> dict:
    async with async_session() as db:
        row = await db.get(QuickCapture, capture_id)
        if row is None:
            return {"status": "missing"}
        row.status = "processing"
        row.error = None
        await db.commit()

    try:
        title = row.title or ""
        content = row.content or ""
        final_url = row.url
        if row.kind in ("link", "article") and row.url and not content:
            fetched_title, fetched_text, final_url = await _fetch_article(row.url)
            title = title or fetched_title
            content = fetched_text
        if row.kind in ("file", "image") and row.file_id and not content:
            content = await _file_text(row.file_id)
        analysis = await _llm_analyze(title, content)
        summary = str(analysis.get("summary") or "").strip() or _clean(content, 300)
        async with async_session() as db:
            row = await db.get(QuickCapture, capture_id)
            if row is None:
                return {"status": "missing"}
            row.title = str(analysis.get("title") or title or row.url or "随手记")[:500]
            row.content = content
            row.summary = summary[:2000]
            row.key_points = analysis.get("key_points") or []
            row.tags = analysis.get("tags") or []
            row.people = analysis.get("people") or []
            row.suggested_actions = analysis.get("suggested_actions") or []
            if final_url and final_url != row.url:
                row.url = final_url
            row.status = "ready"
            row.error = None
            await db.commit()
            capture = row
        await index_content(
            capture.user_id, "capture", capture.id,
            capture.title or "随手记", capture.content or capture.summary or "",
            metadata={"link": f"/captures/{capture.id}"},
        )
        try:
            from core.people import service as people_service

            for name in capture.people or []:
                if name:
                    await people_service.mention_person(
                        capture.user_id, str(name),
                        source_type="capture", source_id=capture.id,
                        title=capture.title, snippet=capture.summary,
                        occurred_at=capture.created_at,
                    )
        except Exception as exc:
            log.warning("capture people index failed: %s", exc)
        return {"status": "ready", "id": capture.id}
    except Exception as exc:
        log.warning("capture analyze failed id=%s: %s", capture_id, exc)
        async with async_session() as db:
            row = await db.get(QuickCapture, capture_id)
            if row is not None:
                row.status = "failed"
                row.error = str(exc)[:1000]
                await db.commit()
        return {"status": "failed", "error": str(exc)[:500]}


async def create_capture(
    user_id: int,
    *,
    kind: str,
    source: str = "web",
    url: str | None = None,
    text: str | None = None,
    title: str | None = None,
    file_id: int | None = None,
) -> QuickCapture:
    kind = (kind or "text").lower()
    if kind not in {"link", "article", "image", "text", "file"}:
        raise ValueError("unsupported capture kind")
    if kind in {"link", "article"} and not (url or "").strip():
        raise ValueError("url is required")
    if kind == "text" and not (text or "").strip():
        raise ValueError("text is required")
    if kind in {"image", "file"} and not file_id:
        raise ValueError("file_id is required")
    async with async_session() as db:
        row = QuickCapture(
            user_id=user_id,
            kind=kind,
            source=source or "web",
            url=(url or "").strip() or None,
            title=(title or "").strip() or None,
            content=text or "",
            file_id=file_id,
            status="inbox",
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        capture_id = row.id
        from core.events.bus import record_event

        await record_event(
            db, user_id, "capture.created", "capture", capture_id,
            f"新增采集：{row.title or row.url or '随手记'}",
            {"kind": kind, "source": source},
        )
        await db.commit()

    from core.jobs.service import enqueue

    await enqueue(
        "capture.analyze",
        {"capture_id": capture_id},
        user_id=user_id,
        idempotency_key=f"capture:analyze:{capture_id}",
    )
    return row


async def list_captures(
    user_id: int,
    *,
    status: str | None = None,
    kind: str | None = None,
    limit: int = 50,
) -> list[QuickCapture]:
    async with async_session() as db:
        q = select(QuickCapture).where(QuickCapture.user_id == user_id)
        if status:
            q = q.where(QuickCapture.status == status)
        if kind:
            q = q.where(QuickCapture.kind == kind)
        q = q.order_by(QuickCapture.id.desc()).limit(min(max(limit, 1), 200))
        return list((await db.execute(q)).scalars().all())


async def get_capture(user_id: int, capture_id: int) -> QuickCapture | None:
    async with async_session() as db:
        return (
            await db.execute(
                select(QuickCapture).where(
                    QuickCapture.id == capture_id,
                    QuickCapture.user_id == user_id,
                )
            )
        ).scalar_one_or_none()


async def convert_capture(user_id: int, capture_id: int, target: str, params: dict | None = None) -> dict:
    from plugins.notes.backend.schemas import NoteCreate
    from plugins.notes.backend.service import create_note
    from plugins.schedule.backend.schemas import EventCreate
    from plugins.schedule.backend.service import create_event
    from plugins.todo.backend.schemas import TodoCreate
    from plugins.todo.backend.service import create_todo

    params = params or {}
    async with async_session() as db:
        row = await db.get(QuickCapture, capture_id)
        if row is None or row.user_id != user_id:
            raise ValueError("capture not found")
        title = str(params.get("title") or row.title or "随手记")[:500]
        content = str(params.get("content") or row.content or row.summary or "")
        if target == "note":
            created = await create_note(db, user_id, NoteCreate(title=title, content=content))
            row.note_id = created.id
            result = {"note_id": created.id}
        elif target == "todo":
            created = await create_todo(db, user_id, TodoCreate(
                title=title, description=params.get("description") or row.summary,
            ))
            result = {"todo_id": created.id}
        elif target == "event":
            if not params.get("start_time"):
                raise ValueError("start_time is required for event conversion")
            created = await create_event(db, user_id, EventCreate(
                title=title,
                start_time=params["start_time"],
                end_time=params.get("end_time"),
                notes=params.get("notes") or row.summary,
            ))
            result = {"event_id": created.id}
        else:
            raise ValueError("target must be note/todo/event")
        row.status = "converted"
        await db.commit()
    return result


async def delete_capture(user_id: int, capture_id: int) -> bool:
    async with async_session() as db:
        row = await db.get(QuickCapture, capture_id)
        if row is None or row.user_id != user_id:
            return False
        await db.delete(row)
        await db.commit()
        return True


async def _handle_capture_analyze(job) -> dict:
    capture_id = int((job.payload or {}).get("capture_id") or 0)
    if not capture_id:
        raise ValueError("capture_id is required")
    return await analyze_capture(capture_id)


def register_capture_handlers() -> None:
    from core.jobs.service import register_handler

    register_handler("capture.analyze", _handle_capture_analyze)
