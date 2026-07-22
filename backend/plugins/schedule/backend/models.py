from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, func
from core.database.base import Base


class Event(Base):
    __tablename__ = "schedule_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    title = Column(String(200), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    color = Column(String(20), default="#409EFF")
    remind_before = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
