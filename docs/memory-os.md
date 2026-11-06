# Memory OS 2.0

Memory OS 把“聊天记录”升级为可审核、可追溯、可遗忘的长期记忆。

## 数据流

```
聊天 / Run / 邮件 / RSS / MCP 消息
              │
        LLM 记忆抽取
              │
      memory_candidates（待审核）
        ├─ trusted（对话/用户输入）
        └─ untrusted（邮件/网页/外部消息）
              │ 人工审核 / 高置信自动通过
              ▼
      memory_records（长期记忆）
              │
      Bot 每次对话按相关度注入
```

## 两类记忆

- `memory_candidates`：候选记忆，默认 `pending`。可信来源可以直接审核通过；外部内容标记 `untrusted`，必须先确认。
- `memory_records`：已确认的长期记忆，带 `kind`、置信度、重要度、来源列表、`valid_from/valid_to`。
- 遗忘是软删除：`status=deleted`，保留审计但不注入上下文。

## 抽取规则

只抽取值得跨会话保留的信息：

- `fact`：稳定事实
- `preference`：偏好
- `commitment`：承诺/截止
- `relationship`：重要关系
- `project`：项目

**不抽取**：一次性操作、闲聊、临时状态、模型自己的猜测。

当前调度器每天 22:00 生成每日回顾后，分析过去 24 小时的**用户消息**。助理输出不作为长期记忆来源，避免模型幻觉变成“事实”。

## 外部内容隔离

邮件、RSS、钉钉消息都属于外部内容，可能被他人控制：

- 重要邮件在入库后调用 `ingest_text(..., trust="untrusted")`，只生成候选，绝不自动通过。
- RSS 文章只用于「资讯」阅读和幕僚长材料，不参与记忆抽取、实体图谱和每日回顾。
- RSS 与钉钉目前只作为幕僚长（CoS）的分析材料，不会自动写入记忆；后续如需接入，必须同样走 `untrusted` 队列。
- 外部候选在「关于我」里显示为「外部内容」，必须人工点「记住」。
- 开关：`MEMORY_EXTERNAL_EXTRACT_ENABLED`（默认开）。
- 同一内容已存在活跃记录时不会重复入队。
- 外部来源确认后，注入时会带上来源标记（如 `[commitment/email]`），便于区分“用户说的”和“邮件里写的”。
- 邮件抽取在数据库会话之外执行，避免 LLM 超时长期占用连接池。

## 冲突与时间版本

同一 `kind` 的新记忆只有在**更具体**时才会取代旧记忆（旧内容是新内容的子串，且两者不完全相同）。反过来，新记忆若只是旧记录的简短摘要，不会让更丰富的旧事实消失。

- 旧记录标记：`status=superseded`、`valid_to=now`、`superseded_by=<新记录 id>`
- 旧记录不再注入上下文，但保留在库中可审计
- 用户重新确认一条已被取代的记忆时，会把它恢复为 active，并把此前的取代者标记为 superseded，保证同一事实只有一条 active
- 删除（遗忘）与取代是两种状态：`deleted` 不会出现在普通记录列表，重新确认会显式恢复

## 关系图

记忆被确认时会扫描用户画像中的联系人与项目，命中名称则写入 `memory_edges`：

- `target_type`：`person` / `project`
- `relation`：默认 `mentions`
- API：`GET /api/memory/graph` 返回 `nodes` + `edges`；读取时会为老记忆补建边，并对重复边去重

## API

```
GET    /api/memory/candidates?status=pending
POST   /api/memory/candidates/{id}/approve
POST   /api/memory/candidates/{id}/reject
GET    /api/memory/records?q=
PATCH  /api/memory/records/{id}      # 修正内容 / 重要度；重名返回 409
DELETE /api/memory/records/{id}      # 遗忘
GET    /api/memory/graph             # 记忆-人物/项目关系图
POST   /api/memory/extract           # 立即抽取最近会话
POST   /api/memory/consolidate       # 自动通过高置信可信候选
```

Web「关于我」页面：

- 待审核记忆：记住 / 忽略
- 长期记忆：查看 / 遗忘
- 「整理记忆」按钮：立即从最近对话抽取

## 注入

`core/bots/memory.py::build_bot_context` 会追加：

```
【长期记忆】
- [preference] 用户偏好先列大纲再写正文
- [project] 用户的项目代号是北极星
```

最多 8 条、约 1600 字，避免挤占上下文。

检索顺序：

1. PostgreSQL + pgvector 环境下先走向量检索（`source_type="memory"`，集合 `omnidocs`）；
2. 向量不可用（MySQL/SQLite、未配置 embedding）或没有命中时退回关键词匹配，不会产生额外 embedding 调用；
3. 注入成功的记录会累加 `use_count` 并更新 `last_used_at`，作为“这条记忆确实有用”的反馈信号。

记忆写入、修正时会同步索引；遗忘时删除对应向量，避免已遗忘内容继续被检索到。

## 安全边界

- 只有 `trusted` 来源的候选可以自动通过（默认阈值 90）；外部内容必须人工确认。
- 抽取只读用户消息，不把助理生成的文本当作事实。
- 遗忘只影响记忆注入与向量索引，不删除原始聊天/邮件。
- 每条记忆保留来源 `source_type/source_id/source_ref`，便于“为什么知道”。
- 被新事实取代的记录保留 `superseded_by`，可追溯但不参与注入。

## 后续

- 记忆使用反馈升级为显式采纳/纠正（当前用 `use_count` 与人工修正近似）。
- 向量检索与关键词检索做加权融合，而不是简单回退。
- 钉钉消息按会话/联系人批量抽取，避免逐条调用 LLM。
