"""SMTP sending for the mail plugin.

Runs the blocking smtplib call in a worker thread. Attachments come from the
existing MinIO-backed file records, so mobile uploads them once through the
normal file pipeline.
"""

from __future__ import annotations

import asyncio
import smtplib
import uuid
from datetime import datetime
from email.message import EmailMessage

from sqlalchemy import func, select

from core.crypto import decrypt_secret
from core.database.session import async_session


class MailSendError(RuntimeError):
    pass


def _addresses(value: list[str] | None) -> list[str]:
    return [str(item).strip() for item in (value or []) if str(item).strip()]


def _smtp_send(
    account,
    password: str,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    body: str,
    reply_headers: dict[str, str],
    attachments: list[tuple[str, str, bytes]],
) -> str:
    domain = (account.email or "omniaide.local").split("@")[-1]
    message_id = f"<{uuid.uuid4().hex}@{domain}>"

    message = EmailMessage()
    message["From"] = account.email
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    message["Message-ID"] = message_id
    for key, value in reply_headers.items():
        if value:
            message[key] = value
    message.set_content(body or "")

    for name, mime, data in attachments:
        maintype, _, subtype = (mime or "application/octet-stream").partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        message.add_attachment(
            data,
            maintype=maintype,
            subtype=subtype,
            filename=name or "attachment",
        )

    recipients = to + cc + bcc
    host = account.smtp_host
    port = int(account.smtp_port or 465)
    timeout = 45
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=timeout)
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
            if account.smtp_tls:
                server.starttls()
        with server:
            server.login(account.username, password)
            server.send_message(message, to_addrs=recipients)
    except Exception as exc:
        raise MailSendError(str(exc)) from exc
    return message_id


async def send_mail(
    *,
    user_id: int,
    account_id: int | None,
    to: list[str],
    cc: list[str] | None,
    bcc: list[str] | None,
    subject: str,
    body: str,
    reply_to_id: int | None = None,
    attachment_file_ids: list[int] | None = None,
) -> dict:
    from plugins.files.backend.models import File
    from plugins.mail.backend.models import MailAccount, MailMessage

    to = _addresses(to)
    cc = _addresses(cc)
    bcc = _addresses(bcc)
    if not to:
        raise MailSendError("至少需要一个收件人")
    if not subject.strip():
        raise MailSendError("主题不能为空")

    async with async_session() as db:
        account_query = select(MailAccount).where(MailAccount.user_id == user_id)
        if account_id:
            account_query = account_query.where(MailAccount.id == account_id)
        account = (
            await db.execute(account_query.order_by(MailAccount.id).limit(1))
        ).scalar_one_or_none()
        if account is None:
            raise MailSendError("还没有配置邮箱账号")

        original = None
        if reply_to_id:
            original = (
                await db.execute(
                    select(MailMessage).where(
                        MailMessage.id == reply_to_id,
                        MailMessage.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()

        attachments: list[tuple[str, str, bytes]] = []
        file_meta: list[dict] = []
        if attachment_file_ids:
            from core.minio.client import minio_client

            rows = (
                await db.execute(
                    select(File).where(
                        File.id.in_(attachment_file_ids),
                        File.user_id == user_id,
                        File.status == "active",
                    )
                )
            ).scalars().all()
            by_id = {row.id: row for row in rows}
            for file_id in attachment_file_ids:
                record = by_id.get(file_id)
                if record is None or minio_client is None:
                    continue
                try:
                    response = minio_client.get_object(
                        record.bucket, record.object_key
                    )
                    data = response.read()
                    response.close()
                except Exception:
                    continue
                mime = record.mime_type or "application/octet-stream"
                attachments.append((record.original_name, mime, data))
                file_meta.append(
                    {
                        "file_id": record.id,
                        "name": record.original_name,
                        "size": record.size,
                        "mime_type": record.mime_type,
                    }
                )

        password = decrypt_secret(account.password)
        reply_headers = {}
        if original is not None:
            original_message_id = original.message_id
            if original_message_id:
                reply_headers["In-Reply-To"] = original_message_id
                reply_headers["References"] = original_message_id
        message_id = await asyncio.to_thread(
            _smtp_send,
            account,
            password,
            to,
            cc,
            bcc,
            subject.strip(),
            body,
            reply_headers,
            attachments,
        )

        now = datetime.now()
        min_uid = (
            await db.execute(
                select(func.min(MailMessage.uid)).where(
                    MailMessage.account_id == account.id
                )
            )
        ).scalar()
        uid = (min_uid - 1) if min_uid is not None else -1
        thread_id = None
        if original is not None:
            thread_id = original.thread_id or original.message_id
        thread_id = thread_id or message_id

        record = MailMessage(
            user_id=user_id,
            account_id=account.id,
            uid=uid,
            message_id=message_id,
            subject=subject.strip(),
            from_address=account.email,
            to_addresses=", ".join(to),
            cc_addresses=", ".join(cc) or None,
            bcc_addresses=", ".join(bcc) or None,
            date=now,
            preview=(body or "")[:300],
            content=body,
            important=False,
            read=True,
            folder="sent",
            direction="outbound",
            in_reply_to=reply_headers.get("In-Reply-To"),
            thread_id=thread_id,
            attachments=file_meta or None,
            has_attachments=bool(file_meta),
            sent_at=now,
        )
        db.add(record)
        await db.flush()
        await db.refresh(record)
        await db.commit()
        return {
            "id": record.id,
            "message_id": message_id,
            "thread_id": thread_id,
            "to": to,
            "cc": cc,
            "bcc": bcc,
            "subject": subject,
            "sent_at": now.isoformat(),
            "attachments": file_meta,
        }
