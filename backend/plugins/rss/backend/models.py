from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, func, ForeignKey
from core.database.base import Base


class Feed(Base):
    __tablename__ = "rss_feeds"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    url = Column(String(500), nullable=False)
    title = Column(String(200), nullable=True)
    icon = Column(String(500), nullable=True)
    last_fetch = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Entry(Base):
    __tablename__ = "rss_entries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    feed_id = Column(Integer, ForeignKey("rss_feeds.id", ondelete="CASCADE"), nullable=False, index=True)
    guid = Column(String(500), nullable=False)
    title = Column(String(500), nullable=False)
    link = Column(String(500), nullable=True)
    summary = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    author = Column(String(200), nullable=True)
    published = Column(DateTime, nullable=True)
    read = Column(Boolean, default=False)
    starred = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
