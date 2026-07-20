from pydantic import BaseModel
from datetime import datetime


# ---- Sync Events ----

class SyncEventResponse(BaseModel):
    id: int
    workspace_id: int | None = None
    event_type: str
    file_path: str
    file_size: int | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SyncEventListResponse(BaseModel):
    events: list[SyncEventResponse]
    total: int


# ---- Sync Folders ----

class SyncFolderCreate(BaseModel):
    server_path: str
    local_path: str


class SyncFolderUpdate(BaseModel):
    enabled: bool


class SyncFolderResponse(BaseModel):
    id: int
    server_path: str
    local_path: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SyncFolderListResponse(BaseModel):
    folders: list[SyncFolderResponse]
