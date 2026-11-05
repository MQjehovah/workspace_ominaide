# Chief-of-Staff 场景包

幕僚长（CoS）把已有的邮件、资讯、日程、待办、钉钉和长期记忆聚合成四类工作流：

| 场景 | 入口 | 说明 |
|---|---|---|
| 统一收件箱 triage | `GET /api/cos/triage` | 把邮件/资讯/钉钉/待办/日程合并分组：紧急、待回复、今天、知会 |
| 每日简报 | `GET /api/cos/daily-brief` | 今日日程、到期/逾期待办、未读邮件、钉钉未读、资讯、记忆提醒 |
| 会议准备 | `POST /api/cos/meeting-prep` | 按主题/关键词检索相关邮件、待办、资讯、钉钉消息与记忆，生成议程与问题 |
| 周报 | `GET /api/cos/weekly-review` | 汇总近 7 天每日回顾、完成/待办、下周日程与重要邮件 |
| 回复草稿 | `POST /api/cos/draft-reply` | 基于邮件或传入消息生成草稿，只起草不发送 |

Web 入口：侧栏「幕僚长」→ `/cos`。

## 数据来源

| 来源 | 表 / 工具 | 说明 |
|---|---|---|
| 邮件 | `mail_messages` | 后端 IMAP 同步结果，重要度与 AI 摘要优先 |
| 资讯 | `rss_entries` + `rss_feeds` | 按用户过滤，取最近文章 |
| 日程 | `schedule_events` | 当天/未来窗口 |
| 待办 | `plugin_todo_items` | 未完成、到期与逾期 |
| 钉钉 | MCP `dingtalk__list_unread` / `search_messages` | 未配置时返回 `not_configured`，不影响其他来源 |
| 记忆 | `memory_records` | 长期记忆作为提醒与会议背景 |

## Triage 规则

1. 重要且未读邮件、逾期待办、2 小时内的日程 → `urgent`
2. 其他未读邮件、钉钉未读 → `needs_reply`
3. 日程与待办 → `today`
4. 资讯与其他邮件 → `fyi`

每条 item 带 `source/source_id/title/summary/from/time/priority/link/meta`，前端可以直接「转待办」或「起草回复」。

## 降级策略

所有生成都是确定性优先：

- 没有 LLM key 时仍返回完整结构：摘要由规则拼接，议程使用固定骨架，草稿使用模板。
- 钉钉未配置或调用失败时，`sources.dingtalk` 标记状态，其他来源照常工作。
- 草稿不会自动发送；发送仍需用户明确确认，并走钉钉 MCP 的 `confirmed` / 邮件发送流程。

## 安全边界

- 所有查询按 `user_id` 过滤，跨用户邮件/待办/日程不可见。
- 外部内容（邮件、钉钉）只作为“材料”进入摘要，不会被写成长期记忆；Memory 侧仍走 `untrusted` 审核。
- 会议准备和周报的 LLM 提示明确要求“不编造材料中没有的人名或数字”。
- 回复草稿只返回文本，`sent=false`。

## API

```
GET  /api/cos/triage?days=3
GET  /api/cos/daily-brief?day=YYYY-MM-DD
POST /api/cos/meeting-prep
     {"title": "预算评审会", "query": "预算", "attendees": ["张三"], "start": "2026-11-06T10:00:00"}
GET  /api/cos/weekly-review?weeks=1
POST /api/cos/draft-reply
     {"source": "mail", "message_id": 12, "tone": "friendly"}
```

## 后续

- 把 triage 结果做成可批量操作（批量转待办、批量已读）。
- 会议结束后自动生成会议纪要并提取行动项。
- 周报可一键保存到笔记/文档，或推送到钉钉群（需确认）。
