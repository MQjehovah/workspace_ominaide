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
    sync_enabled: bool = True
    folder: str | None = None
    last_uid: int = 0
    last_sync_at: datetime | None = None
    sync_error: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class MailAccountSyncResponse(BaseModel):
    account_id: int
    new: int = 0
    fetched: int = 0
    skipped: bool = False
    error: str | None = None


class MailMessageResponse(BaseModel):
    id: int
    user_id: int
    account_id: int
    uid: int
    message_id: str | None = None
    subject: str | None = None
    from_address: str | None = None
    to_addresses: str | None = None
    cc_addresses: str | None = None
    bcc_addresses: str | None = None
    date: datetime | None = None
    preview: str | None = None
    has_attachments: bool = False
    important: bool = False
    ai_summary: str | None = None
    ai_actions: list | None = None
    read: bool = False
    starred: bool = False
    folder: str = "inbox"
    direction: str = "inbound"
    in_reply_to: str | None = None
    thread_id: str | None = None
    attachments: list | None = None
    sent_at: datetime | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class MailMessageDetail(MailMessageResponse):
    content: str | None = None


class MailSendRequest(BaseModel):
    account_id: int | None = None
    to: list[str]
    cc: list[str] = []
    bcc: list[str] = []
    subject: str
    body: str
    reply_to_id: int | None = None
    attachment_file_ids: list[int] = []


class MailEventCreate(BaseModel):
    account_id: str | None = None
    uid: int | None = None
    subject: str | None = None
    from_address: str | None = None
    date: str | None = None
    preview: str | None = None
    content: str | None = None
    important: bool = False


class MailEventResponse(BaseModel):
    id: int
    user_id: int
    account_id: str | None = None
    uid: int | None = None
    subject: str | None = None
    from_address: str | None = None
    date: str | None = None
    preview: str | None = None
    content: str | None = None
    important: bool = False
    created_at: datetime
    model_config = {"from_attributes": True}
