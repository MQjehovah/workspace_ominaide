"""RSS articles are reading material, not user entities."""


def test_rss_only_entities_are_external():
    from core.memory_router import _is_external_entity

    assert _is_external_entity({"sources": [{"type": "rss", "id": 1}]}) is True
    assert _is_external_entity({"sources": [{"type": "rss_entry", "id": 1}]}) is True
    assert _is_external_entity({"sources": [{"type": "article", "id": 1}]}) is True
    assert _is_external_entity({"sources": [{"type": "chat", "id": 1}]}) is False
    assert _is_external_entity({
        "sources": [{"type": "rss", "id": 1}, {"type": "chat", "id": 2}],
    }) is False
    assert _is_external_entity({"sources": []}) is False


def test_bot_memory_uses_the_same_external_filter():
    from core.bots.memory import _is_external_entity

    assert _is_external_entity({"sources": [{"type": "rss", "id": 1}]}) is True
    assert _is_external_entity({"sources": [{"type": "note", "id": 1}]}) is False
