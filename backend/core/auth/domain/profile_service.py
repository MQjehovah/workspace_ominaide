import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.auth.domain.models import UserProfile
from core.auth.domain.schemas import UserProfileUpdate


async def get_or_create_profile(db: AsyncSession, user_id: int, username: str) -> UserProfile:
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = UserProfile(user_id=user_id, name=username)
        db.add(profile)
        await db.flush()
    return profile


async def update_profile(db: AsyncSession, user_id: int, data: UserProfileUpdate) -> UserProfile:
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
    if data.name is not None:
        profile.name = data.name
    if data.role is not None:
        profile.role = data.role
    if data.company is not None:
        profile.company = data.company
    if data.contacts is not None:
        profile.contacts = json.dumps([c.model_dump() for c in data.contacts], ensure_ascii=False)
    if data.projects is not None:
        profile.projects = json.dumps([p.model_dump() for p in data.projects], ensure_ascii=False)
    if data.preferences is not None:
        profile.preferences = json.dumps(data.preferences, ensure_ascii=False)
    await db.flush()
    return profile
