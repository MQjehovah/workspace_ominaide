from pydantic import BaseModel
from datetime import datetime


class MailAccountCreate(BaseModel):
    name: str = ""
    email: str
    imap_host: str
    imap_port: int = 993
    imap_tls: bool = True
    smtp_host: str
    smtp_port: int = 465
    smtp_tls: bool = True
    username: str
    password: str


class MailAccountUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    imap_tls: bool | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_tls: bool | None = None
    username: str | None = None
    password: str | None = None


class MailAccountResponse(BaseModel):
    id: int
    user_id: int
    name: str
    email: str
    imap_host: str
    imap_port: int
    imap_tls: bool
    smtp_host: str
    smtp_port: int
    smtp_tls: bool
    username: str
    password: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
