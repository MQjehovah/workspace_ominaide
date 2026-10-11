from sqlalchemy import inspect, text


async def ensure_schema_migrations():
    """Apply lightweight schema migrations for existing databases.

    `Base.metadata.create_all` only creates missing tables, not missing columns,
    so columns added after a table already exists need explicit ALTER TABLE.
    The DDL below is dialect-aware (PostgreSQL / MySQL).
    """
    from core.database.session import engine

    dialect = engine.dialect.name  # "postgresql" | "mysql" | "sqlite"
    bool_default = "false" if dialect == "postgresql" else "0"

    def _needed_columns(sync_conn) -> list[str]:
        inspector = inspect(sync_conn)
        result = []
        table_names = inspector.get_table_names()
        if "users" in table_names:
            cols = {c["name"] for c in inspector.get_columns("users")}
            if "is_admin" not in cols:
                result.append("users")
        if "schedule_events" in table_names:
            cols = {c["name"] for c in inspector.get_columns("schedule_events")}
            if "reminded" not in cols:
                result.append("schedule_events")
        if "chat_messages" in table_names:
            cols = {c["name"] for c in inspector.get_columns("chat_messages")}
            if "session_id" not in cols:
                result.append("chat_messages")
        # LONGTEXT widening is only meaningful on MySQL; PostgreSQL TEXT is unbounded.
        if dialect == "mysql" and "plugin_notes" in table_names:
            cols = {c["name"]: c["type"] for c in inspector.get_columns("plugin_notes")}
            content_type = str(cols.get("content", "")).lower()
            if content_type and "longtext" not in content_type and "mediumtext" not in content_type:
                result.append("plugin_notes")
        return result

    async with engine.begin() as conn:
        tables = await conn.run_sync(_needed_columns)
        for table in tables:
            if table == "users":
                await conn.execute(text(f"ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT {bool_default}"))
            elif table == "schedule_events":
                await conn.execute(text(f"ALTER TABLE schedule_events ADD COLUMN reminded BOOLEAN DEFAULT {bool_default}"))
            elif table == "chat_messages":
                await conn.execute(text("ALTER TABLE chat_messages ADD COLUMN session_id VARCHAR(64) DEFAULT 'default'"))
            elif table == "plugin_notes":
                await conn.execute(text("ALTER TABLE plugin_notes MODIFY content LONGTEXT NULL"))
