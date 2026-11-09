from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func

from core.database.base import Base


class CodingRun(Base):
    """Coding-specific extension for one generic ``runs`` row."""

    __tablename__ = "coding_runs"

    run_id = Column(
        Integer,
        ForeignKey("runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_path = Column(String(500), nullable=False, index=True)
    branch = Column(String(200), nullable=True)
    engine = Column(String(20), default="builtin", nullable=False)
    created_at = Column(DateTime, server_default=func.now())
