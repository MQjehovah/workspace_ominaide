import base64


def encode_cursor(value: int | str) -> str:
    return base64.urlsafe_b64encode(str(value).encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> str | None:
    if not cursor:
        return None
    raw = cursor + "=" * (-len(cursor) % 4)
    try:
        return base64.urlsafe_b64decode(raw.encode()).decode()
    except Exception:
        return None


def decode_int_cursor(cursor: str | None) -> int | None:
    value = decode_cursor(cursor)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
