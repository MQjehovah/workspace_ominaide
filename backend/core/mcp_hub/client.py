"""Minimal MCP client for stdio and streamable HTTP servers.

The hub intentionally supports the small protocol surface OmniAide needs:
initialize, tools/list and tools/call. Keeping the client in-process avoids a
separate bridge process and works for both container-local and remote servers.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import httpx

PROTOCOL_VERSION = "2024-11-05"
DEFAULT_TIMEOUT = 30.0


class McpError(RuntimeError):
    pass


class McpConnection:
    async def start(self) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError

    async def list_tools(self) -> list[dict]:
        raise NotImplementedError

    async def call_tool(self, name: str, arguments: dict) -> dict:
        raise NotImplementedError

    async def request(self, method: str, params: dict | None = None) -> Any:
        raise NotImplementedError


class StdioMcpConnection(McpConnection):
    def __init__(self, command: str, args: list[str] | None = None,
                 env: dict[str, str] | None = None, cwd: str | None = None):
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.cwd = cwd
        self.proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._next_id = 0
        self._write_lock = asyncio.Lock()
        self._closed = False
        self.stderr_tail = ""

    async def start(self) -> None:
        env = {**os.environ, **self.env}
        env.setdefault("PYTHONUNBUFFERED", "1")
        try:
            self.proc = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self.cwd,
            )
        except FileNotFoundError as e:
            raise McpError(f"无法启动 MCP 服务 {self.command}: {e}")
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._stderr_loop())
        init = await self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "omniaide", "version": "1.0"},
        })
        await self._notify("notifications/initialized", {})
        if not isinstance(init, dict):
            raise McpError("MCP initialize 返回格式错误")

    async def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        while not self._closed:
            line = await self.proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode("utf-8", errors="replace"))
            except Exception:
                continue
            if "id" in msg and msg["id"] in self._pending:
                fut = self._pending.pop(msg["id"])
                if not fut.done():
                    if msg.get("error"):
                        fut.set_exception(McpError(str(msg["error"])))
                    else:
                        fut.set_result(msg.get("result"))
            # server notifications are intentionally ignored

    async def _stderr_loop(self) -> None:
        assert self.proc and self.proc.stderr
        while not self._closed:
            line = await self.proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                self.stderr_tail = (self.stderr_tail + "\n" + text)[-2000:]
                print(f"[mcp:{self.command}] {text}", file=sys.stderr)

    async def _notify(self, method: str, params: dict) -> None:
        assert self.proc and self.proc.stdin
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        async with self._write_lock:
            self.proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
            await self.proc.stdin.drain()

    async def request(self, method: str, params: dict | None = None) -> Any:
        if not self.proc or not self.proc.stdin:
            raise McpError("MCP 服务未启动")
        self._next_id += 1
        req_id = self._next_id
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params
        async with self._write_lock:
            self.proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
            await self.proc.stdin.drain()
        try:
            return await asyncio.wait_for(fut, timeout=DEFAULT_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise McpError(f"MCP 请求超时: {method}")
        finally:
            self._pending.pop(req_id, None)

    async def list_tools(self) -> list[dict]:
        tools: list[dict] = []
        cursor = None
        for _ in range(20):
            params = {"cursor": cursor} if cursor else {}
            result = await self.request("tools/list", params)
            if not isinstance(result, dict):
                break
            tools.extend(result.get("tools") or [])
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return tools

    async def call_tool(self, name: str, arguments: dict) -> dict:
        result = await self.request("tools/call", {"name": name, "arguments": arguments})
        return result if isinstance(result, dict) else {"content": [{"type": "text", "text": str(result)}]}

    async def close(self) -> None:
        self._closed = True
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(McpError("MCP 连接已关闭"))
        self._pending.clear()
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        for task in (self._reader_task, self._stderr_task):
            if task:
                task.cancel()


class HttpMcpConnection(McpConnection):
    def __init__(self, url: str, headers: dict[str, str] | None = None):
        self.url = url
        self.headers = headers or {}
        self.client: httpx.AsyncClient | None = None
        self.session_id: str | None = None
        self._next_id = 0

    async def start(self) -> None:
        self.client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        init = await self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "omniaide", "version": "1.0"},
        })
        if not isinstance(init, dict):
            raise McpError("MCP initialize 返回格式错误")
        await self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    async def _post(self, payload: dict) -> Any:
        assert self.client
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self.headers,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        resp = await self.client.post(self.url, json=payload, headers=headers)
        sid = resp.headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            return self._parse_sse(resp.text, payload.get("id"))
        if not resp.text.strip():
            return None
        return resp.json()

    @staticmethod
    def _parse_sse(text: str, req_id: Any) -> Any:
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if req_id is None or msg.get("id") == req_id:
                if msg.get("error"):
                    raise McpError(str(msg["error"]))
                return msg.get("result")
        return None

    async def request(self, method: str, params: dict | None = None) -> Any:
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            payload["params"] = params
        result = await self._post(payload)
        if isinstance(result, dict) and result.get("error"):
            raise McpError(str(result["error"]))
        return result

    async def list_tools(self) -> list[dict]:
        tools: list[dict] = []
        cursor = None
        for _ in range(20):
            params = {"cursor": cursor} if cursor else {}
            result = await self.request("tools/list", params)
            if not isinstance(result, dict):
                break
            tools.extend(result.get("tools") or [])
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return tools

    async def call_tool(self, name: str, arguments: dict) -> dict:
        result = await self.request("tools/call", {"name": name, "arguments": arguments})
        return result if isinstance(result, dict) else {"content": [{"type": "text", "text": str(result)}]}

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()
            self.client = None
