---
name: daily-review
description: 复盘当天完成的事项、推进的项目、未完成事项和明日建议，并写入每日回顾。
allowed-tools:
  - list_activities
  - list_recent_chats
metadata:
  icon: insights
  category: productivity
  output: daily_review
---

# 每日回顾

你是当前 Bot。回顾用户今天的活动与会话，形成一条可长期查看的每日回顾。

## 输入

- `day`（可选）：`YYYY-MM-DD`，默认今天。
- `force`（可选）：是否重新生成，默认 true。
- `notify`（可选）：是否发送通知，默认 true。

## 要求

1. 只使用当天的活动、对话、完成的待办和日程，不要扫描更早的原始历史。
2. 总结完成了什么、推进了哪些事项、还有哪些未完成。
3. 给出 1-3 条明天可执行的建议。
4. 不要编造数据里没有的人名、数字或承诺。
5. 结果写入每日回顾，之后可以随时查看。
