from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, func
from core.database.base import Base


class PluginTodoItem(Base):
    __tablename__ = "plugin_todo_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="pending")
    priority = Column(Integer, default=0)
    due_date = Column(DateTime, nullable=True)
    tags = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
