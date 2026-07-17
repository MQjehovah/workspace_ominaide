from pydantic import BaseModel
from datetime import datetime


class PluginInfo(BaseModel):
    name: str
    version: str
    title: str
    description: str | None = None
    icon: str | None = None
    enabled: bool
    installed_at: datetime

    model_config = {"from_attributes": True}


class PluginToggleResponse(BaseModel):
    name: str
    enabled: bool
