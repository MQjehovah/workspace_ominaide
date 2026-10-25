"""Knowledge-base importers: PDF / Word / HTML / plain text / web pages.

Extraction is intentionally dependency-light and personal-scale:
- PDF: pypdf (text PDFs; scanned PDFs need OCR later)
- DOCX: python-docx
- HTML/web: BeautifulSoup
- TXT/MD: UTF-8 with GB18030 fallback
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from core.config.settings import settings

MAX_IMPORT_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 300_000

_WS_RE = re.compile(r"[ \t]+\n")
_MULTI_NL_RE = re.compile(r"\n{3,}")


class ImportFailed(ValueError):
    pass


def _clean(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub("\n", text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    return text.strip()


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ImportFailed("无法识别文本编码")


def extract_document(filename: str, data: bytes) -> tuple[str, str]:
    """Return (title, markdown/plain text) from an uploaded document."""
    if not data:
        raise ImportFailed("文件为空")
    if len(data) > MAX_IMPORT_BYTES:
        raise ImportFailed("文件超过 20MB 限制")

    name = Path(filename or "imported").name
    title = Path(name).stem or "导入笔记"
    ext = Path(name).suffix.lower()

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except Exception as e:
            raise ImportFailed(f"PDF 解析组件缺失: {e}")
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception:
                    raise ImportFailed("PDF 有密码，暂不支持")
            parts: list[str] = []
            for i, page in enumerate(reader.pages, 1):
                try:
                    t = page.extract_text() or ""
                except Exception:
                    t = ""
                if t.strip():
                    parts.append(f"## 第 {i} 页\n\n{t.strip()}")
            text = "\n\n".join(parts)
            if not text.strip():
                raise ImportFailed("PDF 没有可提取文字（可能是扫描版，暂不支持 OCR）")
            return title, _clean(text)[:MAX_TEXT_CHARS]
        except ImportFailed:
            raise
        except Exception as e:
            raise ImportFailed(f"PDF 解析失败: {e}")

    if ext == ".docx":
        try:
            import docx
        except Exception as e:
            raise ImportFailed(f"Word 解析组件缺失: {e}")
        try:
            doc = docx.Document(io.BytesIO(data))
            parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    cells = [c.text.strip() for c in row.cells]
                    if any(cells):
                        parts.append("| " + " | ".join(cells) + " |")
            text = "\n\n".join(parts)
            if not text.strip():
                raise ImportFailed("Word 文档没有可提取文字")
            return title, _clean(text)[:MAX_TEXT_CHARS]
        except ImportFailed:
            raise
        except Exception as e:
            raise ImportFailed(f"Word 解析失败: {e}")

    if ext in (".html", ".htm"):
        return title, _clean(_html_text(_decode_text(data)))[:MAX_TEXT_CHARS]

    if ext in (".txt", ".md", ".markdown", ".csv", ".json", ".log"):
        return title, _clean(_decode_text(data))[:MAX_TEXT_CHARS]

    # Unknown binary: only accept if it decodes as text.
    try:
        return title, _clean(_decode_text(data))[:MAX_TEXT_CHARS]
    except ImportFailed:
        raise ImportFailed(f"暂不支持的文件类型: {ext or 'unknown'}")


def _html_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        body = soup.get_text("\n", strip=True)
        return (title + "\n\n" + body) if title else body
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)


async def fetch_url(url: str) -> tuple[str, str]:
    """Fetch a web page (or PDF) and return (title, text)."""
    import httpx
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ImportFailed("只支持 http/https 链接")

    headers = {"User-Agent": "OmniAide/1.0 (+knowledge-import)"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=25, headers=headers) as client:
        resp = await client.get(url)
        if resp.status_code >= 400:
            raise ImportFailed(f"网页返回 HTTP {resp.status_code}")
        data = resp.content
        if len(data) > 8 * 1024 * 1024:
            raise ImportFailed("网页内容超过 8MB")
        ctype = (resp.headers.get("content-type") or "").lower()
        if "pdf" in ctype or parsed.path.lower().endswith(".pdf"):
            name = Path(parsed.path).name or "web.pdf"
            title, text = extract_document(name, data)
        else:
            html = resp.text
            title = ""
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                title = soup.title.get_text(" ", strip=True) if soup.title else ""
            except Exception:
                pass
            text = _clean(_html_text(html))
            if not title:
                title = parsed.netloc + parsed.path
            if not text:
                raise ImportFailed("网页没有可提取正文")
        return title[:200] or "网页导入", text[:MAX_TEXT_CHARS]


def title_from_text(text: str, fallback: str = "导入笔记") -> str:
    for line in text.splitlines():
        line = line.strip("#> -*\t ")
        if line:
            return line[:80]
    return fallback


async def transcribe_audio(filename: str, data: bytes, mime: str | None = None) -> str:
    """Transcribe an audio/video file via the configured ASR provider."""
    if len(data) > 25 * 1024 * 1024:
        raise ImportFailed("音频超过 25MB 限制")
    api_key = settings.asr_api_key or settings.llm_api_key
    if not api_key:
        raise ImportFailed("未配置 ASR API Key")
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key, base_url=settings.asr_base_url)
        tr = await client.audio.transcriptions.create(
            model=settings.asr_model,
            file=(filename or "audio.mp3", data, mime or "application/octet-stream"),
        )
        text = (getattr(tr, "text", "") or "").strip()
        if not text:
            raise ImportFailed("没有识别到语音内容")
        return text[:MAX_TEXT_CHARS]
    except ImportFailed:
        raise
    except Exception as e:
        raise ImportFailed(f"语音转写失败: {e}")
