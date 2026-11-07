from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    UniqueConstraint,
    func,
)
from core.database.base import Base


class MailAccount(Base):
    __tablename__ = "plugin_mail_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False, default="")
    email = Column(String(200), nullable=False)
    imap_host = Column(String(200), nullable=False)
    imap_port = Column(Integer, default=993)
    imap_tls = Column(Boolean, default=True)
    smtp_host = Column(String(200), nullable=False)
    smtp_port = Column(Integer, default=465)
    smtp_tls = Column(Boolean, default=True)
    username = Column(String(200), nullable=False)
    password = Column(String(500), nullable=False)
    # Server-side IMAP sync state. The backend is the source of truth; desktop
    # clients only read cached messages from the API.
    sync_enabled = Column(Boolean, default=True)
    folder = Column(String(100), default="INBOX")
    last_uid = Column(Integer, default=0)
    uidvalidity = Column(Integer, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    sync_error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class MailMessage(Base):
    """A message pulled by the backend IMAP synchroniser."""

    __tablename__ = "mail_messages"
    __table_args__ = (
        UniqueConstraint("account_id", "uid", name="uq_mail_message_account_uid"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    account_id = Column(
        Integer, ForeignKey("plugin_mail_accounts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    uid = Column(Integer, nullable=False)
    uidvalidity = Column(Integer, nullable=True)
    message_id = Column(String(500), nullable=True)
    subject = Column(String(500), nullable=True)
    from_address = Column(String(500), nullable=True)
    to_addresses = Column(Text, nullable=True)
    date = Column(DateTime, nullable=True)
    preview = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    has_attachments = Column(Boolean, default=False)
    important = Column(Boolean, default=False)
    ai_summary = Column(Text, nullable=True)
    ai_actions = Column(JSON, nullable=True)
    read = Column(Boolean, default=False)
    starred = Column(Boolean, default=False)
    folder = Column(String(20), default="inbox", index=True)
    direction = Column(String(20), default="inbound")
    in_reply_to = Column(String(500), nullable=True)
    thread_id = Column(String(500), nullable=True)
    cc_addresses = Column(Text, nullable=True)
    bcc_addresses = Column(Text, nullable=True)
    attachments = Column(JSON, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<MailMessage id={self.id} uid={self.uid} subject={self.subject}>"


class MailEvent(Base):
    """A received email reported by the desktop client for AI access."""
    __tablename__ = "mail_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    account_id = Column(String(100), nullable=True)
    uid = Column(Integer, nullable=True)
    subject = Column(String(500), nullable=True)
    from_address = Column(String(500), nullable=True)
    date = Column(String(100), nullable=True)
    preview = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    important = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<MailEvent id={self.id} user_id={self.user_id} subject={self.subject}>"
