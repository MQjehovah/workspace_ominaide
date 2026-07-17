from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class TodoCreate(BaseModel):
    title: str
    description: str | None = None
    priority: int = 0
    due_date: str | None = None
    tags: list[str] | None = None


class TodoUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: int | None = None
    due_date: str | None = None
    tags: list[str] | None = None


class TodoResponse(BaseModel):
    id: int
    user_id: int
    title: str
    description: str | None = None
    status: str
    priority: int = 0
    due_date: datetime | None = None
    tags: list[str] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
