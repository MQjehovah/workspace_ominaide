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


async def test_resolve_entity_by_email_alias(client):
    token, user_id = await _new_user(client)
    from ai.entities.models import EntityAlias
    from ai.entities.service import resolve_entity
    from core.database.session import async_session

    async with async_session() as db:
        first = await resolve_entity(db, user_id, "person", "张三", alias_type="name")
        db.add(EntityAlias(
            user_id=user_id,
            entity_id=first.id,
            alias="zhangsan@example.com",
            alias_type="email",
        ))
        await db.flush()
        second = await resolve_entity(
            db, user_id, "person", "zhangsan@example.com", alias_type="email"
        )
        await db.commit()
        assert first.id == second.id


async def test_mention_and_relation_are_user_scoped(client):
    token, user_id = await _new_user(client)
    from ai.entities.service import add_mention, add_relation, resolve_entity
    from core.database.session import async_session

    async with async_session() as db:
        a = await resolve_entity(db, user_id, "person", "张三")
        b = await resolve_entity(db, user_id, "project", "预算评审")
        relation = await add_relation(db, user_id, a.id, b.id, "owns")
        mention = await add_mention(
            db, user_id, a.id,
            source_type="memory",
            source_id=1,
            quote="张三负责预算",
        )
        await db.commit()
        assert mention.entity_id == a.id
        assert relation.from_entity_id == a.id

    other_token, other_user_id = await _new_user(client)
    async with async_session() as db:
        try:
            await add_mention(
                db, other_user_id, a.id,
                source_type="memory",
                source_id=2,
                quote="越权",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("cross-user mention should be rejected")


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
