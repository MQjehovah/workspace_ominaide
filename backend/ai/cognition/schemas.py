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
    goal_id: int | None = None
    session_id: str | None = None
    constraints: dict | None = None
    expires_at: datetime | None = None


class GoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    bot_id: int | None = None
    due_at: datetime | None = None
    priority: int = Field(default=50, ge=0, le=100)
    success_criteria: list | dict | None = None
    context: dict | None = None
    primary_session_id: str | None = None
    origin_message_id: int | None = None


class GoalOut(BaseModel):
    id: int
    user_id: int
    bot_id: int | None = None
    title: str
    description: str | None = None
    status: str
    priority: int
    due_at: datetime | None = None
    success_criteria: list | dict | None = None
    context: dict | None = None
    workspace_id: int | None = None
    primary_session_id: str | None = None
    token_budget: int | None = None
    cost_budget: float | None = None
    max_steps: int
    max_runs: int
    budget_used: dict | None = None
    next_wake_at: datetime | None = None
    last_run_at: datetime | None = None
    created_by: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    agent_profile_key: str | None = None
    depends_on: list[int] | None = None
    acceptance: list | dict | None = None
    risk: str = "suggest"
    input: dict | None = None
    sort_order: int = 0
    deadline: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    agent_profile_key: str | None = None
    status: str | None = None
    depends_on: list[int] | None = None
    acceptance: list | dict | None = None
    risk: str | None = None
    input: dict | None = None
    output: dict | None = None
    sort_order: int | None = None
    deadline: datetime | None = None


class TaskOut(BaseModel):
    id: int
    goal_id: int
    parent_task_id: int | None = None
    title: str
    description: str | None = None
    agent_profile_key: str | None = None
    status: str
    depends_on: list | None = None
    acceptance: list | dict | None = None
    risk: str
    input: dict | None = None
    output: dict | None = None
    sort_order: int
    deadline: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class WorkspaceItemCreate(BaseModel):
    type: str = "fact"
    key: str | None = None
    content: dict | list | str | int | float | bool | None = None
    source: str | None = None
    confidence: float = 0.5
    created_by: str | None = None


class WorkspaceArtifactCreate(BaseModel):
    file_id: int | None = None
    kind: str = "draft"


class HandoffRequest(BaseModel):
    machine_id: str = Field(min_length=1, max_length=120)
    goal_id: int | None = None
    session_id: str | None = None
    note: str | None = None


class GrantOut(BaseModel):
    id: int
    user_id: int
    bot_id: int | None = None
    goal_id: int | None = None
    session_id: str | None = None
    agent_profile_key: str | None = None
    capability_key: str
    decision: str
    scope: str
    constraints: dict | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
