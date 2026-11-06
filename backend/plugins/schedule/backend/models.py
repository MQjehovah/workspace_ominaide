from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, JSON, Index, func
from core.database.base import Base


class Event(Base):
    __tablename__ = "schedule_events"
    __table_args__ = (
        Index("ix_schedule_source_external", "user_id", "source", "external_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    title = Column(String(200), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    color = Column(String(20), default="#409EFF")
    remind_before = Column(Integer, default=0)
    reminded = Column(Boolean, default=False)
    # manual | agent | dingtalk
    source = Column(String(20), default="manual", nullable=False, index=True)
    external_id = Column(String(200), nullable=True, index=True)
    external_meta = Column(JSON, nullable=True)
    location = Column(String(500), nullable=True)
    status = Column(String(20), default="confirmed", nullable=False, index=True)
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
