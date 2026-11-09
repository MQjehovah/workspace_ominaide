from __future__ import annotations

from core.logging import get_logger
log = get_logger(__name__)

import asyncio
import json
from datetime import datetime

from sqlalchemy import select

from core.config.settings import settings
from core.ai.llm import llm_json
from core.database.session import async_session
from core.meetings.asr import AsrError, transcribe_minio_object
from core.meetings.models import MeetingMinutesJob

_tasks: set[asyncio.Task] = set()
_semaphore: asyncio.Semaphore | None = None
_MAX_TRANSCRIPT_CHARS = 300_000


def _asr_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(max(1, settings.meeting_asr_concurrency))
    return _semaphore


def _short(value, limit: int = 80) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _seconds(value) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _clock(value: float | None) -> str:
    if value is None:
        return ""
    seconds = max(0, int(value))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _normalise_minutes(data: dict | None, transcript: str) -> dict:
    if not isinstance(data, dict):
        text = transcript.strip()
        return {
            "summary": _short(text, 220) if text else "",
            "discussion": [],
            "decisions": [],
            "action_items": [],
            "risks": [],
        }

    def strings(key: str) -> list[str]:
        value = data.get(key)
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            return [
                str(item).strip()
                for item in value
                if str(item or "").strip()
            ]
        return []

    actions: list[dict] = []
    raw_actions = data.get("action_items") or data.get("todos")
    if isinstance(raw_actions, list):
        for row in raw_actions:
            if isinstance(row, str) and row.strip():
                actions.append({"title": row.strip(), "owner": "", "due": ""})
            elif isinstance(row, dict):
                title = str(row.get("title") or row.get("task") or "").strip()
                if title:
                    actions.append(
                        {
                            "title": title,
                            "owner": str(row.get("owner") or "").strip(),
                            "due": str(row.get("due") or "").strip(),
                        }
                    )

    return {
        "summary": _short(data.get("summary") or data.get("overview"), 400),
        "discussion": strings("discussion")[:12],
        "decisions": strings("decisions")[:12],
        "action_items": actions[:20],
        "risks": strings("risks")[:12],
    }


def _fallback_minutes(transcript: str) -> dict:
    return _normalise_minutes(None, transcript)


async def _summarise_long(transcript: str, bot) -> dict:
    """Keep prompt size bounded without splitting the audio file itself."""
    text = transcript[:_MAX_TRANSCRIPT_CHARS]
    if len(text) <= 16000:
        return _normalise_minutes(
            await llm_json(
                _MINUTES_SYSTEM,
                text,
                bot=bot,
            ),
            text,
        )

    chunks: list[str] = []
    size = 12000
    for start in range(0, len(text), size):
        piece = text[start : start + size]
        result = await llm_json(
            "提炼这段会议转写的讨论点、决议、待办和风险，输出 JSON："
            '{"discussion":[],"decisions":[],"action_items":[],"risks":[]}。'
            "不要编造。",
            piece,
            bot=bot,
        )
        if isinstance(result, dict):
            chunks.append(json.dumps(result, ensure_ascii=False))

    merged = "\n\n".join(chunks)[:24000]
    return _normalise_minutes(
        await llm_json(
            _MINUTES_SYSTEM,
            "以下是分段提炼结果，请合并为最终会议纪要：\n\n" + merged,
            bot=bot,
        ),
        text,
    )


_MINUTES_SYSTEM = (
    "你是会议纪要助手。根据会议转写生成结构化中文纪要。"
    "只输出 JSON："
    '{"summary":"2-4句摘要","discussion":["关键讨论"],'
    '"decisions":["明确决议"],"action_items":[{"title":"事项","owner":"负责人","due":"截止时间"}],'
    '"risks":["风险或遗留问题"]}。'
    "只写转写中出现的信息，不要编造；没有的字段用空数组。"
)


def _build_markdown(
    title: str,
    transcript: str,
    segments: list[dict] | None,
    minutes: dict,
    file_id: int,
    created_at: datetime,
) -> str:
    lines: list[str] = [
        f"# {title}",
        "",
        f"- 时间：{created_at.strftime('%Y-%m-%d %H:%M')}",
        f"- 录音文件：文件 ID {file_id}（已保留，可在文件中播放）",
        "",
        "## 摘要",
        "",
        minutes.get("summary") or "（未能生成摘要）",
    ]

    def section(name: str, values: list[str]) -> None:
        if not values:
            return
        lines.extend(["", f"## {name}", ""])
        for value in values:
            lines.append(f"- {value}")

    section("关键讨论", minutes.get("discussion") or [])
    section("决议", minutes.get("decisions") or [])
    section("风险与遗留", minutes.get("risks") or [])

    actions = minutes.get("action_items") or []
    if actions:
        lines.extend(["", "## 待办", ""])
        for item in actions:
            suffix = []
            if item.get("owner"):
                suffix.append(f"负责人：{item['owner']}")
            if item.get("due"):
                suffix.append(f"截止：{item['due']}")
            tail = f"（{'，'.join(suffix)}）" if suffix else ""
            lines.append(f"- [ ] {item.get('title', '')}{tail}")

    lines.extend(["", "## 转写", ""])
    if segments:
        for row in segments:
            speaker = row.get("speaker")
            label = f"说话人 {speaker}" if speaker not in (None, "") else "发言人"
            stamp = _clock(_seconds(row.get("start")))
            prefix = f"[{stamp}] " if stamp else ""
            lines.append(f"- {prefix}{label}：{row.get('text', '')}")
    else:
        lines.append(transcript[:200_000] or "（无转写内容）")

    return "\n".join(lines).strip() + "\n"


async def _run_job(job_id: int) -> None:
    bot = None
    try:
        async with async_session() as db:
            job = await db.get(MeetingMinutesJob, job_id)
            if job is None or job.status in {"done", "failed"}:
                return
            job.status = "transcribing"
            job.started_at = job.started_at or datetime.now()
            job.error = None
            file_id = job.file_id
            user_id = job.user_id
            title = job.title
            created_at = job.created_at or datetime.now()
            await db.flush()
            await db.commit()

        from plugins.files.backend.models import File

        async with async_session() as db:
            file_record = await db.get(File, file_id)
        if file_record is None:
            raise ValueError("录音文件不存在")

        async with _asr_semaphore():
            result = await transcribe_minio_object(file_record)

        transcript = str(result.get("text") or "").strip()[: _MAX_TRANSCRIPT_CHARS]
        segments = result.get("segments") or []
        if not transcript:
            raise AsrError("没有识别到语音内容")

        async with async_session() as db:
            job = await db.get(MeetingMinutesJob, job_id)
            if job is None:
                return
            job.transcript = transcript
            job.segments = segments
            job.status = "summarizing"
            await db.flush()
            await db.commit()

        try:
            from core.bots.registry import get_active_bot

            bot = await get_active_bot(user_id)
        except Exception:
            bot = None

        minutes = await _summarise_long(transcript, bot)
        markdown = _build_markdown(
            title,
            transcript,
            segments,
            minutes,
            file_id,
            created_at,
        )

        from plugins.notes.backend.schemas import NoteCreate
        from plugins.notes.backend import service as notes_service

        async with async_session() as db:
            note = await notes_service.create_note(
                db,
                user_id,
                NoteCreate(title=title[:200], content=markdown),
            )
            job = await db.get(MeetingMinutesJob, job_id)
            if job is None:
                return
            job.note_id = note.id
            job.minutes = minutes
            job.status = "done"
            job.finished_at = datetime.now()
            await db.flush()
            await db.commit()
    except Exception as exc:
        async with async_session() as db:
            job = await db.get(MeetingMinutesJob, job_id)
            if job is not None:
                job.status = "failed"
                job.error = str(exc)[:2000]
                job.finished_at = datetime.now()
                await db.flush()
                await db.commit()
        log.warning(f"[meetings] job {job_id} failed: {exc}")


def schedule_job(job_id: int) -> None:
    task = asyncio.create_task(_run_job(job_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def recover_pending_jobs() -> None:
    async with async_session() as db:
        rows = (
            await db.execute(
                select(MeetingMinutesJob.id).where(
                    MeetingMinutesJob.status.in_(
                        ["queued", "transcribing", "summarizing"]
                    )
                )
            )
        ).scalars().all()
    for job_id in rows:
        schedule_job(job_id)


async def delete_job(job_id: int, user_id: int, *, delete_audio: bool) -> bool:
    from plugins.files.backend import service as file_service
    from plugins.notes.backend import service as notes_service

    async with async_session() as db:
        job = (
            await db.execute(
                select(MeetingMinutesJob).where(
                    MeetingMinutesJob.id == job_id,
                    MeetingMinutesJob.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if job is None:
            return False
        note_id = job.note_id
        file_id = job.file_id
        if note_id:
            try:
                await notes_service.delete_note(db, user_id, note_id)
            except Exception:
                pass
        # Delete the job before its audio file; meeting_minutes_jobs.file_id
        # has a foreign key to files, so the reverse order violates the FK.
        await db.delete(job)
        await db.flush()
        if delete_audio:
            try:
                await file_service.permanent_delete(db, user_id, file_id)
            except Exception:
                pass
        await db.flush()
        await db.commit()
    return True
