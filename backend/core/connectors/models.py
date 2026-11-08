from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)

from core.database.base import Base


class ConnectorAccount(Base):
    """One OAuth account connected to an external provider."""

    __tablename__ = "connector_accounts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", "account_id",
            name="uq_connector_user_provider_account",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String(32), nullable=False, index=True)
    account_id = Column(String(200), nullable=False)
    email = Column(String(255), nullable=True)
    name = Column(String(200), nullable=True)
    access_token = Column(Text, nullable=False, default="")
    refresh_token = Column(Text, nullable=True)
    scopes = Column(JSON, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
