from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from .models import MailAccount
from .schemas import MailAccountCreate, MailAccountUpdate


async def list_accounts(db: AsyncSession, user_id: int) -> list[MailAccount]:
    result = await db.execute(
        select(MailAccount).where(MailAccount.user_id == user_id)
        .order_by(MailAccount.id)
    )
    return list(result.scalars().all())


async def create_account(db: AsyncSession, user_id: int, req: MailAccountCreate) -> MailAccount:
    acc = MailAccount(
        user_id=user_id,
        name=req.name,
        email=req.email,
        imap_host=req.imap_host,
        imap_port=req.imap_port,
        imap_tls=req.imap_tls,
        smtp_host=req.smtp_host,
        smtp_port=req.smtp_port,
        smtp_tls=req.smtp_tls,
        username=req.username,
        password=req.password,
    )
    db.add(acc)
    await db.flush()
    await db.refresh(acc)
    return acc


async def update_account(db: AsyncSession, user_id: int, account_id: int, req: MailAccountUpdate) -> MailAccount | None:
    result = await db.execute(
        select(MailAccount).where(MailAccount.id == account_id, MailAccount.user_id == user_id)
    )
    acc = result.scalar_one_or_none()
    if not acc:
        return None
    if req.name is not None:
        acc.name = req.name
    if req.email is not None:
        acc.email = req.email
    if req.imap_host is not None:
        acc.imap_host = req.imap_host
    if req.imap_port is not None:
        acc.imap_port = req.imap_port
    if req.imap_tls is not None:
        acc.imap_tls = req.imap_tls
    if req.smtp_host is not None:
        acc.smtp_host = req.smtp_host
    if req.smtp_port is not None:
        acc.smtp_port = req.smtp_port
    if req.smtp_tls is not None:
        acc.smtp_tls = req.smtp_tls
    if req.username is not None:
        acc.username = req.username
    if req.password is not None:
        acc.password = req.password
    await db.flush()
    await db.refresh(acc)
    return acc


async def delete_account(db: AsyncSession, user_id: int, account_id: int) -> bool:
    result = await db.execute(
        select(MailAccount).where(MailAccount.id == account_id, MailAccount.user_id == user_id)
    )
    acc = result.scalar_one_or_none()
    if not acc:
        return False
    await db.delete(acc)
    await db.flush()
    return True
