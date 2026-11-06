from pydantic import BaseModel
from datetime import datetime


class SourceCreate(BaseModel):
    provider: str = "rss"
    url: str | None = None
    config: dict | None = None


class SourceResponse(BaseModel):
    id: int
    user_id: int
    provider: str
    config: dict | None = None
    url: str
    title: str | None = None
    icon: str | None = None
    last_fetch: datetime | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class ItemResponse(BaseModel):
    id: int
    source_id: int
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
    source_title: str | None = None
    model_config = {"from_attributes": True}


class ProviderResponse(BaseModel):
    key: str
    label: str
    config_schema: dict
