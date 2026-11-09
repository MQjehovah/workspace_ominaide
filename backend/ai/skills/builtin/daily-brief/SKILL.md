---
name: daily-brief
description: 汇总今天的日程、待办、邮件、资讯和长期记忆，生成一份可直接阅读的今日简报。
allowed-tools:
  - list_schedule_events
  - list_recent_emails
  - list_notifications
  - unified_search
metadata:
  icon: insights
  category: productivity
  output: daily_brief
---

# 每日简报

你是当前 Bot，不是另一个独立角色。用当前 Bot 的语气和记忆为用户生成今日简报。

## 输入

- `day`（可选）：`YYYY-MM-DD`，默认今天。

## 步骤

1. 读取目标日期的日程、待办、未读邮件、资讯和长期记忆。
2. 按以下顺序组织：
   - 必须处理：逾期、冲突、2 小时内开始的日程
   - 今天安排：日程与今天到期的待办
   - 需要回复：重要或未读邮件、钉钉未读
   - 知会：资讯与长期记忆提醒
3. 先讲最重要的冲突或截止，再讲日程与需要回复的人。
4. 不要编造材料中没有的人名、数字、承诺或时间。
5. 没有数据时明确说“今天没有需要特别处理的事项”，不要凑内容。

## 输出

返回与 `daily_brief` 结构一致的 JSON：`summary`、`focus`、`sections`、`stats`。
