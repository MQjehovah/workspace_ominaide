from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint, func,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from core.database.base import Base


class PluginNote(Base):
    __tablename__ = "plugin_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False, default="无标题")
    content = Column(Text().with_variant(LONGTEXT, "mysql"), nullable=True, default="")
    parent_id = Column(Integer, ForeignKey("plugin_notes.id"), nullable=True)
    is_folder = Column(Integer, default=0)
    icon = Column(String(50), nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class NoteVersion(Base):
    """Snapshot of a note's content at a point in time (page history / rollback)."""
    __tablename__ = "plugin_note_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    note_id = Column(Integer, ForeignKey("plugin_notes.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(500), nullable=True)
    content = Column(Text().with_variant(LONGTEXT, "mysql"), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, server_default=func.now())


class NoteChunk(Base):
    """Fine-grained evidence layer for RAG (one note -> many chunks).

    The embedding is stored as a JSON array in TEXT/LONGTEXT so the same schema
    works on MySQL, PostgreSQL and SQLite. Cosine similarity is computed in
    Python for personal-scale corpora; pgvector can be added later without
    changing the public API.
    """
    __tablename__ = "plugin_note_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    note_id = Column(Integer, ForeignKey("plugin_notes.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False, default=0)
    content = Column(Text().with_variant(LONGTEXT, "mysql"), nullable=True)
    context = Column(String(1000), nullable=True)
    embedding = Column(Text().with_variant(LONGTEXT, "mysql"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("note_id", "chunk_index", name="uq_note_chunk_index"),
    )


class NoteTerm(Base):
    """BM25 term-frequency table (Chinese bigrams + English words)."""
    __tablename__ = "plugin_note_terms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    note_id = Column(Integer, ForeignKey("plugin_notes.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    term = Column(String(120), nullable=False, index=True)
    tf = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("note_id", "term", name="uq_note_term"),
    )
