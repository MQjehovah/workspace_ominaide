# OmniAide 智能层架构设计

日期: 2026-07-22
状态: 草案

## 三层架构

```
┌─────────────────────────────────────────────┐
│              智能层 (Intelligence)            │
│  规律发现 · 主动简报 · 主动安排 · 自然语言操作 │
└──────────────────┬──────────────────────────┘
                   │ 依赖
┌──────────────────▼──────────────────────────┐
│              记忆层 (Memory)                  │
│  个人画像 · 活动日志 · 实体图谱              │
│  让 AI「认识你」                            │
└──────────────────┬──────────────────────────┘
                   │ 全部向量化
┌──────────────────▼──────────────────────────┐
│              数据层 (Data)                    │
│  统一索引器 → Qdrant → 统一搜索 API          │
│  所有数据（文件/笔记/RSS/日程/活动）一个接口  │
└─────────────────────────────────────────────┘
```

---

## 数据层

### 目标

所有业务数据进入 Qdrant 向量库，通过一个 `/api/search` 接口跨类型检索。

### 现状

- Qdrant 已部署（docker-compose 中运行）
- embedding 生成函数已存在（`core/ai/embeddings.py`）
- 但没有任何数据在 Qdrant 中，embedding 功能未被使用

### 统一索引器 `core/ai/indexer.py`

提供通用索引函数，各业务模块在关键操作点调用：

```python
async def index_content(
    user_id: int,
    source_type: str,      # 'file' | 'note' | 'rss_entry' | 'event' | 'activity'
    source_id: int,
    title: str,
    content: str,           # 要向量化的正文
    metadata: dict = {},    # 额外 payload（时间、链接等）
)
```

- 生成 embedding → 写入 Qdrant `omnidocs` collection
- payload: `{user_id, source_type, source_id, title, created_at, ...}`
- 各模块调用点：

| 业务模块 | 触发时机 | source_type |
|---|---|---|
| files | 上传完成/文件内容更新 | `file` |
| notes | 笔记创建/保存 | `note` |
| rss | 新条目抓取 | `rss_entry` |
| schedule | 日程创建/更新 | `event` |
| events | 活动日志写入（已有 events 表） | `activity` |

### 统一搜索 API `POST /api/search`

```json
// Request
{"q": "预算方案", "types": ["file","note","event"], "top_k": 10}
// Response
{
  "results": [
    {"type": "file", "title": "2026预算方案", "snippet": "...", "score": 0.92, "link": "/files/123"},
    {"type": "note", "title": "预算讨论纪要", "snippet": "...", "score": 0.85, "link": "/notes/456"}
  ]
}
```

### MCP 工具

`unified_search(q, types?)` → 替代现有分散的 `search_files`、`search_articles` 等工具。AI 用一个工具查全部数据。

---

## 记忆层

### 目标

让 AI 真正「认识」用户——知道你是谁、你在做什么、你和谁合作、你的习惯。

### 2a. 个人画像 `user_profile` 表

| 字段 | 说明 | 来源 |
|---|---|---|
| name | 姓名 | 注册 / 手动填写 |
| role | 角色/职位 | 手动填写 |
| company | 公司 | 手动填写 |
| contacts | `[{name, relation}]` 联系人 | 手动 + AI 从活动提取 |
| projects | `[{name, deadline}]` 项目 | 手动 + AI 从文件/日程提取 |
| preferences | `{key: value}` 偏好设置 | AI 学习 + 手动调整 |

每次对话时，画像信息注入 system prompt：

```
你正在和 张三 对话。他是 技术负责人，在 XX公司 工作。
他的联系人：李四（同事），他的项目：Q3项目（2026-09截止）。
最近关注：预算方案。
```

### 2b. 活动日志（复现存的 events 表）

**不做新表**，用户的 events 表就是活动日志。需要补充：

1. 确保所有关键操作都写 events（文件上传、笔记保存、RSS 抓取、日程创建）
2. 写 events 时自动调 `index_content` 向量化
3. 已有的 `GET /api/events` 足够作为活动查询接口

现有 events 表结构（已有）：
```
id, user_id, event_type, entity_type, entity_id, summary, details, created_at
```

### 2c. 实体图谱

每条内容（文件、笔记、事件等）写入时，LLM 提取实体：

```
input: "与张三讨论Q3项目预算方案，下周五截止"
output: [{name:"张三", type:"person"}, {name:"Q3项目", type:"project"}, {name:"预算方案", type:"document"}]
```

存入 Qdrant `entities` collection：
```
{id, name, type, user_id, sources: [{type, id, title}], first_seen, last_seen}
```

查询示例：
```
用户："帮我整理张三相关的东西"
→ 搜 entities 找到 "张三" → 拿所有 source_ids → 跨类型聚合 → 汇总返回
```

---

## 智能层

### 目标

建立在数据层和记忆层之上，AI 主动发现规律、生成简报、代理安排。

### 3a. 规律发现（后台任务）

每天定时运行，分析近期活动日志：

```
输入：最近 30 天活动日志（Qdrant 向量检索 + events 表）
LLM 分析：
  - "你每周一早上都会看 RSS"
  - "你和张三每周三下午有会"
  - "你最近频繁搜索'预算'相关"
输出：写入 preferences（AI 学习到的规律）
```

### 3b. 主动简报

每天 09:00（或开机时），AI 生成自然语言摘要推送通知：

```
"早上好张三，今天你有 3 个会。
 张三的日程改到明天了。
 我发现你最近在关注预算方案，需要整理相关文件吗？"
```

推送通道：现有的 WebSocket 通知系统。

### 3c. 主动安排

规律足够明确后，AI 主动执行或询问：

```
检测到"每周三下午3点和李四开会"→
如果日历上没有，主动问："要创建例行会议吗？"

检测到"每次保存预算文件后都创建笔记"→
"预算文件已上传，自动创建笔记吗？"
```

---

## 依赖图

```
智能层
  ├─ 需要：规律发现（记忆层活动日志）
  ├─ 需要：主动简报（数据层统一搜索 + 记忆层画像）
  └─ 需要：主动安排（数据层 + 记忆层 + 用户确认）

记忆层
  ├─ 个人画像：独立
  ├─ 活动日志：复用 events 表，无新表
  └─ 实体图谱：需要数据层 Qdrant 基础设施

数据层
  ├─ Qdrant 已部署
  ├─ embedding 生成已存在
  └─ 需要：各业务模块的索引钩子
```

## 实施顺序

| 阶段 | 内容 | 前置 |
|---|---|---|
| P1 | 统一索引器 + 各业务索引钩子 + `/api/search` | Qdrant 就绪 |
| P2 | 补充 events 覆盖 + events 自动向量化 | P1 |
| P3 | 实体提取 pipeline + entities collection | P1 |
| P4 | 个人画像表 + 表单 + 对话注入 | P2 |
| P5 | 规律发现后台任务 | P2+P3 |
| P6 | 主动简报 + 主动安排 | P4+P5 |
