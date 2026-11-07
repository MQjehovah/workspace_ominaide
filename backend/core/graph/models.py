from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)

from core.database.base import Base


class EntityLink(Base):
    __tablename__ = "entity_links"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "from_type",
            "from_id",
            "to_type",
            "to_id",
            "relation",
            name="uq_entity_link",
        ),
        Index("ix_entity_links_from", "user_id", "from_type", "from_id"),
        Index("ix_entity_links_to", "user_id", "to_type", "to_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    from_type = Column(String(40), nullable=False)
    from_id = Column(Integer, nullable=False)
    to_type = Column(String(40), nullable=False)
    to_id = Column(Integer, nullable=False)
    relation = Column(String(60), nullable=False, default="related")
    confidence = Column(Float, nullable=False, default=1.0)
    source = Column(String(60), nullable=True)
    meta = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class SyncState(Base):
    __tablename__ = "sync_states"
    __table_args__ = (
        UniqueConstraint("user_id", "connector", name="uq_sync_state_user_connector"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    connector = Column(String(60), nullable=False, index=True)
    cursor = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="idle")
    error = Column(Text, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
