from datetime import datetime
from pydantic import BaseModel, Field


class BotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str | None = Field(default=None, max_length=64)
    avatar: str | None = None
    role: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    temperature: float = 0.7
    allowed_tools: list[str] | None = None
    risk_policy: dict | None = None
    max_turns: int = 30
    token_budget: int | None = None
    is_default: bool = False


class BotUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, max_length=64)
    avatar: str | None = None
    role: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = None
    allowed_tools: list[str] | None = None
    risk_policy: dict | None = None
    max_turns: int | None = None
    token_budget: int | None = None
    is_default: bool | None = None
    status: str | None = None


class BotOut(BaseModel):
    id: int
    user_id: int
    slug: str
    name: str
    avatar: str | None = None
    role: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = None
    allowed_tools: list[str] | None = None
    risk_policy: dict | None = None
    max_turns: int | None = None
    token_budget: int | None = None
    is_default: bool = False
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    kind: str = "fact"
    importance: float = 0.5
    expires_at: datetime | None = None


class MemoryOut(BaseModel):
    id: int
    bot_id: int
    user_id: int
    kind: str
    content: str
    importance: float
    source_run_id: int | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class RunCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    session_id: str | None = None
    auto_start: bool = True


class RunOut(BaseModel):
    id: int
    bot_id: int
    user_id: int
    routine_id: int | None = None
    session_id: str | None = None
    trigger: str
    status: str
    input: str | None = None
    output: str | None = None
    error: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class StepOut(BaseModel):
    id: int
    run_id: int
    seq: int
    type: str
    tool_name: str | None = None
    arguments: dict | None = None
    result: str | None = None
    status: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class RunDetail(RunOut):
    steps: list[StepOut] = []


class RoutineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    trigger_type: str = "cron"
    cron_expr: str | None = None
    event_type: str | None = None
    event_filter: dict | None = None
    prompt: str | None = None
    enabled: bool = True


class RoutineUpdate(BaseModel):
    name: str | None = None
    trigger_type: str | None = None
    cron_expr: str | None = None
    event_type: str | None = None
    event_filter: dict | None = None
    prompt: str | None = None
    enabled: bool | None = None


class RoutineOut(BaseModel):
    id: int
    bot_id: int
    user_id: int
    name: str
    trigger_type: str
    cron_expr: str | None = None
    event_type: str | None = None
    event_filter: dict | None = None
    prompt: str | None = None
    enabled: bool = True
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_status: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ApprovalOut(BaseModel):
    id: int
    run_id: int
    bot_id: int
    user_id: int
    tool_name: str
    arguments: dict | None = None
    risk_level: str
    status: str
    reason: str | None = None
    created_at: datetime | None = None
    decided_at: datetime | None = None

    model_config = {"from_attributes": True}


class ApprovalDecision(BaseModel):
    approved: bool
    reason: str | None = None
