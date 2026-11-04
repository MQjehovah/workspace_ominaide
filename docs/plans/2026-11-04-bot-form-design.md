# OmniAide Bot 形态改造设计

日期: 2026-11-04
状态: 草案
关联: `docs/prd.md`、`docs/plans/2026-07-22-intelligence-layer-design.md`

---

## 0. 一句话结论

把现在的「单一 AI 助理 + 全局会话」升级为「**命名 Bot + 独立记忆 + 常驻任务 + 例程触发 + 审批边界**」，但运行时留在自己的服务器上，不引入厂商云电脑。

Bot 不是比 Agent 更聪明的模型，而是 Agent 的**产品化形态**：给它名字、岗位、记忆、运行时和触发器，让它从「干一件事」变成「长期负责一份活」。

---

## 0.1 术语约定：Chatbot / Agent / Bot

这三个词经常被混用，本项目按下面的边界使用，后续文档与代码命名都以此为准。

| 概念 | 回答的问题 | 计量单位 | 生命周期 | 本项目对应物 |
|---|---|---|---|---|
| Chatbot | 谁在回话 | 一条消息 | 会话内 | 旧式问答机器人，**不是本方案** |
| Agent | 能不能把这件事做完 | 一次 run / 一个任务 | 一次执行 | `core/ai/agent.py::run_agent_stream` + `tool_registry` |
| Bot | 谁长期对这件事负责 | 一个岗位 / 一个身份 | 跨会话、跨任务 | `bots` 行 + `bot_memories` + `bot_routines` + `bot_runs` |

### 三条判定规则

1. **有工具循环，只是 Agent。** 能调工具、能多步执行，但没有独立身份和持久记忆，仍然是一次性的执行器。
2. **有名字和头像，不一定是 Bot。** 必须同时具备「独立记忆 + 明确职责 + 可归属的运行记录」，否则只是给 Agent 换了个皮肤。
3. **能被定时/事件触发、关掉页面还在跑、失败能归属到某个责任主体，才是 Bot。** 这三条对应 `bot_routines`、`bot_runs`、`bot_id`。

### 层次关系：组合，不是继承

```
┌─────────────────────────────────────┐
│ Bot 层（组织抽象）                    │
│ 身份 · 职责 · 记忆 · 例程 · 审批      │
│              │ 依赖                 │
├──────────────▼──────────────────────┤
│ Agent 层（执行能力）                  │
│ 模型 · 工具循环 · 单次 run            │
│              │ 调用                 │
├──────────────▼──────────────────────┤
│ Tool / MCP 层                        │
└─────────────────────────────────────┘
```

- **不是并列**：Bot 不能脱离 Agent 存在。没有执行能力，Bot 只是一个空档案。
- **不是继承**：Bot 不是「一种 Agent」。面向对象地说，是 `Bot has-many AgentRun`、`AgentRun uses AgentLoop`，而不是 `Bot extends Agent`。
- **依赖单向**：Bot 层依赖 Agent 层；`core/ai/agent.py` 不需要知道 `bot_id` 的存在。反过来，Agent 可以完全独立使用（`/api/chat/agent`）。
- **数量不是 1:1**：一个 Bot 可以有 N 次 run；N 个 Bot 共享同一套 Agent 引擎。

结论：**Bot 在 Agent 之上，但这是「包含/使用」关系，不是「继承/升级」关系。** 更准确的说法是：Agent 是能力层，Bot 是组织层。

### 反例（避免误用）

- `/api/chat/agent` 是 **Agent 调用**，不是 Bot：它没有 `bot_id`、没有 run 归属、没有独立记忆。
- `main` 默认 Bot 是 **Bot**：它有稳定的 `bot_id`，对话与记忆挂在它名下，routines 与 runs 都归属于它。
- 「给 Agent 加一个自定义 system prompt」不是 Bot 化，只是换人格；Bot 化的最小闭环是 **身份 + 记忆 + 运行归属**。

### 常见误区：把记忆写进 prompt 就是 Bot 吗？

不是。这最多是「**静态人格 + 静态记忆**」，属于 Agent 的一种用法。两者差在五个机制上：

| 机制 | 写进 prompt | Bot 记忆 |
|---|---|---|
| 读 | 每轮全量注入 | 按 query 相关性检索 top-k |
| 写 | 改代码/配置并重启 | 运行时写入，下一轮即可用 |
| 作用域 | 全局共享 | 按 `bot_id` 隔离 |
| 生命周期 | 无法过期 | 可更新、可遗忘、可设 `expires_at` |
| 溯源 | 不知道来自哪次对话 | `source_run_id` 可追溯 |

判定标准：**能不能在不改代码、不发版的前提下，新增一个角色、更新一条记忆、删除一条记忆，并把一次失败归因到某个角色？** 有一个做不到，就还不是 Bot。

---

## 0.2 职责边界：不是「有没有 prompt」，而是「哪一层负责什么」

正确的方向是把**身份与长期状态**从 Agent 层拿出来，放进 Bot 层。但不能理解成「Agent 不再需要 prompt」——Agent 仍然需要一份**与角色无关的执行契约**。

### 四类作用域（不是严格四层嵌套）

| 概念 | 类别 | 负责 | 不负责 | 本项目位置 |
|---|---|---|---|---|
| **Agent** | 执行机制（engine） | 执行契约：工具循环、上下文窗口管理、重试、流式输出、停止条件 | 人格、长期记忆、角色权限 | `core/ai/agent.py` |
| **Bot** | 责任主体（actor） | 身份与长期状态：人格、职责、记忆、默认策略、模型/预算 | 单次任务的具体指令 | `core/bots/*` |
| **Run** | 工作记录（work item） | 本次任务：输入、检索到的上下文、routine 的 prompt、审批状态 | 跨任务持久身份 | `bot_runs` |
| **Session** | 对话容器（transcript） | 对话连续性：消息历史 | 长期事实 | `chat_messages` |

这四者是**四种不同类别的东西**，不是一条自上而下的链。真实关系是：

```
Bot ──owns──► Run ──uses──► Agent ──calls──► Tool
 │             │
 │             └──belongs to (可选)──► Session
 ├──owns──► Memory
 └──owns──► Routine ──triggers──► Run
```

| 关系 | 类型 | 说明 |
|---|---|---|
| Bot → Run | 拥有（composition） | Bot 删除/归档时，Run 跟随处理 |
| Run → Agent | 使用（use） | Agent 不认识 Bot / Run / Session |
| Run → Session | 关联（association，可选） | 例程触发的 Run 可以没有 Session |
| Bot → Memory | 拥有 | 按 `bot_id` 隔离 |
| Bot → Routine | 拥有 | Routine 触发 Run |

基数：

- Bot `1 : N` Run / Memory / Routine
- Run `1 : N` Agent loop invocation（v0 通常 1；审批恢复、子任务会 > 1）
- Session `1 : N` Run
- Run `0..1 : 1` Session

**唯一的严格层级只有「Bot 拥有 Run」；其余是使用或关联。** 把四者做成 `Bot extends Agent extends Run` 之类的线性继承，是范畴错误：Bot 是责任主体，Run 是记录，Agent 是机制，Session 是容器。

### 四条规则

1. **Agent 层只认 `AgentSpec`，不读全局配置。** `settings.assistant_system_prompt` 只作为 `main` Bot 的种子，不再被 Agent 直接读取。
2. **Bot 层不实现工具循环，只组装 spec + context。** 它决定「用谁、记得什么、允许做什么」，不决定「怎么循环」。
3. **Run 层不写回人格。** 它只产生「记忆候选」，由 Bot 层决定是否沉淀、是否过期。
4. **Session 不是记忆。** Session 只保存对话原文；长期事实必须经 Run 提炼后写入 Bot 记忆，不能靠翻聊天记录。

### 接口形状

```python
@dataclass
class AgentSpec:
    instructions: str          # 与角色无关的执行契约
    model: str
    temperature: float
    tools: list[MCPTool]
    max_turns: int
    token_budget: int | None
    on_event: Callable         # 落库 + SSE

async def run_agent_stream(spec: AgentSpec, messages: list[dict]): ...
```

Bot 层的组装：

```python
bot = await get_bot(bot_id)
run = await create_run(bot, input)

context = await build_bot_context(bot, query)   # 人格 + 记忆 + 共享事实
spec = AgentSpec(
    instructions=AGENT_BASE_PROMPT,             # 执行契约，Agent 层持有
    model=bot.model or settings.llm_model,
    tools=resolve_tools(bot.allowed_tools),     # Bot 层决定工具子集
    max_turns=bot.max_turns,
    token_budget=bot.token_budget,
    on_event=lambda e: persist_and_stream(run, e),
)
messages = compose(bot.system_prompt, context, history, run.input)
await run_agent_stream(spec, messages)
```

### 两个容易踩的坑

- **搬家不等于分层。** 把一段记忆字符串从 `agent.py` 挪到 `runner.py`，如果仍然是「每轮全量拼接」，那只是换了文件位置。分层的标志是**读写接口**：记忆有检索、写入、过期、删除，身份有 `bot_id`，运行有归属。
- **工具调用能力主要不靠 system prompt。** 工具的名称、描述、schema 才是第一杠杆；Agent 层的契约只负责「什么时候必须调用、调用失败怎么办、什么时候停」。把具体业务规则塞进 Agent 的 prompt，等于把 Bot 的职责又漏回去了。
- **别把 routine 的指令写进 Bot 人格。** 那是 Run 层的输入；写进人格会导致所有后续对话都被这次任务污染。

### 一句话检验

> 同一个 Bot 换一个 Agent 实现，人格和记忆应该不变；同一个 Agent 换一个 Bot，执行逻辑应该不变。

满足这条，分层才是真的。

---

## 0.3 子 Agent 与子 Run：能力调用还是 Bot 交接

典型例子：**一个助手 Bot，只有在用户要求写代码时，才调用编码 agent。**

结论：编码 agent 是**能力**，不是 Bot。默认应作为工具或子 Run 挂在助手的 Run 下，而不是再建一个平级 Bot。

### 三种做法

| 做法 | 适用 | 新建 Bot | 新建 Run |
|---|---|---|---|
| 内联工具调用 | 秒级、无副作用、结果直接回父上下文 | 否 | 否 |
| **子 Run（编码推荐）** | 分钟级、要审计、可取消、可恢复 | 否 | 是 |
| Bot 交接 | 有独立记忆、权限、触发器、长期职责 | 是 | 是 |

编码任务同时具备「长、贵、危险、产物多」四个特征（diff、commit、命令日志、测试结果），所以默认选**子 Run**，不是内联调用，也不是新建 Bot。

```
Bot: 助手
 └─ Run: "帮我修这个 bug"
     ├─ Agent loop（助手）
     │   ├─ tool: search_knowledge
     │   └─ tool: delegate_coding ──► 子 Run（vibecoding）
     │                                  └─ Agent loop（编码 harness）
     └─ 产物：diff / commit / 测试报告
```

### 为什么编码不适合内联

- 一次工具调用阻塞几分钟，父 Run 无法取消、无法心跳、无法审批。
- 编码要跑 `exec` 类命令，必须走审批闸门。
- 失败要能单独归因到子 Run，而不是污染父 Run 的输出。

### 什么时候才需要「编码 Bot」

只有满足至少一条：

- 需要长期记住仓库约定、代码风格、历史 review 结论；
- 有独立的权限边界（比如只能读某个 workspace）；
- 有自己的触发器（监听 PR、定时跑测试）；
- 需要和别的 Bot 交接产物。

否则，新建一个「编码 Bot」只会多出两套记忆和两套权限，收益很低。

### 0.4 Coding：运行时属于核心，项目管理才是插件

`plugins/vibecoding` 现在把两件不同的事混在了一起：

1. **Coding 运行时**：agent loop、workspace、sandbox、git 策略、delivery
2. **项目管理**：项目列表、任务记录、分支/提交/产物视图

这两者不应该在同一个插件里。**Coding 是 Bot 的能力，属于核心运行时；项目管理才是业务插件，和日程、文件、笔记同级。**

正确的落位：

| 层 | 负责 | 位置 |
|---|---|---|
| Bot | 身份、记忆、策略、触发器 | `core/bots` |
| Run | 一次任务的状态、审计、取消、审批 | `bot_runs` |
| Coding runtime | agent loop、sandbox、workspace、git delivery | `core/coding/` |
| Project management | 项目注册、任务/分支/提交/产物视图 | `plugins/projects/` |

目标结构：

```text
core/
  coding/
    workspace.py      # 路径约束、sandbox、git 策略
    delivery.py       # verify → branch → commit
    engine.py         # builtin coding loop
    opencode.py       # OpenCode 适配器
    prompts.py
  ai/mcp/tools/coding.py   # delegate_coding / list_projects / list_tasks
  bots/runner.py           # 创建子 Run，注入权限与预算

plugins/
  projects/           # 项目管理（与 schedule/files 同级）
    models.py         # project、任务视图、交付物
    router.py         # 项目 CRUD、Run/分支/产物查询
    frontend/         # 项目面板
```

主流程：

```text
主 Bot → Run（帮我改登录页）
          └─ Agent（主助手）
               └─ tool: delegate_coding
                    └─ 子 Run（trigger=coding，parent_run_id=...）
                         └─ Coding runtime（builtin / OpenCode）
                              └─ workspace / delivery / 产物
```

规则：

- **插件里不允许再有 agent loop、sandbox、git delivery。**
- `plugins/vibecoding` 应该被拆掉并重命名为 `plugins/projects`。
- `vibecoding_tasks` 不作为第二套任务真相；统一落到 `bot_runs`，项目插件只补充项目元数据和视图。
- 项目管理插件可以调用核心 coding runtime，但不能自己实现一套。

**结论：Coding 不是插件，Coding 是核心能力；项目管理才是插件。**

---

## 1. 背景

xAI 对 Grok Bot 的定义是：

> Bots are **persistent agents** with their own **identity, memory, runtime, and tools**.
> Chats are disposable. The main objects are **Bots, not conversations**.

这恰好是 OmniAide 目前缺的那一层：我们有工具、有记忆、有事件流，但**只有一个全局助理**，所有场景共享一份会话和一套上下文。Bot 化改造就是把「一次性对话」变成「可持续的职责」。

### 为什么 OmniAide 适合 Bot 形态

- 已有 MCP 工具注册中心，Bot 可以按需分配工具子集。
- 已有 `user_profiles`、`user_activities`、pgvector 向量表（`embeddings`），记忆分层有现成底座。
- 已有 `scheduler_loop`、通知中心、WebSocket、设备事件通道，常驻与主动推送的管道是通的。
- 自托管意味着「云电脑」这层可以换成「你自己服务器上的执行环境」，数据主权反而是差异化优势。

### 非目标

- **不做厂商云电脑**：不引入远程桌面/浏览器登录态托管。执行环境就是本机后端容器。
- **不替换 coding harness**：代码类任务仍交给 vibecoding 专用链路。
- **不追求多 Bot 社交**：第一阶段不做 Bot 间自主群聊；先把单 Bot 常驻跑稳。
- **不做多租户隔离**：仍按单用户设计，表结构保留 `user_id` 以便未来扩展。

---

## 2. 目标

| 编号 | 目标 | 验收信号 |
|---|---|---|
| G1 | Bot 成为一等公民：有名字、职责、头像、独立提示词 | 侧边栏可在多个 Bot 间切换 |
| G2 | 每个 Bot 有独立记忆，同时共享用户事实 | A Bot 的偏好不会污染 B Bot |
| G3 | 任务可常驻：关掉页面后继续跑，重启后可恢复 | `bot_runs` 有完整状态，重启不丢任务 |
| G4 | 例程可自动触发：定时 + 事件 | 晨间简报由 routine 驱动，而非硬编码 |
| G5 | 危险动作有人工审批闸门 | 执行类工具默认 `ask`，可在 UI 批准/拒绝 |

---

## 3. 现状盘点

| 能力 | 现有实现 | 复用方式 |
|---|---|---|
| Agent 循环 | `backend/core/ai/agent.py` 的 `run_agent` / `run_agent_stream` | 保留循环，增加 `bot_id`、run 状态回写 |
| 工具注册 | `backend/core/ai/mcp/registry.py`、`register_core.py`、`register_ai.py`、`plugin_tools.py` | 增加「工具风险等级 + 按 Bot 过滤」 |
| 会话存储 | `plugins/chat/backend/models.py` 的 `ChatMessage` / `ChatSession` | 增加 `bot_id` 列，历史按 Bot 分区 |
| 上下文注入 | `plugins/chat/backend/memory.py` 的 `build_context(user_id, query)` | 扩展为 `build_bot_context(user_id, bot_id, query)` |
| 用户画像 | `core/auth/domain/models.py` 的 `UserProfile` | 作为共享事实层，不拆 |
| 事件流 | `core/events/bus.py` 的 `record_event` / `worker_loop`，`UserActivity` 表 | 作为 routine 的事件触发器来源 |
| 后台调度 | `core/ai/scheduler.py` 的 `scheduler_loop`（硬编码简报/提醒/扫描/日分析） | 拆成「系统级调度 + Bot routine」两层 |
| 通知 | `plugins/notifications` 的 `create_notification` + `core/wschannel/hub.py` + 设备事件 | 复用，新增 `approval` 类型 |
| 记忆/洞察 | `core/ai/insights.py`、`core/ai/indexer.py`、pgvector `embeddings` | 增加按 Bot 的记忆命名空间 |
| 启动装配 | `backend/main.py` 的 `lifespan` | 增加 Bot runner / routine loop |

### 关键缺口

1. **没有身份层**：`settings.assistant_system_prompt` 是全局唯一的，`llm_model` 也是全局的。
2. **没有 run 概念**：一次请求就是一次 SSE，进程重启即丢。
3. **没有例程**：简报时间写死在 `settings.morning_brief_hour/minute`。
4. **没有审批**：`tool_registry.call()` 直接执行，`quicklinks` 这类能跑脚本的工具没有任何闸门。
5. **记忆没有分区**：`build_context` 只按 `user_id` 取画像和实体。

---

## 4. 目标架构

```
┌──────────────────────────────────────────────────────────┐
│                        端层                               │
│  Web / Electron / Flutter / ESP 设备 / 语音               │
│  侧边栏 Bot 切换 · 审批卡片 · 运行状态                     │
└───────────────────────────┬──────────────────────────────┘
                            │ /api/bots/*  ·  SSE
┌───────────────────────────▼──────────────────────────────┐
│                     Bot 服务层（新增）                     │
│  core/bots/                                              │
│   ├─ registry.py    Bot CRUD / 默认 Bot 种子               │
│   ├─ runner.py      Run 状态机 · 执行器 · 恢复             │
│   ├─ routines.py    cron / event 触发器                   │
│   ├─ memory.py      共享事实 + Bot 私有记忆               │
│   └─ policy.py      工具风险分级 · 审批                    │
└───────┬───────────────┬───────────────┬──────────────────┘
        │               │               │
┌───────▼──────┐ ┌──────▼───────┐ ┌─────▼────────────┐
│ Agent 循环    │ │ MCP 工具注册  │ │ 事件总线          │
│ (现有)        │ │ (现有)        │ │ (现有)            │
└───────┬──────┘ └──────┬───────┘ └─────┬────────────┘
        │               │               │
┌───────▼───────────────▼───────────────▼──────────────────┐
│                     数据与记忆层                          │
│  MySQL: bots / bot_memories / bot_routines / bot_runs     │
│         bot_approvals / chat_messages(bot_id)             │
│  pgvector: omnidocs · entities · bot_memory               │
│  Redis:  run queue · 锁 · 事件队列                        │
└──────────────────────────────────────────────────────────┘
```

---

## 5. 数据模型

新增表放在 `backend/core/bots/models.py`，在 `main.py` lifespan 的 `Base.metadata.create_all` 前 import。

### 5.1 `bots`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | |
| `user_id` | int FK users.id, index | |
| `slug` | varchar(64) | 用户内唯一，如 `main`、`notes`、`news` |
| `name` | varchar(100) | 显示名 |
| `avatar` | varchar(200) | emoji 或图片 URL |
| `role` | varchar(200) | 一句话职责 |
| `system_prompt` | text | 该 Bot 的人格与规则 |
| `model` | varchar(100) nullable | 为空则用 `settings.llm_model` |
| `temperature` | float default 0.7 | |
| `allowed_tools` | JSON nullable | 为空 = 全部允许 |
| `risk_policy` | JSON nullable | 覆盖默认风险策略 |
| `max_turns` | int default 20 | |
| `token_budget` | int nullable | 单次 run 上限 |
| `status` | varchar(20) default `active` | `active` / `archived` |
| `created_at` / `updated_at` | datetime | |

唯一索引：`(user_id, slug)`。

种子逻辑：首次启动创建 `slug=main` 的默认 Bot，`system_prompt` 取 `settings.assistant_system_prompt`，`allowed_tools=NULL`。

### 5.2 `bot_memories`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | |
| `bot_id` | int FK bots.id, index | |
| `user_id` | int, index | 方便按用户清理 |
| `kind` | varchar(20) | `fact` / `preference` / `summary` / `skill` |
| `content` | text | 记忆正文 |
| `importance` | float default 0.5 | 检索加权 |
| `source_run_id` | int nullable | 溯源 |
| `created_at` / `updated_at` | datetime | |
| `expires_at` | datetime nullable | 支持遗忘 |

向量写入 `embeddings` 表（`collection=bot_memory`），`metadata` 含 `{user_id, bot_id, memory_id, kind}`。

### 5.3 `bot_routines`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | |
| `bot_id` | int FK, index | |
| `user_id` | int, index | |
| `name` | varchar(120) | |
| `trigger_type` | varchar(20) | `cron` / `event` / `manual` |
| `cron_expr` | varchar(64) nullable | 5 段 cron，如 `30 7 * * *` |
| `event_type` | varchar(50) nullable | 对应 `UserActivity.event_type` |
| `event_filter` | JSON nullable | 简单等值过滤 |
| `prompt` | text | 触发时交给 Bot 的任务 |
| `enabled` | bool default true | |
| `next_run_at` | datetime nullable | cron 用 |
| `last_run_at` | datetime nullable | |
| `last_status` | varchar(20) nullable | |
| `created_at` / `updated_at` | datetime | |

### 5.4 `bot_runs`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | |
| `bot_id` / `user_id` | int FK, index | |
| `routine_id` | int nullable | |
| `trigger` | varchar(20) | `chat` / `cron` / `event` / `api` |
| `status` | varchar(20) | `queued` / `running` / `waiting_approval` / `done` / `failed` / `cancelled` |
| `input` | text | 用户/例程输入 |
| `output` | text nullable | 最终回复 |
| `error` | text nullable | |
| `tokens_in` / `tokens_out` | int default 0 | |
| `idempotency_key` | varchar(120) nullable, unique | 防止例程重复触发 |
| `started_at` / `finished_at` / `heartbeat_at` | datetime | |
| `created_at` | datetime | |

恢复规则：启动时把 `running` 且 `heartbeat_at` 超过 5 分钟的标记为 `failed`（原因 `interrupted`）；`queued` 重新入队。

### 5.5 `bot_approvals`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | |
| `run_id` / `bot_id` / `user_id` | int FK, index | |
| `tool_name` | varchar(100) | |
| `arguments` | JSON | |
| `risk_level` | varchar(20) | `write` / `exec` / `external` |
| `status` | varchar(20) | `pending` / `approved` / `denied` / `expired` |
| `reason` | text nullable | 模型给出的理由 |
| `created_at` / `decided_at` | datetime | |

### 5.6 `bot_run_steps`（审计，可选）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | |
| `run_id` | int FK bot_runs.id, index | |
| `seq` | int | 步序 |
| `type` | varchar(20) | `llm` / `tool` / `approval` |
| `tool_name` | varchar(100) nullable | |
| `arguments` | JSON nullable | |
| `result` | text nullable | 截断保存 |
| `status` | varchar(20) | `ok` / `error` / `denied` |
| `created_at` | datetime | |

用途：审批追溯、失败复盘、产物溯源。数据量大时按 `run_id` 定期归档。

### 5.7 会话表变更

`chat_messages` 与 `chat_sessions` 增加 `bot_id`（int nullable, index）。约定 `NULL` = `main` Bot，保证旧数据与旧接口兼容。迁移走 `core/database/migrations.py` 的 `ensure_schema_migrations()`，不要手写一次性脚本。

---

## 6. 记忆分层

三层，读时合并、写时分离：

```
L0 共享事实（全局，唯一）
   UserProfile: 姓名/角色/公司/联系人/项目/开发者档案/preferences
   来源：手动填写 + 每日分析（core/ai/scheduler.py::_daily_event_analysis）

L1 Bot 私有记忆（按 bot_id 隔离）
   bot_memories: fact / preference / summary / skill
   来源：run 结束后的摘要 + 显式「记住这件事」

L2 会话历史（按 bot_id + session_id 隔离）
   chat_messages
```

### 读取

`build_bot_context(user_id, bot_id, query)`：

1. 取 `UserProfile` → 「用户信息」段。
2. 取该 Bot 最近 N 条 `summary` + 向量召回 top-k `bot_memories` → 「本 Bot 记忆」段。
3. 复用 `memory.py` 的实体召回（`entities` collection）。
4. 拼接顺序：全局人格 → Bot 人格 → 用户信息 → Bot 记忆 → 相关实体 → 历史。

### 写入

- 一次 run 结束后，若满足任一条件（超过 6 轮、工具调用 ≥ 3 次、输出长度 > 800 字），异步生成一条 `summary`。
- 「记住」类指令显式写 `fact` / `preference`。
- 每日分析（现有 `_daily_event_analysis`）只更新 L0；L1 的整理单独按 Bot 跑，避免把所有行为都归因到某个 Bot。

### 冲突规则

- **身份与事实以 L0 为准**：姓名、公司、联系人等 L1 不得覆盖。
- **工作方式以 L1 为准**：例如「写作 Bot 偏好先列大纲」只影响该 Bot。
- 硬删除 Bot（`?purge=true`）→ 级联删除 `bot_memories`、`bot_routines` 与 pgvector `embeddings` 中对应记录；默认删除为归档，保留数据。
- 提供 `DELETE /api/bots/{id}/memories?kind=` 支持定向遗忘。

---

## 7. 运行时与任务模型

### 状态机

```
queued ──► running ──► done
             │  ▲
             │  └── waiting_approval ──► running
             ├──► failed
             └──► cancelled
```

### 执行器

分两步走，避免一开始就引入重中间件：

**v0（先做）**：进程内执行器。

- `core/bots/runner.py` 用 `asyncio.create_task` + 信号量限制并发（默认 2）。
- 每个 run 落库并每 15 秒更新 `heartbeat_at`。
- 复用 `run_agent_stream` 的循环，但把事件回调改成写 `bot_runs` + 推送 SSE。
- 适合当前单进程部署，改动最小。

**v1（有需要再上）**：Redis 队列。

- 复用 `core/events/bus.py::worker_loop` 的模式，新增 `bot_run_queue`。
- 多 worker 时用 Redis 锁保证同一 routine 不并发。
- 与 v0 接口保持一致，只换调度实现。

### 事件协议（SSE）

在现有 `token` / `reasoning` / `tool_call` / `tool_result` / `usage` / `done` 之外增加：

| 事件 | 时机 |
|---|---|
| `run_started` | 返回 `run_id`、`bot_id` |
| `approval_required` | 命中审批策略，附带 `approval_id`、`tool_name`、`arguments` |
| `run_finished` | 终态 + 摘要 |

`done` 保留，客户端不必一次性改完。

### 预算与取消

- `max_turns` 取 Bot 配置，默认 20；routine 触发的 run 默认 12。
- `token_budget` 超限 → `failed`，原因 `budget_exceeded`。
- `POST /api/runs/{id}/cancel` 设置取消标志，循环在每个 turn 检查。

---

## 8. 例程与触发器

### 调度分层

| 层 | 负责 | 实现 |
|---|---|---|
| 系统级 | 日程提醒、设备事件、事件扫描 | 保留在 `core/ai/scheduler.py` |
| Bot 级 | 用户/默认 Bot 定义的 cron 与事件例程 | 新增 `core/bots/routines.py` |

### 迁移现有硬编码

把 `_send_briefing` 从「写死 9:30 + 固定提示词」改为：

- 种子一个 routine：`main` Bot，`cron=30 7 * * *`，`prompt="生成今天的晨间简报，包含天气、日程、待办、未读通知和新订阅文章。"`
- `_send_briefing` 的数据组装逻辑保留为 routine 可调用的工具/上下文函数，不再直接决定时间。
- `settings.morning_brief_*` 保留一个版本用于回退，之后标记 deprecated。

### 触发规则

- **cron**：调度循环每分钟检查 `next_run_at <= now`，命中则入队并计算下一次。
- **event**：启动时对 `bus.subscribe` 注册一个匹配器，读取启用的 `bot_routines`，按 `event_type` + `event_filter` 命中后入队。
- **manual**：`POST /api/bots/{id}/routines/{rid}/run`。

### 防抖与幂等

- `idempotency_key = f"{routine_id}:{scheduled_minute}"`，唯一索引挡重复。
- 同一 routine 已有 `queued`/`running` 时，cron 触发跳过（可配置 `coalesce=true`）。
- 事件触发做 60 秒去重窗口，避免一次批量事件触发多次。

---

## 9. 工具权限与审批

### 风险分级

在工具注册时标注，默认 `read`：

| 等级 | 示例 | 默认策略 |
|---|---|---|
| `read` | `search_files`、`list_schedule_events`、`unified_search` | `auto` |
| `write` | `create_schedule_event`、笔记保存、待办创建 | `auto`（可改为 `ask`） |
| `exec` | `quicklinks` 跑脚本、vibecoding 命令、终端 | `ask` |
| `external` | 发邮件、控制设备、对外发送 | `ask` |

工具到等级的映射放在 `core/bots/policy.py` 的 `TOOL_RISK`，未登记的工具按 `read` 处理，但**执行类插件必须在注册时显式登记**，否则拒绝执行（fail-closed）。

### 策略解析顺序

1. Bot 的 `risk_policy` 覆盖；
2. 全局默认；
3. 未登记 → `read`，但名称命中 `exec` 前缀（`shell.`、`script.`、`cmd.`）→ `exec`。

### 审批流程

```
runner 命中 ask
  → 创建 bot_approvals(pending)
  → run 置 waiting_approval
  → create_notification(type="approval")
  → WS 推送 / SSE approval_required
  → 用户批准/拒绝
  → 批准：继续执行该工具；拒绝：把拒绝原因作为 tool 结果回灌模型
  → 24h 未处理：expired，run failed
```

实现上**不要改每个工具**：在 `tool_registry.call` 外面包一层 `policy_gate(user_id, bot_id, run_id, req)`，由 runner 调用。

### 桌面端本地工具

`quicklinks` 等桌面插件实际在 Electron 侧执行。后端只能看到代理调用，因此：

- 后端按工具名做策略判定；
- 客户端在执行前再校验一次，收到 `approval_required` 必须等用户确认；
- 本地执行日志回传 `bot_run_steps`（可选），否则至少回传结果摘要。

---

## 10. API 设计

新增 `backend/core/bots/router.py`，在 `main.py` 注册。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/bots` | 列出 Bot |
| POST | `/api/bots` | 创建 Bot |
| GET/PATCH/DELETE | `/api/bots/{id}` | 详情/更新/删除（默认归档，`?purge=true` 硬删并级联清理） |
| POST | `/api/bots/{id}/chat` | SSE 对话，创建 run |
| GET | `/api/bots/{id}/runs` | 运行历史 |
| GET | `/api/runs/{id}` | 单次运行详情 |
| POST | `/api/runs/{id}/cancel` | 取消 |
| GET/POST | `/api/bots/{id}/routines` | 例程列表/创建 |
| PATCH/DELETE | `/api/bots/{id}/routines/{rid}` | 更新/删除 |
| POST | `/api/bots/{id}/routines/{rid}/run` | 手动触发 |
| GET/DELETE | `/api/bots/{id}/memories` | 查看/遗忘 |
| GET | `/api/approvals?status=pending` | 待审批列表 |
| POST | `/api/approvals/{id}/decision` | 批准/拒绝 |

### 兼容策略

- `/api/chat/agent` 与 `/api/chat/agent/stream` 保持不变，内部解析为 `main` Bot。
- `/api/chat/history`、`/api/chat/sessions` 增加可选 `bot_id`，不传则返回 `main` 或全部。
- 旧客户端不需要改就能继续用；新客户端逐步切到 `/api/bots/{id}/chat`。

---

## 11. 端适配

| 端 | 改造 |
|---|---|
| Web | 侧边栏 Bot 列表；对话头部显示当前 Bot；通知中心增加审批卡片 |
| Electron | 复用 Web 组件；`Ctrl+Shift+A` 打开上次使用的 Bot；本地插件执行前校验审批 |
| Flutter | Bot 选择器 + 运行状态；语音入口固定到 `main` |
| ESP 设备 | 语音固定到 `main`；简报由 routine 产生，设备只负责 TTS |

---

## 12. 与 Grok Bot 的差异

| 维度 | Grok Bot | OmniAide Bot（本方案） |
|---|---|---|
| 运行位置 | 厂商云电脑 | 自己的服务器/容器 |
| 数据主权 | 厂商云 | 全量本地 |
| 隔离 | 同账号 Bot 共用一台云电脑，官方称不构成安全边界 | 同用户共用数据库，但按 `bot_id` 做逻辑分区；执行仍在本机 |
| 模型 | 仅 Grok | 任意 OpenAI 兼容接口，可按 Bot 配模型 |
| 成本 | 订阅 + 厂商算力 | 自己的 API 账单，可设预算/本地模型 |
| 生态 | 连接器 + 电脑操作 | 现有 13+ 插件 + MCP 工具 |
| 协作 | 多 Bot 群聊、主 Bot 调度 | 第一阶段不做，留接口 |

结论：**形态对齐，路线相反**。Grok Bot 用云端能力换开箱即用；OmniAide 用本地部署换数据主权。

---

## 13. 实施阶段

按个人开发节奏估算，每个阶段都可独立交付。

### Phase 0：身份层（0.5–1 天）

- `bots` 表 + 默认 Bot 种子。
- `chat_messages` / `chat_sessions` 加 `bot_id`，迁移脚本。
- `/api/bots` CRUD。
- `build_messages` 支持 Bot 人格与模型。
- Web/Electron 加 Bot 切换器。

**验收**：能创建第二个 Bot，和它对话时人格/模型不同，历史互不串。

### Phase 1：常驻执行（1–2 天）

- `bot_runs` + `bot_run_steps`（可选）。
- `core/bots/runner.py` v0：持久化、心跳、取消、恢复。
- SSE 增加 `run_started` / `run_finished`。
- `POST /api/runs/{id}/cancel`。

**验收**：发起一个长任务，关闭页面再打开仍能看到状态；重启服务后 `queued` 任务继续、`running` 任务标记中断。

### Phase 2：例程（1 天）

- `bot_routines` + cron 计算 + 事件订阅。
- 晨间简报改为种子 routine。
- 幂等键与并发锁。

**验收**：新建一个「每天 22:00 汇总未读 RSS」的例程，第二天能在通知里看到结果；重复触发只产生一次 run。

### Phase 3：记忆分层（1 天）

- `bot_memories` + pgvector `bot_memory` collection。
- `build_bot_context` 合并三层。
- run 结束摘要 + 遗忘接口。

**验收**：两个 Bot 对同一问题的回答体现不同偏好；删除 Bot 后其记忆不可检索。

### Phase 4：审批（1 天）

- 工具风险表 + `policy_gate`。
- `bot_approvals` + 通知 + SSE。
- 客户端审批 UI。

**验收**：让 Bot 执行一个 `exec` 类工具，必须弹审批；拒绝后模型收到拒绝原因并给出替代方案。

### Phase 5（可选）：多 Bot 协作（2–3 天）

- Bot 间消息表 / 任务交接。
- 主 Bot 调度子 Bot。
- 群聊线程。

**验收**：一个「选题 → 写作 → 校对」的链路能自动流转，产物可溯源。

---

## 14. 风险与取舍

| 风险 | 影响 | 缓解 |
|---|---|---|
| 常驻任务烧 token | API 账单失控 | `token_budget`、routine 用便宜模型、失败不自动重试无限次 |
| 记忆漂移 | Bot 记住错误偏好 | L0 权威、记忆可查看可删除、摘要带来源 |
| 权限过宽 | 脚本/文件误操作 | `exec`/`external` 默认 `ask`，fail-closed |
| 单人场景过度设计 | 开发成本 > 收益 | 先 1 个主 Bot + 2 个专职；Phase 5 永远可选 |
| 单进程重启丢任务 | 长任务失败 | run 落库 + 心跳 + 启动恢复 |
| 桌面端绕过审批 | 本地工具直接执行 | 客户端二次校验 + 日志回传 |

### 关键取舍

- **先做「单 Bot + 常驻 + 例程」**，这是 ROI 最高的三件套；记忆分层和审批紧随其后；多 Bot 协作放最后。
- **不做云电脑**，因为 OmniAide 的用户要的就是数据不出门；需要浏览器操作时，用现有远程控制插件或后续加「受控浏览器」工具，而不是把整台机器交出去。
- **保留全局 `settings.llm_model` 作为兜底**，Bot 的 `model` 为空时回退，避免配置爆炸。

---

## 15. 验收清单

- [ ] 默认 `main` Bot 在首次启动自动创建，旧会话仍可读。
- [ ] 至少两个 Bot 的提示词、模型、工具集、记忆互不干扰。
- [ ] run 状态可持久化、可取消、重启可恢复。
- [ ] 晨间简报由 routine 触发，时间可在 UI 修改。
- [ ] 事件触发例程具备幂等与去重。
- [ ] `exec` 类工具必须审批；拒绝后对话可继续。
- [ ] 删除 Bot 级联清理记忆与向量。
- [ ] 旧接口 `/api/chat/*` 行为不变。

---

## 16. 开放问题

1. **记忆摘要用 LLM 还是规则？** 倾向 LLM，但要限制频率（仅在长 run 后触发），否则成本翻倍。
2. **routine 失败是否重试？** 建议最多 1 次，且只在 `failed` 原因为网络/超时时重试；业务失败不重试。
3. **桌面本地工具如何纳入统一审批？** 需要定义客户端 → 后端的审批握手协议，Phase 4 再定。
4. **是否允许 Bot 修改自己的 routine？** 建议禁止，避免自我放大；只允许建议，由用户确认。
5. **多用户预留到什么程度？** 所有新表保留 `user_id`，但唯一索引按 `(user_id, slug)`，暂不做权限模型。

---

## 17. 实现记录

### 2026-11-04：Phase 0（身份层）+ 记忆作用域（Phase 3 前半）

已完成：

- 新增 `backend/core/bots/`：
  - `models.py`：`bots`、`bot_memories`
  - `registry.py`：默认 Bot 懒创建、启动回填、CRUD、默认切换、归档/硬删
  - `router.py`：`/api/bots` 与 `/api/bots/{id}/memories`
  - `memory.py`：按 Bot 隔离的记忆写入、检索、上下文组装
  - `context.py`：用 ContextVar 把 `bot_id` 传给工具
- `chat_messages` / `chat_sessions` 增加 `bot_id`；迁移走 `ensure_schema_migrations()`。
- `/api/chat`、`/api/chat/agent`、`/api/chat/stream`、`/api/chat/voice*` 支持可选 `bot_id`，不传时解析为当前默认 Bot。
- Bot 可配置 `system_prompt`、`model`、`temperature`、`max_turns`、`allowed_tools`。
- `save_memory` 按当前 Bot 落库；`build_bot_context` 合并 L0 用户信息 + L1 Bot 记忆 + 相关实体，并修复了旧实现只注入 `title`（80 字截断）的问题。
- 测试：`backend/tests/test_bots.py` 覆盖默认 Bot、CRUD、跨用户隔离、记忆 CRUD、记忆作用域、默认切换。

实现偏差：

- 记忆向量没有新建 `bot_memory` collection，而是复用 `entities`，在 `metadata.bot_id` 上做过滤。好处是旧记忆可平滑共存，代价是检索时需要多取一些再过滤。

尚未实现（对应 Phase 1/2/4/5）：

- `bot_runs` / `bot_routine` / `bot_approvals` 表与执行器。
- 晨间简报改为 routine 驱动。
- 工具风险分级与审批闸门。
- Web/Electron/Flutter 的 Bot 切换与审批 UI。
- run 结束后的自动记忆摘要。

### 2026-11-05：Phase 1/2/4 + Web/Electron Bot 切换

已完成：

- 新增表：`bot_runs`、`bot_run_steps`、`bot_routines`、`bot_approvals`。
- `core/bots/runner.py`：
  - run 状态机（queued / running / waiting_approval / done / failed / cancelled）
  - 后台执行、心跳、超时、协作式取消、重启恢复
  - SSE 轮询流：`token` / `tool_result` / `approval_required` / `done`
  - run 结束后自动写一条 `summary` 记忆
  - 例程完成后的通知（站内 + WebSocket + 设备事件）
- `core/bots/routines.py`：
  - 5 段 cron 解析与 `next_run`
  - cron 循环 + 事件触发（`UserActivity.event_type` + 简单 filter）
  - 幂等键防重复触发
  - 为每个用户种子 `morning_brief` 例程；旧的硬编码简报在例程存在时自动跳过
- `core/bots/policy.py`：
  - 工具风险分级：read / write / exec / external
  - 默认 read/write=auto，exec/external=ask
  - 支持 Bot 级 `risk_policy` 覆盖（按级别或按工具）
  - 审批暂停后持久化 messages + pending tool call，批准/拒绝后从 checkpoint 恢复
- API：
  - `POST/GET /api/bots/{id}/runs`
  - `GET /api/runs/{id}`、`GET /api/runs/{id}/stream`、`POST /api/runs/{id}/cancel`
  - `GET/POST /api/bots/{id}/routines`、`PATCH/DELETE .../{rid}`、`POST .../{rid}/run`
  - `GET /api/approvals`、`POST /api/approvals/{id}/decision`
  - `POST /api/chat/runs`：带历史与 Bot 人格创建持久 run
- UI：
  - Web `AssistantPanel.vue` 增加 Bot 选择器与待审批条（轮询 `/api/approvals`，可直接允许/拒绝）
  - Electron `assistant/Page.vue` 增加 Bot 选择器、待审批条、历史导入按 Bot 过滤
- 测试：`backend/tests/test_bots.py` 新增 cron、策略、run 生命周期、例程 CRUD、审批状态机；全量 **56 passed**。
- 构建验证：`frontend npm run build`、`desktop npm run build-frontends` 均通过。

仍未实现：

- Flutter 端的 Bot 选择器与审批卡片。
- Phase 5 的多 Bot 协作 / 任务交接。
- 桌面本地工具（quicklinks 等）的客户端二次审批校验。

### 2026-11-05：线上问题修复

- **记忆写不进去**：`from core.config import settings` 实际拿到的是 `core.config` 模块，不是 Settings 对象。修正 `knowledge.py` / `productivity.py` / `personal.py` 的导入，并在 `core/config/__init__.py` 正式导出 `settings`。
- **日程时区错误**：前端 Dashboard 用 `toISOString()` 传 `Z` 时间，asyncpg 把 aware datetime 与 `TIMESTAMP WITHOUT TIME ZONE` 比较时报错。新增 `core/timeutil.py`，统一把 `Z` / `+08:00` 转成本地 naive 时间；覆盖日程查询、创建、更新与待办截止时间。AI 工具的日程默认时间也改为本地 `now()`。
- **通知前端**：
  - WebSocket 断线重连加指数退避，并在组件卸载后停止重连（修复退出登录后仍反复重连）。
  - 通知下拉显示正文、点击跳转 `link`、新增“查看全部通知”。
  - 审批事件通过 `omniaide:approval` 事件即时刷新助手审批条，FAB 显示待审批角标。
  - 通知事件通过 `omniaide:notification` 让 Dashboard 未读数实时刷新。
- 验证：后端 **59 passed**；前端 `npm run build` 通过；线上 `schedule` aware 查询 200、Bot 记忆创建/列表/删除 200。

### 2026-11-05：Bot 控制台

- 新增 `/bots` 页面与侧边栏入口：
  - Bot 列表 / 新建 / 编辑 / 设为默认 / 归档
  - 人格、模型、温度、最大轮次、工具白名单、风险策略、System Prompt
  - 例程 CRUD、启用/停用、手动运行
  - 记忆查看 / 添加 / 删除
  - Runs 列表、详情（输入/输出/错误/步骤）、取消、手动发起
  - 审批列表、参数查看、允许/拒绝
- 通知深链改为 `/bots?tab=runs` / `/bots?tab=approvals`。
- `list_bots` 过滤 `archived`，归档后不再出现在列表。
- 线上冒烟验证：创建/更新 Bot、创建例程、写入/读取记忆、创建/查询/取消 run、归档 Bot 全部通过。

### 2026-11-05：Word / PPT 文档能力

- 新增 `core/ai/mcp/tools/documents.py`：
  - `create_word_document`：Markdown 转 Word，支持标题层级、列表、编号、表格、代码块、分页。
  - `create_presentation`：结构化 slides 转 PPT，支持封面、正文页、备注、结束页。
- 生成文件通过 `plugins/files` 写入 MinIO，并登记到文件库，返回 30 分钟有效的下载链接。
- 两个工具注册进核心 MCP 工具，风险等级为 `write`（自动执行）。
- 线上验证：Word / PPT 均生成成功，下载链接 200，验证后已清理测试文件。
- 设计原则：**一个主助手 + 工具能力**，Word/PPT/改代码都走工具层，不为每种文件类型拆 Bot。

### 2026-11-05：Coding 运行时核心化 + 项目管理插件

- 删除 `plugins/vibecoding`。
- 新增 `core/coding/`：
  - `workspace.py`：路径约束、sandbox、git 策略
  - `delivery.py`：verify → feature/* → commit
  - `context.py`：项目快照
  - `engine.py`：内置 coding agent
  - `models.py` / `service.py`：`coding_runs` 扩展表与 Run 创建
- `BotRun` 保持通用：只增加 `parent_run_id`；不再有 `kind/project/branch/engine`。
- coding 专属信息放到 `coding_runs`：`project_path` / `branch` / `engine`。
- runner 通过 `coding_runs` 是否存在来发现 coding Run，没有 `kind` 判别字段。
- 新工具：`delegate_coding` / `list_coding_projects` / `list_coding_runs`。
- 新增 `plugins/projects`：项目 CRUD、扫描 `/workspace`、项目 Run 列表、发起 Run。
- Web 新增 `/projects` 页面，替换旧 `/coding`；Dashboard 改为读取项目 Run。
- 线上验证：Coding Run #3 只读任务执行成功，steps 为 `list_dir × 5 + delivery`，未修改文件。

### 2026-11-05：Web 移动端适配

- `CoreLayout`：≤768px 侧边栏改为抽屉式，带遮罩；Header 按钮切换抽屉，不再压缩主内容。
- `CoreHeader`：移动端隐藏全局搜索与用户名，缩小间距和面包屑。
- `AssistantPanel`：移动端改为全屏面板，Bot 选择器缩窄，审批条保留。
- `BotConsole` / `Projects`：单列布局，Bot/项目列表改为横向滚动，头部操作换行。
- `Dashboard`：统计卡片在窄屏改为单列，Hero 区纵向排列。
- 全局：移动端缩小页面 padding、弹窗/抽屉全宽、表单标签纵向排列、通知下拉不超出视口。
- 部署后 `/ominaide/`、`/projects`、`/bots` 均返回 200。

### 2026-11-05：项目 Git 属性、导航与通知页

- `projects` 新增 `is_git`：添加项目时用复选框选择是否为 Git 仓库，只有 Git 项目才显示仓库地址和默认分支。
- 移除项目级 `verify_command`：验证命令属于开发者档案 / 运行配置，不再挂在项目上。
- 项目删除改为硬删除，历史 `bot_runs` / `coding_runs` 保留。
- 菜单：`Bot 控制台` 移入“管理”并改名为 `助手管理`；`活动记录` 改为 `活动`；`智能设备` 改为 `设备`。
- Dashboard：待办跳转 `/apps/todo`，未读通知跳转新增的 `/notifications` 页面，不再都落到活动页。
- 新增 `Notifications.vue`：支持全部 / 未读筛选、单条已读、全部已读、跟随通知链接。
- Header 的“查看全部通知”改为跳转 `/notifications`。

### 2026-11-05：项目默认路径、删除目录与委派回复

- 添加项目时路径可留空，后端默认使用 `/workspace/<项目名>`。
- Git 项目必须填写仓库地址；默认分支默认 `master`。
- 删除项目时同时删除项目目录，但拒绝删除工作区根目录或工作区外路径。
- 移除“扫描工作区”接口和页面按钮。
- 修复 `list_coding_runs` 读取 `BotRun.project` 导致的报错，改为联查 `coding_runs`。
- 委派 Coding Run 会继承当前聊天会话：完成后写入聊天历史，并通过 `/ws/host` 的 `chat.chat_reply` 推送到打开的聊天面板。
- 聊天面板手机端：全屏 `100dvh`、安全区适配、隐藏悬浮按钮避免遮挡输入框、气泡字号/间距优化、消息入场动画、Enter 发送与 Shift+Enter 换行，并修复 SSE 分块解析。

### 2026-11-05：Coding Agent 信任加固

- 镜像补齐 `git` / `openssh-client`，创建无特权沙箱用户 `agent`（uid 1001 / gid 1000）。
- `backend/.dockerignore` 排除 `__pycache__`、测试与 DB，避免旧字节码进镜像。
- 默认改为 `CODING_AUTO_PUSH=false`：只提交到 `agent/*` 分支，不自动推送。
- 开发者档案改为 `["read","edit","commit"]`，不再默认授予 push；新增 `verify_command` 支持。
- 本项目验证命令设为 `python -m compileall -q backend`。
- 线上验证：
  - `sandbox_identity=('agent','omniaide')`
  - `run_command` sandbox=`agent`，`git status` 退出码 0
  - `write_file` 后文件 uid=1001
  - 验证命令退出码 0
- 仍建议：启用 push 前换专用 deploy key + 分支保护；把 `compileall` 换成项目真实测试/构建命令。
