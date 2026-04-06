#!/usr/bin/env python3
"""Fix Board Health dashboard variable: change mhs to ths in the miner IP dropdown query."""
import json, urllib.request, base64

uid = "afi3p5mhapn9ce"
url = f"http://localhost:3000/api/dashboards/uid/{uid}"
creds = base64.b64encode(b"admin:002300rf").decode()

# Fetch current dashboard
req = urllib.request.Request(url)
req.add_header("Authorization", f"Basic {creds}")
resp = urllib.request.urlopen(req, timeout=10)
d = json.loads(resp.read())
dash = d["dashboard"]

# Fix the variable query
templating = dash.get("templating", {}).get("list", [])
fixed = False
for t in templating:
    if t.get("name") == "miner":
        q = t.get("query", {})
        if isinstance(q, dict) and "board_rate_mhs" in q.get("query", ""):
            q["query"] = q["query"].replace("board_rate_mhs", "board_rate_ths")
            fixed = True
            print(f"Fixed variable query: {q['query']}")

if not fixed:
    print("Variable query not found or already fixed")
else:
    # Save back
    dash.pop("id", None)  # Remove id for update
    save_url = "http://localhost:3000/api/dashboards/db"
    payload = json.dumps({
        "dashboard": dash,
        "folderId": d.get("meta", {}).get("folderId", 0),
        "overwrite": True
    }).encode()
    
    req2 = urllib.request.Request(save_url, data=payload, method="POST")
    req2.add_header("Authorization", f"Basic {creds}")
    req2.add_header("Content-Type", "application/json")
    resp2 = urllib.request.urlopen(req2, timeout=10)
    result = json.loads(resp2.read())
    print(f"Dashboard saved: {result.get('status', 'ok')}")
