from sqlalchemy import Column, DateTime, Integer, JSON, String, Text, func

from core.database.base import Base


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True)
    kind = Column(String(80), nullable=False, index=True)
    payload = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="queued", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    run_after = Column(DateTime, nullable=True, index=True)
    locked_at = Column(DateTime, nullable=True)
    idempotency_key = Column(String(200), nullable=True, unique=True)
    error = Column(Text, nullable=True)
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
