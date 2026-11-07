from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from core.auth.domain.models import User
from core.auth.domain.schemas import RegisterRequest
from core.auth.password import hash_password, verify_password
from core.auth.jwt import create_access_token, create_refresh_token, decode_refresh_token


async def _create_user(
    db: AsyncSession,
    *,
    username: str,
    email: str,
    password: str,
    is_admin: bool,
) -> User:
    existing = await db.execute(select(User).where(
        (User.username == username) | (User.email == email)
    ))
    if existing.scalar_one_or_none():
        raise ValueError("Username or email already exists")
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        is_admin=is_admin,
    )
    db.add(user)
    await db.flush()
    return user


async def register(db: AsyncSession, req: RegisterRequest) -> User:
    count_result = await db.execute(select(func.count(User.id)))
    is_first = (count_result.scalar() or 0) == 0
    return await _create_user(
        db,
        username=req.username,
        email=req.email,
        password=req.password,
        is_admin=is_first,
    )


async def admin_create_user(db: AsyncSession, req) -> User:
    return await _create_user(
        db,
        username=req.username,
        email=req.email,
        password=req.password,
        is_admin=bool(getattr(req, "is_admin", False)),
    )


async def login(db: AsyncSession, username: str, password: str) -> tuple[str, str]:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("Invalid username or password")
    if not user.is_active:
        raise ValueError("User is disabled")
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    return access_token, refresh_token


async def refresh_access_token(
    db: AsyncSession,
    refresh_token: str,
) -> tuple[str, str]:
    payload = decode_refresh_token(refresh_token)
    if not payload:
        raise ValueError("Invalid or expired refresh token")
    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("Invalid refresh token")
    try:
        user = await db.get(User, int(user_id))
    except (TypeError, ValueError):
        user = None
    if user is None or not user.is_active:
        raise ValueError("User disabled or not found")
    new_access = create_access_token({"sub": str(user.id)})
    new_refresh = create_refresh_token({"sub": str(user.id)})
    return new_access, new_refresh
