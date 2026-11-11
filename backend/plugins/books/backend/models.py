from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)

from core.database.base import Base


class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    file_id = Column(
        Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(500), nullable=False, default="")
    author = Column(String(300), default="")
    format = Column(String(16), default="txt")
    content = Column(Text, default="")
    # unread / reading / finished
    status = Column(String(16), default="unread", index=True)
    progress = Column(Float, default=0.0)
    # Paragraph index inside the extracted content.
    position = Column(Integer, default=0)
    paragraph_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_opened = Column(DateTime, nullable=True, index=True)


class BookBookmark(Base):
    __tablename__ = "book_bookmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position = Column(Integer, default=0)
    label = Column(String(200), default="")
    note = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now())
