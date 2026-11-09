"""Logging redaction and a guard against new print() calls."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_PRINT_CALL = re.compile(r"(?<![\w.])print\(")


def test_redacts_tokens_and_passwords():
    from core.logging import redact

    text = "GET /api/files/stream?token=abc123&x=1 password=hunter2 Bearer aaa.bbb.ccc"
    cleaned = redact(text)
    assert "abc123" not in cleaned
    assert "hunter2" not in cleaned
    assert "aaa.bbb.ccc" not in cleaned
    assert "token=***" in cleaned


def test_runtime_code_has_no_print_calls():
    offenders = []
    for folder in (ROOT / "core", ROOT / "plugins"):
        for path in folder.rglob("*.py"):
            if "__pycache__" in str(path) or "mcp_servers" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if _PRINT_CALL.search(text):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
