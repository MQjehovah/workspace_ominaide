from pydantic import BaseModel
from datetime import datetime


class EventCreate(BaseModel):
    title: str
    start_time: datetime
    end_time: datetime | None = None
    notes: str | None = None
    color: str = "#409EFF"
    remind_before: int = 0


class EventUpdate(BaseModel):
    title: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    notes: str | None = None
    color: str | None = None
    remind_before: int | None = None


class EventResponse(BaseModel):
    id: int
    title: str
    start_time: datetime
    end_time: datetime | None = None
    notes: str | None = None
    color: str = "#409EFF"
    remind_before: int = 0
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
