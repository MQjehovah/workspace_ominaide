"""Agent Skills API: catalog, per-bot enablement and execution."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth.dependencies import get_current_user
from ai.bots.registry import get_or_create_default_bot
from ai.skills import runtime
from ai.skills.loader import get_skill, list_skills

router = APIRouter(prefix="/api/skills", tags=["skills"])
bots_router = APIRouter(prefix="/api/bots", tags=["skills"])


class SkillRunRequest(BaseModel):
    bot_id: int | None = None
    input: dict = Field(default_factory=dict)


class BotSkillUpdate(BaseModel):
    enabled: bool = True


@router.get("")
async def catalog(user: dict = Depends(get_current_user)):
    return {"skills": [skill.summary() for skill in list_skills()]}


@router.get("/{skill_key}")
async def detail(skill_key: str, user: dict = Depends(get_current_user)):
    skill = get_skill(skill_key)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill.summary()


@router.post("/{skill_key}/run")
async def run(
    skill_key: str,
    req: SkillRunRequest,
    user: dict = Depends(get_current_user),
):
    bot_id = req.bot_id
    if bot_id is None:
        bot = await get_or_create_default_bot(user["id"])
        bot_id = bot.id
    try:
        return await runtime.run_skill(
            user["id"], bot_id, skill_key, req.input
        )
    except runtime.SkillNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except runtime.SkillDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except runtime.SkillError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@bots_router.get("/{bot_id}/skills")
async def bot_skills(bot_id: int, user: dict = Depends(get_current_user)):
    try:
        return {
            "skills": await runtime.list_bot_skills(user["id"], bot_id)
        }
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@bots_router.put("/{bot_id}/skills/{skill_key}")
async def update_bot_skill(
    bot_id: int,
    skill_key: str,
    req: BotSkillUpdate,
    user: dict = Depends(get_current_user),
):
    try:
        return await runtime.set_bot_skill(
            user["id"], bot_id, skill_key, req.enabled
        )
    except runtime.SkillNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))
