from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from .schemas import (
    MailAccountCreate,
    MailAccountUpdate,
    MailAccountResponse,
    MailAccountSyncResponse,
    MailEventCreate,
    MailEventResponse,
    MailMessageDetail,
    MailMessageResponse,
    MailSendRequest,
)
from . import service as mail_service
from . import sync as mail_sync
from .models import MailAccount, MailEvent, MailMessage

router = APIRouter(prefix="/api/plugins/mail", tags=["mail"])


class AiDraftRequest(BaseModel):
    tone: str = "professional"
    instructions: str | None = None
    bot_id: int | None = None


@router.get("/accounts", response_model=list[MailAccountResponse])
async def list_accounts(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    accounts = await mail_service.list_accounts(db, user["id"])
    return [MailAccountResponse.model_validate(a) for a in accounts]


@router.post("/accounts", response_model=MailAccountResponse, status_code=201)
async def create_account(
    req: MailAccountCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    acc = await mail_service.create_account(db, user["id"], req)
    return MailAccountResponse.model_validate(acc)


@router.put("/accounts/{account_id}", response_model=MailAccountResponse)
async def update_account(
    account_id: int,
    req: MailAccountUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    acc = await mail_service.update_account(db, user["id"], account_id, req)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    return MailAccountResponse.model_validate(acc)


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await mail_service.delete_account(db, user["id"], account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"message": "Account deleted"}


@router.get("/accounts/{account_id}/secret")
async def get_account_secret(
    account_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner-only password retrieval for legacy desktop IMAP use.

    The account list never includes passwords; clients must ask explicitly and
    must not cache the value in logs or shared storage.
    """
    password = await mail_service.get_account_secret(db, user["id"], account_id)
    if password is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"password": password}


@router.post("/accounts/{account_id}/sync", response_model=MailAccountSyncResponse)
async def sync_account(
    account_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pull new mail for one account right now (backend IMAP)."""
    exists = (await db.execute(
        select(MailAccount).where(
            MailAccount.id == account_id, MailAccount.user_id == user["id"]
        )
    )).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return await mail_sync.sync_account(account_id)


@router.post("/sync")
async def sync_due_mail(user: dict = Depends(get_current_user)):
    """Sync every due account for the current user."""
    from core.database.session import async_session

    async with async_session() as db:
        r = await db.execute(
            select(MailAccount.id).where(
                MailAccount.user_id == user["id"],
                MailAccount.sync_enabled == True,
            )
        )
        ids = [row[0] for row in r.all()]
    total = 0
    for account_id in ids:
        result = await mail_sync.sync_account(account_id)
        total += int(result.get("new") or 0)
    return {"accounts": len(ids), "new": total}


@router.get("/messages")
async def list_messages(
    account_id: int | None = Query(None),
    unread: bool = False,
    important: bool = False,
    starred: bool = False,
    folder: str = Query("inbox"),
    cursor: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from core.pagination import decode_int_cursor, encode_cursor

    cursor_id = decode_int_cursor(cursor)
    items, total = await mail_sync.list_messages(
        db, user["id"], account_id, unread, important, starred, page, page_size,
        folder=folder, cursor=cursor_id,
    )
    return {
        "items": [MailMessageResponse.model_validate(m) for m in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "next_cursor": encode_cursor(items[-1].id) if len(items) >= page_size else None,
    }


@router.post("/messages/send")
async def send_message(
    req: MailSendRequest,
    user: dict = Depends(get_current_user),
):
    from plugins.mail.backend.send import MailSendError, send_mail

    try:
        return await send_mail(
            user_id=user["id"],
            account_id=req.account_id,
            to=req.to,
            cc=req.cc,
            bcc=req.bcc,
            subject=req.subject,
            body=req.body,
            reply_to_id=req.reply_to_id,
            attachment_file_ids=req.attachment_file_ids,
        )
    except MailSendError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/messages/{message_id}", response_model=MailMessageDetail)
async def get_message(
    message_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    msg = (await db.execute(
        select(MailMessage).where(
            MailMessage.id == message_id, MailMessage.user_id == user["id"]
        )
    )).scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return msg


@router.post("/messages/{message_id}/ai-draft")
async def ai_draft(
    message_id: int,
    req: AiDraftRequest,
    user: dict = Depends(get_current_user),
):
    from core.bots.registry import get_active_bot, get_or_create_default_bot
    from core.skills.runtime import run_skill

    try:
        bot = (
            await get_active_bot(user["id"], req.bot_id)
            if req.bot_id
            else await get_or_create_default_bot(user["id"])
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Bot not found")
    try:
        result = await run_skill(
            user["id"],
            bot.id,
            "draft-reply",
            {
                "source": "mail",
                "message_id": message_id,
                "tone": req.tone,
                "instructions": req.instructions,
            },
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Message not found or empty")
    return result.get("output") or {}


@router.put("/messages/read-all")
async def mark_all_messages_read(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        update(MailMessage)
        .where(
            MailMessage.user_id == user["id"],
            MailMessage.read == False,  # noqa: E712
        )
        .values(read=True)
    )
    await db.flush()
    return {"updated": result.rowcount or 0}


@router.put("/messages/{message_id}/read")
async def mark_message_read(
    message_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    msg = (await db.execute(
        select(MailMessage).where(
            MailMessage.id == message_id, MailMessage.user_id == user["id"]
        )
    )).scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.read = True
    await db.flush()
    return {"message": "Read"}


@router.put("/messages/{message_id}/star")
async def star_message(
    message_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    msg = (await db.execute(
        select(MailMessage).where(
            MailMessage.id == message_id, MailMessage.user_id == user["id"]
        )
    )).scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.starred = not msg.starred
    await db.flush()
    return {"starred": msg.starred}


@router.post("/events", response_model=MailEventResponse, status_code=201)
async def report_mail_event(
    req: MailEventCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept a newly-received email reported by the desktop client.

    Deduplicated by (account_id, uid). Records an activity event, indexes the
    content for semantic search, and pushes a notification so the AI and the
    user can react to important mail.
    """
    existing = None
    if req.uid and req.account_id:
        r = await db.execute(
            select(MailEvent).where(
                MailEvent.user_id == user["id"],
                MailEvent.account_id == req.account_id,
                MailEvent.uid == req.uid,
            )
        )
        existing = r.scalar_one_or_none()
    if existing:
        return MailEventResponse.model_validate(existing)

    event = MailEvent(
        user_id=user["id"],
        account_id=req.account_id,
        uid=req.uid,
        subject=req.subject,
        from_address=req.from_address,
        date=req.date,
        preview=req.preview,
        content=req.content,
        important=req.important,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)

    # Record activity for the event stream
    try:
        from core.events.recorder import record_event
        await record_event(
            db, user["id"], "mail.received", "email", event.id,
            f"新邮件: {event.subject or ''}",
            {
                "message_id": event.id,
                "from": event.from_address,
                "subject": event.subject,
                "date": event.date,
                "important": event.important,
                "preview": (event.preview or event.content or "")[:300],
            },
        )
    except Exception:
        pass

    # Index for semantic search (AI can query via unified_search)
    try:
        from core.ai.indexer import index_content
        content_src = (event.preview or "") + "\n" + (event.content or "")
        await index_content(
            user_id=user["id"],
            source_type="email",
            source_id=event.id,
            title=event.subject or "(无主题)",
            content=content_src[:8000],
            metadata={"from": event.from_address or "", "link": "/plugins/mail"},
        )
    except Exception:
        pass

    # Importance is decided by a periodic LLM scan of events (see scheduler).
    await db.commit()
    return MailEventResponse.model_validate(event)


@router.get("/events", response_model=list[MailEventResponse])
async def list_mail_events(
    limit: int = 30,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        select(MailEvent).where(MailEvent.user_id == user["id"])
        .order_by(MailEvent.created_at.desc()).limit(limit)
    )
    return [MailEventResponse.model_validate(e) for e in r.scalars().all()]
