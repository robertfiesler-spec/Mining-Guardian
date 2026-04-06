#!/usr/bin/env python3
"""Replace accepted shares cumulative with per-miner accepted shares (top 10) — 
this is what the old dashboard showed and we know it works."""
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
        panel.clear()
        panel.update({
            "id": 5,
            "type": "timeseries",
            "title": "Accepted vs Rejected Shares \u2014 Fleet Total",
            "datasource": {"type": "prometheus", "uid": "efi3m84mbf668b"},
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 4},
            "targets": [
                {
                    "datasource": {"type": "prometheus", "uid": "efi3m84mbf668b"},
                    "expr": "sum(mining_guardian_pool_accepted)",
                    "legendFormat": "Accepted",
                    "refId": "A",
                },
                {
                    "datasource": {"type": "prometheus", "uid": "efi3m84mbf668b"},
                    "expr": "sum(mining_guardian_pool_rejected)",
                    "legendFormat": "Rejected",
                    "refId": "B",
                },
            ],
            "fieldConfig": {
                "defaults": {
                    "custom": {
                        "drawStyle": "line",
                        "lineWidth": 2,
                        "fillOpacity": 10,
                        "showPoints": "never",
                        "spanNulls": True,
                        "stacking": {"mode": "none"},
                        "axisPlacement": "auto",
                    },
                },
                "overrides": [
                    {
                        "matcher": {"id": "byName", "options": "Accepted"},
                        "properties": [
                            {"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}},
                        ],
                    },
                    {
                        "matcher": {"id": "byName", "options": "Rejected"},
                        "properties": [
                            {"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}},
                            {"id": "custom.axisPlacement", "value": "right"},
                        ],
                    },
                ],
            },
            "options": {
                "legend": {"displayMode": "list", "placement": "bottom"},
                "tooltip": {"mode": "multi"},
            },
        })
        print("Rebuilt panel 5: Accepted vs Rejected with dual axis")

dash.pop("id", None)
dash["version"] = dash.get("version", 1) + 1
result = api("POST", "/api/dashboards/db", {"dashboard": dash, "folderId": folder_id, "overwrite": True})
print(f"Dashboard saved: {result.get('status', 'unknown')}")
