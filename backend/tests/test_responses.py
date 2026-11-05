import json
from datetime import datetime

from core.responses import UTCJSONResponse


def _body(payload) -> dict:
    resp = UTCJSONResponse(content=payload)
    return json.loads(resp.body)


def test_created_at_is_marked_utc():
    body = _body({"created_at": "2026-11-05T08:28:00.340407", "id": 1})
    assert body["created_at"] == "2026-11-05T08:28:00.340407Z"


def test_aware_and_local_times_untouched():
    body = _body({
        "created_at": "2026-11-05T16:28:00+08:00",
        "next_run_at": "2026-11-06T09:00:00",
        "start_time": "2026-11-06T10:00:00",
        "due_date": "2026-11-07T18:00:00",
        "published": "2026-11-05T09:00:00",
        "title": "2026-11-05T08:00:00",
    })
    assert body["created_at"].endswith("+08:00")
    assert body["next_run_at"] == "2026-11-06T09:00:00"
    assert body["start_time"] == "2026-11-06T10:00:00"
    assert body["due_date"] == "2026-11-07T18:00:00"
    assert body["published"] == "2026-11-05T09:00:00Z"
    # Free text is never rewritten.
    assert body["title"] == "2026-11-05T08:00:00"


def test_nested_payloads_and_lists():
    body = _body({"items": [{"updated_at": "2026-11-05T08:00:00", "meta": {"last_analysis": "2026-11-04T01:02:03"}}]})
    item = body["items"][0]
    assert item["updated_at"] == "2026-11-05T08:00:00Z"
    assert item["meta"]["last_analysis"] == "2026-11-04T01:02:03Z"


def test_non_iso_strings_untouched():
    body = _body({"created_at": "not-a-date", "updated_at": "", "finished_at": "2026-11-05"})
    assert body["created_at"] == "not-a-date"
    assert body["updated_at"] == ""
    assert body["finished_at"] == "2026-11-05"


def test_insights_local_hour_conversion():
    from core.ai.insights import _local

    assert _local(datetime(2026, 11, 5, 8, 30)).hour == 16
    aware = datetime(2026, 11, 5, 8, 30, tzinfo=__import__("datetime").timezone.utc)
    assert _local(aware).hour == 16
    assert _local(None) is None
