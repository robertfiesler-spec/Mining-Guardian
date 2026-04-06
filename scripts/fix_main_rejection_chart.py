#!/usr/bin/env python3
"""Fix Pool Rejection Rate panel on Main dashboard — replace per-miner lines with fleet avg + worst."""
import json, urllib.request, base64

UID = "bfi3t0krwak1sd"
GRAFANA = "http://localhost:3000"
CREDS = base64.b64encode(b"admin:002300rf").decode()
DS = {"type": "prometheus", "uid": "efi3m84mbf668b"}

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

# Find and fix the rejection rate panel
for panel in dash.get("panels", []):
    title = str(panel.get("title", ""))
    if "ejection" in title and "ool" in title:
        print(f"Found panel {panel['id']}: {title}")
        
        # Replace with clean 2-line chart: fleet avg + worst miner
        panel["title"] = "Pool Rejection Rate %"
        panel["targets"] = [
            {
                "expr": "sum(mining_guardian_pool_rejected) / (sum(mining_guardian_pool_accepted) + sum(mining_guardian_pool_rejected) + 1) * 100",
                "legendFormat": "Fleet Avg",
                "refId": "A",
            },
            {
                "expr": "max(mining_guardian_pool_rejected / (mining_guardian_pool_accepted + mining_guardian_pool_rejected + 1) * 100)",
                "legendFormat": "Worst Miner",
                "refId": "B",
            },
        ]
        panel["fieldConfig"] = {
            "defaults": {
                "unit": "percent",
                "decimals": 3,
                "custom": {
                    "drawStyle": "line",
                    "lineWidth": 2,
                    "fillOpacity": 0,
                    "showPoints": "never",
                    "thresholdsStyle": {"mode": "line"},
                },
                "thresholds": {
                    "steps": [
                        {"color": "transparent", "value": None},
                        {"color": "red", "value": 1.0},
                    ]
                },
            },
            "overrides": [
                {
                    "matcher": {"id": "byName", "options": "Fleet Avg"},
                    "properties": [
                        {"id": "color", "value": {"mode": "fixed", "fixedColor": "blue"}},
                        {"id": "custom.lineWidth", "value": 2},
                    ],
                },
                {
                    "matcher": {"id": "byName", "options": "Worst Miner"},
                    "properties": [
                        {"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}},
                        {"id": "custom.lineWidth", "value": 1},
                        {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 5]}},
                    ],
                },
            ],
        }
        panel["options"] = {
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi"},
        }
        print("  -> Fixed: Fleet Avg (blue) + Worst Miner (orange dashed) + red threshold at 1%")

dash.pop("id", None)
dash["version"] = dash.get("version", 1) + 1

result = api("POST", "/api/dashboards/db", {
    "dashboard": dash,
    "folderId": folder_id,
    "overwrite": True,
})
print(f"Dashboard saved: {result.get('status', 'unknown')}")
