from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database.session import get_db
from plugins.books.backend import service
from plugins.books.backend.schemas import (
    AddBookRequest,
    BookmarkRequest,
    BookmarkResponse,
    BookContentResponse,
    BookResponse,
    ProgressRequest,
)

router = APIRouter(prefix="/api/books", tags=["books"])


@router.get("")
async def list_books(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await service.list_books(db, user["id"])
    return {"books": [service.to_response(row) for row in rows]}


@router.post("", status_code=201)
async def add_book(
    req: AddBookRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        book = await service.add_book(db, user["id"], req.file_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"导入失败: {exc}")
    return service.to_response(book)


@router.get("/{book_id}")
async def get_book(
    book_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    book = await service.get_book(db, user["id"], book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return service.to_response(book)


@router.get("/{book_id}/content")
async def get_content(
    book_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await service.open_book(db, user["id"], book_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Book not found")
    book, bookmarks = result
    return service.to_content(book, bookmarks)


@router.put("/{book_id}/progress")
async def update_progress(
    book_id: int,
    req: ProgressRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    book = await service.update_progress(
        db,
        user["id"],
        book_id,
        position=req.position,
        progress=req.progress,
        status=req.status,
    )
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return service.to_response(book)


@router.delete("/{book_id}")
async def delete_book(
    book_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await service.delete_book(db, user["id"], book_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Book not found")
    return {"message": "Book deleted"}


@router.get("/{book_id}/bookmarks")
async def list_bookmarks(
    book_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    book = await service.get_book(db, user["id"], book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    rows = await service.list_bookmarks(db, book_id)
    return {"bookmarks": [service.to_bookmark(row) for row in rows]}


@router.post("/{book_id}/bookmarks", status_code=201)
async def add_bookmark(
    book_id: int,
    req: BookmarkRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await service.add_bookmark(
        db,
        user["id"],
        book_id,
        position=req.position,
        label=req.label,
        note=req.note,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return service.to_bookmark(row)


@router.delete("/{book_id}/bookmarks/{bookmark_id}")
async def delete_bookmark(
    book_id: int,
    bookmark_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await service.delete_bookmark(db, user["id"], book_id, bookmark_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return {"message": "Bookmark deleted"}
