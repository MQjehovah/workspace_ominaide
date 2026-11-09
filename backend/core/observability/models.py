from sqlalchemy import Column, DateTime, Index, Integer, String, Text, func

from core.database.base import Base


class RequestTrace(Base):
    __tablename__ = "request_traces"
    __table_args__ = (
        Index("ix_request_traces_kind_created", "kind", "created_at"),
        Index("ix_request_traces_user_created", "user_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(64), nullable=False, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    kind = Column(String(20), nullable=False, default="request", index=True)
    name = Column(String(300), nullable=False)
    method = Column(String(10), nullable=True)
    status = Column(String(20), nullable=False, default="ok")
    status_code = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=False, default=0)
    tokens_in = Column(Integer, nullable=False, default=0)
    tokens_out = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
