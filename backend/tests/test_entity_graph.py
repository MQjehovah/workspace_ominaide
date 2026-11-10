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


async def test_same_name_can_belong_to_two_entity_types(client):
    token, user_id = await _new_user(client)
    from ai.entities.service import resolve_entity
    from core.database.session import async_session

    async with async_session() as db:
        person = await resolve_entity(db, user_id, "person", "张三")
        project = await resolve_entity(db, user_id, "project", "张三")
        await db.commit()
    assert person.id != project.id
    assert person.type == "person"
    assert project.type == "project"


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


async def test_seed_profile_creates_person_and_project(client):
    token, user_id = await _new_user(client)
    import json
    from ai.entities.extract import seed_from_profile
    from core.auth.domain.models import UserProfile
    from core.database.session import async_session

    async with async_session() as db:
        profile = await db.get(UserProfile, user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)
            db.add(profile)
            await db.flush()
        profile.contacts = json.dumps([{"name": "张三", "relation": "客户"}])
        profile.projects = json.dumps([{"name": "预算评审"}])
        await db.commit()

        result = await seed_from_profile(db, user_id)
        await db.commit()
        assert result["entities"] >= 2


async def test_memory_edges_backfill_is_idempotent(client):
    token, user_id = await _new_user(client)
    from ai.entities.backfill import backfill_memory_edges
    from ai.memory.models import MemoryEdge, MemoryRecord
    from core.database.session import async_session

    async with async_session() as db:
        memory = MemoryRecord(
            user_id=user_id,
            kind="relationship",
            content="张三负责预算评审",
            normalized="张三负责预算评审",
            confidence=80,
        )
        db.add(memory)
        await db.flush()
        db.add(MemoryEdge(
            user_id=user_id,
            memory_id=memory.id,
            target_type="person",
            target_name="张三",
            relation="mentions",
        ))
        await db.commit()

    first = await backfill_memory_edges()
    second = await backfill_memory_edges()
    assert first["mentions_created"] >= 1
    assert second["mentions_created"] == 0

    from sqlalchemy import select
    from ai.entities.models import Entity, EntityMention
    from core.database.session import async_session

    async with async_session() as db:
        entity = (await db.execute(
            select(Entity).where(
                Entity.user_id == user_id,
                Entity.type == "person",
                Entity.canonical_name == "张三",
            )
        )).scalar_one()
        mention = (await db.execute(
            select(EntityMention).where(
                EntityMention.user_id == user_id,
                EntityMention.entity_id == entity.id,
                EntityMention.source_type == "memory",
            )
        )).scalar_one()
        assert mention.source_id == memory.id
        assert "张三" in (mention.quote or "")


async def test_entity_reads_are_user_scoped(client):
    token_a, user_a = await _new_user(client)
    token_b, user_b = await _new_user(client)
    from ai.entities.service import (
        add_mention,
        mentions_for_entities,
        related_entities,
        resolve_entity,
    )
    from core.database.session import async_session

    async with async_session() as db:
        person = await resolve_entity(db, user_a, "person", "隔离张三")
        project = await resolve_entity(db, user_a, "project", "隔离项目")
        from ai.entities.service import add_relation

        await add_relation(db, user_a, person.id, project.id, "owns")
        await add_mention(
            db, user_a, person.id,
            source_type="memory", source_id=99, quote="隔离测试",
        )
        await db.commit()

    async with async_session() as db:
        assert await mentions_for_entities(db, user_b, [person.id]) == []
        assert await related_entities(db, user_b, [person.id]) == []


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


async def test_canonical_graph_endpoint_and_chat_context(client):
    token, user_id = await _new_user(client)
    from ai.entities.service import add_mention, add_relation, resolve_entity
    from core.database.session import async_session

    async with async_session() as db:
        person = await resolve_entity(db, user_id, "person", "图测试张三")
        project = await resolve_entity(db, user_id, "project", "图测试项目")
        await add_relation(db, user_id, person.id, project.id, "works_on")
        await add_mention(
            db, user_id, person.id,
            source_type="note", source_id=1, quote="图测试张三负责项目",
        )
        await add_mention(
            db, user_id, project.id,
            source_type="note", source_id=1, quote="图测试项目进度",
        )
        await db.commit()

    response = await client.get(
        "/api/memory/entities/graph?q=图测试", headers=auth(token)
    )
    assert response.status_code == 200, response.text
    data = response.json()
    names = {node["name"] for node in data["nodes"]}
    assert {"图测试张三", "图测试项目"} <= names
    assert any(link["relation"] == "works_on" for link in data["links"])

    context = await client.get(
        "/api/context/build?q=图测试张三", headers=auth(token)
    )
    assert context.status_code == 200, context.text
    payload = context.json()
    assert payload["graph"]["entities"]
    assert any(
        relation["relation"] == "works_on"
        for relation in payload["graph"]["relations"]
    )


async def test_merge_entities_moves_aliases_mentions_and_relations(client):
    token, user_id = await _new_user(client)
    from ai.entities.models import Entity, EntityAlias, EntityMention
    from ai.entities.service import add_mention, add_relation, resolve_entity
    from core.database.session import async_session
    from sqlalchemy import select

    async with async_session() as db:
        source = await resolve_entity(db, user_id, "person", "合并前张三")
        target = await resolve_entity(db, user_id, "person", "合并后张三")
        project = await resolve_entity(db, user_id, "project", "合并项目")
        await add_mention(
            db, user_id, source.id,
            source_type="note", source_id=9, quote="合并前张三",
        )
        await add_relation(db, user_id, source.id, project.id, "works_on")
        await db.commit()
        source_id, target_id = source.id, target.id

    response = await client.post(
        f"/api/memory/entities/{source_id}/merge",
        headers=auth(token),
        json={"into_id": target_id},
    )
    assert response.status_code == 200, response.text

    async with async_session() as db:
        merged = await db.get(Entity, source_id)
        assert merged.status == "merged"
        assert merged.merged_into == target_id
        alias = (await db.execute(
            select(EntityAlias).where(
                EntityAlias.entity_id == target_id,
                EntityAlias.alias == "合并前张三",
            )
        )).scalar_one_or_none()
        assert alias is not None
        mention = (await db.execute(
            select(EntityMention).where(
                EntityMention.entity_id == target_id,
                EntityMention.source_type == "note",
                EntityMention.source_id == 9,
            )
        )).scalar_one_or_none()
        assert mention is not None
