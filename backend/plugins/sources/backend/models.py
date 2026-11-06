from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    Boolean,
    JSON,
    ForeignKey,
    UniqueConstraint,
    func,
)
from core.database.base import Base


class ContentSource(Base):
    """A user's information source (RSS, GitHub Trending, ...)."""

    __tablename__ = "content_sources"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", "url", name="uq_content_source_user_url"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    provider = Column(String(50), nullable=False, default="rss", index=True)
    config = Column(JSON, nullable=True)
    url = Column(String(1000), nullable=False)
    title = Column(String(200), nullable=True)
    icon = Column(String(500), nullable=True)
    last_fetch = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class ContentItem(Base):
    """A single article/release/post fetched from a source."""

    __tablename__ = "content_items"
    __table_args__ = (
        UniqueConstraint("source_id", "guid", name="uq_content_item_source_guid"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(
        Integer,
        ForeignKey("content_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    guid = Column(String(500), nullable=False)
    title = Column(String(500), nullable=False)
    link = Column(String(1000), nullable=True)
    summary = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    author = Column(String(200), nullable=True)
    published = Column(DateTime, nullable=True)
    read = Column(Boolean, default=False)
    starred = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
