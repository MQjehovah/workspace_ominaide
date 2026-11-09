"""Web search and page reading tools.

Search uses Bing's public HTML endpoint (works without an API key and is
reachable from mainland China). Page fetching is restricted to public HTTP(S)
hosts to avoid turning the assistant into an SSRF proxy for internal services.
"""
import base64
import ipaddress
import re
import socket
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ai.mcp.core import MCPCallResponse, MCPContent, MCPTool
from core.config.settings import settings

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


def _err(text: str) -> MCPCallResponse:
    return MCPCallResponse(isError=True, content=[MCPContent(text=text)])


def _public_host(host: str) -> bool:
    host = (host or "").strip().lower()
    if not host or host == "localhost" or host.endswith(".local"):
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


def _validate_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("只支持 http/https 网页")
    if not parsed.hostname:
        raise ValueError("URL 缺少主机名")
    if not _public_host(parsed.hostname):
        raise ValueError("拒绝访问内网/本地地址")
    return parsed.geturl()


def _unwrap_bing_url(href: str, base: str) -> str:
    """Decode Bing's /ck/a?u=a1<base64> redirect wrapper."""
    if not href:
        return ""
    href = urljoin(base, href)
    parsed = urlparse(href)
    if parsed.netloc.endswith("bing.com") and parsed.path.startswith("/ck/a"):
        token = (parse_qs(parsed.query).get("u") or [""])[0]
        if token.startswith("a1"):
            raw = token[2:]
            raw += "=" * (-len(raw) % 4)
            try:
                decoded = base64.urlsafe_b64decode(raw).decode("utf-8", "replace")
                if decoded.startswith(("http://", "https://")):
                    return decoded
            except Exception:
                pass
    return href


def parse_bing_results(html: str, max_results: int = 5) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    results = []
    for item in soup.select("li.b_algo"):
        link = item.select_one("h2 a")
        if link is None:
            continue
        title = link.get_text(" ", strip=True)
        href = _unwrap_bing_url(link.get("href", ""), "https://cn.bing.com")
        if not title or not href.startswith(("http://", "https://")):
            continue
        caption = item.select_one(".b_caption p") or item.select_one("p")
        cite = item.select_one("cite")
        results.append({
            "title": title,
            "url": href,
            "snippet": caption.get_text(" ", strip=True) if caption else "",
            "site": cite.get_text(" ", strip=True) if cite else "",
        })
        if len(results) >= max_results:
            break
    return results


async def web_search(user_id: int, args: dict) -> MCPCallResponse:
    query = (args.get("query") or "").strip()
    if not query:
        return _err("query 必填")
    try:
        max_results = int(args.get("max_results") or settings.web_search_max_results)
    except (TypeError, ValueError):
        max_results = settings.web_search_max_results
    max_results = min(max(max_results, 1), 10)

    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
            resp = await client.get(
                settings.web_search_url,
                params={"q": query, "setlang": "zh-CN"},
            )
    except Exception as e:
        return _err(f"搜索失败：{str(e)[:160]}")

    if resp.status_code >= 400:
        return _err(f"搜索失败：HTTP {resp.status_code}")
    results = parse_bing_results(resp.text, max_results)
    if not results:
        return _err("没有搜到结果（搜索引擎可能触发了验证码，请换个关键词）")

    lines = [f"搜索「{query}」的结果："]
    for i, item in enumerate(results, start=1):
        lines.append(f"{i}. {item['title']}")
        lines.append(f"   URL: {item['url']}")
        if item["snippet"]:
            lines.append(f"   摘要: {item['snippet']}")
    lines.append("需要正文时调用 web_fetch(url)。")
    return _ok("\n".join(lines))


async def web_fetch(user_id: int, args: dict) -> MCPCallResponse:
    url = (args.get("url") or "").strip()
    if not url:
        return _err("url 必填")
    try:
        url = _validate_url(url)
    except ValueError as e:
        return _err(str(e))

    try:
        max_chars = int(args.get("max_chars") or settings.web_fetch_max_chars)
    except (TypeError, ValueError):
        max_chars = settings.web_fetch_max_chars
    max_chars = min(max(max_chars, 500), 30_000)

    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=25, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    return _err(f"打开网页失败：HTTP {resp.status_code}")
                content_type = (resp.headers.get("content-type") or "").lower()
                allowed = (
                    "text/html", "text/plain", "application/xhtml",
                    "application/json", "text/markdown",
                )
                if content_type and not any(t in content_type for t in allowed):
                    return _err(f"暂不支持该内容类型：{content_type.split(';')[0]}")
                chunks = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > settings.web_fetch_max_bytes:
                        chunks.append(chunk[: max(0, settings.web_fetch_max_bytes - (total - len(chunk)))])
                        break
                    chunks.append(chunk)
                raw = b"".join(chunks)
                final_url = str(resp.url)
                encoding = resp.charset_encoding or "utf-8"
    except Exception as e:
        return _err(f"打开网页失败：{str(e)[:160]}")

    text = raw.decode(encoding, errors="replace")
    if "html" in content_type or "xml" in content_type:
        soup = BeautifulSoup(text, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        for tag in soup([
            "script", "style", "noscript", "nav", "footer", "header",
            "form", "svg", "iframe", "aside",
        ]):
            tag.decompose()
        body = soup.body or soup
        content = body.get_text("\n", strip=True)
    else:
        title = ""
        content = text

    content = re.sub(r"[ \t]+\n", "\n", content)
    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    truncated = len(content) > max_chars
    content = content[:max_chars]

    lines = [f"URL: {final_url}"]
    if title:
        lines.append(f"标题: {title}")
    lines.append("")
    lines.append(content or "（没有提取到正文）")
    if truncated:
        lines.append("\n…（正文已截断）")
    return _ok("\n".join(lines))


TOOLS = [
    (
        MCPTool(
            name="web_search",
            description=(
                "搜索公开互联网（Bing）。用户问实时信息、新闻、价格、技术文档、"
                "某个网站/产品的最新情况时使用。需要网页正文时接着调用 web_fetch。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "max_results": {
                        "type": "integer",
                        "description": "返回条数，默认 5，最大 10",
                    },
                },
                "required": ["query"],
            },
        ),
        web_search,
    ),
    (
        MCPTool(
            name="web_fetch",
            description=(
                "打开一个公开网页并提取正文。先用 web_search 找到 URL，再调用它读取详情。"
                "只支持公网 http/https 地址。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要打开的网页 URL"},
                    "max_chars": {
                        "type": "integer",
                        "description": "正文最大字符数，默认 12000，最大 30000",
                    },
                },
                "required": ["url"],
            },
        ),
        web_fetch,
    ),
]
