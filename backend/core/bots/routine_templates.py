"""Ready-to-use automation templates.

Templates are plain data so the web UI can preview them and the API can create
a routine with the user's bot in one call.
"""

ROUTINE_TEMPLATES: list[dict] = [
    {
        "key": "morning_brief",
        "name": "晨间简报",
        "description": "每天汇总天气、日程、待办、通知和未读资讯，生成口语化晨报。",
        "trigger_type": "cron",
        "cron_expr": "30 7 * * *",
        "prompt": (
            "生成今天的晨间简报。先获取天气、今日日程、未完成待办、未读通知和新订阅文章，"
            "再用 3-6 句中文口语化播报：问候、天气/穿衣建议、今日日程、最重要的 1-2 个待办，"
            "最后提醒今天最先要做的事。不要 Markdown，不要编造数据。"
        ),
    },
    {
        "key": "event_scan",
        "name": "重要事件扫描",
        "description": "每 15 分钟检查新邮件/日程/待办，只在确实紧急时提醒。",
        "trigger_type": "cron",
        "cron_expr": "*/15 * * * *",
        "prompt": (
            "检查最近 15 分钟内的新邮件、日程、待办和通知。"
            "只有当事项确实紧急、需要我立刻处理时才发一条简短提醒；"
            "历史事件、普通操作和常规订阅不要提醒。没有紧急事项时不要发通知。"
        ),
    },
    {
        "key": "profile_refresh",
        "name": "画像更新",
        "description": "每天根据最近 24 小时的活动与会话更新 AI 对我的理解。",
        "trigger_type": "cron",
        "cron_expr": "0 3 * * *",
        "prompt": (
            "回顾我最近 24 小时的邮件、日程、待办、笔记和对话，"
            "更新你对我工作习惯、关注领域和近期项目的理解。"
            "只记录有证据支撑的内容，不要编造。"
        ),
    },
    {
        "key": "daily_review",
        "name": "每日回顾",
        "description": "每天结束前复盘当天的活动与会话，提炼完成事项和明日建议。",
        "trigger_type": "cron",
        "cron_expr": "0 22 * * *",
        "prompt": (
            "复盘今天的活动与会话：总结完成了什么、推进了哪些事项、有哪些未完成，"
            "给出 1-3 条明天可执行的建议。用 3-5 句中文，不要编造。"
        ),
    },
    {
        "key": "weekly_review",
        "name": "每周复盘",
        "description": "每周五汇总本周成果、未完成事项和下周重点。",
        "trigger_type": "cron",
        "cron_expr": "0 18 * * 5",
        "prompt": (
            "生成本周复盘：列出本周完成的关键事项、仍未完成的事项、下周最重要的三件事。"
            "用中文，简洁分点，不要编造。"
        ),
    },
    {
        "key": "rss_digest",
        "name": "资讯摘要",
        "description": "每天阅读未读订阅，挑出值得关注的几条并说明原因。",
        "trigger_type": "cron",
        "cron_expr": "0 8 * * *",
        "prompt": (
            "汇总最近 24 小时的未读资讯：先给一句总览，再挑 2-4 条最重要的说明为什么值得看。"
            "不要 Markdown 列表，不要编造。"
        ),
    },
    {
        "key": "run_summary",
        "name": "运行摘要",
        "description": "每次 Bot 运行结束后，把结论和未完成事项写入长期记忆。",
        "trigger_type": "event",
        "event_type": "bot.run.finished",
        "prompt": (
            "下面是一次刚结束的 Bot 运行，包含输入和输出。"
            "请把结论、用户偏好、未完成事项和关键事实压缩成一条不超过 200 字的长期记忆，"
            "并调用 save_memory 工具保存。不要编造，不要复述过程。"
            "这是后台整理任务，不要调用 send_notification。"
        ),
    },
    {
        "key": "mail_triage",
        "name": "重要邮件处理",
        "description": "收到邮件时分析摘要、重要度和后续动作，只有重要时才提醒。",
        "trigger_type": "event",
        "event_type": "mail.received",
        "prompt": (
            "下面是一封刚收到的邮件，主题、发件人和正文在事件详情里。请判断："
            "1) 用 2-3 句中文概括要点；"
            "2) 重要度（高/中/低）；"
            "3) 是否需要我后续动作（回复/建待办/安排日程/忽略）。"
            "只有重要度高、或确实需要我处理时，调用 send_notification 工具发一条提醒，"
            "标题用「📬 邮件：主题」，正文包含摘要和建议动作。"
            "不重要时不要调用任何工具，直接结束。"
            "不要修改邮件本身，不要编造。"
        ),
    },
    {
        "key": "file_summary",
        "name": "文件自动摘要",
        "description": "上传文件后读取正文，生成摘要、关键词和建议归档位置。",
        "trigger_type": "event",
        "event_type": "file.uploaded",
        "prompt": (
            "刚刚上传了一个新文件。读取它的正文，生成 2-3 句摘要、3-5 个关键词，"
            "并建议一个合适的文件夹或标签。然后调用 send_notification 把摘要发给我。"
            "用中文，不要编造文件内容。"
        ),
    },
    {
        "key": "meeting_prep",
        "name": "会议准备",
        "description": "工作日早上为今天的第一个会议准备相关文件与要点。",
        "trigger_type": "cron",
        "cron_expr": "30 8 * * 1-5",
        "prompt": (
            "查看今天的第一个会议，找出与会议主题相关的笔记、文件和邮件，"
            "整理 3-5 条会前要点和可能需要确认的问题。用中文。"
        ),
    },
    {
        "key": "evening_cleanup",
        "name": "晚间收尾",
        "description": "每天傍晚整理未读通知、临期待办和明天的日程。",
        "trigger_type": "cron",
        "cron_expr": "30 18 * * *",
        "prompt": (
            "帮我做今天收尾：列出仍未读的重要通知、明天到期或已逾期的待办、明天的日程，"
            "并建议今晚先处理哪一件。用中文，简洁。"
        ),
    },
]


def list_templates() -> list[dict]:
    return [dict(t) for t in ROUTINE_TEMPLATES]


def get_template(key: str) -> dict | None:
    for t in ROUTINE_TEMPLATES:
        if t["key"] == key:
            return dict(t)
    return None
