from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
)

from core.database.base import Base


class BotSkill(Base):
    """Per-bot skill enablement. Skill content lives on disk (SKILL.md)."""

    __tablename__ = "bot_skills"
    __table_args__ = (
        UniqueConstraint("bot_id", "skill_key", name="uq_bot_skills_bot_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(
        Integer,
        ForeignKey("bots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    skill_key = Column(String(80), nullable=False, index=True)
    enabled = Column(Boolean, default=True, nullable=False)
    config = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
