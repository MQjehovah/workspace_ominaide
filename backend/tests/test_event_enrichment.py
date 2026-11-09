"""Activity event enrichment: rich but bounded details for the agent."""


def test_argument_preview_redacts_and_bounds():
    from activities.preview import preview_arguments

    preview = preview_arguments({
        "query": "x" * 300,
        "password": "secret",
        "nested": {"a": 1},
        "items": list(range(20)),
    })
    assert preview["password"] == "***"
    assert len(preview["query"]) <= 241
    assert preview["nested"] == {"a": 1}
    assert len(preview["items"]) == 8


def test_generic_activity_summaries_are_specific():
    from activities.middleware import _derive_event_type, _make_summary

    event_type = _derive_event_type("POST", "/api/bots/1/routines/2/run")
    assert _make_summary("POST", "/api/bots/1/routines/2/run", event_type) == "运行 Bot 例行任务"

    event_type = _derive_event_type("POST", "/api/mcp/servers/1/connect")
    assert _make_summary("POST", "/api/mcp/servers/1/connect", event_type) == "连接 MCP 服务"

    event_type = _derive_event_type("PATCH", "/api/bots/1/routines/2")
    assert _make_summary("PATCH", "/api/bots/1/routines/2", event_type) == "修改 Bot 例行任务"
