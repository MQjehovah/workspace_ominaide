import json, urllib.request, time

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjoxNzg2Mjc3MDE4LCJ0eXBlIjoiYWNjZXNzIn0.G009OBrtTDJH_GHSDDkoYj1P4_lTUTnx6SX3alr2XTA"
req = urllib.request.Request("http://localhost:8000/api/chat/stream",
    data=json.dumps({"message": "说三句话", "history": []}).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + TOKEN})
resp = urllib.request.urlopen(req, timeout=30)
print("status:", resp.status)
t0 = time.time()
count = 0
for line in resp:
    s = line.decode("utf-8", "replace").strip()
    if s.startswith("data: "):
        count += 1
        if count <= 3:
            print(f"  [{time.time()-t0:.2f}s] {s[:80]}")
print("total events:", count, f"({time.time()-t0:.2f}s)")
