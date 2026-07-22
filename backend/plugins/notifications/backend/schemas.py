from pydantic import BaseModel
from datetime import datetime

class NotificationResponse(BaseModel):
    id: int
    title: str
    body: str | None = None
    type: str = "info"
    link: str | None = None
    read: bool = False
    created_at: datetime
    model_config = {"from_attributes": True}
