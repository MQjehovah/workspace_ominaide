---
name: weekly-review
description: 汇总最近 7 天的每日回顾、完成/待办、下周日程和重要邮件，生成一份周报。
allowed-tools:
  - list_schedule_events
  - list_recent_emails
  - list_notifications
metadata:
  icon: calendar_view_week
  category: productivity
  output: weekly_review
---

# 周报

你是当前 Bot。用当前 Bot 的语气和记忆为用户写周报。

## 输入

- `weeks`（可选）：回顾周数，默认 1。

## 步骤

1. 读取最近 7 天的每日回顾、已完成待办、未完成待办、下周日程和重要邮件。
2. 输出：
   - 3-5 句总结
   - 成果
   - 进行中
   - 风险 / 逾期
   - 下周重点
3. 只基于数据，不编造数字或承诺。

## 输出

返回 JSON：`period`、`summary`、`wins`、`in_progress`、`risks`、`next_week`、`stats`。
