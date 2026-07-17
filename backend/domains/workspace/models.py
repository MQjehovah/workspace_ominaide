from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, func
from core.database.base import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    bucket = Column(String(50), nullable=False)
    sync_enabled = Column(Boolean, default=False)
    local_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
