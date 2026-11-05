# OmniAide 业务增强实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 OmniAide 从“功能齐全的工具箱”推进为“主动、可信、跨端一致的个人 AI 管家”。

**Architecture:** 后端作为唯一事实源：洞察、邮件、RSS、通知、记忆全部在后端产生和消费；桌面/Web/移动/设备只是展示与输入终端。所有后台任务由现有 `scheduler_loop` 统一编排，新增能力必须可按用户隔离、可重试、可幂等。

**Tech Stack:** FastAPI + SQLAlchemy async + PostgreSQL/SQLite、现有 LLM/Embedding 封装、Vue 3、Flutter、Electron、ESP32 固件。

**Spec:** 本文件；分项细节在同目录对应计划中。

## Global Constraints

- 所有新表必须同时兼容 PostgreSQL（生产）与 SQLite（测试）。
- 所有后台分析必须按 `user_id` 过滤，禁止跨用户混批。
- 所有通知必须走 `plugins.notifications.backend.router.notify_user`（Web + 设备双通道）。
- 洞察只做“日增量”：每天只分析当天活动和当天会话；禁止再次扫描 30 天原始事件。
- 邮件/RSS 的接收、入库、分析、通知全部在后端完成；桌面端只保留可选的本地阅读/缓存能力。
- LLM 不可用时必须有确定性降级结果，不得静默丢数据。
- 每个任务先写失败测试，再实现，再提交。

---

## 用户补充需求（必须满足）

1. **日洞察**：每天分析“当天活动 + 当天会话”，产出当日回顾；长期规律从日回顾汇总，不再重复分析 30 天原始数据。
2. **邮件/RSS 后端化**：后端负责定时收取、正文入库、AI 摘要/重要性判断/待办提取、通知与检索；桌面端不再是唯一入口。

---

## 阶段与顺序

| 阶段 | 内容 | 交付物 | 状态 |
|---|---|---|---|
| **Wave 0** | 地基修复 | 下载鉴权、活动按用户隔离、设备待办端点、日程改期重置、通知统一出口、密码脱敏、桌面 Agent 审批 | 基本完成（sync/workspaces 残留待清理） |
| **Wave 1** | 日洞察与每日回顾 | `daily_insights` 表、生成器、API、调度、Bot 上下文、Web 页面 | 已完成 |
| **Wave 2** | 通知行动中心 + 待办提醒 | 通知动作、统一出口、待办到期提醒、改期重置、Web/移动动作 UI | 已完成 |
| **Wave 3** | 邮件/RSS 后端化 | IMAP 增量同步、邮件正文/分析/通知、RSS 定时刷新与摘要、Web 页面 | 已完成（桌面端停止重复收取，保留本地阅读） |
| **Wave 4** | 会话中心 + 移动端修复 | `/chat` 工作台、跨端会话、移动端解析/流式/笔记格式修复 | 已完成（富文本仍为纯文本编辑） |
| **Wave 5** | 知识库可信化 | Office 抽取、删除清理向量、关键词降级、引用跳转 | 已完成（知识库/搜索均受益） |
| **Wave 6** | 自动化规则中心 | 规则模板、自然语言建规则、Dry-run、运行日志 | 已完成 |
| **Wave 7** | 设备语音闭环 | 流式语音接线、播报打断、待办回写、天气展示 | 已完成（固件改动待硬件编译验证） |
| **Wave 8** | 隐私与权限中心 | 插件权限执行、禁用即停、采集透明化 | 已完成（shell/storage/notification/screenshot/remote 按 manifest 执行；api 保持兼容不拦截） |
| **Wave 9** | 跨端同步 / Coding 工作台 / 记忆图谱 / 快速捕获 | 设置同步（快捷键/禁用插件/审批开关）、Coding 工作台、关于我/实体图谱、全局快速记录 | 已完成 |

## MCP Hub（2026-11-05 追加）

新增统一 MCP 管理层，详见 `docs/mcp-hub.md`：

- `mcp_servers / mcp_tools / mcp_calls` 三张表
- stdio + HTTP MCP 客户端；启动自动连接、工具发现、命名空间 `server__tool`
- 现有 builtin 工具与外部 MCP 工具统一出现在 `/api/mcp/tools`
- 动态风险注册到 Bot 策略；写操作仍走审批
- 钉钉作为标准 MCP Server（`mcp_servers/dingtalk`），内部调用 `dws`
- Web「MCP 管理」页：Server CRUD、连接、工具风险、调用审计
- 容器镜像内置 Node + `dws`，`DWS_CONFIG_DIR=/data/dws`，无需桌面 Bridge

## 实施日志（2026-11-05）

| 提交 | 内容 |
|---|---|
| `98500cb` | 日洞察：按用户/按天采集活动+会话，幂等生成，API，调度补跑，晨报与 Bot 上下文注入 |
| `6d03e84` | 邮件/RSS 后端化：IMAP 增量同步与去重、邮件摘要/重要性/通知、RSS 定时刷新与资讯摘要、Web 邮件页 |
| `db92f6d` | 通知行动中心：完成待办/稍后提醒/打开动作、去重与静默时段、待办到期提醒、改期重置、按用户隔离 |
| `7d2264e` | Web 会话中心 `/chat`；移动端通知/待办解析、SSE 流式对话与历史、笔记 JSON 保存、日程统计 |
| `913cb14` | 知识库可信化：Office/PDF 正文抽取、关键词降级检索、删除时清理向量、笔记正文搜索 |
| `86ab3ca` | 自动化中心：8 个模板、一句话建规则（LLM + 本地降级）、Dry-run、按例程查看 Runs/统计 |
| `689582e` | 设备语音：流式语音接线、播报打断、失败回退、天气显示、待办回写端点 |
| `d6b61bc` | 隐私：禁用插件立即停止子进程、禁用时不再读取剪贴板、插件采集透明提示与一键暂停 |
| `6bc120d` | Coding 工作台：Run 详情、工具步骤、实时轮询、取消、重试、PR/Compare 链接 |
| `0990f2d` | 安全：桌面本地 Agent 对写文件/删除/命令执行弹窗审批；邮箱密码不再随账号列表返回，改为显式 owner-only 获取 |
| `2730269` | 权限：插件子进程按 manifest 执行 shell/storage/notification/screenshot/remote 权限 |
| `cc5eac4` | 「关于我」：用户画像、AI 洞察、实体图谱与遗忘、最近回顾；桌面 `Ctrl+Shift+N` 全局快速记录（保存笔记/创建待办） |
| `a84d061` | 跨端设置同步：`/api/sync/settings/*` + 桌面 60s 增量同步（快捷键、禁用插件、审批开关，last-write-wins） |
| `507d08b` | sync 事件接线：文件创建/上传/重命名/移动/删除/恢复自动发布同步事件；manifest 插件只挂载一次，消除重复路由 |

## 遗留验证与清理

- **设备固件**：流式语音/打断/天气改动已写入，但当前环境没有 PlatformIO/Arduino 工具链，需在硬件构建环境编译并真机验证。
- 后端 `110 passed`，包含“无重复 /api 路由”与“文件变更生成同步事件”的回归测试。

---

# Wave 1：日洞察与每日回顾

## 数据流

```
当天 UserActivity ─┐
当天 ChatMessage  ─┼─> collect_day_data(user, day) ─> LLM 总结 ─> daily_insights(user, day)
当天 Todo/Schedule ┘                                              │
                                                                  ├─> 通知（每日回顾，Web+设备）
                                                                  ├─> Bot 上下文（最近 1-2 天）
                                                                  └─> 晨间简报（昨日回顾 + 今日安排）
```

## 文件结构

- Create: `backend/core/ai/insight_models.py` — `DailyInsight` 表。
- Create: `backend/core/ai/daily_insights.py` — 采集、生成、查询、上下文。
- Create: `backend/core/ai/insights_router.py` — `/api/insights`。
- Modify: `backend/core/ai/scheduler.py` — 每日 22:00 生成 + 启动补跑昨日 + 晨报接入。
- Modify: `backend/core/bots/memory.py` — 注入最近两日回顾。
- Modify: `backend/main.py` — 注册模型与路由。
- Modify: `backend/core/config/settings.py` — 日回顾开关与时间。
- Create: `backend/tests/test_daily_insights.py`.
- Create: `frontend/src/views/Insights.vue`.
- Modify: `frontend/src/router/index.ts`, `frontend/src/core/layout/CoreSidebar.vue`.

## 接口约定

```python
# backend/core/ai/insight_models.py
class DailyInsight(Base):
    __tablename__ = "daily_insights"
    id: int
    user_id: int
    day: date                 # 用户本地日期
    summary: str              # 2-4 句中文回顾
    highlights: list[str]     # 当天完成/发生的关键事项
    patterns: list[str]       # 当天观察到的规律
    suggestions: list[dict]   # [{"text": str, "action": "todo|schedule|none"}]
    stats: dict               # 事件数、会话数、待办完成数、日程数、常用应用
    session_ids: list[str]    # 当天会话 id
    generated_at: datetime
    # UNIQUE(user_id, day)

# backend/core/ai/daily_insights.py
async def collect_day_data(user_id: int, day: date) -> dict
async def generate_daily_insight(user_id: int, day: date, force: bool = False, notify: bool = False) -> DailyInsight | None
async def get_recent_insights(user_id: int, days: int = 7) -> list[DailyInsight]
async def build_insight_context(user_id: int, days: int = 2) -> str | None
async def ensure_daily_insight(user_id: int, day: date) -> DailyInsight | None
```

## Task 1：DailyInsight 表与迁移

**Files:**
- Create: `backend/core/ai/insight_models.py`
- Modify: `backend/main.py:21-36`
- Test: `backend/tests/test_daily_insights.py`

- [ ] **Step 1：写失败测试**：注册用户后直接查 `daily_insights` 表可写入并唯一约束生效。
- [ ] **Step 2：运行测试确认失败**（表不存在）。
- [ ] **Step 3：实现模型**：`Date`、`JSON`、`UniqueConstraint("user_id", "day")`；在 `main.py` lifespan 中 import。
- [ ] **Step 4：运行测试通过。**
- [ ] **Step 5：提交** `feat(insights): add daily insight model`

## Task 2：当天数据采集

**Files:**
- Create: `backend/core/ai/daily_insights.py`
- Test: `backend/tests/test_daily_insights.py`

- [ ] **Step 1：写失败测试**：构造用户 A/B 的活动、会话、待办、日程；断言 `collect_day_data(A, day)` 只统计 A 且只在当天，`stats` 字段完整。
- [ ] **Step 2：运行失败。**
- [ ] **Step 3：实现采集**：
  - 时间范围 `[day 00:00, day+1 00:00)`，使用 naive local。
  - `UserActivity` 按用户过滤，排除 `device.*`；聚合 `event_type`、`details.app`、摘要。
  - `ChatMessage` 按用户和时间过滤；按 `session_id` 分组，每会话最多 20 条、每条截断 500 字。
  - `PluginTodoItem` 当天完成数（`status="done"` 且 `updated_at` 在范围内）。
  - `Event` 当天日程数与前 10 条标题。
- [ ] **Step 4：运行通过。**
- [ ] **Step 5：提交** `feat(insights): collect per-day activity and chat data`

## Task 3：生成与降级

**Files:**
- Modify: `backend/core/ai/daily_insights.py`
- Test: `backend/tests/test_daily_insights.py`

- [ ] **Step 1：写失败测试**：
  - LLM 不可用时仍生成非空 `summary`，且 `stats` 正确。
  - 同一天重复调用只保留一条记录（幂等）。
  - `force=True` 会覆盖并按新数据更新。
- [ ] **Step 2：运行失败。**
- [ ] **Step 3：实现**：LLM 提示词要求严格 JSON；解析失败走确定性摘要；无任何数据返回 `None`；`upsert` 按 `(user_id, day)`。
- [ ] **Step 4：运行通过。**
- [ ] **Step 5：提交** `feat(insights): generate daily insight with deterministic fallback`

## Task 4：API

**Files:**
- Create: `backend/core/ai/insights_router.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_daily_insights.py`

- [ ] **Step 1：写失败测试**：未登录 401；登录后 `GET /api/insights/daily?days=7` 返回列表；`POST /api/insights/daily/run` 可生成；不能读取他人数据。
- [ ] **Step 2：运行失败。**
- [ ] **Step 3：实现** `GET /api/insights/daily`、`GET /api/insights/daily/{day}`、`POST /api/insights/daily/run`、`GET /api/insights/latest`。
- [ ] **Step 4：运行通过。**
- [ ] **Step 5：提交** `feat(insights): expose daily insights API`

## Task 5：调度、补跑与晨报

**Files:**
- Modify: `backend/core/ai/scheduler.py`
- Modify: `backend/core/config/settings.py`
- Test: `backend/tests/test_daily_insights.py`

- [ ] **Step 1：写失败测试**：`ensure_daily_insight` 对昨天可补跑；`_send_briefing` 包含昨日回顾。
- [ ] **Step 2：运行失败。**
- [ ] **Step 3：实现**：
  - 新增 `daily_review_enabled/hour/minute`（默认 22:00）。
  - 每天到点对活跃用户生成当天回顾并 `notify_user`，`type="daily_review"`，`link="/insights"`。
  - 启动后/每天首次循环补跑昨天。
  - 晨报取昨日 `DailyInsight.summary` 放在最前。
  - 移除 `discover_insights` 的 30 天调用。
- [ ] **Step 4：运行通过。**
- [ ] **Step 5：提交** `feat(insights): schedule daily review and inject into briefing`

## Task 6：Bot 上下文注入

**Files:**
- Modify: `backend/core/bots/memory.py`
- Test: `backend/tests/test_daily_insights.py`

- [ ] **Step 1：写失败测试**：存在最近两日回顾时，`build_bot_context` 返回内容包含回顾摘要。
- [ ] **Step 2：运行失败。**
- [ ] **Step 3：实现** `_insight_block(user_id)`，最多取 2 天，限制 800 字，追加到 parts。
- [ ] **Step 4：运行通过。**
- [ ] **Step 5：提交** `feat(insights): inject recent reviews into bot context`

## Task 7：Web 洞察页

**Files:**
- Create: `frontend/src/views/Insights.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/core/layout/CoreSidebar.vue`

- [ ] **Step 1：实现** 列表 + 详情 + 手动生成 + 空状态；失败时可见错误。
- [ ] **Step 2：`npm run build` 通过。**
- [ ] **Step 3：提交** `feat(web): add daily insights page`

---

# 后续 Wave 的关键决策（执行时再细化）

## Wave 3：邮件/RSS 后端化

- 邮件新增 `mail_messages` 表：`account_id, uid, uidvalidity, message_id, subject, from_address, to_addresses, date, preview, content, has_attachments, important, ai_summary, ai_actions, read, starred`。
- 使用标准库 `imaplib` + `asyncio.to_thread` 增量拉取（记录 `last_uid`/`uidvalidity`），不新增重依赖。
- 每封新邮件入库后：索引 → LLM 摘要/重要性/待办提取 → 重要则 `notify_user`。
- 桌面端邮件插件改为“可选本地缓存/阅读”，后端为唯一同步源；Web/移动新增邮件页。
- RSS 由调度器按 `last_fetch` 节流刷新；新文章入库后索引与摘要；每日生成资讯摘要。
- 测试用 fake IMAP / monkeypatch fetch，不访问真实网络。

## Wave 2：通知行动中心

- `notifications` 增加 `actions` JSON、`channel`、`dedupe_key`、`scheduled_at`。
- `POST /api/notifications/{id}/action` 支持 `open / complete_todo / approve_run / reject_run / snooze`。
- 所有模块统一 `notify_user`；审批、Coding Run、邮件全部接入设备推送。

## Wave 4：会话中心

- 后端已有 `/chat/sessions`、`/chat/history`、`/chat/stream`、`/runs/{id}/stream`；Web/移动接入，桌面与会话 id 对齐。
- 移动端先修通知/待办解析、笔记格式、文件打开，再接流式。

---

## Review Focus

- 用户当天没有任何活动/会话：不应生成空回顾，也不应发通知。
- 跨天边界与服务器时区：22:00 生成“今天”，00:00 后补跑“昨天”，不能重复或漏天。
- LLM 超时/返回非 JSON：必须降级，不能丢当天数据。
- 多用户：任何查询、通知、上下文注入都不得串用户。
- 重复调度/重启：同一天只能有一条回顾；通知可重发但不应无限重复。
