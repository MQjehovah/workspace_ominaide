import asyncio
from core.database.session import engine
from core.database.base import Base
# Import all models to ensure they're registered
import core.plugin.models  # noqa
import core.auth.domain.models  # noqa
import plugins.files.backend.models  # noqa
import plugins.files.backend.sync_models  # noqa
import plugins.todo.backend.models  # noqa
import plugins.notes.backend.models  # noqa
import plugins.music.backend.models  # noqa
import plugins.mail.backend.models  # noqa
import core.database.redis  # noqa
import activities.models  # noqa
import plugins.notifications.backend.models  # noqa
import plugins.chat.backend.models  # noqa
import app.objects.models  # noqa
import plugins.sources.backend.models  # noqa
import ai.memory.models  # noqa
import ai.cognition.models  # noqa
import ai.mcp_hub.models  # noqa
import ai.insights.review_models  # noqa
import ai.memory.graph.models  # noqa
import core.jobs.models  # noqa
import core.observability.models  # noqa
import ai.skills.models  # noqa
import plugins.meetings.backend.models  # noqa
import ai.bots.models  # noqa
import ai.automation.models  # noqa
import plugins.captures.backend.models  # noqa
import ai.memory.people.models  # noqa
import ai.coding.models  # noqa
import plugins.schedule.backend.models  # noqa
import plugins.projects.backend.models  # noqa


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    from core.database.migrations import ensure_schema_migrations
    await ensure_schema_migrations()
    print("Database tables created.")


async def drop_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("Database tables dropped.")


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "init":
        asyncio.run(init_db())
    elif cmd == "drop":
        asyncio.run(drop_db())
    else:
        print("Usage: python manage.py [init|drop]")
