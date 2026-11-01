from sqlalchemy import (
    BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text, func,
)
from sqlalchemy.dialects.mysql import LONGTEXT

from core.database.base import Base
import core.auth.domain.models  # noqa: F401  (registers `users`, the FK target)


def _long_text():
    """TEXT on PostgreSQL/SQLite, LONGTEXT on MySQL (same pattern as notes)."""
    return Text().with_variant(LONGTEXT, "mysql")


class CodingTask(Base):
    """Persisted history for server-side coding-agent tasks.

    The in-memory registry in `service.VibecodingHub` stays authoritative for
    live routing (it also holds desktop tasks); this table is the durable copy
    that survives backend restarts and enables "continue this task".
    """

    __tablename__ = "coding_tasks"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    parent_id = Column(String(64), nullable=True)
    project = Column(String(1000), nullable=False)
    project_name = Column(String(200), nullable=True)
    source = Column(String(50), nullable=True)
    engine = Column(String(20), nullable=False, default="server")
    instruction = Column(_long_text(), nullable=True)
    status = Column(String(20), nullable=False, default="running", index=True)
    code = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    turns = Column(Integer, nullable=True, default=0)
    output = Column(_long_text(), nullable=True)
    error = Column(_long_text(), nullable=True)
    events = Column(_long_text(), nullable=True)
    messages = Column(_long_text(), nullable=True)
    branch = Column(String(255), nullable=True)
    commit_sha = Column(String(64), nullable=True)
    pr_url = Column(String(500), nullable=True)
    started_ts = Column(BigInteger, nullable=True)
    ended_ts = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_coding_tasks_user_created", "user_id", "created_at"),
    )
