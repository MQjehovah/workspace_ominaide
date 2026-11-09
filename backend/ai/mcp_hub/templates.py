"""Suggested MCP server templates shown in the unified manager."""

TEMPLATES = [
    {
        "key": "home-assistant",
        "name": "Home Assistant",
        "description": "连接 Home Assistant 的 MCP 端点，控制灯、开关、场景等。",
        "transport": "http",
        "url": "http://homeassistant.local:8123/mcp",
        "scope": "backend",
        "risk_default": "read",
        "header_hints": ["Authorization"],
    },
    {
        "key": "playwright",
        "name": "Playwright",
        "description": "浏览器自动化：打开页面、点击、填表、截图。",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@playwright/mcp@latest"],
        "scope": "backend",
        "risk_default": "read",
    },
    {
        "key": "filesystem",
        "name": "本地文件系统",
        "description": "只读或读写指定目录的 MCP 文件服务。",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"],
        "scope": "backend",
        "risk_default": "read",
    },
    {
        "key": "fetch",
        "name": "网页抓取",
        "description": "抓取网页并转换为 Markdown，适合做研究。",
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "scope": "backend",
        "risk_default": "read",
    },
    {
        "key": "github",
        "name": "GitHub",
        "description": "读取仓库、Issue、PR；需要 GitHub token。",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "scope": "backend",
        "risk_default": "read",
        "env_hints": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
    },
]


def list_templates() -> list[dict]:
    return [dict(t) for t in TEMPLATES]
