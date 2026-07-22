from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, func
from core.database.base import Base

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=True)
    type = Column(String(50), default="info")
    link = Column(String(500), nullable=True)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
