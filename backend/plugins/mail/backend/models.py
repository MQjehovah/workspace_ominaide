from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, func
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
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
