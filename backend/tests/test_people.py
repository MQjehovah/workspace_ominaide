"""People index, timeline and merge."""

import random
import string


async def _uid(client):
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"person_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    uid = r.json()["user_id"]
    return uid


async def test_people_timeline_and_merge(client):
    uid = await _uid(client)
    from core.people import service

    person = await service.upsert_person(uid, "张三", email="zhang@example.com")
    await service.add_mention(
        uid, person.id, source_type="mail", source_id=1,
        title="预算评审", snippet="周五前给回复", role="from",
    )
    await service.add_mention(
        uid, person.id, source_type="event", source_id=2,
        title="项目会", snippet="讨论预算", role="attendee",
    )

    people = await service.list_people(uid)
    assert any(p["display_name"] == "张三" and p["mention_count"] == 2 for p in people)

    items = await service.timeline(uid, person.id)
    assert {item["type"] for item in items} == {"mail", "event"}

    duplicate = await service.upsert_person(uid, "张三", email="other@example.com")
    # Same normalized name resolves to the same person.
    assert duplicate.id == person.id

    other = await service.upsert_person(uid, "李四")
    assert await service.merge_people(uid, person.id, other.id)


async def test_people_are_user_scoped(client):
    uid_a = await _uid(client)
    uid_b = await _uid(client)
    from core.people import service

    person = await service.upsert_person(uid_a, "王五")
    assert await service.get_person(uid_b, person.id) is None
    assert all(p["id"] != person.id for p in await service.list_people(uid_b))
