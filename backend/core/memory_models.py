"""Memory OS 2.0: candidate extraction, review and consolidated long-term memory."""

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey,
    UniqueConstraint, func,
)

from core.database.base import Base


class MemoryCandidate(Base):
    """A proposed memory extracted from conversations or external sources."""

    __tablename__ = "memory_candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="SET NULL"), nullable=True, index=True)
    kind = Column(String(32), default="fact", nullable=False)  # fact/preference/commitment/relationship/project
    content = Column(Text, nullable=False)
    normalized = Column(String(600), nullable=False, index=True)
    confidence = Column(Integer, default=60)  # 0-100
    source_type = Column(String(32), default="chat")
    source_id = Column(Integer, nullable=True)
    source_ref = Column(JSON, nullable=True)
    trust = Column(String(20), default="trusted")  # trusted | untrusted
    status = Column(String(20), default="pending", index=True)  # pending/approved/rejected/merged
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    reviewed_at = Column(DateTime, nullable=True)


class MemoryRecord(Base):
    """Consolidated, user-level long-term memory."""

    __tablename__ = "memory_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id", ondelete="SET NULL"), nullable=True, index=True)
    kind = Column(String(32), default="fact", nullable=False)
    content = Column(Text, nullable=False)
    normalized = Column(String(600), nullable=False, index=True)
    confidence = Column(Integer, default=60)
    importance = Column(Integer, default=50)
    source_type = Column(String(32), default="chat")
    source_id = Column(Integer, nullable=True)
    sources = Column(JSON, nullable=True)
    status = Column(String(20), default="active", index=True)  # active/superseded/deleted
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    superseded_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_used_at = Column(DateTime, nullable=True)
    use_count = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("user_id", "normalized", "kind", name="uq_memory_record_user_norm_kind"),
    )
