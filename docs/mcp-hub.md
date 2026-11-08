# 统一 MCP 管理（McpHub）

OmniAide 把 Home Assistant、钉钉、Playwright 等能力统一为 MCP Server，由后端 **McpHub** 负责连接、发现、路由、风险与审计。

## 分层

```
Bot / CoS / Web Chat / 桌面 Agent
              │
       /api/mcp/tools · /api/mcp/call
              │
           McpHub
   ├─ builtin providers（日程/待办/文件/笔记/HA 旧工具）
   ├─ stdio MCP Server（钉钉、Playwright、filesystem…）
   └─ HTTP MCP Server（Home Assistant…）
              │
       mcp_servers / mcp_tools / mcp_calls
```

- **McpHub**：后端常驻，负责生命周期、工具发现、命名空间、风险元数据与审计。
- **MCP Server**：能力提供方，stdio 或 HTTP。
- **builtin provider**：现有 `tool_registry` 工具，不需要独立进程，也会出现在统一目录里。
- **工具命名**：外部工具为 `{server_slug}__{tool}`，避免冲突。

## 使用

Web →「MCP 管理」：

1. 「添加 Server」→ 选模板或手填。
2. stdio：命令 + 参数 + 环境变量；HTTP：URL + Headers。
3. 保存后自动连接，失败可在列表重试。
4. 「工具」里可调整每个工具的 risk 与启用状态。
5. 「调用记录」查看审计（参数摘要、状态、耗时、错误）。

API：

```
GET    /api/mcp/servers
POST   /api/mcp/servers
PATCH  /api/mcp/servers/{id}
DELETE /api/mcp/servers/{id}
POST   /api/mcp/servers/{id}/connect
POST   /api/mcp/servers/{id}/disconnect
GET    /api/mcp/servers/{id}/tools
PATCH  /api/mcp/servers/{id}/tools/{tool}
GET    /api/mcp/tools          # 聚合 builtin + 外部工具
POST   /api/mcp/call
GET    /api/mcp/calls
GET    /api/mcp/templates
```

## 钉钉插件与私有 MCP

钉钉已从核心模块迁移为独立插件：

- 插件代码：`backend/plugins/dingtalk/`
- 私有 MCP Server：`backend/plugins/dingtalk/mcp_server/`，内部调用 `dws`
- 插件路由：`/api/plugins/dingtalk/*`

私有 MCP 以 `scope=internal`、`owner_plugin=dingtalk`、`expose_tools=false` 注册到
McpHub。原始 `mcp:dingtalk-*__*` 工具不会进入全局工具表，也不会出现在用户的
MCP 管理页；只有插件 curated 的 `dingtalk_*` 工具对 Bot 可见。

核心保持通用能力：MCP Hub、定时任务、活动分析。钉钉插件自己负责账号、
登录、消息同步、日程同步和会话查看；日程通过通用事件
`calendar.external.upsert` / `calendar.external.delete` 交给 schedule 插件。

周期任务：

| 任务 | 周期 | 说明 |
| --- | --- | --- |
| `dingtalk.sync_calendar` | 1 小时 | 拉取日程并发布外部日历事件 |
| `dingtalk.sync_chat` | 24 小时 | 同步会话并发布 `dingtalk.conversation` 活动 |
| `schedule.reminders` | 1 分钟 | 日程提醒 |
| `todo.reminders` | 1 分钟 | 待办到期提醒 |
| `mail.sync_due` | 5 分钟 | IMAP 增量同步 |
| `sources.refresh_due` | 30 分钟 | 资讯源刷新 |
| `core.daily_brief` | 1 小时 | 每个用户生成简报摘要和工作台快捷建议 |
| `core.activity_analysis` | 1 小时 | 每个用户生成可执行活动建议 |
| `schedule.external.apply` | 事件驱动 | 消费外部日历事件，失败自动重试 |

外部日历消费不再使用周期轮询；schedule 插件在启动时订阅事件，并执行一次最近 7 天的回填。

### 容器内登录 dws

Dockerfile 已安装 Node + `dingtalk-workspace-cli@1.0.62`。DingTalk 配置和 token 属于每个用户自己的运行态数据：

```
/data/workspace/<user_id>/dingtalk/.dws    # DWS_CONFIG_DIR
/data/workspace/<user_id>/dingtalk/home    # HOME，token 在 ~/.local/share/dws-cli
```

对应宿主机 `/data/docker/omniaide/data/workspace/<user_id>/dingtalk`。每次调用 `dws` 都必须注入该用户的环境（`plugins.dingtalk.backend.paths.dingtalk_env(user_id)`）；不再有全局 `DWS_CONFIG_DIR`，也不会在 `/config` 下保存 token。

绑定入口：Web「设置 → 钉钉」或移动端「设置 → 钉钉」，后端 API 为：

```
GET  /api/plugins/dingtalk/status
POST /api/plugins/dingtalk/login/start
GET  /api/plugins/dingtalk/login/status
POST /api/plugins/dingtalk/logout
GET  /api/plugins/dingtalk/conversations
GET  /api/plugins/dingtalk/messages?conversation_id=...
```

首次绑定使用设备流，页面展示授权码和链接；登录态持久化，token 自动刷新。

## 风险与权限

- 外部工具的 risk 由 server 默认值 + 工具名推断，可在 UI 覆盖。
- Bot 调用仍走现有 `core/bots/policy.py`；动态工具会注册到 `policy`，不会默认按 read 放过写操作。
- 审计写入 `mcp_calls`，参数会截断，不记录 token。
- 环境变量与 Headers 使用 `core.crypto` 加密存储，API 只返回 key 名。

## 限制

- 当前支持 stdio 与 HTTP（JSON / 基础 SSE）；旧版 SSE transport 尚未覆盖。
- `scope=desktop` 的本地 MCP 通过统一工具网关 `tool_search(scope="local")` / `tool_call` 按需发现和调用，不把每个本地工具注册到后端工具表。
- 多用户共享一个全局工具目录，slug 必须全局唯一；多用户/多组织场景后续可改为 per-user namespace。

- 服务端与本地工具统一走 `tool_search` / `tool_call`，见 [工具网关](tool-gateway.md)。
