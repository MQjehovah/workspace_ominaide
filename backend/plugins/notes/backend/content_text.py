"""Convert note content (TipTap JSON / markdown / html / text) to plain readable text.

Notes are stored as TipTap JSON by the desktop editor. For AI indexing / searching /
context, we want human-readable text rather than raw JSON or HTML.
"""

import json
import re

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _node_text(node: dict, inline: bool = False) -> str:
    t = node.get("type", "")
    if t in ("text", "link", "strong", "emoji", "mention"):
        return node.get("text") or node.get("attrs", {}).get("href", "") or ""
    if t == "image":
        return " [图片: " + (node.get("attrs", {}).get("src", "") or "") + "] "
    if t == "hardBreak":
        return "\n"
    children = node.get("content") or []
    # paragraph/heading inside list item / table cell → inline text (no block breaks)
    child_inline = inline or t in ("paragraph", "listItem", "tableCell", "tableHeader")
    text = "".join(_node_text(c, child_inline) for c in children if isinstance(c, dict))
    if t == "heading":
        level = node.get("attrs", {}).get("level", 1)
        return "\n\n" + "#" * level + " " + text
    if t == "listItem":
        return "\n- " + text
    if t == "blockquote":
        return "\n> " + text
    if t == "codeBlock":
        return "\n```\n" + text + "\n```\n"
    if t == "tableRow":
        return "\n| " + text + " |"
    if t == "tableCell" or t == "tableHeader":
        return text + " | "
    if t == "paragraph":
        return text if inline else "\n\n" + text
    if t == "bulletList" or t == "orderedList":
        return text
    if t == "doc":
        return text
    if t == "horizontalRule":
        return "\n\n---\n\n"
    return text


def json_to_text(content: str) -> str:
    """Convert TipTap JSON string to readable plain text (preserving structure loosely)."""
    try:
        doc = json.loads(content)
    except Exception:
        return content or ""
    return _node_text(doc).strip()


def html_to_text(content: str) -> str:
    text = _HTML_TAG_RE.sub(" ", content or "")
    return _WS_RE.sub(" ", text).strip()


def note_content_to_text(content: str | None) -> str:
    """Best-effort: convert any stored note content to readable plain text."""
    if not content:
        return ""
    trimmed = content.strip()
    if trimmed.startswith("{"):
        # TipTap JSON (our current format)
        return json_to_text(content)
    if "<" in trimmed and ">" in trimmed and any(x in trimmed for x in ("<p", "<div", "<h1", "<h2", "<ul", "<li", "<table")):
        # HTML
        return html_to_text(content)
    # Markdown or plain text — strip basic markdown symbols lightly
    return trimmed
