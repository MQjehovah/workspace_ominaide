"""Backend-first mail ingestion.

The backend pulls IMAP incrementally, stores messages, then analyses each new
message with the LLM (summary + importance + suggested actions). Desktop and
web clients only read the API.
"""

from __future__ import annotations

import asyncio
import email
import imaplib
import json
import re
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime

from core.config.settings import settings

MAX_BODY_CHARS = 20000


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        parts = decode_header(value)
        out = []
        for part, charset in parts:
            if isinstance(part, bytes):
                out.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                out.append(part)
        return "".join(out).strip()
    except Exception:
        return str(value).strip()


def _decode_bytes(raw: bytes, charset: str | None) -> str:
    for enc in (charset, "utf-8", "gb18030", "latin-1"):
        if not enc:
            continue
        try:
            return raw.decode(enc, errors="replace")
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def _extract_body(msg) -> tuple[str, bool]:
    """Return (plain-text body, has_attachments)."""
    plain: list[str] = []
    html: list[str] = []
    has_attachments = False

    if msg.is_multipart():
        for part in msg.walk():
            disposition = (part.get("Content-Disposition") or "").lower()
            filename = part.get_filename()
            if filename or "attachment" in disposition:
                has_attachments = True
                continue
            ctype = part.get_content_type()
            if ctype not in ("text/plain", "text/html"):
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            text = _decode_bytes(payload, part.get_content_charset())
            (plain if ctype == "text/plain" else html).append(text)
    else:
        payload = msg.get_payload(decode=True)
        if payload is not None:
            text = _decode_bytes(payload, msg.get_content_charset())
            (plain if msg.get_content_type() == "text/plain" else html).append(text)

    if plain:
        return "\n".join(plain).strip(), has_attachments
    if html:
        try:
            from bs4 import BeautifulSoup

            text = BeautifulSoup("\n".join(html), "html.parser").get_text("\n")
        except Exception:
            text = re.sub(r"<[^>]+>", " ", "\n".join(html))
        return re.sub(r"\n{3,}", "\n\n", text).strip(), has_attachments
    return "", has_attachments


def _parse_message(raw: bytes, uid: int, uidvalidity: int | None) -> dict:
    msg = email.message_from_bytes(raw)
    body, has_attachments = _extract_body(msg)
    body = body[:MAX_BODY_CHARS]
    preview = re.sub(r"\s+", " ", body)[:300]
    date = None
    try:
        if msg.get("Date"):
            parsed = parsedate_to_datetime(msg.get("Date"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            date = parsed
    except Exception:
        date = None
    return {
        "uid": uid,
        "uidvalidity": uidvalidity,
        "message_id": (msg.get("Message-ID") or "").strip()[:500] or None,
        "subject": _decode_header(msg.get("Subject"))[:500],
        "from_address": _decode_header(msg.get("From"))[:500],
        "to_addresses": _decode_header(msg.get("To"))[:2000],
        "date": date,
        "preview": preview,
        "content": body,
        "has_attachments": has_attachments,
    }


def fetch_imap_messages(account: dict, password: str, limit: int = 20) -> tuple[list[dict], int | None]:
    """Incrementally fetch new messages for one account (blocking; call in a thread)."""
    host = account["imap_host"]
    port = int(account.get("imap_port") or 993)
    tls = bool(account.get("imap_tls", True))
    folder = account.get("folder") or "INBOX"
    last_uid = int(account.get("last_uid") or 0)
    known_validity = account.get("uidvalidity")

    conn = imaplib.IMAP4_SSL(host, port) if tls else imaplib.IMAP4(host, port)
    try:
        conn.login(account["username"], password)
        typ, _ = conn.select(folder, readonly=True)
        if typ != "OK":
            raise RuntimeError(f"无法打开邮件文件夹 {folder}")

        uidvalidity = None
        try:
            typ, data = conn.response("UIDVALIDITY")
            if data and data[0]:
                uidvalidity = int(data[0])
        except Exception:
            uidvalidity = None

        # A changed UIDVALIDITY means earlier UIDs are meaningless.
        if uidvalidity is not None and known_validity is not None and uidvalidity != known_validity:
            last_uid = 0

        start = last_uid + 1
        typ, data = conn.uid("search", None, f"UID {start}:*")
        if typ != "OK" or not data or not data[0]:
            return [], uidvalidity
        uids = sorted({int(x) for x in data[0].split() if x.isdigit() and int(x) > last_uid})
        uids = uids[:limit]

        out: list[dict] = []
        for uid in uids:
            typ, payload = conn.uid("fetch", str(uid), "(BODY.PEEK[])")
            if typ != "OK" or not payload:
                continue
            raw = None
            for item in payload:
                if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
                    raw = bytes(item[1])
                    break
            if not raw:
                continue
            out.append(_parse_message(raw, uid, uidvalidity))
        return out, uidvalidity
    finally:
        try:
            conn.logout()
        except Exception:
            pass


async def list_messages(
    db,
    user_id: int,
    account_id: int | None = None,
    unread: bool = False,
    important: bool = False,
    starred: bool = False,
    page: int = 1,
    page_size: int = 20,
):
    from sqlalchemy import func, select
    from plugins.mail.backend.models import MailMessage

    q = select(MailMessage).where(MailMessage.user_id == user_id)
    if account_id:
        q = q.where(MailMessage.account_id == account_id)
    if unread:
        q = q.where(MailMessage.read == False)
    if important:
        q = q.where(MailMessage.important == True)
    if starred:
        q = q.where(MailMessage.starred == True)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    r = await db.execute(
        q.order_by(MailMessage.date.desc(), MailMessage.id.desc())
        .offset(max(0, (page - 1) * page_size))
        .limit(page_size)
    )
    return list(r.scalars().all()), total


async def sync_account(account_id: int, limit: int | None = None) -> dict:
    """Pull new messages for one account and analyse them."""
    from sqlalchemy import select
    from core.database.session import async_session
    from core.crypto import decrypt_secret
    from plugins.mail.backend.models import MailAccount, MailMessage

    max_messages = limit or settings.mail_max_per_sync

    async with async_session() as db:
        account = (await db.execute(
            select(MailAccount).where(MailAccount.id == account_id)
        )).scalar_one_or_none()
        if account is None or not account.sync_enabled:
            return {"account_id": account_id, "new": 0, "skipped": True}
        account_data = {
            "imap_host": account.imap_host,
            "imap_port": account.imap_port,
            "imap_tls": account.imap_tls,
            "username": account.username,
            "folder": account.folder or "INBOX",
            "last_uid": account.last_uid or 0,
            "uidvalidity": account.uidvalidity,
        }
        user_id = account.user_id
        try:
            password = decrypt_secret(account.password)
            messages, uidvalidity = await asyncio.to_thread(
                fetch_imap_messages, account_data, password, max_messages
            )
        except Exception as e:
            account.sync_error = str(e)[:1000]
            account.last_sync_at = datetime.utcnow()
            await db.commit()
            return {"account_id": account_id, "new": 0, "error": str(e)[:300]}

        new_ids: list[int] = []
        max_uid = account.last_uid or 0
        for item in messages:
            exists = (await db.execute(
                select(MailMessage).where(
                    MailMessage.account_id == account.id,
                    MailMessage.uid == item["uid"],
                )
            )).scalar_one_or_none()
            if exists is not None:
                max_uid = max(max_uid, item["uid"])
                continue
            msg = MailMessage(
                user_id=user_id,
                account_id=account.id,
                uid=item["uid"],
                uidvalidity=item.get("uidvalidity"),
                message_id=item.get("message_id"),
                subject=item.get("subject"),
                from_address=item.get("from_address"),
                to_addresses=item.get("to_addresses"),
                date=item.get("date"),
                preview=item.get("preview"),
                content=item.get("content"),
                has_attachments=bool(item.get("has_attachments")),
            )
            db.add(msg)
            await db.flush()
            new_ids.append(msg.id)
            max_uid = max(max_uid, item["uid"])

        account.last_uid = max_uid
        if uidvalidity is not None:
            account.uidvalidity = uidvalidity
        account.last_sync_at = datetime.utcnow()
        account.sync_error = None
        await db.commit()

    for message_id in new_ids:
        await _after_ingest(user_id, message_id)

    return {"account_id": account_id, "new": len(new_ids), "fetched": len(messages)}


async def _after_ingest(user_id: int, message_id: int) -> None:
    """Emit mail.received; any LLM analysis is a Bot routine's job.

    The message row is left untouched — routines decide importance and whether
    to notify, but never rewrite the mailbox data.
    """
    from sqlalchemy import select
    from core.database.session import async_session
    from plugins.mail.backend.models import MailMessage

    async with async_session() as db:
        msg = (await db.execute(
            select(MailMessage).where(MailMessage.id == message_id)
        )).scalar_one_or_none()
        if msg is None:
            return
        try:
            from core.events.recorder import record_event

            await record_event(
                db, user_id, "mail.received", "email", msg.id,
                f"新邮件: {msg.subject or ''}",
                {
                    "message_id": msg.id,
                    "from": msg.from_address or "",
                    "to": msg.to_addresses or "",
                    "subject": msg.subject or "",
                    "date": str(msg.date or ""),
                    "preview": (msg.preview or "")[:1000],
                    "content": (msg.content or msg.preview or "")[:6000],
                },
            )
        except Exception:
            pass
        try:
            from core.ai.indexer import index_content

            await index_content(
                user_id=user_id,
                source_type="email",
                source_id=msg.id,
                title=msg.subject or "(无主题)",
                content=((msg.preview or "") + "\n" + (msg.content or ""))[:8000],
                metadata={"from": msg.from_address or "", "link": "/mail"},
            )
        except Exception:
            pass
        await db.commit()


async def sync_due_accounts(interval_seconds: int) -> dict:
    """Sync accounts whose last sync is older than the interval."""
    from datetime import timedelta
    from sqlalchemy import or_, select
    from core.database.session import async_session
    from plugins.mail.backend.models import MailAccount

    cutoff = datetime.utcnow() - timedelta(seconds=interval_seconds)
    async with async_session() as db:
        r = await db.execute(
            select(MailAccount.id).where(
                MailAccount.sync_enabled == True,
                or_(MailAccount.last_sync_at == None, MailAccount.last_sync_at < cutoff),
            )
        )
        ids = [row[0] for row in r.all()]

    total = 0
    for account_id in ids:
        result = await sync_account(account_id)
        total += int(result.get("new") or 0)
    return {"accounts": len(ids), "new": total}
