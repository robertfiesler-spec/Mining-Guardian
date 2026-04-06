#!/usr/bin/env python3
"""
Redesign Pool Stats dashboard:
- Fix "No data" tile (fleet hashrate)
- Remove noisy bottom charts
- Clean, operator-focused layout
"""
import json, urllib.request, base64

uid = "afi3q9w5ishz4f"
creds = base64.b64encode(b"admin:002300rf").decode()

# Fetch current dashboard
req = urllib.request.Request(f"http://localhost:3000/api/dashboards/uid/{uid}")
req.add_header("Authorization", f"Basic {creds}")
resp = urllib.request.urlopen(req, timeout=10)
d = json.loads(resp.read())
dash = d["dashboard"]

# Print current panel titles for reference
panels = dash.get("panels", [])
print(f"Current panels ({len(panels)}):")
for i, p in enumerate(panels):
    title = p.get("title", "untitled")
    ptype = p.get("type", "?")
    print(f"  [{i}] {title} ({ptype})")

# Strategy:
# Keep panels 0-3 (stat tiles) — fix the "No data" one
# Keep panel 4 (Accepted Shares Fleet Total) — good
# Keep panel 5 (Rejection Rate chart) — useful  
# Keep panel 6 (Problem Miners table) — essential
# REMOVE panels 7+ (noisy per-miner charts)

# Fix the "No data" stat tile — it's probably querying a metric that doesn't exist
for p in panels:
    title = p.get("title", "")
    targets = p.get("targets", [])
    
    # Print the stat tile queries so we can fix them
    if p.get("type") == "stat":
        for t in targets:
            expr = t.get("expr", "")
            print(f"\n  Stat tile '{title}': {expr}")

# Remove the bottom two noisy charts (Accepted by Miner, Rejected by Miner)
# These are typically the last 2 panels
new_panels = []
remove_titles = [
    "Accepted Shares by Miner",
    "Rejected Shares by Miner",
    "Accepted Shares by Miner (Top 10)",
    "Rejected Shares by Miner (Top 5 Worst)",
]
for p in panels:
    title = p.get("title", "")
    if any(rt in title for rt in remove_titles):
        print(f"\n  REMOVING: {title}")
    else:
        new_panels.append(p)

# Fix the "No data" stat — change query to use pool accepted shares sum
for p in new_panels:
    title = p.get("title", "")
    if "No data" in str(p) or "Fleet Hashrate" in title or "hashrate" in title.lower():
        # This tile probably queries a fleet hashrate metric that doesn't exist
        # Change it to show total accepted shares or fleet hashrate from miner readings
        for t in p.get("targets", []):
            expr = t.get("expr", "")
            if "hashrate" in expr.lower() and "pool" not in expr.lower():
                # Replace with fleet total hashrate from the miner metrics
                t["expr"] = 'sum(mining_guardian_miner_hashrate_ths{site="usa_188"})'
                print(f"\n  FIXED stat tile '{title}': {t['expr']}")

# Expand the problem miners table to be taller since we removed bottom charts
for p in new_panels:
    title = p.get("title", "")
    if "Problem" in title:
        gp = p.get("gridPos", {})
        gp["h"] = 10  # Make it taller
        print(f"\n  Expanded '{title}' height to 10")

dash["panels"] = new_panels

# Save
dash.pop("id", None)
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
print(f"\nDashboard saved: {result.get('status', 'ok')}")
print(f"Panels: {len(panels)} → {len(new_panels)}")
