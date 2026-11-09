"""Skill gateway: discovery and invocation."""

import json
from pathlib import Path

from ai.mcp.tools import skills as skill_tools
from ai.skills.loader import SkillDefinition


class DummyBot:
    id = 1
    user_id = 1


def _skill():
    return SkillDefinition(
        key="daily-brief",
        name="今日简报",
        description="汇总今天的日程、待办和邮件",
        body="",
        path=Path("."),
        inputs={"day": {"type": "string"}},
        outputs={"summary": {"type": "string"}},
        allowed_tools=["list_schedule_events"],
    )


async def test_skill_search_finds_enabled_skill(monkeypatch):
    async def fake_bot(user_id):
        return DummyBot()

    async def fake_enabled(bot):
        return [_skill()]

    monkeypatch.setattr(skill_tools, "_current_bot", fake_bot)
    from ai.skills import runtime

    monkeypatch.setattr(runtime, "enabled_skills", fake_enabled)

    response = await skill_tools.skill_search(1, {"query": "简报"})
    assert not response.isError
    payload = json.loads(response.content[0].text)
    assert payload["skills"][0]["skill_key"] == "daily-brief"
    assert payload["skills"][0]["inputs"]["day"]["type"] == "string"


async def test_skill_call_requires_enabled_key(monkeypatch):
    async def fake_bot(user_id):
        return DummyBot()

    async def fake_enabled(bot):
        return [_skill()]

    monkeypatch.setattr(skill_tools, "_current_bot", fake_bot)
    from ai.skills import runtime

    monkeypatch.setattr(runtime, "enabled_skills", fake_enabled)

    response = await skill_tools.skill_call(
        1, {"skill_key": "missing-skill", "input": {}}
    )
    assert response.isError
    assert "未启用" in response.content[0].text


async def test_skill_call_runs_handler(monkeypatch):
    async def fake_bot(user_id):
        return DummyBot()

    async def fake_enabled(bot):
        return [_skill()]

    async def fake_run(user_id, args):
        assert args["skill_key"] == "daily-brief"
        assert args["input"] == {"day": "2026-11-08"}
        return {"ok": True, "summary": "today"}

    monkeypatch.setattr(skill_tools, "_current_bot", fake_bot)
    monkeypatch.setattr(skill_tools, "run_skill_tool", fake_run)
    from ai.skills import runtime

    monkeypatch.setattr(runtime, "enabled_skills", fake_enabled)

    response = await skill_tools.skill_call(
        1,
        {"skill_key": "daily-brief", "input": {"day": "2026-11-08"}},
    )
    assert not response.isError
    payload = json.loads(response.content[0].text)
    assert payload["summary"] == "today"
