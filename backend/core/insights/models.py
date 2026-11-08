from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, func

from core.database.base import Base


class ActivitySuggestion(Base):
    __tablename__ = "activity_suggestions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(20), default="follow_up", nullable=False)
    title = Column(String(200), nullable=False)
    reason = Column(String(500), nullable=True)
    confidence = Column(Float, default=0.5)
    source_event_ids = Column(JSON, nullable=True)
    status = Column(String(20), default="new", nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    expires_at = Column(DateTime, nullable=True)
