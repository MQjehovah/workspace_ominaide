"""Canonical entities, aliases, mentions and relations.

Business objects (mail, events, notes, todos, memories) stay in their own
tables; they attach to entities through ``EntityMention`` rows. Relations
only connect entities, never business objects.
"""

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)

from core.database.base import Base


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (
        Index("ix_entities_user_type", "user_id", "type"),
        Index("ix_entities_user_name", "user_id", "canonical_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # person / organization / project / topic / goal
    type = Column(String(32), nullable=False, default="person")
    canonical_name = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="active", index=True)
    merged_into = Column(
        Integer,
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    meta = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class EntityAlias(Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "alias",
            "alias_type",
            "entity_type",
            name="uq_entity_alias",
        ),
        Index("ix_entity_aliases_entity", "entity_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id = Column(
        Integer,
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias = Column(String(300), nullable=False)
    # name / email / phone / dingtalk / nickname
    alias_type = Column(String(24), nullable=False, default="name")
    # person / organization / project / topic / goal
    entity_type = Column(String(32), nullable=False, default="person")
    source = Column(String(60), nullable=True)
    confidence = Column(Float, nullable=False, default=1.0)
    created_at = Column(DateTime, server_default=func.now())


class EntityMention(Base):
    __tablename__ = "entity_mentions"
    __table_args__ = (
        Index("ix_entity_mentions_entity", "user_id", "entity_id"),
        Index(
            "ix_entity_mentions_source",
            "user_id",
            "source_type",
            "source_id",
        ),
        UniqueConstraint(
            "user_id",
            "entity_id",
            "source_type",
            "source_id",
            name="uq_entity_mention",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id = Column(
        Integer,
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    # memory / chat / mail / event / todo / note / comment
    source_type = Column(String(32), nullable=False)
    source_id = Column(Integer, nullable=False)
    quote = Column(Text, nullable=True)
    # sender / attendee / subject / mentioned / owner
    role = Column(String(32), nullable=False, default="mentioned")
    confidence = Column(Float, nullable=False, default=0.8)
    # rule / llm / manual
    extracted_by = Column(String(20), nullable=False, default="rule")
    created_at = Column(DateTime, server_default=func.now(), index=True)


class EntityRelation(Base):
    __tablename__ = "entity_relations"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "from_entity_id",
            "to_entity_id",
            "relation",
            name="uq_entity_relation",
        ),
        Index("ix_entity_relations_from", "user_id", "from_entity_id"),
        Index("ix_entity_relations_to", "user_id", "to_entity_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_entity_id = Column(
        Integer,
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_entity_id = Column(
        Integer,
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation = Column(String(60), nullable=False, default="related")
    confidence = Column(Float, nullable=False, default=0.8)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    source_mention_id = Column(
        Integer,
        ForeignKey("entity_mentions.id", ondelete="SET NULL"),
        nullable=True,
    )
    meta = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
