from sqlalchemy import Column, Integer, String, BigInteger, Boolean, DateTime, ForeignKey, JSON, func
from core.database.base import Base


class SyncFolder(Base):
    __tablename__ = "sync_folders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    server_path = Column(String(500), nullable=False, default="/")
    local_path = Column(String(500), nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SyncEvent(Base):
    __tablename__ = "sync_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_folder_id = Column(Integer, ForeignKey("sync_folders.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_type = Column(String(20), nullable=False)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=True)
    file_path = Column(String(500), nullable=False)
    file_size = Column(BigInteger, nullable=True)
    checksum = Column(String(64), nullable=True)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, server_default=func.now())
