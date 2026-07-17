from pydantic import BaseModel
from datetime import datetime


class WorkspaceCreate(BaseModel):
    name: str
    description: str | None = None
    sync_enabled: bool = False


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    sync_enabled: bool | None = None


class WorkspaceResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: str | None = None
    bucket: str
    sync_enabled: bool = False
    local_path: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
