from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, JSON, String, Text, func,
)

from core.database.base import Base


class QuickCapture(Base):
    """A link, image, article or text saved for later analysis."""

    __tablename__ = "quick_captures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(20), nullable=False, default="text", index=True)
    source = Column(String(20), nullable=False, default="web")
    url = Column(String(2000), nullable=True)
    title = Column(String(500), nullable=True)
    content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    key_points = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)
    people = Column(JSON, nullable=True)
    suggested_actions = Column(JSON, nullable=True)
    thumbnail_url = Column(String(2000), nullable=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), nullable=False, default="inbox", index=True)
    error = Column(Text, nullable=True)
    note_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
