from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, func
from core.database.base import Base


class PluginRegistry(Base):
    __tablename__ = "plugin_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    version = Column(String(20), nullable=False)
    title = Column(String(200))
    description = Column(Text, nullable=True)
    icon = Column(String(50), nullable=True)
    enabled = Column(Boolean, default=True)
    manifest = Column(JSON, nullable=True)
    installed_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
