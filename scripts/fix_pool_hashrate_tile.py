#!/usr/bin/env python3
"""Fix the Fleet Hashrate stat tile to use sum of board_rate_ths."""
import json, urllib.request, base64

uid = "afi3q9w5ishz4f"
creds = base64.b64encode(b"admin:002300rf").decode()

req = urllib.request.Request(f"http://localhost:3000/api/dashboards/uid/{uid}")
req.add_header("Authorization", f"Basic {creds}")
resp = urllib.request.urlopen(req, timeout=10)
d = json.loads(resp.read())
dash = d["dashboard"]

for p in dash.get("panels", []):
    if "Fleet Hashrate" in p.get("title", ""):
        for t in p.get("targets", []):
            t["expr"] = 'sum(mining_guardian_board_rate_ths{site="usa_188"})'
            print(f"Fixed: {t['expr']}")
        # Add unit formatting — TH/s
        if "fieldConfig" not in p:
            p["fieldConfig"] = {"defaults": {}, "overrides": []}
        p["fieldConfig"]["defaults"]["unit"] = "ths"
        # Actually no unit suffix — just show the number with "TH/s" in title
        p["fieldConfig"]["defaults"]["unit"] = "none"
        p["fieldConfig"]["defaults"]["decimals"] = 0
        p["title"] = "Fleet Hashrate TH/s"

dash.pop("id", None)
payload = json.dumps({
    "dashboard": dash,
    "folderId": d.get("meta", {}).get("folderId", 0),
    "overwrite": True
}).encode()
req2 = urllib.request.Request("http://localhost:3000/api/dashboards/db", data=payload, method="POST")
req2.add_header("Authorization", f"Basic {creds}")
req2.add_header("Content-Type", "application/json")
resp2 = urllib.request.urlopen(req2, timeout=10)
print(f"Saved: {json.loads(resp2.read()).get('status')}")
