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
        "key": "mail_triage",
        "name": "重要邮件处理",
        "description": "收到重要邮件时生成摘要，并建议回复、建待办或忽略。",
        "trigger_type": "event",
        "event_type": "mail.received",
        "event_filter": {"important": True},
        "prompt": (
            "刚刚收到一封重要邮件。先概括它需要我做什么，再给出处理建议："
            "是否需要回复、是否要创建待办、截止时间是什么。用 2-4 句中文。"
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
            "并建议一个合适的文件夹或标签。用中文，不要编造文件内容。"
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
