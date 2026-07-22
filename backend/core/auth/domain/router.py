from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.auth.domain.schemas import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest, UserResponse, AdminUserResponse, ToggleActiveRequest
from core.auth.domain.service import register, login, refresh_access_token
from core.database.session import get_db
from core.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_endpoint(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await register(db, req)
        return {"message": "User created", "user_id": user.id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login_endpoint(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        access_token, refresh_token = await login(db, req.username, req.password)
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/refresh", response_model=TokenResponse)
async def refresh_endpoint(req: RefreshRequest):
    try:
        access_token, refresh_token = await refresh_access_token(req.refresh_token)
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.get("/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from core.auth.domain.models import User as UserModel
    result = await db.execute(select(UserModel).where(UserModel.id == user["id"]))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(u)


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from core.auth.domain.models import User as UserModel
    result = await db.execute(select(UserModel).order_by(UserModel.id))
    users = result.scalars().all()
    return [AdminUserResponse(
        id=u.id,
        username=u.username,
        email=u.email,
        is_active=u.is_active,
        created_at=str(u.created_at) if u.created_at else None
    ) for u in users]


@router.put("/users/{user_id}/toggle-active")
async def toggle_user_active(user_id: int, req: ToggleActiveRequest, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from core.auth.domain.models import User as UserModel
    result = await db.execute(select(UserModel).where(UserModel.id == user_id))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.is_active = req.is_active
    await db.flush()
    return {"id": u.id, "is_active": u.is_active}
