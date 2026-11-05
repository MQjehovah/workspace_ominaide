from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey,
    UniqueConstraint, func,
)

from core.database.base import Base


class McpServer(Base):
    """A user-registered MCP server managed by the backend hub."""

    __tablename__ = "mcp_servers"
    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_mcp_server_user_slug"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    slug = Column(String(64), nullable=False)
    name = Column(String(120), nullable=False)
    scope = Column(String(20), default="backend")   # backend | desktop
    transport = Column(String(20), default="stdio")  # stdio | http
    command = Column(String(500), nullable=True)
    args = Column(JSON, nullable=True)
    env_encrypted = Column(Text, nullable=True)
    url = Column(String(1000), nullable=True)
    headers_encrypted = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True, index=True)
    auto_start = Column(Boolean, default=True)
    risk_default = Column(String(20), default="read")
    tool_allowlist = Column(JSON, nullable=True)
    last_status = Column(String(20), default="unknown")
    last_error = Column(Text, nullable=True)
    last_connected_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class McpTool(Base):
    """Discovered tool metadata for one MCP server."""

    __tablename__ = "mcp_tools"
    __table_args__ = (
        UniqueConstraint("server_id", "name", name="uq_mcp_tool_server_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(
        Integer, ForeignKey("mcp_servers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    input_schema = Column(JSON, nullable=True)
    risk = Column(String(20), default="read")
    enabled = Column(Boolean, default=True)
    discovered_at = Column(DateTime, server_default=func.now())


class McpCall(Base):
    """Audit trail for external MCP tool calls."""

    __tablename__ = "mcp_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    server_id = Column(Integer, nullable=True, index=True)
    tool_name = Column(String(200), nullable=False)
    arguments = Column(JSON, nullable=True)
    status = Column(String(20), default="ok")
    error = Column(Text, nullable=True)
    duration_ms = Column(Integer, default=0)
    run_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
