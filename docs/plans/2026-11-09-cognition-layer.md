# 认知协同层技术方案与实施计划

> 工作名：认知协同层（`ai/cognition/`）。不是产品名，也不是最终品牌名。
>
> 本文档只描述方案和计划，不代表已经改动代码。

## 1. 背景与目标

OmniAide 已经具备 Bot、Run、Skills、MCP、Memory、Activities、多端和本地执行通道。当前缺口不是“再加一个功能”，而是把已有的能力组织成一个持续感知、目标驱动、可验证、可自我更新的协同系统。

目标：

1. 维护用户当前情境（Situation）
2. 把持续意图变成 Goal，把 Goal 拆成 Task，把 Task 执行成 Run
3. 用 Proposal 统一承接主动建议，形成“建议 → 接受 → 执行 → 验证 → 记忆”的闭环
4. 用 Planner / Architect / Executor / Verifier 等独立 Agent 完成工作，Bot 负责任务委派与长期记忆
5. 用 Capability + Grant 做权限与审批
6. 用 Memory Curator 做记忆扩展与自更新
7. 保持单体和现有技术栈，不做微服务

非目标：

- 不做多个 Bot 互相聊天
- 不做多个独立 Agent 进程
- 不做完全无审批的高风险自主执行
- 不重写 Bot、Run、Skills、MCP、Memory

## 2. 设计原则

1. **Bot 是 principal：拥有人格、长期记忆、权限和用户关系。**
2. **Agent 是执行主体：拥有独立上下文和工作记忆，但不拥有长期记忆/身份。**
3. **AgentProfile 是 Agent 的职责模板；Task 是工作单元；Run 是一次执行。**
4. **多 Agent 分级使用：简单任务单 Agent，复杂任务才拆 Planner / Architect / Executor / Verifier。**
5. **状态进 DB，内容进 DB；附件走现有 files/MinIO。** 不做同一份内容双写。
6. **Proposal 是唯一的主动建议模型。** 不保留 `ActivitySuggestion` 兼容层。
7. **所有高风险动作都要有 Capability、Grant、Approval、Audit。**
8. **Agent 之间用 Task 契约 + Workspace 交接，不传完整聊天记录。**
9. **记忆自动更新，但高影响变更要可审核、可纠正、可遗忘。**
10. **不兼容旧接口时一次性迁移，代码保持干净。**

## 3. 目标架构

```
Bot（principal：人格 / 长期记忆 / 权限）
└─ Goal（工作对象）
   ├─ Planner Agent      → 生成 Task 图
   ├─ Task 1
   │  └─ Executor Agent  → Run
   ├─ Task 2
   │  └─ Executor Agent  → Run
   ├─ Verifier Agent     → 验收
   └─ Workspace（DB）
      ├─ workspace_items
      └─ workspace_artifacts → files / MinIO

Proposal（主动建议）
└─ 用户接受 → Goal
```

新增模块：

```text
backend/ai/cognition/
├─ models.py          # Proposal / Goal / Task / Workspace / Grant
├─ schemas.py
├─ router.py          # /api/cognition/*
├─ situation.py       # 情境快照与 Provider
├─ proposals.py       # 提案生命周期
├─ goals.py           # Goal / Task
├─ planner.py         # Planner Agent：Goal -> Task
├─ agent_profiles.py  # AgentProfile：Agent 的职责模板
├─ dispatcher.py      # Task -> Run
├─ verifier.py        # Verifier Agent：验收
├─ capabilities.py    # 能力注册表
├─ policy.py          # 打断/审批策略
├─ workspace.py       # 工作区读写与导出
├─ triggers.py        # 事件/时间触发
├─ memory_curator.py  # 记忆整理
└─ agents/             # Conductor / Researcher / Comms / Schedule / Verifier
```

依赖方向：

```text
cognition → bots / skills / mcp / memory / files
```

反过来不成立。

## 4. 领域模型

### 4.1 Proposal

```sql
proposals
- id
- user_id
- bot_id
- kind              -- reminder / prepare / reply / schedule / follow_up / risk / opportunity
- title
- reason            -- 为什么现在
- evidence          -- JSON：日程、邮件、活动、记忆、文件
- confidence        -- 0-1
- actions           -- JSON：[{key,label,kind,payload}]
- status            -- new / seen / accepted / snoozed / dismissed / executing / done / failed / expired
- channel           -- silent / now / notification / voice
- dedupe_key
- expires_at
- goal_id           -- 接受后生成
- feedback          -- JSON
- created_at
```

状态机：

```text
new → seen → accepted → executing → done
  │        └→ snoozed → seen
  ├→ dismissed
  └→ expired
```

### 4.2 Goal

```sql
goals
- id
- user_id
- bot_id
- title
- description
- status            -- draft / active / waiting / blocked / done / cancelled
- priority
- due_at
- success_criteria  -- JSON
- context           -- JSON
- workspace_id
- primary_session_id -- 主对话线程；后台执行不依赖它在线
- origin_message_id  -- 从哪条消息创建
- token_budget       -- 目标总 token 预算
- cost_budget        -- 目标总成本预算
- max_steps          -- 最多 Task 数
- max_runs           -- 最多执行次数
- budget_used        -- 已用 token / 成本
- next_wake_at       -- 下次检查时间，可为空
- last_run_at
- created_by        -- user / proposal / automation
- created_at
- updated_at
- completed_at
```

### 4.3 Task

```sql
tasks
- id
- goal_id
- parent_task_id
- title
- description
- agent_profile_key          -- conductor / research / comms / schedule / files / verifier
- status            -- pending / ready / running / waiting_approval / blocked / done / failed
- depends_on        -- JSON
- acceptance        -- JSON
- risk              -- read / suggest / write / destructive / exec
- input             -- JSON
- output            -- JSON
- sort_order
- deadline
- created_at
- updated_at
```

说明：这里的 Task 是 Goal 下的执行任务，不是用户待办。用户待办仍在 `plugin_todo_items`。

### 4.4 Run

由现有 `BotRun` 重命名而来。

```sql
runs
- id
- bot_id
- agent_profile_key
- goal_id
- task_id
- parent_run_id
- routine_id
- session_id
- trigger
- status            -- queued / running / waiting_approval / done / failed / cancelled
- input
- output
- error
- partial
- tokens_in
- tokens_out
- checkpoint
- started_at
- finished_at
- created_at
```

### 4.5 RunStep / Approval

```sql
run_steps
- id
- run_id
- seq
- type
- tool_name
- arguments
- result
- status
- created_at

approvals
- id
- run_id
- task_id
- bot_id
- user_id
- capability_key
- tool_name
- arguments
- risk_level
- status            -- pending / approved / rejected / expired
- reason
- created_at
- decided_at
```

### 4.6 Workspace

```sql
workspaces
- id
- user_id
- bot_id
- goal_id
- status            -- active / archived
- created_at

workspace_items
- id
- workspace_id
- type              -- fact / decision / question / constraint / citation
- key
- content           -- JSONB
- source
- confidence
- created_by
- created_at

workspace_artifacts
- id
- workspace_id
- file_id           -- 关联现有 files 插件
- kind              -- draft / export / attachment
- created_at
```

工作区内容全部在 DB。附件走现有 files/MinIO。用户目录只做导出：

```text
GET /api/cognition/workspaces/{id}/export
→ goal.md / plan.json / tasks.json / items.jsonl / artifacts/
```

导出目录不是数据源，不参与状态更新。

### 4.7 CapabilityGrant

```sql
capability_grants
- id
- user_id
- capability_key
- agent_profile_key
- decision          -- allow / deny
- scope             -- once / session / day / always
- constraints       -- JSON
- expires_at
- created_at
```

## 5. 核心流程

### 5.1 对话

```text
用户消息
  → Situation
  → Memory 检索（带预算）
  → Bot / Run
  → 工具调用
  → 回答
```

### 5.2 Proposal

```text
事件 / 定时 / 活动分析 / Goal 状态
  → Proposal
  → Policy（静默 / 通知 / 语音 / 低风险直接执行）
  → 用户动作
  → Goal / Task / Run
```

### 5.3 Goal

```text
用户持续意图 / 接受 Proposal
  → Goal
  → Conductor 生成 Task
  → Dispatcher 创建 Run
  → Verifier 验收
  → 写回 Workspace / Memory
```

### 5.4 对话、Goal、Task、Run 的关系

对话不是 Goal。对话是交互线程，Goal 是持续结果。

```text
Conversation（对话线程）
├─ message
├─ message
└─ Goal（可选）
   ├─ Task
   │  └─ Run
   └─ Workspace
```

| 概念 | 是什么 | 生命周期 | 例子 |
|---|---|---|---|
| Conversation | 用户和 Bot 的对话线程 | 持续、可归档 | 和 Bot 聊预算 |
| Goal | 用户想要的结果 | 跨天、跨会话 | 周五前拿到预算确认 |
| Task | Goal 下的执行单元 | 可重试、可审批 | 起草给张三的回复 |
| Run | Task 的一次执行 | 一次运行 | 第一次草稿 |

规则：

1. 不是每句话都建 Goal。
2. 问答类消息只存对话，不建 Goal、不建 Task。
3. 一次性工具动作可以建 Run，但不建 Goal。
4. 持续意图才建 Goal：用户明确说“帮我跟踪/周五前/以后每周”，或接受 Proposal。
5. 一个 Goal 有一个主对话线程 `primary_session_id`；后台执行不依赖对话在线，结果回到线程和通知。
6. 一个对话可以关联多个 Goal；一个 Goal 也可以有多个相关对话，第一版先做“一个主线程 + 关联线程”。
7. 周期性意图优先走 Routine / Automation；每次触发可以生成 Goal 或 Task。
8. 不同 Bot 的对话和 Goal 相互隔离。

例子：

```text
“今天天气怎么样”
→ 只有对话消息。

“帮我查一下明天的会议”
→ 对话 + 一次性 Run，不建 Goal。

“周五前帮我拿到预算确认”
→ Goal + Task + Run，主线程就是当前对话。

“以后每周一帮我整理上周”
→ Routine；每次触发创建一个 Goal 或 Task。
```

### 5.5 执行模型与 Token 成本

对话、Goal、Task、Run 是四种不同的执行模式：

| 模式 | 触发 | 是否持久化 | Token 消耗 |
|---|---|---|---|
| 对话轮次 | 用户发消息 | 只存消息 | 一次请求 |
| 一次性 Run | 用户命令或工具动作 | 可存 Run | 执行期间 |
| Goal | 持续意图 / 接受 Proposal | Goal + Task | 只在 Task 执行时 |
| Routine | 定时 / 事件 | 每次一个 Run | 每次触发 |

关键结论：

1. **对话轮次不强制建 Run。**  
   纯问答只走 chat 执行循环；需要审批、后台执行、任务编排时才建 Run。

2. **Goal 不是常驻循环。**  
   Goal 只是状态机。`active` 表示“在跟踪”，不表示“在跑”。  
   只有某个 Task 进入 `running` 时才创建 Run、消耗 token。

3. **Goal 是事件驱动 + 预算驱动。**
   - 创建时：Conductor 规划，消耗一次或几次模型调用。
   - 执行时：每个 Task 一次 Run，消耗一次执行预算。
   - 等待时：`waiting` / `blocked` 状态不消耗 token。
   - 检查时：`next_wake_at` 到点只做确定性检查；需要模型时才调用。
   - 完成/失败/取消/超预算：停止。

4. **预算控制。**

```text
Goal
├─ token_budget
├─ cost_budget
├─ max_steps
├─ max_runs
├─ budget_used
└─ next_wake_at
```

超预算时：

```text
Goal → paused
Proposal：目标预算已用完，是否继续？
```

5. **低成本检查优先。**
   - 先查数据库/事件，不调用模型。
   - 只有满足条件才调用 LLM。
   - 规划/验证可用小模型，执行再用大模型。

6. **对话是同步的，Goal 是异步的。**
   - 对话：用户等待回答，流式返回。
   - Goal：后台执行，进度写回主线程和通知。

### 5.6 Agent 是执行主体，AgentProfile 是模板

Bot 是 principal，Agent 是执行主体。

```text
Bot（principal：人格 / 长期记忆 / 权限）
├─ Planner Agent      拆解 Goal，生成 Task
├─ Architect Agent    设计实现方案（复杂任务才启用）
├─ Executor Agent     执行 Task
├─ Researcher Agent   查资料、邮件、文件、记忆
└─ Verifier Agent     验收 Task 输出
```

每个 Agent：

- 有自己的上下文窗口和工作记忆
- 有独立的 Task 契约
- 只拿完成当前 Task 所需的信息
- 不拥有长期记忆、人格、账号
- 通过 MemoryPort 读写 Bot 的记忆
- 权限只能是 Bot 权限的子集

AgentProfile 是 Agent 的模板：

- system prompt
- 可用能力
- 模型
- 预算
- 验收标准

一个 AgentProfile 定义一类 Agent；一个 Agent 实例在一次 Task 中只使用一个 AgentProfile。

### 5.7 分级执行：不是所有任务都上多 Agent

| 模式 | 执行方式 | 上下文 | 例子 |
|---|---|---|---|
| **Chat** | Bot 直接回答 | 对话历史 + Situation | 今天有什么安排 |
| **Simple Goal** | 单 Agent 完成 | Goal + Task 契约 | 查一下明天会议并建提醒 |
| **Complex Goal** | 多 Agent 协作 | 每个 Agent 独立上下文 | 准备预算评审并跟进确认 |

复杂任务才拆：

```text
Bot
└─ Goal
   ├─ Planner Agent       → Task 图
   ├─ Executor Agent 1    → Run
   ├─ Executor Agent 2    → Run
   ├─ Verifier Agent      → 验收
   └─ Bot                 → 汇总 / 更新长期记忆
```

关键点：

1. Chat 不建 Goal，也不建 Task。  
2. 简单 Goal 用一个 Agent，避免多 Agent 开销。  
3. 复杂 Goal 才启动 Planner / Executor / Verifier；Architect 只在方案设计类任务启用。  
4. Agent 之间不传聊天历史，只传 Task 契约和 Workspace 引用。  
5. Verifier 使用独立上下文，避免“自己写、自己判”的自我确认偏差。  
6. Bot 不直接执行 Task，Bot 负责委派、审批、汇总和长期记忆。

判断规则：

```text
一次性问答               → Chat
一次性动作/工具调用       → One-off Run
跨天、多步骤、要验收、
要后台、要审批、要跨端    → Goal
周期性                   → Routine，每次生成 Run 或 Goal
```

### 5.8 为什么不能只靠会话

会话能解决“现在回答我”，但解决不了“持续替我做”。

| 需求 | 会话 | Goal |
|---|---|---|
| 跨天跟踪 | 容易丢 | 持久状态 |
| 多步骤 | 线性聊天 | Task 依赖 |
| 后台执行 | 关闭即停 | 独立运行 |
| 失败重试 | 用户重说 | Task 级重试 |
| 人工审批 | 混在聊天里 | Approval |
| 验收 | 没有标准 | acceptance |
| 多端继续 | 会话绑定端 | Goal 绑定用户 |
| 成本控制 | 无边界 | 预算 |
| 审计 | 消息级 | Goal/Task/Run 级 |

所以：

> **对话是入口，Goal 是工作对象；不是替代关系。**  
> 大多数对话不需要 Goal；只有“持续意图”才升级成 Goal。

### 5.9 Goal 执行时序与状态机

Goal 不常驻。它只在被触发时执行一次 `tick`，然后回到等待。

```text
draft
  → planning
  → ready
  → running
  → verifying
  → waiting
  → done

异常分支：
running → waiting_approval → running
running → blocked
running → failed
any     → paused（超预算）
any     → cancelled
```

一次 tick：

```python
async def goal_tick(goal_id: int) -> None:
    goal = await load_goal(goal_id)
    if goal.status in TERMINAL or goal.status == "paused":
        return

    if goal.budget_exceeded:
        await pause_goal(goal, reason="budget")
        await create_proposal(goal, "预算已用完，是否继续？")
        return

    if goal.status == "draft":
        await plan_goal(goal)          # Conductor 生成 Task
        goal.status = "ready"

    if goal.status == "ready":
        ready = await ready_tasks(goal)  # 依赖已满足
        for task in ready[:goal.max_concurrency]:
            if task.requires_approval and not has_grant(task):
                await create_approval(task)
                continue
            await dispatch_task(task)   # 创建 Run
            task.status = "running"

    if goal.status == "running":
        # 不在这里等待 Run；Run 完成会回调
        return

    if goal.status == "verifying":
        await verify_goal(goal)
        return

    if goal.status == "waiting":
        if await all_tasks_done(goal):
            goal.status = "verifying"
        else:
            await schedule_next_wake(goal)
```

触发源：

- 用户消息明确指向该 Goal
- 相关事件：邮件、日程、待办、活动
- `next_wake_at` 到点
- Approval 决策
- 用户手动“继续”
- 子 Run 完成回调

并发与预算：

- 每个 Goal 最多 1–2 个并发 Task
- 全局 Run 并发受 `bot_run_concurrency` 限制
- 每个 Task 有最大重试次数
- 每个 Goal 有 `token_budget` / `cost_budget` / `max_runs`
- 超预算 → `paused` + Proposal，不静默烧 token

一次完整示例：

```text
周一 09:00  用户说“周五前拿到预算确认”
            → Goal draft
            → planning：1 次模型调用
            → ready：research / draft / schedule / follow-up

周一 09:01  research：查邮件、文件、记忆
            → 2 次工具调用 + 1 次总结
            → done

周一 09:02  draft：生成回复草稿
            → 1 次模型调用
            → verifier：1 次模型调用
            → waiting_approval

周一 09:03  用户批准草稿
            → 发送或保存
            → waiting

周二 10:00  收到张三邮件
            → 确定性判断：相关
            → 触发 follow-up Task
            → 1 次模型调用

周三 09:00  next_wake_at
            → 先查数据：没有新进展
            → 生成 Proposal：是否催一下？
            → 不直接调模型

周五 18:00  Goal done / failed
```

关键点：**等待期间 0 token；只有 planning、task、verification 真正执行时才消耗。**

Handoff 契约：

```json
{
  "task_id": 123,
  "goal_id": 45,
  "assignee": "comms",
  "objective": "起草给张三的预算确认回复",
  "inputs": {"mail_id": 998},
  "constraints": {"tone": "professional", "no_commitment": true},
  "acceptance": ["确认收到", "给出下一步", "不承诺日期"],
  "risk": "suggest",
  "return_schema": {"subject": "string", "body": "string", "citations": "array"}
}
```

返回：

```json
{
  "task_id": 123,
  "status": "done",
  "summary": "已生成回复草稿",
  "artifacts": [{"type": "draft", "id": 55}],
  "citations": [{"source": "mail", "id": 998}],
  "confidence": 0.86
}
```

## 6. API

```http
GET    /api/cognition/now
GET    /api/cognition/proposals
POST   /api/cognition/proposals/{id}/act
GET    /api/cognition/goals
POST   /api/cognition/goals
GET    /api/cognition/goals/{id}
POST   /api/cognition/goals/{id}/plan
GET    /api/cognition/goals/{id}/tasks
GET    /api/cognition/workspaces/{id}
GET    /api/cognition/workspaces/{id}/export
GET    /api/cognition/capabilities
GET    /api/cognition/grants
POST   /api/cognition/grants
DELETE /api/cognition/grants/{id}

GET    /api/runs
GET    /api/runs/{id}
POST   /api/runs/{id}/cancel
GET    /api/approvals
POST   /api/approvals/{id}/decision
```

不保留：

- `/api/insights/suggestions`
- `ActivitySuggestion` 模型
- `BotRun` 命名

## 7. Bot 是 Principal，Agent 是 Worker

| 概念 | 说明 | 面向用户 |
|---|---|---|
| Bot | principal：人格、长期记忆、权限、用户关系 | 是 |
| Agent | 执行主体：独立上下文、工作记忆、Task 契约 | 否 |
| AgentProfile | Agent 的职责模板：prompt / 能力 / 模型 / 预算 | 否 |
| Goal | Bot 的工作对象 | 是 |
| Task | 工作中一个可执行单元，指定 `agent_profile_key` | 部分可见 |
| Run | 某个 Agent 执行 Task 的一次运行 | 可审计 |
| Workspace | Agent 之间共享的事实、产物、决策 | 可查看 |

第一版不做多 Bot 协作。

### 7.1 Bot 驱动 Goal，Agent 执行 Task

用户向 Bot 交代目标；Bot 是 Goal 的拥有者和责任人。Bot 把 Task 委派给 Agent，Agent 在自己的上下文里执行。

```text
用户
  → Bot（principal）
      → Goal
          → Planner Agent      生成 Task 图
          → Task 1
              → Executor Agent → Run
          → Task 2
              → Executor Agent → Run
          → Verifier Agent     验收
          → Bot                汇总 / 更新长期记忆
```

- Bot：拥有身份、长期记忆、权限、用户关系
- Goal：这次工作的持久对象，归属 Bot
- Agent：一次执行主体，有自己的上下文和工作记忆
- Task：分派给某个 Agent 的工作单元
- Run：Agent 执行 Task 的一次记录
- AgentProfile：Agent 的职责模板，不是 Agent 本身

Agent 不拥有长期记忆、人格、账号；它通过 MemoryPort 读取 Bot 的记忆，并把候选记忆写回 Bot。

### 7.2 Agent 与 AgentProfile 的关系

- **Agent** 是执行主体，有独立上下文、工作记忆、运行生命周期。
- **AgentProfile** 是职责模板：prompt、能力子集、模型、预算、验收标准。
- 一个 AgentProfile 可以实例化多个 Agent。
- 一个 Agent 实例在一次 Task 中只使用一个 AgentProfile。
- AgentProfile 是模板，Agent 是实例。

为什么不用一个 Agent 切换所有 AgentProfile：

- 规划、执行、验收的上下文应该隔离，避免相互污染
- Verifier 需要独立上下文，否则容易“自己写、自己判”
- 复杂任务可以并行
- 不同 AgentProfile 可以用不同模型、预算和工具

但不是所有任务都上多 Agent：

```text
Chat          → Bot 直接回答
Simple Goal   → 单个 Agent 完成
Complex Goal  → Planner + Executor(s) + Verifier
方案设计类     → 额外启用 Architect Agent
```

Agent 的生命周期：

- 默认按 Task 创建，Task 完成即结束
- 工作记忆只存在于该 Agent 的上下文和 Workspace
- 长期记忆由 Bot 统一管理
- 需要跨 Task 保留的结论写入 Workspace，不靠 Agent 记忆

## 8. 记忆扩展与自更新

### 8.1 字段扩展

`memory_records` 增加：

```sql
salience
last_accessed_at
provenance       -- JSON
sensitivity      -- private / work / public
expires_at
```

### 8.2 在线更新

- 对话/动作后抽取候选记忆
- 更新 `use_count` / `last_used_at`
- 用户纠正立即生效
- 高置信度低风险候选自动通过
- 低置信度进入候选审核

### 8.3 离线 Curator

每晚：

1. 合并重复
2. 冲突覆盖，保留 `superseded_by`
3. 过期低价值记忆
4. 补人物/项目关系
5. 根据反馈调整 salience
6. 生成记忆快照

### 8.4 检索评分

```text
score =
  0.40 * 向量相似度
+ 0.25 * 时间新鲜度
+ 0.20 * 重要性
+ 0.10 * 当前目标相关度
+ 0.05 * 用户确认
```

再加 token 预算、MMR 去重、引用来源。

## 9. 权限与审批

| 风险 | 示例 | 默认 |
|---|---|---|
| read | 查邮件 | 静默 |
| suggest | 起草回复 | 生成草稿 |
| write | 创建日程 | 首次审批 |
| destructive | 删除文件 | 每次审批 |
| exec | 本地 shell | 每次审批 + 范围限制 |

流程：

```text
Agent 请求能力
  → Policy 查 Grant
  → 没有 Grant：创建 Approval
  → 用户选择：本次 / 今天 / 一直 / 拒绝
  → 写入 capability_grants
  → 执行并审计
```

### 9.1 为什么需要统一授权

工具来源有 builtin / plugin / MCP / local / skill，风险、数据范围、审批方式各不相同。不能在每个工具里各写一套。

统一授权 = 一个 Capability Registry + 一个 Policy Engine + 一个 Grant Store + 一个 Approval 流程。

| 层 | 回答的问题 |
|---|---|
| 认证 | 账号是否已连接 |
| 能力 | 这个动作是什么、风险多大、是否可逆、成本多少 |
| 策略 | 这个 Bot / 当前 AgentProfile / Goal 能不能做 |
| 授权 | 用户是否允许、允许多久、是否只限这个 Goal |
| 审批 | 这一次是否确认 |
| 审计 | 做了什么、结果如何 |

决策结果：

- `allow`
- `deny`
- `require_grant`
- `require_approval`

Grant 范围：

- `once`
- `goal`
- `session`
- `day`
- `always`

例子：

```text
Bot 委派 Comms Agent 调用 mail.send
  → Registry: write, irreversible
  → Policy: Bot 允许 draft，不允许 send；Comms AgentProfile 不能 send
  → require_grant
  → Approval 展示收件人 / 主题 / 正文
  → 用户选择：本 Goal 允许
  → Grant(goal_id=45, capability=mail.send, scope=goal)
  → 执行 + 审计
```

这样 Bot 的 `allowed_tools` 只是输入之一，不是全部权限逻辑。

## 10. 迁移策略（不兼容）

### 10.1 Run 重命名

- `BotRun` → `Run`
- `BotRunStep` → `RunStep`
- `BotApproval` → `Approval`
- `bot_runs` → `runs`
- `bot_run_steps` → `run_steps`
- `bot_approvals` → `approvals`

涉及文件（主）：

```text
backend/ai/bots/models.py
backend/ai/bots/runner.py
backend/ai/bots/router.py
backend/ai/bots/schemas.py
backend/ai/automation/executor.py
backend/ai/bots/automation_service.py
backend/ai/coding/models.py
backend/ai/coding/service.py
backend/ai/mcp/tools/coding.py
backend/ai/skills/runtime.py
backend/core/auth/domain/cleanup.py
backend/plugins/projects/backend/service.py
backend/core/observability/router.py
backend/tests/test_bots.py
backend/tests/test_user_cleanup.py
```

### 10.2 Proposal 替换 ActivitySuggestion

- 新建 `proposals`
- 复制 `activity_suggestions` 数据
- 删除 `activity_suggestions`
- 删除旧模型/路由/类型
- 更新 Web / Mobile
- 通知插件只做通道

涉及文件：

```text
backend/ai/insights/activity_models.py
backend/ai/insights/activity_service.py
backend/ai/insights/activity_router.py
backend/core/database/migrations.py
backend/tests/test_activity_analysis.py
frontend/src/views/Dashboard.vue
mobile/lib/screens/workbench_screen.dart
mobile/lib/services/api_service.dart
```

### 10.3 不做兼容

- 不保留旧 API
- 不保留旧表
- 不保留旧类型
- 不保留双写
- 一次迁移、一次发布、同步更新前端和移动端

## 11. 分阶段计划

### Phase 0：执行原语重命名（1–2 天）

- [ ] `BotRun` → `Run`
- [ ] `BotRunStep` → `RunStep`
- [ ] `BotApproval` → `Approval`
- [ ] 表重命名迁移
- [ ] 更新所有引用、API schema、测试
- [ ] 全量后端测试通过

验收：代码中不再出现 `BotRun`；`/api/runs`、`/api/approvals` 正常。

### Phase 1：Proposal 统一（3–5 天）

- [ ] `proposals` 表与模型
- [ ] `ProposalService` 状态机
- [ ] `ActivitySuggestion` 迁移并删除
- [ ] 通知改为 Proposal 通道
- [ ] Web/Mobile 改为读 Proposal
- [ ] 旧 `/api/insights/suggestions` 删除

验收：提案有 `reason/evidence/actions`；接受后能创建 Goal；忽略/稍后可回写。

### Phase 2：Situation（3–5 天）

- [ ] `SituationSnapshot`
- [ ] Provider 注册表
- [ ] 缓存与事件失效
- [ ] `GET /api/cognition/now`
- [ ] 对话/简报读取 Situation

验收：缓存 p95 < 300ms；冷启动 < 2s；Provider 失败可降级。

### Phase 3：Goal / Task（5–7 天）

- [ ] `goals` / `tasks` 表
- [ ] Goal/Task 状态机
- [ ] `runs.goal_id` / `runs.task_id`
- [ ] Goal/Task API
- [ ] Web 列表与详情

验收：Goal 跨重启恢复；Task 可重试；Run 可关联。

### Phase 4：Workspace（3–5 天）

- [ ] `workspaces` / `workspace_items` / `workspace_artifacts`
- [ ] WorkspaceService
- [ ] 附件关联 files
- [ ] 导出目录 / ZIP
- [ ] 导出只读，不做双写

验收：工作区内容全部在 DB；导出可读；无 DB/文件双写。

### Phase 5：Planner / Agent / Verifier（7–10 天）

- [ ] AgentProfile 定义
- [ ] Planner Agent 生成 Task
- [ ] Dispatcher 按 `agent_profile_key` 实例化 Agent 并创建 Run
- [ ] Executor Agent 执行 Task
- [ ] Verifier Agent 验收
- [ ] Approval 集成

验收：端到端 Goal 可跑通；Verifier 可打回；失败可重试。

### Phase 6：Capability / Policy（5–7 天）

- [ ] Capability 注册表
- [ ] Grant 表与 API
- [ ] 风险等级与审批
- [ ] 打断策略：免打扰、会议中、每日预算

验收：高风险动作必须授权；低置信度只进 Now。

### Phase 7：Memory 扩展与 Curator（5–7 天）

- [ ] 字段扩展
- [ ] 检索评分 + 预算
- [ ] 在线更新
- [ ] Curator 定时任务
- [ ] 纠正/遗忘 API

验收：记忆可解释；纠正立即生效；Curator 可合并冲突。

### Phase 8：多端与评估（5–7 天）

- [ ] presence 与 handoff
- [ ] Eval Harness
- [ ] 运行看板指标
- [ ] 20–30 个黄金任务

验收：跨端继续同一 Goal；Eval 可回归。

## 12. 测试策略

### 单元测试

- Proposal 状态机
- Goal/Task 状态机
- Conductor 拆解
- Verifier 验收
- Policy 打断评分
- Capability 风险判断
- Workspace 读写
- Memory 检索评分

### 集成测试

- Proposal → Goal → Task → Run → Verify → Memory
- 高风险 Task → Approval → 执行
- Situation 缓存失效
- 跨重启恢复

### 回归测试

- 现有 bots / runs / skills / mcp / memory / activities
- 前端 build
- 移动端 analyze / test

### Eval

20–30 个黄金任务，覆盖：

- 会前准备
- 邮件回复
- 日程调整
- 文件整理
- 记忆纠正
- 审批拒绝
- 失败重试

指标：

- 任务成功率
- 工具错误率
- Verifier 通过率
- 人工干预次数
- p50 / p95 延迟
- 每 Goal 成本
- Proposal 接受率
- 误打扰率

## 13. 风险

| 风险 | 处理 |
|---|---|
| 重命名影响面大 | Phase 0 先做，机械替换，全量测试 |
| 主动打扰过多 | 打断评分 + 每日预算 + 低置信度进 Now |
| Agent 切换 / 任务循环 | max_steps / token 预算 / Verifier 兜底 |
| 工具滥用 | Capability + Grant + Approval |
| 外部内容注入 | untrusted 标记，不允许触发高风险动作 |
| 成本失控 | 每 Goal 预算 + 模型分级 |
| 工作区膨胀 | 内容在 DB，附件在 files；导出可清理 |
| 记忆污染 | 候选审核 + provenance + 用户纠正 + Curator |

## 14. 待确认

1. 认知层包名是否用 `ai/cognition/`。
2. `Run` 是否作为最终命名（还是 `AgentRun`）。
3. Workspace 是否确认“内容全 DB，附件走 files，目录只导出”。
4. 第一版 Agent 是否只做 Planner / Executor / Verifier，Architect 只在方案设计类任务启用。
5. 多 Bot 协作是否明确排除在第一版之外。

## 15. ?????2026-11-09?

### ???

- [x] `BotRun`/`BotRunStep`/`BotApproval` ? `Run`/`RunStep`/`Approval`
- [x] `runs`/`run_steps`/`approvals` ??????????
- [x] Proposal ??????`/api/proposals`
- [x] `ActivitySuggestion` ? `proposals` ????????/??
- [x] Proposal ?????notification/voice?
- [x] Proposal ????? Goal
- [x] Situation ??? `/api/cognition/now`
- [x] Goal / Task ??????API
- [x] Workspace / WorkspaceItem / WorkspaceArtifact
- [x] Workspace ?? ZIP
- [x] AgentProfile ???planner/researcher/architect/comms/executor/verifier?
- [x] Planner Agent ?? Task
- [x] Dispatcher ? Task ??? Run
- [x] Verifier Agent ?? Task
- [x] Run ?? goal_id/task_id/agent_profile_key
- [x] AgentProfile ??????
- [x] Goal / Session / AgentProfile ? Grant
- [x] `once` Grant ?????
- [x] Memory ?????salience?curator?????
- [x] ?? handoff ?? `/api/cognition/handoff`
- [x] Web?????????/??/??/??
- [x] ?????????
- [x] `evals/cognition.py` ??????

### ????

- [ ] Chat ??????????????????
- [ ] ???? Proposal ????? UI ??
- [ ] Workspace ?????/?? UI
- [ ] AgentProfile ?? UI
- [ ] ??? `cognition.handoff` ????
- [ ] 20?30 ????????????
- [ ] ? Bot ??
- [ ] Proposal ?????????
- [ ] ???????????????????????
