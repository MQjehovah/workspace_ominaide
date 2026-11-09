"""Schema upgrade coverage for columns added after create_all."""

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine


async def test_schema_migrations_add_new_columns(tmp_path, monkeypatch):
    import core.database.session as session_module
    from core.database.migrations import ensure_schema_migrations

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE memory_records ("
            "id INTEGER PRIMARY KEY, user_id INTEGER, kind VARCHAR(32), "
            "content TEXT, normalized VARCHAR(600), status VARCHAR(20))"
        ))
        await conn.execute(text(
            "CREATE TABLE memory_candidates ("
            "id INTEGER PRIMARY KEY, user_id INTEGER, kind VARCHAR(32), "
            "content TEXT, normalized VARCHAR(600), status VARCHAR(20))"
        ))
        await conn.execute(text(
            "CREATE TABLE proposals ("
            "id INTEGER PRIMARY KEY, user_id INTEGER, title VARCHAR(200), "
            "status VARCHAR(24), dedupe_key VARCHAR(200))"
        ))

    monkeypatch.setattr(session_module, "engine", engine)
    await ensure_schema_migrations()

    async with engine.connect() as conn:
        def columns(table: str) -> set[str]:
            return {col["name"] for col in inspect(conn.sync_connection).get_columns(table)}

        memory_cols = await conn.run_sync(lambda c: columns("memory_records"))
        candidate_cols = await conn.run_sync(lambda c: columns("memory_candidates"))
        proposal_cols = await conn.run_sync(lambda c: columns("proposals"))

    await engine.dispose()

    assert "data" in memory_cols
    assert "data" in candidate_cols
    assert "source" in proposal_cols
    assert "quality_score" in proposal_cols
