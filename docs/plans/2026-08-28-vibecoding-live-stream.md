# VibeCoding 实时直播流：桌面 Agent 过程经后端 WS 中继到手机端

日期：2026-08-28
状态：已实现（v3：全端并入唯一通道 `/ws/host`，legacy 端点已删除）

## 0. 架构终态：全系统唯一 WS 通道 `/ws/host`

v1 插件自持 `/ws/vibecoding`；v2 桌面并入 `/ws/host` 但保留 legacy 端点；**v3 彻底并入**：

- `/ws/host?token=&role=desktop|viewer` 是全系统唯一实时通道：
  - `role=desktop`（默认）：桌面设备，要求 `device_id`，注册为该用户的执行设备；
  - `role=viewer`：瘦客户端（手机），收 channel 广播、可发 channel 指令。
- 所有消息（双向）都带 `channel` 命名空间信封；后端插件调用
  `host_channel.register(channel, on_message, on_connect, on_disconnect, on_viewer_connect)`
  注册协议处理器，hub 按 channel 解析分发。
- **已删除**：`/ws/notifications`、`/ws/vibecoding` 两个专用端点及各自 WSManager。
  notifications 后端只剩 `notify_user(user_id, data)` 函数 = 向 `channel:"notifications"`
  双向广播（desktop hosts + viewers 都会收到）。
- 移动端：新增 `host_channel_service.dart`（viewer 角色单连接、广播流、自动重连）；
  `vibecoding_service.dart` 与 `notification_service.dart` 瘦身为 channel 消费者
  （按 channel 过滤/解包，公开 API 不变，页面零改动）。
- 桌面端 `backendChannel.ts` 连 `/ws/host`（默认 desktop 角色）+ `channel:*` 桥接；
  下行按订阅表路由到插件进程（`executeCommand('channelMessage', {channel, msg})`）；
  `notifications` 为 host 内建 channel → 直接弹系统通知。

**新插件接入实时通道的完整成本**：
- 后端：`host_channel.register("xxx", handler)`；
- 桌面插件：`context.signal('channel:subscribe','xxx')` + `context.signal('channel:send','xxx',msg)`
  + `context.registerCommand('channelMessage', fn)`；
- 手机：`HostChannelService().stream.where((m) => m['channel']=='xxx')`。

## 1. 背景与目标

`vibecoding-proxy` 桌面插件当前的工作方式是：飞书 WS / Telegram 轮询 / 本地 Webhook 收到消息 →
本地一次性 spawn `opencode`/`claude`/`codex` CLI（阻塞等待退出）→ 清洗输出后整段回复到 IM。
**过程完全黑盒，只能看到最终结果，且与后端零交互。**

目标：把 vibecoding 的全过程（任务接收、增量输出、工具调用、文件变更、里程碑、完成/失败）
通过 WebSocket 实时上报到后端，由后端中继转发到手机端（Flutter），实现：

- **监控**：手机上实时看到 agent 正在干什么（流式输出 + 结构化事件 + 状态里程碑）
- **派发**：手机上主动向桌面下发新任务（选项目 + 选工具 + 输入），桌面执行后过程回流手机
- **控制**：手机上取消正在运行的任务

## 2. 总体架构

```
┌─────────────┐  task.event (uplink)   ┌──────────┐  task.event / device.status  ┌──────────┐
│ vibecoding- │ ─────────────────────▶ │  FastAPI │ ────────────────────────────▶ │  Mobile  │
│ proxy 插件   │ ◀───────────────────── │  /ws/    │ ◀──────────────────────────── │ Flutter  │
│ (Electron)  │  task.dispatch/control │ vibecoding│  task.dispatch/control       │ (viewer) │
└─────────────┘                        └──────────┘                              └──────────┘
     role=desktop                JWT ?token= 鉴权                        role=mobile
```

- 复用全仓既有约定：**WS 端点 JWT `?token=` 查询参数鉴权**（同 `/ws/notifications`、`/ws/sync`）、
  **per-user connection manager**（同 notifications/sync/remote 三处先例）。
- 后端是**无状态中继**：不落库，仅维护连接表 + 最近任务环形缓冲（进程内存）。
- 桌面插件经 `context.config.get('serverUrl'/'token')` 获取后端地址与 JWT（同 remote/player 插件先例），
  用插件已有依赖 `ws` 建立长连接，断线自动重连 + 离线事件有界队列补发。

## 3. WS 协议设计

端点：`GET /ws/vibecoding?token=<JWT>&role=desktop|mobile&device_id=<id>&device_name=<name>`

- `role=desktop`：执行端（vibecoding-proxy 插件）。`device_id` 缺省时服务端拒绝。
- `role=mobile`：观察/控制端（Flutter）。`device_id` 可选。
- 鉴权失败 close 4001（同 notifications）。

### 3.1 桌面 → 后端（并中继到该用户全部手机连接）

统一信封：

```json
{ "type": "task.event", "task_id": "t-xxx", "event": "...", "data": {...}, "ts": 1730000000000 }
```

`event` 取值（全量结构化）：

| event | data 字段 | 说明 |
|---|---|---|
| `started` | `tool, project, project_name, input, source` | 任务开始；source ∈ mobile/feishu/telegram/webhook/panel |
| `milestone` | `stage` | spawning/continuing/executing/replying/cancelled |
| `output` | `chunk` | 增量原始输出（插件端按 ~400ms/256B 批量节流） |
| `tool` | `name, detail` | 解析出的工具调用（Read/Edit/Write/Bash/exec/apply_patch…） |
| `file` | `path, action` | 解析出的文件变更 created/modified/read/deleted |
| `done` | `code, duration_ms, output` | 完成；output 为清洗后的最终完整回复 |
| `failed` | `error, duration_ms, code` | 失败 |

另有两个非任务信封：

```json
{ "type": "projects.response", "request_id": "r1", "projects": [...], "tools": {...} }
{ "type": "pong" }
```

### 3.2 手机 → 后端（路由到该用户的桌面设备）

```json
{ "type": "task.dispatch", "task_id": "t-xxx", "tool": "opencode", "project": "E:\\repo", "input": "..." , "device_id": "可选" }
{ "type": "task.control", "task_id": "t-xxx", "action": "cancel" }
{ "type": "projects.request", "request_id": "r1" }
{ "type": "ping" }
```

- `task.dispatch`：带 `device_id` 则定点；否则广播给该用户全部在线桌面设备（所有桌面都会收到，
  由插件端凭"项目路径是否在本机存在"决定是否认领——认领者立即回报 `task.event started`，
  未认领设备静默忽略。单机场景等价于直达）。
- `task.control`：按 `task_id` 前缀路由到上报过该任务的设备（后端维护 task_id → device_id 映射），
  查不到则广播。
- `projects.response`：后端按 `request_id` 回给发起请求的那台手机（pending map，10s 超时清理）。

### 3.3 后端 → 手机

```json
{ "type": "device.status", "devices": [{ "device_id": "...", "name": "...", "connected": true, "active_task": "t-xxx" }] }
{ "type": "task.event", "device_id": "...", ...同上信封 }
{ "type": "projects.response", ... }
{ "type": "pong" }
```

桌面连接/断开时向该用户全部手机广播 `device.status`。

## 4. REST 接口（`/api/vibecoding`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/vibecoding/devices` | 当前在线桌面设备列表（JWT Bearer） |
| GET | `/api/vibecoding/tasks?limit=50` | 最近任务摘要（进程内环形缓冲，含状态/耗时/最终输出，供手机冷启动回放） |

## 5. 后端实现（plugins/vibecoding）

```
backend/plugins/vibecoding/
├── __init__.py
└── backend/
    ├── __init__.py
    ├── service.py    # VibecodingHub：desktop/mobile 连接表、task→device 映射、
    │                 #   最近任务环形缓冲(deque maxlen=200)、request_id pending map、广播/路由
    └── router.py     # ws_router: /ws/vibecoding；router: /api/vibecoding/devices|tasks
```

- 在 `main.py` 显式 `include_router`（`discover_plugins` 只自动挂 `router`，不挂 `ws_router`，
  与 notifications 一致）。
- 无 DB 模型；`manifest.json` 不放（避免 discover_plugins 重复注册），仅作为内部插件目录存在。

## 6. 桌面插件实现（desktop/plugins/vibecoding-proxy）

```
src/utils/
├── backendReporter.ts  # WS 客户端：/ws/vibecoding role=desktop；uuid device_id 持久化在插件 storage；
│                       #   5s 指数退避重连(封顶60s)；离线事件队列(max 500)重连后补发；
│                       #   emit() / onDispatch / onControl / requestProjects / status()
├── outputParser.ts     # 增量输出行缓冲 + 结构化解析：⏺ Read/Edit/Write/Bash(claude 风格)、
│                       #   exec/apply_patch/touch(codex 风格)、通用 `动词 path` 行；每任务内去重
└── terminalLauncher.ts # 改造：spawnAiProcess 增加可选 onChunk 回调（stdout/stderr 数据即回调）；
                        #   保留当前 child 引用，新增 cancelActiveProcess()
src/index.ts            # 埋点接线（见下）
```

`index.ts` 接线：

- activate 时创建 reporter 并 start；`onDispatch` → 与 IM 消息共用 `runTaskWithEvents()` 管道；
- `runTaskWithEvents(taskId, tool, projectPath, input, source, reply?)`：
  1. emit `started`（读 `binding_project` 得 project_name）
  2. `spawnAiProcess(tool, dir, input, onChunk)`：onChunk 里节流批量 emit `output`，
     同时喂 `outputParser` 产出 `tool`/`file` 事件
  3. emit `milestone`(continuing/executing) → 结束 emit `done`/`failed`
  4. 完成后仍按原逻辑回复 IM（若来自 IM 通道）
- IM 回调（飞书/TG/webhook）改走同一管道，source 取 channelId 对应通道类型 → 手机能看到 IM 派发的任务；
- `task.control cancel` → `cancelActiveProcess()` + emit `milestone: cancelled`；
- `projects.request` → 回 `projects.response`（getProjects() + checkAiTools()）；
- 任务用 promise 队列串行化（延续既有"单会话 continuation"语义，避免并发 spawn 互相污染 `--continue` 状态）；
- 新命令 `getBackendStatus` 供面板展示连接状态。

## 7. 手机端实现（mobile）

```
lib/models/vibecoding_models.dart   # VibecodingDevice / VibecodingTask / VibeEvent（fromJson + copyWith）
lib/services/vibecoding_service.dart# 单例 WS 客户端：dart:io WebSocket、?token= 鉴权、
                                    #   断线自动重连(指数退避)、broadcast Stream<Map>、
                                    #   dispatch()/cancel()/requestProjects()/连接状态 ValueNotifier
lib/screens/vibecoding_screen.dart  # 主页：设备状态 + 派发表单(项目下拉←projects.request、工具选择、
                                    #   多行输入) + 最近任务列表(GET tasks 回放 + 实时事件合并)
lib/screens/vibecoding_task_screen.dart # 任务直播页：里程碑时间线 + 工具/文件事件 chips + 流式输出文本
dashboard_screen.dart               # Quick Actions 增加 "VibeCoding" 入口卡片 → vibecoding_screen
```

- 任务列表合并策略：REST 拉最近任务 → WS `task.event` 按 task_id 实时 upsert；
- 派发后本地生成 task_id（`t-<ms>-<rand>`），乐观插入列表，等 `started`/`done` 事件校正。

## 8. 安全与边界

- 鉴权：WS 查询参数 JWT（既有约定）；REST Bearer。所有连接绑定 user_id，**只中继同一用户**的
  桌面↔手机消息，跨用户不可达。
- 后端不持久化任何 agent 输出（内存环形缓冲，进程重启即清空），避免敏感代码驻留服务端。
- `output` 事件有节流与分块上限（单 chunk >8KB 截断），离线队列有界（500 条），防止打爆手机。
- 桌面端 `spawnAiProcess` 仍为一次性 exec 语义（`--continue` 续会话），本设计不改变执行模型，
  只增加旁路观测与远程派发入口。

## 9. 验证

- 后端：`python -m py_compile` 各新文件；启动后 `wscat`/脚本连 `/ws/vibecoding` 冒烟。
- 桌面：插件目录 `npm run build`（vite 构建 dist/index.js）+ `npx tsc --noEmit`（若有 tsconfig）。
- 移动：`flutter analyze` 零新告警。
