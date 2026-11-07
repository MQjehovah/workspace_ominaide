from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, JSON, String, Text, func, UniqueConstraint,
)

from core.database.base import Base


class AutomationRun(Base):
    """One execution of a BotRoutine/automation."""

    __tablename__ = "automation_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_automation_run_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    routine_id = Column(
        Integer, ForeignKey("bot_routines.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    trigger_type = Column(String(20), nullable=False, default="manual")
    trigger_context = Column(JSON, nullable=True)
    spec_snapshot = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="queued", index=True)
    action_results = Column(JSON, nullable=True)
    agent_run_id = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    idempotency_key = Column(String(200), nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
