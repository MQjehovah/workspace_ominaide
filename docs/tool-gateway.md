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
  ├─ tool_search / tool_call
  ├─ save_memory / send_notification / web_search / web_fetch
  └─ skill_search / skill_call

本地机器工具（source=local，不属于 builtin，也不常驻）：
  └─ 只能通过 tool_search(scope="machine") 发现

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
local     本地机器工具 / 本地 MCP（只在 scope=machine 时出现）
```

`scope`：

```text
server    服务端工具（默认）
machine   本地机器工具 + 本地 MCP
all       两者
```

`local` 仍然作为 `machine` 的兼容别名。

本地机器工具和本地 MCP 使用 `scope=machine` 或 `scope=all`：

```text
tool_search(query="browser", scope="machine", machine_id="...")
tool_search(query="local_shell", scope="machine")
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

## 本地工具

`local_*` 不是 builtin 工具，也不常驻在工具表里：

- `source = "local"`
- 永远不出现在 LLM 的默认工具列表
- 必须用 `tool_search(scope="machine")` 或 `scope="all"` 搜索
- 再用 `tool_call` 调用
- 桌面端离线时搜索返回空/错误
- 其他用户不会因为别人的机器在线而搜到本地工具

文件操作合并为一个入口：

```text
local_file(op=list|read|write|grep, path=..., ...)
```

- `op=list` 列目录
- `op=read` 读文本
- `op=write` 写文件
- `op=grep` 在目录中搜索

旧的 `local_list_dir` / `local_read_file` / `local_write_file` / `local_grep`
保留兼容，但不再常驻，也不出现在搜索结果里。

本地 shell：

```text
local_shell            同步执行
local_shell_start      长任务，返回 job_id
local_shell_wait       读取增量输出
```

`local_shell_cancel` 和 `list_local_machines` 按需通过 `tool_search` 发现。
只有一台本地机器在线时不需要 machine_id；多台时错误信息会列出可选 machine_id。

## 技能

技能不是普通工具，走独立入口：

```text
skill_search(query)
  → skill_key / name / description / inputs / allowed_tools

skill_call(skill_key, input)
  → 执行技能
```

系统提示只告诉模型「有 N 个已启用技能」，不再展开全部技能描述。
旧的 `skill` 工具保留兼容，但不再常驻。

## 安全

- 不能通过 `tool_call` 调用 `tool_search` / `tool_call` 自身
- 不能调用当前用户不可见的工具
- 配置了 `allowed_tools` 的 Bot 只能调用白名单里的工具
- 本地 MCP 工具默认按 `exec` 风险处理

## 相关代码

```text
ai/mcp/gateway.py         搜索、调用、暴露策略
ai/mcp/tools/register_core.py  注册 tool_search / tool_call
ai/bots/policy.py            解析底层工具风险
ai/bots/runner.py            只把暴露后的工具发给 LLM
```
