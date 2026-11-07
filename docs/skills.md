# Agent Skills

OmniAide 的技能层对齐 **Anthropic Agent Skills**（`SKILL.md`）。技能属于 Bot，不是独立角色。

## 技能 vs 工具 vs 例程

| 概念 | 说明 | 例子 |
|---|---|---|
| 工具 | 原子动作 | `list_recent_emails`、`create_schedule_event` |
| 技能 | 面向用户的高层能力，由 `SKILL.md` + 工具 + 脚本/资料组成 | `daily-brief`、`meeting-prepare`、`weekly-review` |
| 例程 | 定时/事件触发技能 | 每天 08:00 运行 `daily-brief` |
| Bot | 人格、记忆、工具、技能、例程的容器 | 我的助理 |

统一收件箱是 **功能面**，不是技能；回复邮件是邮件功能里的 AI 起草动作。

## 目录

```
data/skills/                 # settings.skills_dir
  users/<user_id>/<key>/     # 用户技能
  bots/<bot_id>/<key>/       # Bot 私有技能

backend/skills/builtin/      # 随版本发布
  daily-brief/
    SKILL.md
    scripts/fallback.py
    references/briefing-template.md
  meeting-prepare/
  weekly-review/
```

`SKILL.md`：

```markdown
---
name: daily-brief
description: 汇总今天的日程、待办、邮件、资讯和长期记忆，生成今日简报。
allowed-tools:
  - list_schedule_events
  - list_recent_emails
metadata:
  icon: insights
---

# 每日简报
...
```

- `name` 必须匹配目录名，使用 lowercase-hyphen
- `description` 是模型选择技能的主要依据
- `allowed-tools` 与 `Bot.allowed_tools` 取交集
- 渐进式加载：L1 name/description → L2 SKILL.md 正文 → L3 scripts/references/assets

## Bot 与执行

- `bot_skills` 表只存开关；技能正文在文件系统
- 技能默认全开，用户可在「AI 角色 → 技能」关闭
- 技能运行记录复用 `bot_runs`，`trigger='skill'`
- Agent 通过一个 `skill(skill_key, input)` 元工具调用
- 运行时注入 Bot 的 system prompt、记忆和模型

## API

```http
GET  /api/skills
GET  /api/skills/{key}
POST /api/skills/{key}/run             {bot_id, input}
GET  /api/bots/{bot_id}/skills
PUT  /api/bots/{bot_id}/skills/{key}   {enabled}

GET  /api/inbox/groups
POST /api/plugins/mail/messages/{id}/ai-draft
```

旧的 `/api/cos/*` 已删除，不提供兼容层。
