from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from .schemas import MailAccountCreate, MailAccountUpdate, MailAccountResponse
from . import service as mail_service

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
