"""Unified entity graph: entities, aliases, mentions and relations."""

import random
import string

from conftest import auth


async def _new_user(client):
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"entity_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "testpass123",
        },
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "testpass123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def test_entity_tables_and_user_isolation(client):
    token, user_id = await _new_user(client)
    from ai.entities.models import Entity, EntityAlias
    from core.database.session import async_session
    from sqlalchemy import select

    async with async_session() as db:
        row = Entity(user_id=user_id, type="person", canonical_name="张三")
        db.add(row)
        await db.flush()
        db.add(EntityAlias(
            user_id=user_id,
            entity_id=row.id,
            alias="zhangsan@example.com",
            alias_type="email",
        ))
        await db.commit()

    async with async_session() as db:
        rows = list((await db.execute(
            select(Entity).where(Entity.user_id == user_id)
        )).scalars())
        assert len(rows) == 1
        assert rows[0].canonical_name == "张三"
