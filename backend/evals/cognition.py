"""Golden-path checks for the cognition layer.

Usage:
    python -m evals.cognition --user-id 1
"""

from __future__ import annotations

import argparse
import asyncio

from ai.bots.registry import get_active_bot
from ai.cognition.authorization import authorize, create_grant
from ai.cognition.goals import create_goal, list_tasks
from ai.cognition.planner import plan_goal
from ai.cognition.proposals import act_proposal, create_proposal
from ai.cognition.situation import get_situation


async def run(user_id: int) -> int:
    results: list[tuple[str, bool, str]] = []

    situation = await get_situation(user_id, force=True)
    results.append((
        "situation",
        bool(situation.get("generated_at")) and "signals" in situation,
        "situation snapshot",
    ))

    proposal = await create_proposal(
        user_id,
        kind="follow_up",
        title="评测：跟进客户",
        reason="评测用例",
        actions=[{"key": "create_goal", "label": "接受", "kind": "create_goal", "payload": {}}],
    )
    acted = await act_proposal(user_id, proposal.id, action="accept")
    results.append((
        "proposal_to_goal",
        bool(acted and acted.get("goal_id")),
        "proposal acceptance creates a goal",
    ))

    goal = await create_goal(user_id, title="评测：准备会议", description="评测用例")
    planned = await plan_goal(user_id, goal.id)
    tasks = await list_tasks(user_id, goal.id)
    results.append((
        "goal_plan",
        bool(planned and tasks),
        "planner creates tasks",
    ))

    bot = await get_active_bot(user_id)
    first = await authorize(user_id, "send_email", {"to": ["x@example.com"]}, bot=bot)
    grant = await create_grant(user_id, "send_email", scope="always", bot_id=bot.id)
    second = await authorize(user_id, "send_email", {"to": ["x@example.com"]}, bot=bot)
    results.append((
        "capability_grant",
        first.decision == "require_approval" and second.decision == "allow",
        f"grant id={grant.id}",
    ))

    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    print(f"\n{passed}/{len(results)} cognition cases passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=int, required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.user_id)))
