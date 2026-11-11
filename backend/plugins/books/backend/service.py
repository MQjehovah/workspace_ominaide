"""Book library: file-backed ebooks, reading progress, bookmarks."""

from __future__ import annotations

import asyncio
import html as html_lib
import io
import posixpath
import re
import zipfile
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import defer
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from plugins.books.backend.models import Book, BookBookmark
from plugins.books.backend.schemas import (
    BookContentResponse,
    BookmarkResponse,
    BookResponse,
)

log = get_logger(__name__)

MAX_TEXT_CHARS = 4_000_000
MAX_SOURCE_BYTES = 120 * 1024 * 1024
SUPPORTED = {"epub", "pdf", "txt", "md", "markdown", "docx"}


def _clean(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _paragraphs(text: str) -> int:
    return len([part for part in text.split("\n\n") if part.strip()])


def _extract_pdf(data: bytes) -> tuple[str, str, str]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            raise ValueError("PDF 有密码，暂不支持")
    title = ""
    author = ""
    try:
        meta = reader.metadata
        if meta is not None:
            title = str(meta.title or "").strip()
            author = str(meta.author or "").strip()
    except Exception:
        pass
    parts: list[str] = []
    for index, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            parts.append(f"## 第 {index} 页\n\n{text.strip()}")
    return title, author, "\n\n".join(parts)


def _extract_docx(data: bytes) -> tuple[str, str, str]:
    import docx

    document = docx.Document(io.BytesIO(data))
    parts = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append("| " + " | ".join(cells) + " |")
    return "", "", "\n\n".join(parts)


def _extract_epub(data: bytes) -> tuple[str, str, str]:
    from bs4 import BeautifulSoup

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        opf_path = None
        if "META-INF/container.xml" in names:
            container = archive.read("META-INF/container.xml").decode(
                "utf-8", "ignore"
            )
            match = re.search(r'full-path=["\']([^"\']+)["\']', container)
            if match:
                opf_path = match.group(1)
        if not opf_path:
            for name in names:
                if name.lower().endswith(".opf"):
                    opf_path = name
                    break
        if not opf_path or opf_path not in names:
            raise ValueError("EPUB 结构不完整（缺少 OPF）")
        opf = archive.read(opf_path).decode("utf-8", "ignore")

        title = ""
        author = ""
        match = re.search(r"<dc:title[^>]*>(.*?)</dc:title>", opf, re.S | re.I)
        if match:
            title = BeautifulSoup(match.group(1), "html.parser").get_text(" ").strip()
        match = re.search(r"<dc:creator[^>]*>(.*?)</dc:creator>", opf, re.S | re.I)
        if match:
            author = BeautifulSoup(match.group(1), "html.parser").get_text(" ").strip()

        manifest: dict[str, str] = {}
        for tag in re.findall(r"<item\b[^>]*>", opf, re.I):
            id_match = re.search(r'\bid=["\']([^"\']+)', tag, re.I)
            href_match = re.search(r'\bhref=["\']([^"\']+)', tag, re.I)
            if id_match and href_match:
                manifest[id_match.group(1)] = html_lib.unescape(href_match.group(1))

        spine: list[str] = []
        for match in re.finditer(r'<itemref\b[^>]*idref=["\']([^"\']+)', opf, re.I):
            href = manifest.get(match.group(1))
            if href:
                spine.append(href)
        if not spine:
            spine = [
                name
                for name in archive.namelist()
                if name.lower().endswith((".xhtml", ".html", ".htm"))
            ]

        base = posixpath.dirname(opf_path)
        parts: list[str] = []
        for href in spine:
            path = posixpath.normpath(posixpath.join(base, href.split("#")[0]))
            if path not in names:
                continue
            markup = archive.read(path).decode("utf-8", "ignore")
            soup = BeautifulSoup(markup, "html.parser")
            for tag in soup(["script", "style", "nav"]):
                tag.decompose()
            text = _clean(soup.get_text("\n"))
            if text:
                parts.append(text)
        return title, author, "\n\n".join(parts)


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except Exception:
            continue
    return data.decode("utf-8", "ignore")


def _extract(filename: str, data: bytes) -> tuple[str, str, str, str]:
    """Return (title, author, format, text) for a book file."""
    name = (filename or "book.txt").split("/")[-1]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "txt"
    stem = name.rsplit(".", 1)[0] if "." in name else name
    if ext not in SUPPORTED:
        raise ValueError("暂不支持该格式（支持 EPUB / PDF / TXT / MD / DOCX）")
    if ext == "pdf":
        title, author, text = _extract_pdf(data)
    elif ext == "docx":
        title, author, text = _extract_docx(data)
    elif ext == "epub":
        title, author, text = _extract_epub(data)
    else:
        title, author, text = "", "", _decode_text(data)
    text = _clean(text)[:MAX_TEXT_CHARS]
    if not text.strip():
        raise ValueError("没有从这本书里提取到文字（可能是扫描版）")
    return title or stem, author, ext, text


def _read_object(file_row) -> bytes:
    from core.minio.client import minio_client

    if minio_client is None:
        raise ValueError("MinIO 不可用，无法读取电子书")
    response = minio_client.get_object(file_row.bucket, file_row.object_key)
    try:
        return response.read()
    finally:
        try:
            response.close()
            response.release_conn()
        except Exception:
            pass


def to_response(book: Book) -> BookResponse:
    return BookResponse(
        id=book.id,
        file_id=book.file_id,
        title=book.title or "未命名书籍",
        author=book.author or "",
        format=book.format or "txt",
        status=book.status or "unread",
        progress=float(book.progress or 0),
        position=int(book.position or 0),
        paragraph_count=int(book.paragraph_count or 0),
        created_at=book.created_at,
        updated_at=book.updated_at,
        last_opened=book.last_opened,
    )


def to_content(book: Book, bookmarks: list[BookBookmark]) -> BookContentResponse:
    base = to_response(book)
    return BookContentResponse(
        **base.model_dump(),
        content=book.content or "",
        bookmarks=[to_bookmark(row) for row in bookmarks],
    )


def to_bookmark(row: BookBookmark) -> BookmarkResponse:
    return BookmarkResponse(
        id=row.id,
        position=row.position or 0,
        label=row.label or "",
        note=row.note or "",
        created_at=row.created_at,
    )


async def list_books(db: AsyncSession, user_id: int) -> list[Book]:
    rows = await db.execute(
        select(Book)
        .where(Book.user_id == user_id)
        .options(defer(Book.content))
        .order_by(Book.last_opened.desc().nullslast(), Book.created_at.desc())
    )
    return list(rows.scalars().all())


async def get_book(db: AsyncSession, user_id: int, book_id: int) -> Book | None:
    row = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user_id)
    )
    return row.scalar_one_or_none()


async def add_book(db: AsyncSession, user_id: int, file_id: int) -> Book:
    from plugins.files.backend.models import File

    file_row = await db.get(File, file_id)
    if (
        file_row is None
        or file_row.user_id != user_id
        or (file_row.status or "active") != "active"
    ):
        raise ValueError("文件不存在")

    existing = (await db.execute(
        select(Book).where(Book.user_id == user_id, Book.file_id == file_id)
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    data = await asyncio.to_thread(_read_object, file_row)
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("电子书超过 120MB")
    title, author, fmt, text = await asyncio.to_thread(
        _extract, file_row.original_name or "book.txt", data
    )
    book = Book(
        user_id=user_id,
        file_id=file_id,
        title=title[:500],
        author=author[:300],
        format=fmt[:16],
        content=text,
        status="unread",
        progress=0.0,
        position=0,
        paragraph_count=_paragraphs(text),
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)
    return book


async def delete_book(db: AsyncSession, user_id: int, book_id: int) -> bool:
    book = await get_book(db, user_id, book_id)
    if book is None:
        return False
    await db.delete(book)
    await db.commit()
    return True


async def open_book(
    db: AsyncSession, user_id: int, book_id: int
) -> tuple[Book, list[BookBookmark]] | None:
    book = await get_book(db, user_id, book_id)
    if book is None:
        return None
    if (book.status or "unread") == "unread":
        book.status = "reading"
    book.last_opened = datetime.now()
    await db.commit()
    await db.refresh(book)
    rows = await db.execute(
        select(BookBookmark)
        .where(BookBookmark.book_id == book_id)
        .order_by(BookBookmark.position, BookBookmark.id)
    )
    return book, list(rows.scalars().all())


async def update_progress(
    db: AsyncSession,
    user_id: int,
    book_id: int,
    *,
    position: int,
    progress: float,
    status: str | None = None,
) -> Book | None:
    book = await get_book(db, user_id, book_id)
    if book is None:
        return None
    book.position = max(0, int(position))
    book.progress = max(0.0, min(1.0, float(progress)))
    if status in {"unread", "reading", "finished"}:
        book.status = status
    elif book.progress >= 0.995:
        book.status = "finished"
    else:
        book.status = "reading"
    book.last_opened = datetime.now()
    await db.commit()
    await db.refresh(book)
    return book


async def list_bookmarks(
    db: AsyncSession, book_id: int
) -> list[BookBookmark]:
    rows = await db.execute(
        select(BookBookmark)
        .where(BookBookmark.book_id == book_id)
        .order_by(BookBookmark.position, BookBookmark.id)
    )
    return list(rows.scalars().all())


async def add_bookmark(
    db: AsyncSession,
    user_id: int,
    book_id: int,
    *,
    position: int,
    label: str,
    note: str,
) -> BookBookmark | None:
    book = await get_book(db, user_id, book_id)
    if book is None:
        return None
    row = BookBookmark(
        book_id=book_id,
        position=max(0, int(position)),
        label=(label or "").strip()[:200],
        note=(note or "").strip()[:4000],
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_bookmark(
    db: AsyncSession, user_id: int, book_id: int, bookmark_id: int
) -> bool:
    book = await get_book(db, user_id, book_id)
    if book is None:
        return False
    row = await db.get(BookBookmark, bookmark_id)
    if row is None or row.book_id != book_id:
        return False
    await db.delete(row)
    await db.commit()
    return True
