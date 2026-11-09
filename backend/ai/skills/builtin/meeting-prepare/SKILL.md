---
name: meeting-prepare
description: 为一场会议检索相关邮件、待办、资讯、钉钉消息和记忆，生成议程、要问的问题和风险。
allowed-tools:
  - list_schedule_events
  - list_recent_emails
  - unified_search
  - list_notifications
metadata:
  icon: event_note
  category: productivity
  output: meeting_prepare
---

# 会议准备

你是当前 Bot。使用当前 Bot 的语气、记忆和工具权限为用户准备会议。

## 输入

- `title`：会议主题
- `start`（可选）：开始时间 ISO
- `attendees`（可选）：参会人列表
- `query`（可选）：检索关键词

## 步骤

1. 检索会议时间窗口内的日程、相关邮件、待办、资讯、钉钉消息和长期记忆。
2. 去重并按来源标注材料。
3. 生成：
   - 2-3 句背景与目标
   - 4-6 条议程
   - 3-5 个要问的问题
   - 风险或未决事项
4. 不要编造材料中没有的人名、数字或结论。

## 输出

返回 JSON：`summary`、`agenda`、`questions`、`risks`、`context`、`sources`。
