#!/usr/bin/env python3
"""Debug and fix the Accepted Shares panel on Pool Stats dashboard."""
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

# Find panel 5 and dump its full config
for panel in dash.get("panels", []):
    if panel.get("id") == 5:
        print("CURRENT PANEL 5 CONFIG:")
        print(json.dumps(panel, indent=2)[:500])
        
        # Completely rebuild it from scratch — minimal config
        panel.clear()
        panel.update({
            "id": 5,
            "type": "timeseries",
            "title": "Accepted Shares \u2014 Fleet Total",
            "datasource": {"type": "prometheus", "uid": "efi3m84mbf668b"},
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 4},
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "efi3m84mbf668b"},
                    "expr": "sum(mining_guardian_pool_accepted)",
                    "legendFormat": "Accepted",
                    "refId": "A",
                    "editorMode": "code",
                    "range": True,
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "fixed", "fixedColor": "green"},
                    "custom": {
                        "drawStyle": "line",
                        "lineWidth": 2,
                        "fillOpacity": 20,
                        "showPoints": "never",
                        "spanNulls": True,
                    },
                },
                "overrides": [],
            },
            "options": {
                "legend": {"displayMode": "hidden"},
                "tooltip": {"mode": "single"},
            },
        })
        print("\nREBUILT panel 5 from scratch")

dash.pop("id", None)
dash["version"] = dash.get("version", 1) + 1

result = api("POST", "/api/dashboards/db", {
    "dashboard": dash,
    "folderId": folder_id,
    "overwrite": True,
})
print(f"Dashboard saved: {result.get('status', 'unknown')}")
