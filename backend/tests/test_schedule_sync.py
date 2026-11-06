"""DingTalk calendar mapping sanity checks."""


def test_dingtalk_event_mapping():
    from plugins.schedule.backend.dingtalk_sync import _event_time, _external_meta

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
    meta = _external_meta(raw, "6-5 会议室")
    assert meta["organizer"] == "钱飞飞"
    assert meta["rooms"][0]["name"] == "6-5 会议室"
    assert meta["meeting_room_code"] == "865 618 983"
    assert meta["attendees"][0]["name"] == "季明清"
