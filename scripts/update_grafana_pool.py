#!/usr/bin/env python3
"""Rebuild the Mining Guardian Pool Stats dashboard.

Credentials read from GRAFANA_PASSWORD / GRAFANA_USER / GRAFANA_URL env vars.
See `scripts/_grafana_auth.py` for the contract.
"""
import json
import urllib.request

from _grafana_auth import grafana_basic_auth_header, grafana_url

UID = "afi3q9w5ishz4f"
GRAFANA = grafana_url()
AUTH_HEADER = grafana_basic_auth_header()
DS = {"type": "prometheus", "uid": "efi3m84mbf668b"}


def api(method, path, data=None):
    url = f"{GRAFANA}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", AUTH_HEADER)
    req.add_header("Content-Type", "application/json")
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


existing = api("GET", f"/api/dashboards/uid/{UID}")
folder_id = existing.get("meta", {}).get("folderId", 0)
ver = existing["dashboard"].get("version", 1)

panels = []
y = 0

# Row 1 — 4 stat tiles
for i, (title, expr, unit, thresholds, w, x) in enumerate([
    ("Fleet Hashrate to Pool",
     "sum(mining_guardian_miner_hashrate_ths)",
     "none",
     [{"color": "red", "value": None}, {"color": "orange", "value": 3000}, {"color": "green", "value": 5000}],
     6, 0),
    ("Acceptance Rate",
     "100 - (sum(mining_guardian_pool_rejected) / (sum(mining_guardian_pool_accepted) + sum(mining_guardian_pool_rejected) + 1) * 100)",
     "percent",
     [{"color": "red", "value": None}, {"color": "orange", "value": 98}, {"color": "green", "value": 99}],
     6, 6),
    ("Rejection Rate",
     "sum(mining_guardian_pool_rejected) / (sum(mining_guardian_pool_accepted) + sum(mining_guardian_pool_rejected) + 1) * 100",
     "percent",
     [{"color": "green", "value": None}, {"color": "orange", "value": 0.5}, {"color": "red", "value": 1.0}],
     6, 12),
    ("Miners Submitting Shares",
     "count(mining_guardian_pool_accepted > 0)",
     "none",
     [{"color": "red", "value": None}, {"color": "orange", "value": 30}, {"color": "green", "value": 40}],
     6, 18),
], start=1):
    panels.append({
        "id": i, "type": "stat", "title": title,
        "datasource": DS,
        "gridPos": {"h": 4, "w": w, "x": x, "y": y},
        "targets": [{"expr": expr, "refId": "A"}],
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "textMode": "auto"},
        "fieldConfig": {"defaults": {"unit": unit, "decimals": 2 if unit == "percent" else 0,
            "thresholds": {"steps": thresholds}}},
    })
y += 4

# Row 2 — Accepted shares trend + rejection rate trend
panels.append({
    "id": 5, "type": "timeseries", "title": "Accepted Shares \u2014 Fleet Total",
    "datasource": DS, "gridPos": {"h": 8, "w": 12, "x": 0, "y": y},
    "targets": [{"expr": "sum(mining_guardian_pool_accepted)", "legendFormat": "Accepted", "refId": "A"}],
    "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": "green"},
        "custom": {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 15, "showPoints": "never", "gradientMode": "scheme"}}},
    "options": {"legend": {"displayMode": "hidden"}, "tooltip": {"mode": "single"}},
})

panels.append({
    "id": 6, "type": "timeseries", "title": "Rejection Rate % \u2014 Fleet Avg vs Worst",
    "datasource": DS, "gridPos": {"h": 8, "w": 12, "x": 12, "y": y},
    "targets": [
        {"expr": "sum(mining_guardian_pool_rejected) / (sum(mining_guardian_pool_accepted) + sum(mining_guardian_pool_rejected) + 1) * 100", "legendFormat": "Fleet Avg", "refId": "A"},
        {"expr": "max(mining_guardian_pool_rejected / (mining_guardian_pool_accepted + mining_guardian_pool_rejected + 1) * 100)", "legendFormat": "Worst Miner", "refId": "B"},
    ],
    "fieldConfig": {"defaults": {"unit": "percent", "decimals": 3,
        "custom": {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 0, "showPoints": "never",
            "thresholdsStyle": {"mode": "line"}},
        "thresholds": {"steps": [{"color": "transparent", "value": None}, {"color": "red", "value": 1.0}]}},
        "overrides": [
            {"matcher": {"id": "byName", "options": "Fleet Avg"}, "properties": [
                {"id": "color", "value": {"mode": "fixed", "fixedColor": "blue"}}, {"id": "custom.lineWidth", "value": 2}]},
            {"matcher": {"id": "byName", "options": "Worst Miner"}, "properties": [
                {"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}},
                {"id": "custom.lineWidth", "value": 1},
                {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 5]}}]},
        ]},
    "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}},
})
y += 8

# Row 3 — Problem miners table
panels.append({
    "id": 7, "type": "table", "title": "Problem Miners \u2014 Rejection Rate > 0.3%",
    "description": "Only shows miners with elevated rejection rates. Empty table = fleet is healthy.",
    "datasource": DS, "gridPos": {"h": 8, "w": 24, "x": 0, "y": y},
    "targets": [{"expr": "(mining_guardian_pool_rejected / (mining_guardian_pool_accepted + mining_guardian_pool_rejected + 1) * 100) > 0.3",
        "format": "table", "instant": True, "refId": "A"}],
    "transformations": [
        {"id": "organize", "options": {"excludeByName": {"__name__": True, "job": True, "instance": True, "site": True},
            "renameByName": {"miner_ip": "Miner IP", "Value": "Rejection %"}}},
        {"id": "sortBy", "options": {"sort": [{"field": "Rejection %", "desc": True}]}},
    ],
    "fieldConfig": {"defaults": {"decimals": 3, "custom": {"displayMode": "color-background-solid"},
        "thresholds": {"steps": [{"color": "green", "value": None}, {"color": "orange", "value": 0.5}, {"color": "red", "value": 1.0}]}}},
})
y += 8

# Row 4 — Per-miner detail charts
panels.append({
    "id": 8, "type": "timeseries", "title": "Accepted Shares by Miner (Top 10)",
    "datasource": DS, "gridPos": {"h": 7, "w": 12, "x": 0, "y": y},
    "targets": [{"expr": "topk(10, mining_guardian_pool_accepted)", "legendFormat": "{{miner_ip}}", "refId": "A"}],
    "fieldConfig": {"defaults": {"custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 0, "showPoints": "never"}}},
    "options": {"legend": {"displayMode": "list", "placement": "right"}, "tooltip": {"mode": "multi"}},
})
panels.append({
    "id": 9, "type": "timeseries", "title": "Rejected Shares by Miner (Top 5 Worst)",
    "datasource": DS, "gridPos": {"h": 7, "w": 12, "x": 12, "y": y},
    "targets": [{"expr": "topk(5, mining_guardian_pool_rejected)", "legendFormat": "{{miner_ip}}", "refId": "A"}],
    "fieldConfig": {"defaults": {"custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 0, "showPoints": "never"}}},
    "options": {"legend": {"displayMode": "list", "placement": "right"}, "tooltip": {"mode": "multi"}},
})

dashboard = {
    "uid": UID, "title": "Mining Guardian \u2014 Pool Stats",
    "tags": ["mining-guardian"], "timezone": "browser",
    "refresh": "30s", "time": {"from": "now-6h", "to": "now"},
    "panels": panels, "schemaVersion": 39, "version": ver + 1,
}

result = api("POST", "/api/dashboards/db", {"dashboard": dashboard, "folderId": folder_id, "overwrite": True})
print(f"Dashboard saved: {result.get('status', 'unknown')}")
