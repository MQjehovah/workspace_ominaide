"""DingTalk plugin startup hooks."""

from plugins.dingtalk.backend import service


async def startup() -> None:
    await service.migrate_existing_servers()
