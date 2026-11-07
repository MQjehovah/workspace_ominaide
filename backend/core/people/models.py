from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func,
)

from core.database.base import Base


class Person(Base):
    """Normalized person index built from mail, calendar, meetings and memory."""

    __tablename__ = "people"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    display_name = Column(String(200), nullable=False, index=True)
    normalized_name = Column(String(200), nullable=False, index=True)
    emails = Column(JSON, nullable=True)
    aliases = Column(JSON, nullable=True)
    company = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    meta = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PersonMention(Base):
    """One source record that mentions a person."""

    __tablename__ = "person_mentions"
    __table_args__ = (
        UniqueConstraint(
            "person_id", "source_type", "source_id", "role",
            name="uq_person_mention_source",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(
        Integer, ForeignKey("people.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source_type = Column(String(32), nullable=False, index=True)
    source_id = Column(Integer, nullable=False, index=True)
    title = Column(String(500), nullable=True)
    snippet = Column(Text, nullable=True)
    role = Column(String(32), default="mention", nullable=False)
    occurred_at = Column(DateTime, nullable=True, index=True)
    meta = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
