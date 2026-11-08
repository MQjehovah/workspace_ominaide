"""OAuth provider metadata."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provider:
    key: str
    name: str
    icon: str
    scopes: list[str] = field(default_factory=list)
    description: str = ""


PROVIDERS: dict[str, Provider] = {
    "google": Provider(
        key="google",
        name="Google",
        icon="google",
        description="Gmail、Google Calendar 和 Google Drive",
        scopes=[
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/drive.file",
        ],
    ),
}


def get_provider(key: str) -> Provider | None:
    return PROVIDERS.get((key or "").strip().lower())
