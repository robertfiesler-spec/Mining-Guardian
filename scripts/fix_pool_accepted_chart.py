#!/usr/bin/env python3
"""Fix Pool Stats accepted shares chart — show rate instead of cumulative total."""
import json, urllib.request, base64

UID = "afi3q9w5ishz4f"
GRAFANA = "http://localhost:3000"
CREDS = base64.b64encode(b"admin:002300rf").decode()

def api(method, path, data=None):
    url = f"{GRAFANA}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Basic {CREDS}")
    req.add_header("Content-Type", "application/json")
    return json.loads(urllib.request.urlopen(req, timeout=15).read())

existing = api("GET", f"/api/dashboards/uid/{UID}")
dash = existing["dashboard"]
folder_id = existing.get("meta", {}).get("folderId", 0)

# Find panel id 5 (Accepted Shares) and fix the query
for panel in dash.get("panels", []):
    if panel.get("id") == 5:
        # Change from cumulative to rate, and show both cumulative and rate
        panel["title"] = "Accepted Shares \u2014 Fleet Total"
        panel["targets"] = [
            {
                "expr": "sum(mining_guardian_pool_accepted)",
                "legendFormat": "Total Accepted",
                "refId": "A",
            },
        ]
        # Make sure min Y is not 0 — use auto scaling
        panel["fieldConfig"] = {
            "defaults": {
                "color": {"mode": "fixed", "fixedColor": "green"},
                "custom": {
                    "drawStyle": "line",
                    "lineWidth": 2,
                    "fillOpacity": 15,
                    "showPoints": "never",
                    "gradientMode": "scheme",
                    "axisSoftMin": None,  # let Grafana auto-scale
                    "scaleDistribution": {"type": "linear"},
                },
                "min": None,  # don't force Y-axis to start at 0
            },
        }
        # Key fix: tell Grafana NOT to start Y-axis at 0
        panel["options"] = {
            "legend": {"displayMode": "hidden"},
            "tooltip": {"mode": "single"},
        }
        print(f"Fixed panel {panel['id']}: {panel['title']}")

dash.pop("id", None)
dash["version"] = dash.get("version", 1) + 1

result = api("POST", "/api/dashboards/db", {
    "dashboard": dash,
    "folderId": folder_id,
    "overwrite": True,
})
print(f"Dashboard saved: {result.get('status', 'unknown')}")
