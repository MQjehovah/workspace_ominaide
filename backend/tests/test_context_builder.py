from ai.context_builder import ContextBuilder
from ai.context_window import compact_context


def _turn(index: int, size: int = 200):
    return [
        {"role": "user", "content": f"question {index} " + "x" * size},
        {"role": "assistant", "content": f"answer {index} " + "y" * size},
    ]


async def test_compact_context_summarizes_old_turns():
    messages = [{"role": "system", "content": "system instructions"}]
    for index in range(10):
        messages.extend(_turn(index))
    messages.append({"role": "tool", "content": "z" * 20000, "tool_call_id": "1"})

    result = await compact_context(
        messages,
        threshold_chars=2000,
        keep_recent_turns=2,
        tool_result_max_chars=200,
    )
    assert any("较早上下文摘要" in item.get("content", "") for item in result)
    assert any(item.get("content", "").startswith("question 9") for item in result)
    assert not any(item.get("content", "").startswith("question 0") for item in result)
    assert all(len(item.get("content", "")) < 20000 for item in result)


async def test_context_builder_keeps_required_and_drops_optional():
    builder = ContextBuilder(budget_chars=120)
    builder.section("identity", "i" * 40, priority=100, required=True)
    builder.section("optional", "o" * 200, priority=10)
    builder.user("hello")
    messages = await builder.build()
    contents = [item["content"] for item in messages]
    assert any(content.startswith("i" * 40) for content in contents)
    assert not any(content.startswith("o" * 200) for content in contents)


async def test_context_builder_keeps_recent_history():
    builder = ContextBuilder(budget_chars=1200)
    builder.section("identity", "system", priority=100, required=True)
    history = []
    for index in range(6):
        history.extend(_turn(index, size=200))
    builder.history(history)
    builder.user("now")
    messages = await builder.build()
    assert messages[-1]["content"] == "now"
    assert any("较早上下文摘要" in item.get("content", "") for item in messages)
