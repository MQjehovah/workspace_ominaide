# OmniAide 架构（现行）

> 本文档是模块归属与依赖方向的唯一依据。新增模块、迁移目录、拆分插件前先读这里。
> 历史设计文档 `docs/design.md` 仅作背景参考，与本文冲突时以本文为准。

## 1. 分层

```
端 Hosts
  Web / Desktop / Mobile / Device

产品界面
  对话 / 工作台 / 记忆 / 运行看板（管理员）

业务插件 plugins/
  日程 待办 笔记 文件（含文件同步） 邮件 资讯 项目 设备 钉钉
  音乐 远程 通知 OAuth 随手记 会议

核心业务域
  AI
    LLM / Agent / Bot / 对话编排
    MCP（内置工具 + Tool Gateway + MCP Hub）
    Skills / Memory / Automation
    场景能力：每日简报 / 会议准备 / 周报 / 回复草稿 / 活动洞察
  Activities
    活动采集 / user_activities / 查询统计

内核运行域
  events（事件总线与 worker）
  auth / database / config / jobs / scheduler / observability
  plugin runtime
  wschannel（本地机器 Host 通道）
```

依赖方向只能向下：

```
端 → 产品界面 → 业务插件 → 核心业务域 → 内核运行域
```

内核不认识 AI、Activities 或任何插件。核心业务域不 import 具体插件的路由，只通过服务函数或只读上下文读取数据。

## 2. 各层职责

### 2.1 端

| 端 | 职责 |
|---|---|
| Web | 完整管理界面 |
| Desktop | 本地机器 Host、桌面插件、文件同步 |
| Mobile | 对话、工作台、空间、我的 |
| Device | ESP32 语音硬件 |

没有产品级 CLI。`backend/manage.py`、`backend/scripts/*`、`scripts/*` 是内部工具，不算端。

### 2.2 产品界面

| 界面 | 说明 |
|---|---|
| 对话 | 对话入口，底层走 AI 域 |
| 工作台 | 日程、待办、最近文件/笔记/项目、每日简报建议 |
| 记忆 | 原「关于我」，管理档案、候选记忆、长期记忆、图谱、人物 |
| 运行看板 | 原「能力中心」，管理员查看指标、任务、Agent、上下文调试 |

工作台的快捷建议来自每日简报的 `prompts`，不再单独维护建议接口。

### 2.3 业务插件

插件拥有自己的数据、API、UI、状态和事件。插件可以调用核心 AI 的能力，但不拥有 AI 逻辑。

| 插件 | 说明 |
|---|---|
| `schedule` | 日程 |
| `todo` | 待办 |
| `notes` | 笔记 |
| `files` | 文件，包含原 `sync` 文件同步引擎 |
| `mail` | 邮件 |
| `sources` | 资讯源（RSS、GitHub Trending 等 provider） |
| `projects` | 项目 |
| `device` | 智能硬件 |
| `dingtalk` | 钉钉 |
| `music` | 音乐 |
| `remote` | 远程控制 |
| `notifications` | 通知 |
| `oauth` | 授权 |
| `captures` | 随手记：拥有 `quick_captures`，分析时调用 AI |
| `meetings` | 会议：拥有会议音频、转写、纪要任务，转写/纪要生成调用 AI |

### 2.4 核心业务域

#### AI

| 模块 | 说明 |
|---|---|
| LLM | 模型客户端与 `llm_json` 公共调用 |
| Agent | 一次执行（`BotRun`、步骤、审批、取消、恢复） |
| Bot | 长期身份、策略、私有记忆、Routine |
| 对话编排 | 会话上下文、工具调用、流式输出 |
| MCP | 内置工具注册表、`tool_search` / `tool_call`、MCP Hub |
| Skills | 技能加载、启用、`run_skill` |
| Memory | 档案、长期记忆、关系、实体图谱、人物索引、向量记忆 |
| Automation | DSL、执行器、定时/触发 |
| ASR | 语音转写能力（`ai/asr.py`），供会议等插件调用 |
| 场景能力 | 每日简报、会议准备、周报、回复草稿、活动洞察 |

AI 的场景能力通过 Skills 暴露。技能是入口，不是实现；实现放在 `ai/scenarios/` 或对应 AI 能力模块，避免再造一个 Chief-of-Staff 业务层。

#### Activities

| 模块 | 说明 |
|---|---|
| 采集 | `ActivityMiddleware` 自动记录写操作，插件/客户端显式上报 |
| 存储 | `user_activities` |
| 查询 | `/api/activities` 列表与统计 |

Activities 只负责活动数据，不生成简报、不做分析。简报和洞察属于 AI。

### 2.5 内核运行域

| 模块 | 说明 |
|---|---|
| `core/events` | 事件总线、Redis 队列、worker、订阅者 |
| `core/auth` | 认证与用户 |
| `core/database` | 数据库会话与迁移 |
| `core/config` | 配置 |
| `core/jobs` | 后台任务 |
| `core/scheduler` | 定时调度 |
| `core/observability` | 指标与 Trace |
| `core/plugin` | 插件发现、注册、生命周期 |
| `core/wschannel` | 桌面 Host 通道、local_* 工具 |

`core/events` 不包含活动模型、活动路由或活动采集中间件。`ActivityMiddleware`、`UserActivity`、`/api/activities`、活动参数预览都在 `activities`。

## 3. 关键决策

| 决策 | 结论 |
|---|---|
| AI 的归属 | AI 是核心业务域的子域，不是内核，也不是独立顶层 |
| Activities 的归属 | 核心业务域子域，与 AI 并列 |
| events 与 activities | events 是内核事件管道；activities 是核心业务数据 |
| CoS | 取消。确定性聚合删除，LLM 能力拆到 AI 场景 + Skills |
| Inbox | 取消。移动端收件箱和相关 API 一并删除 |
| `core/context` | 不建。上下文组装是 AI 内部 helper：`ai/context.py` |
| connectors | 删除。没有实现的同步状态壳不再保留 |
| sync | 并回 `files` 插件，不保留独立插件 |
| 关于我 | 并入「记忆」，页面管理 AI Memory |
| People / Graph | 都是 Memory 的表现形式，归 AI |
| 能力中心 | 改名「运行看板」，定位为管理员运维台 |
| 会议转写 | 业务插件 `meetings`；ASR 与纪要生成是 AI 能力 |

## 4. 目录约定

```
backend/
├─ ai/                    # AI 域
│  ├─ agent.py            # Agent 执行循环
│  ├─ agent_router.py     # /api/agent
│  ├─ bots/               # Bot / Run / Routine
│  ├─ skills/             # 技能运行时
│  ├─ mcp/                # 内置工具 + Gateway
│  ├─ mcp_hub/            # 外部 MCP Server
│  ├─ automation/         # DSL、执行器
│  ├─ memory/             # 长期记忆、候选、审核
│  ├─ graph/              # 实体关系边
│  ├─ people/             # 人物索引
│  ├─ activity_insights/  # 活动洞察
│  ├─ scenarios/          # 每日简报、会议准备、回复草稿
│  ├─ context.py          # AI 上下文组装
│  ├─ llm.py              # LLM 公共调用
│  ├─ asr.py              # 语音转写
│  └─ clients/embeddings/indexer/vector_store/...
│
├─ activities/            # Activities 域
│  ├─ middleware.py       # HTTP 写操作采集
│  ├─ models.py           # user_activities
│  ├─ router.py           # /api/activities
│  └─ preview.py          # 活动参数预览
│
├─ core/                  # 内核运行域 + 应用模块
│  ├─ events/             # 事件总线与 worker
│  ├─ auth/ database/ config/ jobs/ scheduler/ observability/
│  ├─ plugin/ wschannel/ minio/
│  ├─ objects/            # 全局对象与搜索
│  ├─ workbench/          # 工作台聚合
│  └─ coding/             # 编码相关
│
├─ plugins/
│  ├─ captures/           # 随手记
│  ├─ meetings/           # 会议
│  ├─ files/              # 文件 + 同步
│  └─ ...
└─ main.py
```

## 5. 新增模块的规则

1. **有独立数据、API、UI、状态或事件** → 建业务插件。
2. **只是调用 AI 分析一段数据** → 留在插件，调用 AI 能力，不要把数据搬进 AI。
3. **确定性聚合、无模型调用** → 放在产品界面对应的 service，不要包装成技能。
4. **需要模型产出** → 建 Skill；实现放 `ai/scenarios/`，handler 只做参数转换。
5. **新增事件类型** → 在产生事件的模块里调用 `record_event`；不要在 `core/events` 里加业务判断。
6. **新增跨源读取** → 放 `ai/context.py` 或插件自己的 service；不要新建共享层。

## 6. 已知架构债

以下两项暂时接受，后续单独处理：

1. **AI 直接读插件表**  
   `ai/context.py` 目前直接 import 邮件、待办、日程、资讯、钉钉的模型。目标方向是插件向核心注册 context provider，AI 通过注册表读取。

2. **events 直接写 Activities 表**  
   `core/events/bus.py` 目前直接写 `user_activities`。目标方向是总线只负责 publish/subscribe，由 Activities 订阅并持久化。

## 7. 落地状态

- [x] `events` 只保留总线、worker 和 recorder
- [x] 活动模型、路由、中间件、参数预览迁入 `activities`
- [x] 删除 `core/connectors` 和 `SyncState`
- [x] 解散 `core/cos`：确定性 triage 删除，LLM 能力进入 AI 场景和 Skills
- [x] 删除 Inbox 后端与移动端收件箱，工作台建议改为读取每日简报 `prompts`
- [x] 上下文组装收口为 `ai/context.py`，LLM 调用收口为 `ai/llm.py`
- [x] 随手记迁入 `plugins/captures`
- [x] 会议纪要迁入 `plugins/meetings`，ASR 保留在 `ai/asr.py`
- [x] 文件同步并回 `plugins/files`
- [x] Web「关于我」改为「记忆」，「能力中心」改为「运行看板」
- [ ] AI 读插件表改为 context provider 注册
- [ ] `events` 持久化改为 Activities 订阅

## 8. 验证

改动模块边界后至少运行：

```bash
# 后端
py -3.12 -m pytest -q

# 前端
cd frontend && npm run build

# 移动端
cd mobile && flutter analyze && flutter test
```
