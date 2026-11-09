"""Cognition-layer persistence: proposals and capability grants."""

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)

from core.database.base import Base


class Proposal(Base):
    """One actionable proposal shown to the user.

    Proposals replace the old ``activity_suggestions`` concept. A proposal
    carries its reason, evidence, confidence and concrete actions, and has a
    single lifecycle (new → accepted/snoozed/dismissed → executed/failed).
    """

    __tablename__ = "proposals"
    __table_args__ = (
        Index("ix_proposals_user_status", "user_id", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="SET NULL"), nullable=True, index=True)
    kind = Column(String(24), nullable=False, default="follow_up")
    title = Column(String(200), nullable=False)
    reason = Column(String(500), nullable=True)
    evidence = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=False, default=0.5)
    actions = Column(JSON, nullable=True)
    status = Column(String(24), nullable=False, default="new", index=True)
    channel = Column(String(20), nullable=False, default="now")
    dedupe_key = Column(String(200), nullable=True, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    snooze_until = Column(DateTime, nullable=True, index=True)
    goal_id = Column(Integer, nullable=True, index=True)
    feedback = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CapabilityGrant(Base):
    """A remembered authorization decision for one capability."""

    __tablename__ = "capability_grants"
    __table_args__ = (
        Index("ix_capability_grants_lookup", "user_id", "capability_key", "decision"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=True, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="CASCADE"), nullable=True, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    agent_profile_key = Column(String(64), nullable=True, index=True)
    capability_key = Column(String(160), nullable=False, index=True)
    decision = Column(String(10), nullable=False, default="allow")
    scope = Column(String(20), nullable=False, default="always")
    constraints = Column(JSON, nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Goal(Base):
    """A persistent outcome owned by a Bot."""

    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, default="draft", index=True)
    priority = Column(Integer, nullable=False, default=50)
    due_at = Column(DateTime, nullable=True, index=True)
    success_criteria = Column(JSON, nullable=True)
    context = Column(JSON, nullable=True)
    workspace_id = Column(Integer, nullable=True, index=True)
    primary_session_id = Column(String(64), nullable=True, index=True)
    origin_message_id = Column(Integer, nullable=True)
    token_budget = Column(Integer, nullable=True)
    cost_budget = Column(Float, nullable=True)
    max_steps = Column(Integer, nullable=False, default=20)
    max_runs = Column(Integer, nullable=False, default=40)
    budget_used = Column(JSON, nullable=True)
    next_wake_at = Column(DateTime, nullable=True, index=True)
    last_run_at = Column(DateTime, nullable=True)
    created_by = Column(String(20), nullable=False, default="user")
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime, nullable=True)


class Task(Base):
    """One executable unit under a Goal, assigned to an AgentProfile."""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    agent_profile_key = Column(String(64), nullable=True, index=True)
    status = Column(String(24), nullable=False, default="pending", index=True)
    depends_on = Column(JSON, nullable=True)
    acceptance = Column(JSON, nullable=True)
    risk = Column(String(20), nullable=False, default="suggest")
    input = Column(JSON, nullable=True)
    output = Column(JSON, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    deadline = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="SET NULL"), nullable=True, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="CASCADE"), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    created_at = Column(DateTime, server_default=func.now())


class WorkspaceItem(Base):
    __tablename__ = "workspace_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(24), nullable=False, default="fact")
    key = Column(String(120), nullable=True, index=True)
    content = Column(JSON, nullable=True)
    source = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=False, default=0.5)
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class WorkspaceArtifact(Base):
    __tablename__ = "workspace_artifacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(Integer, nullable=True, index=True)
    kind = Column(String(24), nullable=False, default="draft")
    created_at = Column(DateTime, server_default=func.now())


class ProposalFeedback(Base):
    """Append-only feedback for proposal quality and interruption tuning."""

    __tablename__ = "proposal_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    proposal_id = Column(Integer, ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(24), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
