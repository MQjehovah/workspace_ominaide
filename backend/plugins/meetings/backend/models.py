from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)

from core.database.base import Base


class MeetingMinutesJob(Base):
    __tablename__ = "meeting_minutes_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False, index=True)
    event_id = Column(Integer, ForeignKey("schedule_events.id"), nullable=True)
    title = Column(String(300), nullable=False, default="会议纪要")
    status = Column(String(30), nullable=False, default="queued", index=True)
    language = Column(String(20), nullable=True)
    transcript = Column(Text, nullable=True)
    segments = Column(JSON, nullable=True)
    minutes = Column(JSON, nullable=True)
    note_id = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
