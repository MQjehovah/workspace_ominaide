from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from core.database.base import Base


class PluginNote(Base):
    __tablename__ = "plugin_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False, default="无标题")
    content = Column(Text, nullable=True, default="")
    parent_id = Column(Integer, ForeignKey("plugin_notes.id"), nullable=True)
    is_folder = Column(Integer, default=0)
    icon = Column(String(50), nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
