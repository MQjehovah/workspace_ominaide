from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.auth.domain.models import User
from core.auth.domain.schemas import RegisterRequest
from core.auth.password import hash_password, verify_password
from core.auth.jwt import create_access_token


async def register(db: AsyncSession, req: RegisterRequest) -> User:
    existing = await db.execute(select(User).where(
        (User.username == req.username) | (User.email == req.email)
    ))
    if existing.scalar_one_or_none():
        raise ValueError("Username or email already exists")
    user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
    )
    db.add(user)
    await db.flush()
    return user


async def login(db: AsyncSession, username: str, password: str) -> str:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("Invalid username or password")
    return create_access_token({"sub": str(user.id)})
