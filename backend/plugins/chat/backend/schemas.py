from pydantic import BaseModel
from datetime import datetime


class ChatMessage(BaseModel):
    role: str
    content: str


class ObjectRef(BaseModel):
    type: str
    id: int


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] | None = None
    images: list[str] | None = None
    session_id: str | None = None
    bot_id: int | None = None
    machine_id: str | None = None
    client_kind: str | None = None
    context_refs: list[ObjectRef] | None = None
    context_comment_id: int | None = None


class ChatResponse(BaseModel):
    reply: str


class ChatHistoryItem(BaseModel):
    id: int
    role: str
    kind: str | None = None
    content: str
    run_id: int | None = None
    created_at: datetime
    bot_id: int | None = None

    model_config = {"from_attributes": True}


class TranslateRequest(BaseModel):
    text: str
    target: str = "zh"  # zh | en | ja | etc.


class TranslateResponse(BaseModel):
    text: str
    translated: str


class AsrResponse(BaseModel):
    text: str


class TtsRequest(BaseModel):
    text: str
    voice: str | None = None
    model: str | None = None
    format: str | None = None


class SessionItem(BaseModel):
    session_id: str
    title: str | None = None
    status: str | None = None
    updated_at: datetime | None = None
    bot_id: int | None = None

    model_config = {"from_attributes": True}


class SessionRename(BaseModel):
    title: str
