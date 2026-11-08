from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)

from core.database.base import Base


class Machine(Base):
    """A desktop computer that can execute local tools for one user."""

    __tablename__ = "machines"
    __table_args__ = (
        UniqueConstraint("user_id", "machine_id", name="uq_machine_user_machine"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    machine_id = Column(String(100), nullable=False, index=True)
    # User-chosen display name. Empty means "use default_name" (the hostname).
    name = Column(String(120), nullable=True)
    default_name = Column(String(120), nullable=False, default="")
    platform = Column(String(32), default="desktop")
    first_seen = Column(DateTime, server_default=func.now())
    last_seen = Column(DateTime, server_default=func.now())

    def display_name(self) -> str:
        return (self.name or "").strip() or self.default_name or self.machine_id
