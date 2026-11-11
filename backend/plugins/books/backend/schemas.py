from datetime import datetime

from pydantic import BaseModel, Field


class AddBookRequest(BaseModel):
    file_id: int


class ProgressRequest(BaseModel):
    position: int = Field(default=0, ge=0)
    progress: float = Field(default=0, ge=0, le=1)
    status: str | None = None


class BookmarkRequest(BaseModel):
    position: int = Field(default=0, ge=0)
    label: str = Field(default="", max_length=200)
    note: str = Field(default="", max_length=4000)


class BookmarkResponse(BaseModel):
    id: int
    position: int
    label: str
    note: str
    created_at: datetime | None = None


class BookResponse(BaseModel):
    id: int
    file_id: int
    title: str
    author: str
    format: str
    status: str
    progress: float
    position: int
    paragraph_count: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_opened: datetime | None = None


class BookContentResponse(BookResponse):
    content: str
    bookmarks: list[BookmarkResponse] = []
