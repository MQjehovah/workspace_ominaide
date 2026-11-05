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

## API

```
GET    /api/memory/candidates?status=pending
POST   /api/memory/candidates/{id}/approve
POST   /api/memory/candidates/{id}/reject
GET    /api/memory/records?q=
DELETE /api/memory/records/{id}      # 遗忘
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

## 安全边界

- 只有 `trusted` 来源的候选可以自动通过（默认阈值 90）；外部内容必须人工确认。
- 抽取只读用户消息，不把助理生成的文本当作事实。
- 遗忘只影响记忆注入，不删除原始聊天/邮件。
- 每条记忆保留来源 `source_type/source_id/source_ref`，便于“为什么知道”。

## 后续

- 邮件/RSS/钉钉消息接入 `ingest_text(trust="untrusted")`，统一进入审核队列。
- 记忆冲突检测与时间版本（同一事实变更时 supersede）。
- 记忆使用反馈：被采纳/被纠正的次数影响置信度。
- 向量检索替换当前的关键词匹配。
