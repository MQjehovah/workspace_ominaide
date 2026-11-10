from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)

from core.database.base import Base


class Session(Base):
    """Unified chat/coding/goal session metadata.

    Messages and execution details stay in their own tables; this table only
    owns the long-lived container: title, objective, status and metadata.
    """

    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(120), nullable=True)
    kind = Column(String(20), nullable=False, default="chat", index=True)
    objective = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, default="active", index=True)
    meta = Column("metadata", JSON, nullable=True)
    active_run_id = Column(Integer, nullable=True, index=True)
    last_message_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SessionMessage(Base):
    """User-visible interaction record for any kind of session.

    Tool arguments/results intentionally live in RunStep, not here.
    """

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String(64), nullable=False, default="default", index=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="SET NULL"), nullable=True, index=True)
    run_id = Column(Integer, nullable=True, index=True)
    role = Column(String(20), nullable=False)
    kind = Column(String(20), nullable=False, default="text")
    content = Column(Text, nullable=False)
    meta = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
