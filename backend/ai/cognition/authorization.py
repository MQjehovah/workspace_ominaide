"""Unified capability authorization.

Policy inputs:
- Bot allowlist + risk policy (existing ``ai.bots.policy``)
- Remembered user grants (``capability_grants``)
- Capability risk from the tool registry

Outcomes:
- allow: execute immediately
- deny: do not execute
- require_approval: create an approval / ask the user
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, select

from ai.bots import policy
from ai.cognition.capabilities import (
    Capability,
    describe_capability,
    normalize_capability_key,
)
from ai.cognition.models import CapabilityGrant
from ai.mcp.core import MCPCallResponse, MCPContent
from ai.mcp.registry import tool_registry
from core.database.session import async_session


@dataclass
class AuthorizationResult:
    capability_key: str
    capability: Capability
    risk: str
    decision: str          # allow | deny | require_approval
    reason: str
    grant: CapabilityGrant | None = None

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"

    @property
    def requires_approval(self) -> bool:
        return self.decision == "require_approval"


async def _resolve_bot(user_id: int, bot):
    if bot is not None:
        return bot
    try:
        from ai.bots.registry import get_active_bot

        return await get_active_bot(user_id)
    except Exception:
        return None


async def find_grants(
    user_id: int,
    capability_key: str,
    *,
    bot_id: int | None = None,
    agent_profile_key: str | None = None,
) -> list[CapabilityGrant]:
    now = datetime.now()
    async with async_session() as db:
        q = select(CapabilityGrant).where(
            CapabilityGrant.user_id == user_id,
            CapabilityGrant.capability_key == capability_key,
            CapabilityGrant.decision.in_(("allow", "deny")),
            or_(CapabilityGrant.expires_at.is_(None), CapabilityGrant.expires_at > now),
            or_(CapabilityGrant.bot_id.is_(None), CapabilityGrant.bot_id == bot_id),
            or_(
                CapabilityGrant.agent_profile_key.is_(None),
                CapabilityGrant.agent_profile_key == agent_profile_key,
            ),
        ).order_by(CapabilityGrant.created_at.desc(), CapabilityGrant.id.desc())
        return list((await db.execute(q)).scalars().all())


async def authorize(
    user_id: int,
    name: str,
    arguments: dict | None = None,
    *,
    bot=None,
    agent_profile_key: str | None = None,
    run_id: int | None = None,
) -> AuthorizationResult:
    bot = await _resolve_bot(user_id, bot)
    key = normalize_capability_key(name, arguments)
    capability = describe_capability(key, bot)
    risk, decision = policy.decide(bot, name, arguments)

    if decision == "deny":
        return AuthorizationResult(
            capability_key=key,
            capability=capability,
            risk=risk,
            decision="deny",
            reason=f"Bot 策略拒绝执行 {key}",
        )

    grants = await find_grants(
        user_id,
        key,
        bot_id=getattr(bot, "id", None),
        agent_profile_key=agent_profile_key,
    )
    for grant in grants:
        if grant.decision == "deny":
            return AuthorizationResult(
                capability_key=key,
                capability=capability,
                risk=risk,
                decision="deny",
                reason=f"用户已拒绝 {key}",
                grant=grant,
            )
    allow_grant = next((g for g in grants if g.decision == "allow"), None)

    if decision == "ask":
        if allow_grant is not None:
            return AuthorizationResult(
                capability_key=key,
                capability=capability,
                risk=risk,
                decision="allow",
                reason=f"已授权 {key}",
                grant=allow_grant,
            )
        return AuthorizationResult(
            capability_key=key,
            capability=capability,
            risk=risk,
            decision="require_approval",
            reason=f"{key} 属于 {risk} 风险，需要用户确认",
        )

    return AuthorizationResult(
        capability_key=key,
        capability=capability,
        risk=risk,
        decision="allow",
        reason="策略允许",
    )


async def authorized_tool_call(
    user_id: int,
    name: str,
    arguments: dict | None = None,
    *,
    bot=None,
) -> MCPCallResponse:
    """Authorize and execute one tool call (used by chat / direct MCP API)."""
    args = arguments or {}
    auth = await authorize(user_id, name, args, bot=bot)
    if auth.decision == "deny":
        return MCPCallResponse(
            isError=True,
            content=[MCPContent(text=f"已拒绝：{auth.reason}")],
        )
    if auth.requires_approval:
        return MCPCallResponse(
            isError=True,
            content=[MCPContent(
                text=(
                    f"需要用户确认：{auth.capability_key} 属于 {auth.risk} 风险。"
                    "请在审批中心确认后重试。"
                )
            )],
        )
    req = type("Req", (), {"name": name, "arguments": args})()
    return await tool_registry.call(user_id, req)


async def create_grant(
    user_id: int,
    capability_key: str,
    *,
    decision: str = "allow",
    scope: str = "always",
    bot_id: int | None = None,
    agent_profile_key: str | None = None,
    constraints: dict | None = None,
    expires_at: datetime | None = None,
) -> CapabilityGrant:
    now = datetime.now()
    if expires_at is None:
        if scope == "once":
            expires_at = now + timedelta(minutes=5)
        elif scope == "day":
            expires_at = now + timedelta(days=1)
    async with async_session() as db:
        row = CapabilityGrant(
            user_id=user_id,
            bot_id=bot_id,
            agent_profile_key=agent_profile_key,
            capability_key=capability_key[:160],
            decision=decision,
            scope=scope,
            constraints=constraints,
            expires_at=expires_at,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


async def list_grants(user_id: int) -> list[CapabilityGrant]:
    async with async_session() as db:
        rows = await db.execute(
            select(CapabilityGrant)
            .where(CapabilityGrant.user_id == user_id)
            .order_by(CapabilityGrant.id.desc())
        )
        return list(rows.scalars().all())


async def revoke_grant(user_id: int, grant_id: int) -> bool:
    async with async_session() as db:
        row = (
            await db.execute(
                select(CapabilityGrant).where(
                    CapabilityGrant.id == grant_id,
                    CapabilityGrant.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        await db.delete(row)
        await db.commit()
        return True
