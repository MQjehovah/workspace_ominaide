"""AgentProfile definitions: templates for execution agents."""

from __future__ import annotations

from dataclasses import dataclass, field

from ai.bots import policy


@dataclass(frozen=True)
class AgentProfile:
    key: str
    title: str
    system_prompt: str
    read_only: bool = False
    allowed_tools: tuple[str, ...] | None = None
    model: str | None = None
    max_turns: int = 40
    token_budget: int | None = None
    acceptance_hint: str = ""


PROFILES: dict[str, AgentProfile] = {
    "planner": AgentProfile(
        key="planner",
        title="规划",
        system_prompt=(
            "你是规划 Agent。只做计划和拆解，不执行副作用操作。"
            "目标要拆成可独立执行、可验收的 Task；每个 Task 指定 "
            "agent_profile_key（researcher/comms/executor/verifier）。"
            "只返回 JSON。"
        ),
        read_only=True,
        max_turns=12,
        acceptance_hint="Task 有明确输入、输出和验收标准",
    ),
    "researcher": AgentProfile(
        key="researcher",
        title="研究",
        system_prompt=(
            "你是研究 Agent。只读取邮件、日程、资讯、笔记、文件和记忆，"
            "产出带来源的事实和结论，不做写操作。"
        ),
        read_only=True,
        max_turns=25,
        acceptance_hint="结论有来源，区分事实和推测",
    ),
    "architect": AgentProfile(
        key="architect",
        title="方案",
        system_prompt=(
            "你是方案 Agent。基于需求和约束给出结构、步骤、风险和取舍，"
            "不直接执行写操作。"
        ),
        read_only=True,
        max_turns=20,
        acceptance_hint="方案包含约束、步骤、风险和替代方案",
    ),
    "comms": AgentProfile(
        key="comms",
        title="沟通",
        system_prompt=(
            "你是沟通 Agent。负责起草邮件、消息和会议邀请。"
            "默认只生成草稿，发送等外部副作用必须经过授权。"
        ),
        max_turns=30,
        acceptance_hint="语气合适、事实准确、不编造承诺",
    ),
    "executor": AgentProfile(
        key="executor",
        title="执行",
        system_prompt=(
            "你是执行 Agent。按 Task 契约完成具体工作，"
            "只做完成任务所需的最小操作，完成后汇报结果和证据。"
        ),
        max_turns=40,
        acceptance_hint="完成 Task 目标，输出可验证",
    ),
    "verifier": AgentProfile(
        key="verifier",
        title="验收",
        system_prompt=(
            "你是验收 Agent。只根据 acceptance criteria 检查产物，"
            "不重写产物，不替执行者解释。只返回 JSON："
            '{"passed": true|false, "notes": ["..."]}。'
        ),
        read_only=True,
        max_turns=12,
        acceptance_hint="按验收标准逐条判断",
    ),
}


def get_profile(key: str | None) -> AgentProfile | None:
    return PROFILES.get((key or "").strip()) if key else None


def scoped_tools(bot, profile: AgentProfile | None) -> list[str] | None:
    """Return the allowlist an agent should see, never wider than the Bot."""
    if profile is None:
        return getattr(bot, "allowed_tools", None)
    base = getattr(bot, "allowed_tools", None)
    if base is not None:
        allowed = set(base)
    else:
        from ai.mcp.registry import tool_registry

        allowed = {tool.name for tool in tool_registry.get_tools()}
    if profile.allowed_tools is not None:
        allowed &= set(profile.allowed_tools)
    if profile.read_only:
        allowed = {name for name in allowed if policy.classify_tool(name) == policy.RISK_READ}
    return sorted(allowed)
