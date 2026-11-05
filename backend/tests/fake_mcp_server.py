"""Tiny stdio MCP server used by tests."""
import json
import sys

TOOLS = [
    {
        "name": "echo",
        "description": "echo text",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "add",
        "description": "add two numbers",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
]


def reply(req_id, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": req_id}
    if error:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        method = msg.get("method")
        req_id = msg.get("id")
        if method == "initialize":
            reply(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake", "version": "1.0"},
            })
        elif method == "notifications/initialized":
            pass
        elif method == "ping":
            reply(req_id, {})
        elif method == "tools/list":
            reply(req_id, {"tools": TOOLS})
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            if name == "echo":
                reply(req_id, {"content": [{"type": "text", "text": "echo:" + str(args.get("text", ""))}]})
            elif name == "add":
                total = float(args.get("a") or 0) + float(args.get("b") or 0)
                reply(req_id, {"content": [{"type": "text", "text": str(total)}]})
            else:
                reply(req_id, {"content": [{"type": "text", "text": "unknown"}], "isError": True})
        else:
            reply(req_id, error={"code": -32601, "message": "not found"})


if __name__ == "__main__":
    main()
