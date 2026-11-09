"""Skill runtime: discovery, per-bot enablement and execution."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select

from ai.bots import registry
from ai.bots.context import get_current_run_id, get_current_session_id
from ai.bots.models import Bot, Run
from core.database.session import async_session
from ai.skills.handlers import HANDLERS, SkillContext
from ai.skills.loader import SkillDefinition, get_skill, list_skills
from ai.skills.models import BotSkill


class SkillError(Exception):
    pass


class SkillNotFound(SkillError):
    pass


class SkillDisabled(SkillError):
    pass


def _run_input(skill_key: str, input: dict[str, Any]) -> str:
    return json.dumps({"skill": skill_key, "input": input}, ensure_ascii=False)


async def _disabled_keys(bot_id: int) -> set[str]:
    async with async_session() as db:
        rows = list(
            (
                await db.execute(
                    select(BotSkill).where(BotSkill.bot_id == bot_id)
                )
            )
            .scalars()
            .all()
        )
    return {row.skill_key for row in rows if not row.enabled}


async def enabled_skills(bot: Bot) -> list[SkillDefinition]:
    disabled = await _disabled_keys(bot.id)
    return [skill for skill in list_skills() if skill.key not in disabled]


async def list_bot_skills(user_id: int, bot_id: int) -> list[dict]:
    bot = await registry.get_active_bot(user_id, bot_id)
    disabled = await _disabled_keys(bot.id)
    return [
        {**skill.summary(), "enabled": skill.key not in disabled}
        for skill in list_skills()
    ]


async def set_bot_skill(
    user_id: int, bot_id: int, skill_key: str, enabled: bool
) -> dict:
    bot = await registry.get_active_bot(user_id, bot_id)
    if get_skill(skill_key) is None:
        raise SkillNotFound(skill_key)
    async with async_session() as db:
        row = (
            await db.execute(
                select(BotSkill).where(
                    BotSkill.bot_id == bot.id,
                    BotSkill.skill_key == skill_key,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = BotSkill(
                bot_id=bot.id,
                user_id=user_id,
                skill_key=skill_key,
                enabled=enabled,
            )
            db.add(row)
        else:
            row.enabled = enabled
        await db.commit()
    return {"key": skill_key, "enabled": enabled}


async def build_skill_context(bot: Bot) -> str:
    skills = await enabled_skills(bot)
    if not skills:
        return ""
    return (
        f"当前 Bot 有 {len(skills)} 个已启用技能。"
        "需要技能时先调用 skill_search 检索，再用 skill_call 执行；"
        "不要猜测技能 key。"
    )


async def run_skill(
    user_id: int,
    bot_id: int,
    skill_key: str,
    input: dict[str, Any] | None = None,
    *,
    parent_run_id: int | None = None,
    session_id: str | None = None,
) -> dict:
    skill = get_skill(skill_key)
    if skill is None:
        raise SkillNotFound(skill_key)
    handler = HANDLERS.get(skill_key)
    if handler is None:
        raise SkillError(f"技能 {skill_key} 没有后端处理器")

    bot = await registry.get_active_bot(user_id, bot_id)
    if skill_key in await _disabled_keys(bot.id):
        raise SkillDisabled(f"技能 {skill_key} 已被关闭")

    payload = input or {}
    parent_run_id = parent_run_id or get_current_run_id()
    session_id = session_id or get_current_session_id()

    async with async_session() as db:
        run = Run(
            bot_id=bot.id,
            user_id=user_id,
            parent_run_id=parent_run_id,
            session_id=session_id,
            trigger="skill",
            status="running",
            input=_run_input(skill_key, payload),
            started_at=datetime.utcnow(),
        )
        db.add(run)
        await db.flush()
        run_id = run.id
        await db.commit()

    try:
        output = await handler(
            SkillContext(
                user_id=user_id,
                bot=bot,
                skill=skill,
                input=payload,
                run_id=run_id,
            )
        )
    except Exception as exc:
        async with async_session() as db:
            row = await db.get(Run, run_id)
            if row is not None:
                row.status = "failed"
                row.error = str(exc)[:4000]
                row.finished_at = datetime.utcnow()
                await db.commit()
        if isinstance(exc, SkillError):
            raise
        raise SkillError(str(exc)) from exc

    async with async_session() as db:
        row = await db.get(Run, run_id)
        if row is not None:
            row.status = "done"
            row.output = json.dumps(output, ensure_ascii=False)[:200000]
            row.finished_at = datetime.utcnow()
            await db.commit()

    return {"skill_key": skill_key, "run_id": run_id, "output": output}


async def is_skill_enabled(bot: Bot, skill_key: str) -> bool:
    """Whether a bot has not explicitly disabled a skill."""
    return skill_key not in await _disabled_keys(bot.id)
