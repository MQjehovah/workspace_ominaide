"""People index: identity resolution, mentions, timeline and commitments."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select

from core.database.session import async_session
from core.logging import get_logger
from ai.memory.models import MemoryEdge, MemoryRecord
from ai.memory.people.models import Person, PersonMention

log = get_logger(__name__)

_TITLES = ("先生", "女士", "老师", "经理", "总", "博士", "教授")
_PUNCT = re.compile(r"[\s,，.。;；:：、()（）<>《》\"'`]+")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+")


def normalize_name(name: str) -> str:
    value = (name or "").strip().lower()
    value = _PUNCT.sub("", value)
    for title in _TITLES:
        if value.endswith(title) and len(value) > len(title) + 1:
            value = value[: -len(title)]
    return value[:200]


def parse_address(value: str) -> tuple[str, str | None]:
    raw = (value or "").strip()
    match = re.match(r"^(.*?)\s*<([^>]+)>$", raw)
    if match:
        name = match.group(1).strip().strip('"')
        email = match.group(2).strip().lower()
        return name or email.split("@")[0], email
    if _EMAIL.fullmatch(raw):
        return raw.split("@")[0], raw.lower()
    return raw, None


def _out_person(person: Person, mention_count: int = 0, last_at: datetime | None = None) -> dict:
    return {
        "id": person.id,
        "display_name": person.display_name,
        "emails": person.emails or [],
        "aliases": person.aliases or [],
        "company": person.company,
        "notes": person.notes,
        "mention_count": mention_count,
        "last_interaction": last_at.isoformat() if last_at else None,
    }


def _link(source_type: str, source_id: int) -> str:
    return {
        "mail": f"/mail?id={source_id}",
        "event": f"/schedule?event={source_id}",
        "meeting": f"/captures?meeting={source_id}",
        "note": f"/notes?id={source_id}",
        "capture": f"/captures/{source_id}",
        "memory": f"/insights?memory={source_id}",
    }.get(source_type, "/")


async def upsert_person(
    user_id: int,
    name: str,
    *,
    email: str | None = None,
    alias: str | None = None,
) -> Person:
    display = (name or email or "未知联系人").strip()[:200]
    normalized = normalize_name(display)
    email = (email or "").strip().lower() or None
    async with async_session() as db:
        persons = list((await db.execute(
            select(Person).where(Person.user_id == user_id)
        )).scalars().all())
        found = None
        for person in persons:
            emails = [str(x).lower() for x in (person.emails or [])]
            aliases = [normalize_name(str(x)) for x in (person.aliases or [])]
            if email and email in emails:
                found = person
                break
            if normalized and (person.normalized_name == normalized or normalized in aliases):
                found = person
                break
        if found is None:
            found = Person(
                user_id=user_id,
                display_name=display,
                normalized_name=normalized,
                emails=[email] if email else [],
                aliases=[alias] if alias else [],
            )
            db.add(found)
        else:
            changed = False
            if email and email not in [str(x).lower() for x in (found.emails or [])]:
                found.emails = [*(found.emails or []), email]
                changed = True
            if alias and alias not in (found.aliases or []):
                found.aliases = [*(found.aliases or []), alias]
                changed = True
            if display and len(display) > len(found.display_name or ""):
                found.display_name = display
                changed = True
            if changed:
                found.normalized_name = normalize_name(found.display_name)
        await db.commit()
        await db.refresh(found)
        return found


async def add_mention(
    user_id: int,
    person_id: int,
    *,
    source_type: str,
    source_id: int,
    title: str | None = None,
    snippet: str | None = None,
    role: str = "mention",
    occurred_at: datetime | None = None,
    meta: dict | None = None,
) -> None:
    async with async_session() as db:
        existing = (
            await db.execute(
                select(PersonMention).where(
                    PersonMention.person_id == person_id,
                    PersonMention.source_type == source_type,
                    PersonMention.source_id == source_id,
                    PersonMention.role == role,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return
        db.add(PersonMention(
            person_id=person_id,
            user_id=user_id,
            source_type=source_type,
            source_id=source_id,
            title=(title or "")[:500] or None,
            snippet=(snippet or "")[:4000] or None,
            role=role,
            occurred_at=occurred_at,
            meta=meta,
        ))
        await db.commit()


async def mention_person(
    user_id: int,
    name: str,
    *,
    email: str | None = None,
    source_type: str,
    source_id: int,
    title: str | None = None,
    snippet: str | None = None,
    role: str = "mention",
    occurred_at: datetime | None = None,
    meta: dict | None = None,
) -> dict:
    person = await upsert_person(user_id, name, email=email)
    await add_mention(
        user_id, person.id,
        source_type=source_type, source_id=source_id,
        title=title, snippet=snippet, role=role,
        occurred_at=occurred_at, meta=meta,
    )
    return {"id": person.id, "name": person.display_name}


async def list_people(user_id: int) -> list[dict]:
    async with async_session() as db:
        people = list((await db.execute(
            select(Person).where(Person.user_id == user_id).order_by(Person.display_name)
        )).scalars().all())
        stats = dict((await db.execute(
            select(PersonMention.person_id, func.count(PersonMention.id))
            .where(PersonMention.user_id == user_id)
            .group_by(PersonMention.person_id)
        )).all())
        last = dict((await db.execute(
            select(PersonMention.person_id, func.max(PersonMention.occurred_at))
            .where(PersonMention.user_id == user_id)
            .group_by(PersonMention.person_id)
        )).all())
    return [_out_person(p, stats.get(p.id, 0), last.get(p.id)) for p in people]


async def get_person(user_id: int, person_id: int) -> Person | None:
    async with async_session() as db:
        return (
            await db.execute(
                select(Person).where(Person.id == person_id, Person.user_id == user_id)
            )
        ).scalar_one_or_none()


async def update_person(user_id: int, person_id: int, data: dict) -> Person | None:
    async with async_session() as db:
        person = (
            await db.execute(
                select(Person).where(Person.id == person_id, Person.user_id == user_id)
            )
        ).scalar_one_or_none()
        if person is None:
            return None
        for key in ("display_name", "company", "notes"):
            if key in data and data[key] is not None:
                setattr(person, key, data[key])
        if "aliases" in data:
            person.aliases = data["aliases"] or []
        person.normalized_name = normalize_name(person.display_name)
        await db.commit()
        await db.refresh(person)
        return person


async def timeline(user_id: int, person_id: int, limit: int = 100) -> list[dict]:
    async with async_session() as db:
        rows = list((await db.execute(
            select(PersonMention).where(
                PersonMention.user_id == user_id,
                PersonMention.person_id == person_id,
            ).order_by(
                PersonMention.occurred_at.desc().nullslast(),
                PersonMention.id.desc(),
            ).limit(min(max(limit, 1), 300))
        )).scalars().all())
    return [
        {
            "id": row.id,
            "type": row.source_type,
            "source_id": row.source_id,
            "title": row.title,
            "snippet": row.snippet,
            "role": row.role,
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
            "link": _link(row.source_type, row.source_id),
            "meta": row.meta or {},
        }
        for row in rows
    ]


async def commitments(user_id: int, person_id: int) -> list[dict]:
    person = await get_person(user_id, person_id)
    if person is None:
        return []
    names = {person.display_name, *(person.aliases or [])}
    async with async_session() as db:
        rows = list((await db.execute(
            select(MemoryRecord, MemoryEdge)
            .join(MemoryEdge, MemoryEdge.memory_id == MemoryRecord.id)
            .where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.kind == "commitment",
                MemoryRecord.status == "active",
                MemoryEdge.target_type == "person",
                MemoryEdge.target_name.in_(names),
            ).order_by(MemoryRecord.created_at.desc()).limit(100)
        )).all())
    return [
        {
            "id": record.id,
            "content": record.content,
            "confidence": record.confidence,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "status": record.status,
        }
        for record, _edge in rows
    ]


async def follow_ups(user_id: int) -> dict:
    async with async_session() as db:
        rows = list((await db.execute(
            select(MemoryRecord).where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.kind == "commitment",
                MemoryRecord.status == "active",
            ).order_by(MemoryRecord.created_at.desc()).limit(100)
        )).scalars().all())
    cutoff = datetime.now() - timedelta(days=30)
    async with async_session() as db:
        people = list((await db.execute(
            select(Person).where(Person.user_id == user_id)
        )).scalars().all())
        last = dict((await db.execute(
            select(PersonMention.person_id, func.max(PersonMention.occurred_at))
            .where(PersonMention.user_id == user_id)
            .group_by(PersonMention.person_id)
        )).all())
    stale = [
        _out_person(p, 0, last.get(p.id))
        for p in people
        if last.get(p.id) is None or last[p.id] < cutoff
    ]
    return {
        "commitments": [
            {
                "id": r.id, "content": r.content,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "stale_people": stale,
    }


async def merge_people(user_id: int, primary_id: int, duplicate_id: int) -> bool:
    if primary_id == duplicate_id:
        return False
    async with async_session() as db:
        primary = await db.get(Person, primary_id)
        duplicate = await db.get(Person, duplicate_id)
        if (
            primary is None or duplicate is None
            or primary.user_id != user_id or duplicate.user_id != user_id
        ):
            return False
        await db.execute(
            PersonMention.__table__.update()
            .where(PersonMention.person_id == duplicate_id)
            .values(person_id=primary_id)
        )
        emails = list(dict.fromkeys([*(primary.emails or []), *(duplicate.emails or [])]))
        aliases = list(dict.fromkeys([
            *(primary.aliases or []), duplicate.display_name, *(duplicate.aliases or []),
        ]))
        primary.emails = emails
        primary.aliases = [a for a in aliases if a and a != primary.display_name]
        await db.delete(duplicate)
        await db.commit()
        return True


async def backfill_user(user_id: int) -> dict:
    """Rebuild the people index for one user from existing records."""
    from plugins.meetings.backend.models import MeetingMinutesJob
    from ai.memory.models import MemoryRecord
    from plugins.files.backend.models import File
    from plugins.mail.backend.models import MailMessage
    from plugins.notes.backend.models import PluginNote
    from plugins.schedule.backend.models import Event

    counts = {"people": 0, "mentions": 0}

    async with async_session() as db:
        profile = None
        from core.auth.domain.models import UserProfile
        profile = (await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )).scalar_one_or_none()
        contacts = []
        if profile and profile.contacts:
            import json
            try:
                contacts = json.loads(profile.contacts)
            except Exception:
                contacts = []
        for contact in contacts:
            if isinstance(contact, dict) and contact.get("name"):
                await upsert_person(user_id, contact["name"], alias=contact.get("relation"))
                counts["people"] += 1

        mails = list((await db.execute(
            select(MailMessage).where(MailMessage.user_id == user_id)
        )).scalars().all())
        for mail in mails:
            name, email = parse_address(mail.from_address or "")
            if name:
                await mention_person(
                    user_id, name, email=email, source_type="mail", source_id=mail.id,
                    title=mail.subject, snippet=mail.preview or mail.content,
                    role="from", occurred_at=mail.date,
                )
                counts["mentions"] += 1

        events = list((await db.execute(
            select(Event).where(Event.user_id == user_id)
        )).scalars().all())
        for event in events:
            for attendee in (event.external_meta or {}).get("attendees") or []:
                name = attendee.get("name") if isinstance(attendee, dict) else None
                if name:
                    await mention_person(
                        user_id, name, source_type="event", source_id=event.id,
                        title=event.title, role="attendee", occurred_at=event.start_time,
                    )
                    counts["mentions"] += 1

        captures = []
        try:
            from plugins.captures.backend.models import QuickCapture
            captures = list((await db.execute(
                select(QuickCapture).where(QuickCapture.user_id == user_id)
            )).scalars().all())
        except Exception:
            pass
        for capture in captures:
            for name in (capture.people or []):
                if name:
                    await mention_person(
                        user_id, str(name), source_type="capture", source_id=capture.id,
                        title=capture.title, snippet=capture.summary,
                        occurred_at=capture.created_at,
                    )
                    counts["mentions"] += 1

        people = list((await db.execute(
            select(Person).where(Person.user_id == user_id)
        )).scalars().all())

        notes = list((await db.execute(
            select(PluginNote).where(PluginNote.user_id == user_id)
        )).scalars().all())
        for note in notes:
            text = f"{note.title or ''}\n{note.content or ''}"
            for person in people:
                if person.display_name and person.display_name in text:
                    await mention_person(
                        user_id, person.display_name, source_type="note", source_id=note.id,
                        title=note.title, snippet=text[:400],
                        occurred_at=note.updated_at,
                    )
                    counts["mentions"] += 1

        meetings = list((await db.execute(
            select(MeetingMinutesJob).where(MeetingMinutesJob.user_id == user_id)
        )).scalars().all())
        for meeting in meetings:
            text = " ".join([
                str(meeting.title or ""),
                str(meeting.transcript or ""),
                str(meeting.minutes or ""),
            ])
            for person in people:
                if person.display_name and person.display_name in text:
                    await mention_person(
                        user_id, person.display_name, source_type="meeting",
                        source_id=meeting.id, title=meeting.title,
                        snippet=text[:400], occurred_at=meeting.created_at,
                    )
                    counts["mentions"] += 1

        memories = list((await db.execute(
            select(MemoryRecord).where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.status == "active",
                MemoryRecord.kind.in_(("relationship", "commitment")),
            )
        )).scalars().all())
        for memory in memories:
            for person in people:
                if person.display_name and person.display_name in (memory.content or ""):
                    await mention_person(
                        user_id, person.display_name, source_type="memory",
                        source_id=memory.id, title=memory.kind,
                        snippet=memory.content, role=memory.kind,
                        occurred_at=memory.created_at,
                    )
                    counts["mentions"] += 1
                    try:
                        from ai.memory.models import MemoryEdge
                        existing = (await db.execute(
                            select(MemoryEdge).where(
                                MemoryEdge.user_id == user_id,
                                MemoryEdge.memory_id == memory.id,
                                MemoryEdge.target_type == "person",
                                MemoryEdge.target_name == person.display_name,
                            )
                        )).scalar_one_or_none()
                        if existing is None:
                            db.add(MemoryEdge(
                                user_id=user_id, memory_id=memory.id,
                                target_type="person", target_id=person.id,
                                target_name=person.display_name,
                                relation="mentions",
                            ))
                            await db.commit()
                    except Exception:
                        pass

    return counts
