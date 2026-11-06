"""Generic business-object comments and notes.

One table backs comments/materials for schedules, mail, 资讯, notes, todos,
files and projects. Replies are threaded with ``parent_id``/``root_id``.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func

from core.database.base import Base


class BusinessComment(Base):
    __tablename__ = "business_comments"
    __table_args__ = (
        Index("ix_business_comments_object", "user_id", "object_type", "object_id", "created_at"),
        Index("ix_business_comments_root", "root_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    object_type = Column(String(32), nullable=False, index=True)
    object_id = Column(Integer, nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("business_comments.id", ondelete="CASCADE"), nullable=True, index=True)
    root_id = Column(Integer, nullable=True, index=True)
    kind = Column(String(20), default="comment", nullable=False)
    title = Column(String(300), nullable=True)
    content = Column(Text, nullable=False)
    author = Column(String(20), default="user", nullable=False)
    session_id = Column(String(64), nullable=True, index=True)
    message_id = Column(Integer, nullable=True)
    meta = Column("metadata", JSON, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
