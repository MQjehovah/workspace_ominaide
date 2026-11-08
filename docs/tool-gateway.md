# 工具网关

服务端不会把全部工具 schema 发给 LLM。默认只暴露少量核心工具，其余通过两个
稳定入口按需发现和调用：

```text
tool_search(query, scope?, source?, machine_id?, limit?)
tool_call(tool_id, arguments, machine_id?)
```

## 暴露策略

Bot 每次运行时的工具列表：

```text
pinned_tools
  ├─ tool_search
  ├─ tool_call
  ├─ save_memory / send_notification / web_search / fetch_url / skill
  └─ 本地 shell / 文件原语

其余工具：插件工具、服务端 MCP、本地 MCP、业务工具
  └─ 只进入搜索目录，不直接进入上下文
```

- `bots.pinned_tools` 为空时使用默认核心集合
- `allowed_tools` 仍然是安全白名单；设置后只允许调用其中的工具
- 设置了 `allowed_tools` 但没有设置 `pinned_tools` 时，允许列表直接作为常驻工具
- 关闭网关：`TOOL_GATEWAY_ENABLED=false`

## 搜索

```json
{
  "tool_id": "plugin:google_gmail_search",
  "name": "google_gmail_search",
  "source": "plugin",
  "server": "google",
  "risk": "read",
  "description": "在已连接的 Gmail 中搜索邮件。",
  "input_schema": {}
}
```

来源：

```text
builtin   核心/业务内置工具
plugin    插件工具，包括外部授权插件（Google）
mcp       服务端 MCP
local     本地机器上的 MCP
```

本地 MCP 使用 `scope=local` 或 `scope=all`：

```text
tool_search(query="browser", scope="all", machine_id="...")
```

本地工具的 `tool_id` 形如：

```text
local:<machine_id>:<server_id>:<tool>
```

## 调用与审批

```text
tool_call(
  tool_id="plugin:google_gmail_send",
  arguments={...}
)
```

审批按底层真实工具执行：

```text
google_gmail_send  -> external -> ask
list_todo_items    -> read     -> auto
local:m1/browser/* -> exec     -> ask
```

审批卡片和运行步骤显示真实工具名，而不是 `tool_call`。

## 安全

- 不能通过 `tool_call` 调用 `tool_search` / `tool_call` 自身
- 不能调用当前用户不可见的工具
- 配置了 `allowed_tools` 的 Bot 只能调用白名单里的工具
- 本地 MCP 工具默认按 `exec` 风险处理

## 相关代码

```text
core/ai/mcp/gateway.py         搜索、调用、暴露策略
core/ai/mcp/tools/register_core.py  注册 tool_search / tool_call
core/bots/policy.py            解析底层工具风险
core/bots/runner.py            只把暴露后的工具发给 LLM
```
