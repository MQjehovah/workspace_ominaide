"""Minimal stdio MCP server for DingTalk (JSON-RPC 2.0, line delimited)."""

from __future__ import annotations

import asyncio
import json
import sys

from .tools import TOOLS, call_tool

PROTOCOL_VERSION = "2024-11-05"


async def _handle(msg: dict) -> dict | None:
    method = msg.get("method")
    req_id = msg.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "omniaide-dingtalk", "version": "1.0.0"},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        result = await call_tool(str(name), args)
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    return {
        "jsonrpc": "2.0", "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


async def main() -> None:
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        try:
            response = await _handle(msg)
        except Exception as e:
            response = {
                "jsonrpc": "2.0", "id": msg.get("id"),
                "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"},
            }
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
