"""Generic workers must not learn from external RSS articles."""


class _Event:
    def __init__(self, event_type: str, entity_type: str | None = None):
        self.event_type = event_type
        self.entity_type = entity_type


def test_rss_and_article_events_are_internal():
    from core.events.workers import _is_internal, _skip_entities

    for event_type in ("article.new", "rss.refreshed"):
        event = _Event(event_type, entity_type="rss_entry")
        assert _is_internal(event) is True
        assert _skip_entities(event) is True


def test_user_events_still_use_the_entity_extractor():
    from core.events.workers import _skip_entities

    assert _skip_entities(_Event("app.used")) is False
    assert _skip_entities(_Event("file.uploaded")) is False
