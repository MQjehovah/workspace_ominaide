import json, urllib.request

req = urllib.request.Request("http://localhost:8000/openapi.json")
try:
    d = json.loads(urllib.request.urlopen(req, timeout=15).read().decode())
    paths = sorted(d["paths"].keys())
    for p in paths:
        if any(k in p for k in ("schedule", "todo", "notification", "chat")):
            print(p, list(d["paths"][p].keys()))
except Exception as e:
    print("ERR", str(e)[:200])
