from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
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

