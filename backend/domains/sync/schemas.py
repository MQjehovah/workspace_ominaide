from pydantic import BaseModel
from datetime import datetime


class SyncEventResponse(BaseModel):
    id: int
    workspace_id: int
    event_type: str
    file_path: str
    file_size: int | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SyncEventListResponse(BaseModel):
    events: list[SyncEventResponse]
    total: int
