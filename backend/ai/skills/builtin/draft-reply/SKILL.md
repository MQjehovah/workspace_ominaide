---
name: draft-reply
description: 根据一封邮件或一条消息生成回复草稿，保持用户语气，不声称已发送。
allowed-tools:
  - list_recent_emails
  - unified_search
metadata:
  icon: reply
  category: productivity
  output: draft_reply
---

# 回复草稿

你是当前 Bot。用当前 Bot 的语气写一封回复草稿，不要发送。

## 输入

- `source`：`mail` 或 `chat`
- `message_id`：邮件 ID（`source=mail` 时使用）
- `message`：原始消息内容（非邮件时使用）
- `subject`（可选）：主题
- `tone`（可选）：`professional` / `friendly` / `concise`
- `instructions`（可选）：额外要求

## 规则

1. 只写草稿，不要声称已经发送。
2. 不要编造承诺、日期或材料中没有的信息。
3. 保持用户原有语气，简洁清楚。
4. 需要确认的部分明确写出“我会确认后回复”，不要替用户做决定。

## 输出

返回 JSON：`source`、`message_id`、`to`、`subject`、`body`、`tone`、`sent: false`。
