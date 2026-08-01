from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from .schemas import MailAccountCreate, MailAccountUpdate, MailAccountResponse, MailEventCreate, MailEventResponse
from . import service as mail_service
from .models import MailEvent

router = APIRouter(prefix="/api/plugins/mail", tags=["mail"])


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
            {"from": event.from_address, "date": event.date, "important": event.important},
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
