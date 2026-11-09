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

    # Rename the old RSS tables/plugin before inspecting columns. Existing
    # installations keep their subscriptions and articles.
    async with engine.begin() as conn:
        table_names = set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
        if "rss_feeds" in table_names and "content_sources" not in table_names:
            await conn.execute(text("ALTER TABLE rss_feeds RENAME TO content_sources"))
            table_names.discard("rss_feeds")
            table_names.add("content_sources")
        if "rss_entries" in table_names and "content_items" not in table_names:
            await conn.execute(text("ALTER TABLE rss_entries RENAME TO content_items"))
            table_names.discard("rss_entries")
            table_names.add("content_items")
        if "connector_accounts" in table_names and "oauth_accounts" not in table_names:
            # OAuth accounts moved from core connectors to the oauth plugin.
            await conn.execute(text("ALTER TABLE connector_accounts RENAME TO oauth_accounts"))
            table_names.discard("connector_accounts")
            table_names.add("oauth_accounts")
        elif "connector_accounts" in table_names and "oauth_accounts" in table_names:
            # create_all creates the new table before migrations run, so copy
            # any existing accounts over and drop the old table.
            await conn.execute(text(
                "INSERT INTO oauth_accounts "
                "(user_id, provider, account_id, email, name, access_token, "
                "refresh_token, scopes, expires_at, status, created_at, updated_at) "
                "SELECT c.user_id, c.provider, c.account_id, c.email, c.name, "
                "c.access_token, c.refresh_token, c.scopes, c.expires_at, c.status, "
                "c.created_at, c.updated_at FROM connector_accounts c "
                "WHERE NOT EXISTS (SELECT 1 FROM oauth_accounts o "
                "WHERE o.user_id = c.user_id AND o.provider = c.provider "
                "AND o.account_id = c.account_id)"
            ))
            await conn.execute(text("DROP TABLE connector_accounts"))
            table_names.discard("connector_accounts")
        if "plugin_registry" in table_names:
            await conn.execute(text(
                "UPDATE plugin_registry SET name = 'sources', title = '资讯' "
                "WHERE name = 'rss'"
            ))

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
            if "source" not in cols:
                result.append("schedule_source")
            if "external_id" not in cols:
                result.append("schedule_external_id")
            if "external_meta" not in cols:
                result.append("schedule_external_meta")
            if "location" not in cols:
                result.append("schedule_location")
            if "status" not in cols:
                result.append("schedule_status")
            if "last_synced_at" not in cols:
                result.append("schedule_last_synced")
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
        if "bot_routines" in table_names:
            cols = {c["name"] for c in inspector.get_columns("bot_routines")}
            if "spec" not in cols:
                result.append("bot_routines_spec")
            if "spec_version" not in cols:
                result.append("bot_routines_spec_version")
            if "last_error" not in cols:
                result.append("bot_routines_last_error")
            if "run_count" not in cols:
                result.append("bot_routines_run_count")
        if "bot_runs" in table_names:
            cols = {c["name"] for c in inspector.get_columns("bot_runs")}
            if "parent_run_id" not in cols:
                result.append("bot_runs_parent")
        if "bots" in table_names:
            cols = {c["name"] for c in inspector.get_columns("bots")}
            if "pinned_tools" not in cols:
                result.append("bots_pinned_tools")
        if "mcp_servers" in table_names:
            cols = {c["name"] for c in inspector.get_columns("mcp_servers")}
            if "owner_plugin" not in cols:
                result.append("mcp_servers_owner_plugin")
            if "expose_tools" not in cols:
                result.append("mcp_servers_expose_tools")
        if "request_traces" in table_names:
            cols = {c["name"] for c in inspector.get_columns("request_traces")}
            if "tokens_in" not in cols:
                result.append("request_traces_tokens_in")
            if "tokens_out" not in cols:
                result.append("request_traces_tokens_out")
        if "activity_suggestions" in table_names:
            cols = {c["name"] for c in inspector.get_columns("activity_suggestions")}
            if "proposed_action" not in cols:
                result.append("activity_suggestions_proposed_action")

        if "projects" in table_names:
            cols = {c["name"] for c in inspector.get_columns("projects")}
            if "is_git" not in cols:
                result.append("projects_is_git")
        if "plugin_mail_accounts" in table_names:
            cols = {c["name"] for c in inspector.get_columns("plugin_mail_accounts")}
            if "sync_enabled" not in cols:
                result.append("mail_sync_state")
        if "mail_messages" in table_names:
            cols = {c["name"] for c in inspector.get_columns("mail_messages")}
            if "folder" not in cols:
                result.append("mail_sent_fields")
        if "plugin_todo_items" in table_names:
            cols = {c["name"] for c in inspector.get_columns("plugin_todo_items")}
            if "reminded" not in cols:
                result.append("todo_reminded")
        if "notifications" in table_names:
            cols = {c["name"] for c in inspector.get_columns("notifications")}
            if "actions" not in cols:
                result.append("notification_actions")
        if "content_sources" in table_names:
            cols = {c["name"] for c in inspector.get_columns("content_sources")}
            if "provider" not in cols:
                result.append("content_sources_provider")
            if "config" not in cols:
                result.append("content_sources_config")
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
            elif table == "schedule_source":
                await conn.execute(text("ALTER TABLE schedule_events ADD COLUMN source VARCHAR(20) DEFAULT 'manual'"))
                await conn.execute(text(
                    "UPDATE schedule_events SET source = 'dingtalk' "
                    "WHERE source = 'manual' AND notes LIKE '钉钉同步%'"
                ))
            elif table == "schedule_external_id":
                await conn.execute(text("ALTER TABLE schedule_events ADD COLUMN external_id VARCHAR(200) NULL"))
            elif table == "schedule_external_meta":
                await conn.execute(text("ALTER TABLE schedule_events ADD COLUMN external_meta JSON NULL"))
            elif table == "schedule_location":
                await conn.execute(text("ALTER TABLE schedule_events ADD COLUMN location VARCHAR(500) NULL"))
            elif table == "schedule_status":
                await conn.execute(text("ALTER TABLE schedule_events ADD COLUMN status VARCHAR(20) DEFAULT 'confirmed'"))
            elif table == "schedule_last_synced":
                await conn.execute(text("ALTER TABLE schedule_events ADD COLUMN last_synced_at TIMESTAMP NULL"))
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
            elif table == "bots_pinned_tools":
                await conn.execute(text("ALTER TABLE bots ADD COLUMN pinned_tools JSON NULL"))
            elif table == "mcp_servers_owner_plugin":
                await conn.execute(text("ALTER TABLE mcp_servers ADD COLUMN owner_plugin VARCHAR(64) NULL"))
            elif table == "mcp_servers_expose_tools":
                await conn.execute(text(f"ALTER TABLE mcp_servers ADD COLUMN expose_tools BOOLEAN DEFAULT {bool_true}"))
            elif table == "activity_suggestions_proposed_action":
                await conn.execute(text("ALTER TABLE activity_suggestions ADD COLUMN proposed_action JSON NULL"))
            elif table == "request_traces_tokens_in":
                await conn.execute(text("ALTER TABLE request_traces ADD COLUMN tokens_in INTEGER DEFAULT 0"))
            elif table == "request_traces_tokens_out":
                await conn.execute(text("ALTER TABLE request_traces ADD COLUMN tokens_out INTEGER DEFAULT 0"))
            elif table == "bot_routines_spec":
                await conn.execute(text("ALTER TABLE bot_routines ADD COLUMN spec JSON NULL"))
            elif table == "bot_routines_spec_version":
                await conn.execute(text("ALTER TABLE bot_routines ADD COLUMN spec_version INTEGER DEFAULT 1"))
            elif table == "bot_routines_last_error":
                await conn.execute(text("ALTER TABLE bot_routines ADD COLUMN last_error TEXT NULL"))
            elif table == "bot_routines_run_count":
                await conn.execute(text("ALTER TABLE bot_routines ADD COLUMN run_count INTEGER DEFAULT 0"))
            elif table == "projects_is_git":
                await conn.execute(text(f"ALTER TABLE projects ADD COLUMN is_git BOOLEAN DEFAULT {bool_true}"))
            elif table == "mail_sync_state":
                await conn.execute(text(f"ALTER TABLE plugin_mail_accounts ADD COLUMN sync_enabled BOOLEAN DEFAULT {bool_true}"))
                await conn.execute(text("ALTER TABLE plugin_mail_accounts ADD COLUMN folder VARCHAR(100) DEFAULT 'INBOX'"))
                await conn.execute(text("ALTER TABLE plugin_mail_accounts ADD COLUMN last_uid INTEGER DEFAULT 0"))
                await conn.execute(text("ALTER TABLE plugin_mail_accounts ADD COLUMN uidvalidity INTEGER NULL"))
                await conn.execute(text("ALTER TABLE plugin_mail_accounts ADD COLUMN last_sync_at TIMESTAMP NULL"))
                await conn.execute(text("ALTER TABLE plugin_mail_accounts ADD COLUMN sync_error TEXT NULL"))
            elif table == "mail_sent_fields":
                await conn.execute(text("ALTER TABLE mail_messages ADD COLUMN folder VARCHAR(20) DEFAULT 'inbox'"))
                await conn.execute(text("ALTER TABLE mail_messages ADD COLUMN direction VARCHAR(20) DEFAULT 'inbound'"))
                await conn.execute(text("ALTER TABLE mail_messages ADD COLUMN in_reply_to VARCHAR(500) NULL"))
                await conn.execute(text("ALTER TABLE mail_messages ADD COLUMN thread_id VARCHAR(500) NULL"))
                await conn.execute(text("ALTER TABLE mail_messages ADD COLUMN cc_addresses TEXT NULL"))
                await conn.execute(text("ALTER TABLE mail_messages ADD COLUMN bcc_addresses TEXT NULL"))
                await conn.execute(text("ALTER TABLE mail_messages ADD COLUMN attachments JSON NULL"))
                await conn.execute(text("ALTER TABLE mail_messages ADD COLUMN sent_at TIMESTAMP NULL"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_mail_messages_folder ON mail_messages (folder)"))
            elif table == "todo_reminded":
                await conn.execute(text(f"ALTER TABLE plugin_todo_items ADD COLUMN reminded BOOLEAN DEFAULT {bool_default}"))
            elif table == "notification_actions":
                await conn.execute(text("ALTER TABLE notifications ADD COLUMN actions JSON NULL"))
                await conn.execute(text("ALTER TABLE notifications ADD COLUMN dedupe_key VARCHAR(200) NULL"))
                await conn.execute(text("ALTER TABLE notifications ADD COLUMN scheduled_at TIMESTAMP NULL"))
            elif table == "content_sources_provider":
                await conn.execute(text(
                    "ALTER TABLE content_sources ADD COLUMN provider VARCHAR(50) DEFAULT 'rss'"
                ))
            elif table == "content_sources_config":
                await conn.execute(text(
                    "ALTER TABLE content_sources ADD COLUMN config JSON NULL"
                ))
            elif table == "plugin_notes":
                await conn.execute(text("ALTER TABLE plugin_notes MODIFY content LONGTEXT NULL"))
