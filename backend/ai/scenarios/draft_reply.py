"""Reply draft scenario for mail and chat messages."""

from __future__ import annotations

import json

from sqlalchemy import select

from ai.llm import llm_json
from core.database.session import async_session

_TONES = {
    "professional": "专业、简洁、有礼貌",
    "friendly": "友好、自然、有人情味",
    "concise": "非常简短，直接说结论和下一步",
}


async def draft_reply(
    user_id: int,
    *,
    source: str = "mail",
    message_id: int | None = None,
    message: str | None = None,
    subject: str | None = None,
    tone: str = "professional",
    instructions: str | None = None,
    bot=None,
    extra_system: str | None = None,
) -> dict | None:
    original_subject = subject or ""
    original_body = (message or "").strip()
    from_address = ""

    if source == "mail":
        from plugins.mail.backend.models import MailMessage

        if not message_id:
            return None
        async with async_session() as db:
            row = (await db.execute(
                select(MailMessage).where(
                    MailMessage.id == message_id,
                    MailMessage.user_id == user_id,
                )
            )).scalar_one_or_none()
        if row is None:
            return None
        original_subject = row.subject or original_subject
        original_body = (row.content or row.preview or "").strip()
        from_address = row.from_address or ""

    if not original_body and not original_subject:
        return None

    tone_text = _TONES.get(tone, _TONES["professional"])
    base_subject = original_subject.strip()
    reply_subject = base_subject if base_subject.lower().startswith("re:") else f"Re: {base_subject}".strip()

    fallback = _fallback_reply(original_subject, original_body, tone)
    enriched = await llm_json(
        f"代写一封{'' if source == 'mail' else '消息'}回复草稿。语气：{tone_text}。"
        "只写草稿，不要声称已经发送，也不要编造承诺或日期。"
        '只返回 JSON: {"subject": "邮件主题", "body": "回复正文"}。',
        json.dumps({
            "channel": source,
            "from": from_address,
            "subject": original_subject,
            "message": original_body[:4000],
            "instructions": instructions or "",
        }, ensure_ascii=False),
        bot=bot,
        extra_system=extra_system,
    )
    body = fallback
    if enriched and isinstance(enriched.get("body"), str) and enriched["body"].strip():
        body = enriched["body"].strip()
        if isinstance(enriched.get("subject"), str) and enriched["subject"].strip():
            reply_subject = enriched["subject"].strip()

    return {
        "source": source,
        "message_id": message_id,
        "to": from_address,
        "subject": reply_subject,
        "body": body,
        "tone": tone,
        "sent": False,
        "note": "这是草稿，尚未发送。确认后再通过邮件或钉钉发送。",
    }


def _fallback_reply(subject: str, body: str, tone: str) -> str:
    topic = f"「{subject}」" if subject else "你提到的事项"
    snippet = " ".join(body.split())[:120]
    if tone == "concise":
        return f"收到，关于{topic}我会尽快确认并回复下一步。"
    if tone == "friendly":
        return (
            f"你好！\n\n看到了关于{topic}的消息。"
            + (f"（{snippet}……）\n\n" if snippet else "\n\n")
            + "我先核对一下相关细节，确认后马上同步进展。有新的信息也欢迎随时告诉我。\n\n谢谢！"
        )
    return (
        f"你好，\n\n收到关于{topic}的消息，核心信息已了解。"
        + (f"\n\n原文要点：{snippet}……\n" if snippet else "\n")
        + "\n我会尽快确认相关细节，并同步后续进展。如需我优先处理某一部分，请直接说明。\n\n谢谢！"
    )
