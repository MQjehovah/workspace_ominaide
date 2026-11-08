"""DingTalk calendar mapping sanity checks."""


def test_dingtalk_event_mapping():
    from plugins.dingtalk.backend.sync_calendar import _event_time, _normalize

    raw = {
        "id": "evt-1",
        "summary": "面试",
        "start": {"dateTime": "2026-11-06T10:00:00+08:00", "timeZone": "Asia/Shanghai"},
        "end": {"dateTime": "2026-11-06T10:30:00+08:00", "timeZone": "Asia/Shanghai"},
        "organizer": {"displayName": "钱飞飞"},
        "attendees": [{"displayName": "季明清", "responseStatus": "accepted", "self": True}],
        "meetingRooms": [{"roomName": "6-5 会议室", "responseStatus": "accepted"}],
        "onlineMeetingInfo": {"url": "dingtalk://meeting", "extraInfo": {"roomCode": "865 618 983"}},
        "status": "confirmed",
        "iCalUID": "ical-1",
    }

    start = _event_time(raw["start"])
    assert start is not None and start.hour == 10
    event = _normalize(raw)
    assert event is not None
    assert event["title"] == "面试"
    meta = event["metadata"]
    assert meta["organizer"] == "钱飞飞"
    assert meta["rooms"][0] == "6-5 会议室"
    assert meta["meeting_room_code"] == "865 618 983"
    assert meta["attendees"][0]["displayName"] == "季明清"


def test_dingtalk_event_fingerprint_changes_on_update():
    from plugins.dingtalk.backend.sync_calendar import _fingerprint

    base = {"title": "面试", "start": "2026-11-06T10:00:00", "status": "confirmed"}
    assert _fingerprint(base) == _fingerprint(dict(base))
    changed = dict(base, title="面试改期")
    assert _fingerprint(base) != _fingerprint(changed)
