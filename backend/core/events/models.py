from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, func
from core.database.base import Base


class UserEvent(Base):
    __tablename__ = "user_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(50), nullable=True)  # todo, file, note
    entity_id = Column(Integer, nullable=True)
    summary = Column(String(500), nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
