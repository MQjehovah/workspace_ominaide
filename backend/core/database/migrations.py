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
    bool_true = "true" if dialect == "postgresql" else "1"

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
            if "bot_id" not in cols:
                result.append("chat_messages_bot")
        if "chat_sessions" in table_names:
            cols = {c["name"] for c in inspector.get_columns("chat_sessions")}
            if "bot_id" not in cols:
                result.append("chat_sessions_bot")
        if "user_profiles" in table_names:
            cols = {c["name"] for c in inspector.get_columns("user_profiles")}
            if "developer" not in cols:
                result.append("user_profiles")
        if "bot_runs" in table_names:
            cols = {c["name"] for c in inspector.get_columns("bot_runs")}
            if "parent_run_id" not in cols:
                result.append("bot_runs_parent")
        if "bot_routines" in table_names:
            cols = {c["name"] for c in inspector.get_columns("bot_routines")}
            if "silent" not in cols:
                result.append("bot_routines_silent")
        if "projects" in table_names:
            cols = {c["name"] for c in inspector.get_columns("projects")}
            if "is_git" not in cols:
                result.append("projects_is_git")
        if "plugin_mail_accounts" in table_names:
            cols = {c["name"] for c in inspector.get_columns("plugin_mail_accounts")}
            if "sync_enabled" not in cols:
                result.append("mail_sync_state")
        if "plugin_todo_items" in table_names:
            cols = {c["name"] for c in inspector.get_columns("plugin_todo_items")}
            if "reminded" not in cols:
                result.append("todo_reminded")
        if "notifications" in table_names:
            cols = {c["name"] for c in inspector.get_columns("notifications")}
            if "actions" not in cols:
                result.append("notification_actions")
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
            elif table == "chat_messages_bot":
                await conn.execute(text("ALTER TABLE chat_messages ADD COLUMN bot_id INTEGER NULL"))
            elif table == "chat_sessions_bot":
                await conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN bot_id INTEGER NULL"))
            elif table == "user_profiles":
                await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN developer TEXT NULL"))
            elif table == "bot_runs_parent":
                await conn.execute(text("ALTER TABLE bot_runs ADD COLUMN parent_run_id INTEGER NULL"))
            elif table == "bot_routines_silent":
                await conn.execute(text(f"ALTER TABLE bot_routines ADD COLUMN silent BOOLEAN DEFAULT {bool_default}"))
            elif table == "projects_is_git":
                await conn.execute(text(f"ALTER TABLE projects ADD COLUMN is_git BOOLEAN DEFAULT {bool_true}"))
            elif table == "mail_sync_state":
                await conn.execute(text(f"ALTER TABLE plugin_mail_accounts ADD COLUMN sync_enabled BOOLEAN DEFAULT {bool_true}"))
                await conn.execute(text("ALTER TABLE plugin_mail_accounts ADD COLUMN folder VARCHAR(100) DEFAULT 'INBOX'"))
                await conn.execute(text("ALTER TABLE plugin_mail_accounts ADD COLUMN last_uid INTEGER DEFAULT 0"))
                await conn.execute(text("ALTER TABLE plugin_mail_accounts ADD COLUMN uidvalidity INTEGER NULL"))
                await conn.execute(text("ALTER TABLE plugin_mail_accounts ADD COLUMN last_sync_at TIMESTAMP NULL"))
                await conn.execute(text("ALTER TABLE plugin_mail_accounts ADD COLUMN sync_error TEXT NULL"))
            elif table == "todo_reminded":
                await conn.execute(text(f"ALTER TABLE plugin_todo_items ADD COLUMN reminded BOOLEAN DEFAULT {bool_default}"))
            elif table == "notification_actions":
                await conn.execute(text("ALTER TABLE notifications ADD COLUMN actions JSON NULL"))
                await conn.execute(text("ALTER TABLE notifications ADD COLUMN dedupe_key VARCHAR(200) NULL"))
                await conn.execute(text("ALTER TABLE notifications ADD COLUMN scheduled_at TIMESTAMP NULL"))
            elif table == "plugin_notes":
                await conn.execute(text("ALTER TABLE plugin_notes MODIFY content LONGTEXT NULL"))
