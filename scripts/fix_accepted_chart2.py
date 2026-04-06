#!/usr/bin/env python3
"""Fix Accepted Shares chart — use increase() to show new shares, not cumulative."""
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

for panel in dash.get("panels", []):
    if panel.get("id") == 5:
        # Try a completely different metric that we know works
        # The rejection rate chart works fine — let's use a similar pattern
        panel["targets"] = [
            {
                "datasource": {"type": "prometheus", "uid": "efi3m84mbf668b"},
                "expr": "sum(mining_guardian_pool_accepted)",
                "legendFormat": "Total Accepted",
                "refId": "A",
                "editorMode": "code",
                "range": True,
                "instant": False,
                "intervalMs": 30000,
            }
        ]
        # Remove any min/null settings that might cause rendering issues
        panel["fieldConfig"] = {
            "defaults": {
                "color": {"mode": "fixed", "fixedColor": "green"},
                "custom": {
                    "drawStyle": "line",
                    "lineWidth": 2,
                    "fillOpacity": 20,
                    "showPoints": "auto",
                    "spanNulls": False,
                    "lineInterpolation": "linear",
                    "axisCenteredZero": False,
                },
            },
            "overrides": [],
        }
        print("Fixed panel 5 — added explicit range/instant/interval settings")

dash.pop("id", None)
dash["version"] = dash.get("version", 1) + 1
result = api("POST", "/api/dashboards/db", {"dashboard": dash, "folderId": folder_id, "overwrite": True})
print(f"Dashboard saved: {result.get('status', 'unknown')}")
