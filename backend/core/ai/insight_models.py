from sqlalchemy import (
    Column,
    Date,
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


class DailyInsight(Base):
    """One day's review for one user.

    Generated from that day's activities and chat messages only. Long-term
    patterns are derived from these daily rows, never by rescanning raw history.
    """

    __tablename__ = "daily_insights"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_daily_insight_user_day"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    day = Column(Date, nullable=False, index=True)
    summary = Column(Text, nullable=False, default="")
    highlights = Column(JSON, nullable=True)
    patterns = Column(JSON, nullable=True)
    suggestions = Column(JSON, nullable=True)
    stats = Column(JSON, nullable=True)
    session_ids = Column(JSON, nullable=True)
    generated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<DailyInsight user_id={self.user_id} day={self.day}>"
