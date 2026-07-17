from pydantic import BaseModel
from datetime import datetime


class NoteCreate(BaseModel):
    title: str = "无标题"
    content: str = ""
    parent_id: int | None = None
    is_folder: bool = False
    icon: str | None = None


class NoteUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    parent_id: int | None = None
    is_folder: bool | None = None
    icon: str | None = None
    sort_order: int | None = None


class NoteResponse(BaseModel):
    id: int
    user_id: int
    title: str
    content: str | None = ""
    parent_id: int | None = None
    is_folder: bool = False
    icon: str | None = None
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
