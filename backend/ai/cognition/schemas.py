from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProposalOut(BaseModel):
    id: int
    user_id: int
    bot_id: int | None = None
    kind: str
    title: str
    reason: str | None = None
    evidence: dict | None = None
    confidence: float
    actions: list[dict] = Field(default_factory=list)
    primary_action: dict | None = None
    status: str
    channel: str
    dedupe_key: str | None = None
    expires_at: datetime | None = None
    snooze_until: datetime | None = None
    goal_id: int | None = None
    feedback: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProposalAct(BaseModel):
    action: str = Field(pattern="^(seen|accept|execute|dismiss|snooze)$")
    snooze_minutes: int = Field(default=60, ge=5, le=60 * 24 * 30)


class CapabilityOut(BaseModel):
    key: str
    title: str
    description: str = ""
    source: str = "builtin"
    risk: str = "read"
    reversible: bool = True
    cost: str = "low"
    data_scopes: list[str] = Field(default_factory=list)
    grant: str | None = None


class GrantCreate(BaseModel):
    capability_key: str = Field(min_length=1, max_length=160)
    decision: str = Field(default="allow", pattern="^(allow|deny)$")
    scope: str = Field(default="always", pattern="^(once|goal|session|day|always)$")
    agent_profile_key: str | None = Field(default=None, max_length=64)
    bot_id: int | None = None
    constraints: dict | None = None
    expires_at: datetime | None = None


class GrantOut(BaseModel):
    id: int
    user_id: int
    bot_id: int | None = None
    agent_profile_key: str | None = None
    capability_key: str
    decision: str
    scope: str
    constraints: dict | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
