"""DingTalk plugin-owned cache for the conversation viewer."""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)

from core.database.base import Base


class DingTalkConversation(Base):
    __tablename__ = "dingtalk_conversations"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "conversation_id",
            name="uq_dingtalk_conversation_user",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(String(200), nullable=False, index=True)
    name = Column(String(300), nullable=True)
    kind = Column(String(30), nullable=True)
    last_message_at = Column(DateTime, nullable=True, index=True)
    unread_count = Column(Integer, default=0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DingTalkMessage(Base):
    __tablename__ = "dingtalk_messages"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "conversation_id", "message_id",
            name="uq_dingtalk_message_user_conv_msg",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(String(200), nullable=False, index=True)
    message_id = Column(String(200), nullable=False)
    sender = Column(String(200), nullable=True)
    text = Column(Text, nullable=False, default="")
    sent_at = Column(DateTime, nullable=True, index=True)
    raw = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class DingTalkCalendarSnapshot(Base):
    """Fingerprint of the last published version of an external event."""

    __tablename__ = "dingtalk_calendar_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", "external_id",
            name="uq_dingtalk_calendar_snapshot",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String(40), nullable=False, default="dingtalk")
    external_id = Column(String(200), nullable=False, index=True)
    fingerprint = Column(String(64), nullable=False)
    status = Column(String(20), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

