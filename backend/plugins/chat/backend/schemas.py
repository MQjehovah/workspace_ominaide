from pydantic import BaseModel
from datetime import datetime


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] | None = None
    images: list[str] | None = None


class ChatResponse(BaseModel):
    reply: str


class ChatHistoryItem(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TranslateRequest(BaseModel):
    text: str
    target: str = "zh"  # zh | en | ja | etc.


class TranslateResponse(BaseModel):
    text: str
    translated: str
