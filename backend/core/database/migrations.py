from sqlalchemy import inspect, text


async def ensure_schema_migrations():
    """Apply lightweight schema migrations for existing databases.

    `Base.metadata.create_all` only creates missing tables, not missing columns,
    so columns added after a table already exists need explicit ALTER TABLE.
    """
    from core.database.session import engine

    def _needed_columns(sync_conn) -> list[str]:
        inspector = inspect(sync_conn)
        result = []
        if "users" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("users")}
            if "is_admin" not in cols:
                result.append("users")
        if "schedule_events" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("schedule_events")}
            if "reminded" not in cols:
                result.append("schedule_events")
        if "plugin_notes" in inspector.get_table_names():
            cols = {c["name"]: c["type"] for c in inspector.get_columns("plugin_notes")}
            content_type = str(cols.get("content", "")).lower()
            if content_type and "longtext" not in content_type and "mediumtext" not in content_type:
                result.append("plugin_notes")
        return result

    async with engine.begin() as conn:
        tables = await conn.run_sync(_needed_columns)
        for table in tables:
            if table == "users":
                await conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0"))
            elif table == "schedule_events":
                await conn.execute(text("ALTER TABLE schedule_events ADD COLUMN reminded BOOLEAN DEFAULT 0"))
            elif table == "plugin_notes":
                await conn.execute(text("ALTER TABLE plugin_notes MODIFY content LONGTEXT NULL"))
