from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    Float,
    JSON,
    ForeignKey,
    UniqueConstraint,
    func,
)
from core.database.base import Base


class Bot(Base):
    """A named, persistent assistant identity.

    Agent = execution engine (one run). Bot = owner of identity, memory and
    default policy. See docs/plans/2026-11-04-bot-form-design.md.
    """

    __tablename__ = "bots"
    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_bots_user_slug"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    slug = Column(String(64), nullable=False)
    name = Column(String(100), nullable=False)
    avatar = Column(String(200), nullable=True)
    role = Column(String(200), nullable=True)
    system_prompt = Column(Text, nullable=True)
    model = Column(String(100), nullable=True)
    temperature = Column(Float, default=0.7)
    allowed_tools = Column(JSON, nullable=True)
    # Tools always exposed to the LLM. Others are reachable through
    # tool_search/tool_call when the tool gateway is enabled.
    pinned_tools = Column(JSON, nullable=True)
    risk_policy = Column(JSON, nullable=True)
    max_turns = Column(Integer, default=60)
    token_budget = Column(Integer, nullable=True)
    is_default = Column(Boolean, default=False)
    status = Column(String(20), default="active", index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Bot id={self.id} slug={self.slug} user_id={self.user_id}>"


class BotMemory(Base):
    """Long-term memory owned by one bot. Shared user facts stay in UserProfile."""

    __tablename__ = "bot_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(20), default="fact", nullable=False)
    content = Column(Text, nullable=False)
    importance = Column(Float, default=0.5)
    source_run_id = Column(Integer, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<BotMemory id={self.id} bot_id={self.bot_id} kind={self.kind}>"


class Run(Base):
    """One persisted unit of work. A run may contain several agent turns."""

    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    routine_id = Column(Integer, ForeignKey("bot_routines.id", ondelete="SET NULL"), nullable=True, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="SET NULL"), nullable=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    agent_profile_key = Column(String(64), nullable=True, index=True)
    parent_run_id = Column(Integer, ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    trigger = Column(String(20), default="api", nullable=False)
    status = Column(String(24), default="queued", nullable=False, index=True)
    input = Column(Text, nullable=True)
    output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    partial = Column(Text, nullable=True)
    tokens_in = Column(Integer, default=0)
    tokens_out = Column(Integer, default=0)
    idempotency_key = Column(String(160), nullable=True, unique=True)
    checkpoint = Column(JSON, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    heartbeat_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<Run id={self.id} bot_id={self.bot_id} status={self.status}>"


class RunStep(Base):
    """Audit trail for a run: tool calls, approvals and outcomes."""

    __tablename__ = "run_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    seq = Column(Integer, default=0)
    type = Column(String(20), default="tool")
    tool_name = Column(String(100), nullable=True)
    arguments = Column(JSON, nullable=True)
    result = Column(Text, nullable=True)
    status = Column(String(20), default="ok")
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<RunStep run={self.run_id} seq={self.seq} {self.type}>"


class BotRoutine(Base):
    """A schedule/event trigger owned by a bot."""

    __tablename__ = "bot_routines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    trigger_type = Column(String(20), default="cron", nullable=False)
    cron_expr = Column(String(64), nullable=True)
    event_type = Column(String(50), nullable=True, index=True)
    event_filter = Column(JSON, nullable=True)
    prompt = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True, index=True)
    next_run_at = Column(DateTime, nullable=True, index=True)
    last_run_at = Column(DateTime, nullable=True)
    last_status = Column(String(20), nullable=True)
    spec = Column(JSON, nullable=True)
    spec_version = Column(Integer, default=1)
    last_error = Column(Text, nullable=True)
    run_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<BotRoutine id={self.id} bot_id={self.bot_id} name={self.name}>"


class Approval(Base):
    """A pending human decision for a risky tool call."""

    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False)
    capability_key = Column(String(160), nullable=True, index=True)
    arguments = Column(JSON, nullable=True)
    risk_level = Column(String(20), default="exec")
    status = Column(String(20), default="pending", index=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    decided_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Approval id={self.id} run={self.run_id} status={self.status}>"
