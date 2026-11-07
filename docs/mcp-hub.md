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

## 钉钉 MCP Server

`backend/mcp_servers/dingtalk/` 是一个标准 stdio MCP Server，内部调用 `dws`：

- `health`
- `search_messages`
- `list_unread`
- `recent_conversations`
- `send_message`
- `list_events`
- `create_event`
- `list_todos`
- `create_todo`

写工具带 `confirmed` 参数；未确认时只返回 `confirmation_required`，不执行发送/创建。

### 容器内登录 dws

Dockerfile 已安装 Node + `dingtalk-workspace-cli@1.0.62`，并设置：

```
DWS_CONFIG_DIR=/config/dws
```

生产环境使用两个标准挂载点：

- `/data/docker/omniaide/data` → `/data`：workspace、skills、配件数据
- `/data/docker/omniaide/config` → `/config`：DWS 配置、DWS token store、SSH 部署密钥

DWS CLI 的加密 token 存在 `~/.local/share/dws-cli`（不在 `DWS_CONFIG_DIR` 内），镜像中已把该目录软链到 `/config/dws-cli`，所以容器重建后登录态不会丢。首次登录：

```bash
docker compose exec backend dws auth login --device --recommend
# 或生产（docker run）
docker exec -it omniaide-backend dws auth login --device --recommend
```

手机钉钉确认即可。登录态持久化，token 自动刷新；失效时在「MCP 管理」看到连接错误。

## 风险与权限

- 外部工具的 risk 由 server 默认值 + 工具名推断，可在 UI 覆盖。
- Bot 调用仍走现有 `core/bots/policy.py`；动态工具会注册到 `policy`，不会默认按 read 放过写操作。
- 审计写入 `mcp_calls`，参数会截断，不记录 token。
- 环境变量与 Headers 使用 `core.crypto` 加密存储，API 只返回 key 名。

## 限制

- 当前支持 stdio 与 HTTP（JSON / 基础 SSE）；旧版 SSE transport 尚未覆盖。
- `scope=desktop` 的本地 MCP 尚未代理到后端；桌面端仍使用自己的 `mcp-manager`。
- 多用户共享一个全局工具目录，slug 必须全局唯一；多用户/多组织场景后续可改为 per-user namespace。
