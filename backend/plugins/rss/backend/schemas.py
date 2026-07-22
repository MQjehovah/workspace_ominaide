from pydantic import BaseModel
from datetime import datetime


class FeedCreate(BaseModel):
    url: str


class FeedResponse(BaseModel):
    id: int
    url: str
    title: str | None = None
    icon: str | None = None
    last_fetch: datetime | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class EntryResponse(BaseModel):
    id: int
    feed_id: int
    guid: str
    title: str
    link: str | None = None
    summary: str | None = None
    content: str | None = None
    author: str | None = None
    published: datetime | None = None
    read: bool = False
    starred: bool = False
    created_at: datetime
    model_config = {"from_attributes": True}


class SearchParams(BaseModel):
    q: str
    feed_id: int | None = None
    page: int = 1
    page_size: int = 20
