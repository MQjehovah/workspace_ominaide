from sqlalchemy import Column, Integer, String, BigInteger, Boolean, DateTime, JSON, ForeignKey, Text, func
from core.database.base import Base


class File(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True, index=True)
    bucket = Column(String(50), nullable=False)
    object_key = Column(String(500), nullable=False)
    original_name = Column(String(255), nullable=False)
    size = Column(BigInteger, default=0)
    mime_type = Column(String(100), nullable=True)
    tags = Column(JSON, nullable=True)
    is_favorite = Column(Boolean, default=False)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)
