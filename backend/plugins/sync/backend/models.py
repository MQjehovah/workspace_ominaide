from sqlalchemy import Column, Integer, String, BigInteger, DateTime, ForeignKey, JSON, func
from core.database.base import Base


class SyncEvent(Base):
    __tablename__ = "sync_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_type = Column(String(20), nullable=False)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=True)
    file_path = Column(String(500), nullable=False)
    file_size = Column(BigInteger, nullable=True)
    checksum = Column(String(64), nullable=True)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, server_default=func.now())
