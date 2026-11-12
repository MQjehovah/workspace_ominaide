import pytest

from core.wschannel import vibecoding


@pytest.mark.asyncio
async def test_detail_events_are_only_sent_to_watched_sessions(monkeypatch):
    mobile = object()
    desktop = object()
    sent: list[tuple] = []

    monkeypatch.setattr(
        vibecoding.host_channel,
        "viewer_sockets",
        lambda user_id: [mobile, desktop],
    )

    async def fake_send(ws, channel, payload):
        sent.append((ws, payload.get("session_id"), payload.get("event")))
        return True

    async def fake_broadcast(user_id, channel, payload):
        sent.append(("broadcast", payload.get("session_id"), payload.get("event")))
        return 2

    monkeypatch.setattr(vibecoding.host_channel, "send_to_ws", fake_send)
    monkeypatch.setattr(
        vibecoding.host_channel, "broadcast_to_viewers", fake_broadcast
    )

    vibecoding._detail_viewers.clear()
    vibecoding._watches.clear()
    vibecoding._detail_viewers[1] = {mobile}
    vibecoding._watches[1] = {mobile: {"ses_a"}}
    try:
        # The watched session reaches both the mobile and the desktop viewer.
        await vibecoding._broadcast_coding_event(
            1, {"event": "session.text.delta", "session_id": "ses_a"}
        )
        assert (mobile, "ses_a", "session.text.delta") in sent
        assert (desktop, "ses_a", "session.text.delta") in sent

        # A background session's text never reaches the mobile viewer.
        sent.clear()
        await vibecoding._broadcast_coding_event(
            1, {"event": "session.text.delta", "session_id": "ses_b"}
        )
        assert (mobile, "ses_b", "session.text.delta") not in sent
        assert (desktop, "ses_b", "session.text.delta") in sent

        # Lifecycle events stay global so the app-wide run monitor works.
        sent.clear()
        await vibecoding._broadcast_coding_event(
            1, {"event": "session.execution.succeeded", "session_id": "ses_b"}
        )
        assert sent == [("broadcast", "ses_b", "session.execution.succeeded")]
    finally:
        vibecoding._detail_viewers.clear()
        vibecoding._watches.clear()
