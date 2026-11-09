"""Cross-device handoff over the existing host WebSocket channel."""

from __future__ import annotations

from core.wschannel.hub import host_channel


async def handoff(
    user_id: int,
    *,
    machine_id: str,
    goal_id: int | None = None,
    session_id: str | None = None,
    note: str | None = None,
) -> dict:
    machines = host_channel.machine_ids(user_id)
    if machine_id not in machines:
        return {"sent": False, "reason": "machine offline", "machines": machines}
    ok = await host_channel.send_to_machine(
        user_id,
        machine_id,
        "cognition.handoff",
        {
            "type": "cognition.handoff",
            "goal_id": goal_id,
            "session_id": session_id,
            "note": note,
        },
    )
    return {"sent": bool(ok), "machine_id": machine_id}
