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


class WeeklyReview(Base):
    """One week's review for one user, generated from daily insights."""

    __tablename__ = "weekly_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_weekly_review_user_start"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    week_start = Column(Date, nullable=False, index=True)
    week_end = Column(Date, nullable=False)
    summary = Column(Text, nullable=False, default="")
    wins = Column(JSON, nullable=True)
    in_progress = Column(JSON, nullable=True)
    risks = Column(JSON, nullable=True)
    next_week = Column(JSON, nullable=True)
    stats = Column(JSON, nullable=True)
    generated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<WeeklyReview user_id={self.user_id} week_start={self.week_start}>"
