"""Periodic IMAP sync owned by the mail plugin."""

from core.config.settings import settings
from core.scheduler import PeriodicJob


async def sync_due_mail() -> dict:
    if not settings.mail_sync_enabled:
        return {"skipped": True, "reason": "disabled"}
    from plugins.mail.backend.sync import sync_due_accounts

    result = await sync_due_accounts(settings.mail_sync_interval_seconds)
    if result.get("new"):
        from core.logging import get_logger

        get_logger(__name__).info("[mail] synced %s new message(s)", result["new"])
    return result


JOBS = [
    PeriodicJob(
        key="mail.sync_due",
        owner="mail",
        handler=sync_due_mail,
        interval_seconds=max(60, int(settings.mail_sync_interval_seconds)),
        timeout_seconds=900,
        run_on_start=True,
    ),
]
