import asyncio
from core.database.session import engine
from core.database.base import Base
# Import all models to ensure they're registered
import core.plugin.models  # noqa
import domains.auth.models  # noqa
import domains.file.models  # noqa
import domains.workspace.models  # noqa
import domains.sync.models  # noqa
import plugins.todo.backend.models  # noqa
import plugins.notes.backend.models  # noqa
import core.database.redis  # noqa


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
