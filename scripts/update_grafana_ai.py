#!/usr/bin/env python3
"""Update the Grafana AI & Learning dashboard with the new AI Intelligence Center iframe.

Credentials read from GRAFANA_PASSWORD / GRAFANA_USER / GRAFANA_URL env vars.
See `scripts/_grafana_auth.py` for the contract.
"""
import requests

from _grafana_auth import grafana_basic_auth_tuple, grafana_url

GRAFANA = grafana_url()
AUTH = grafana_basic_auth_tuple()

# Get current dashboard
r = requests.get(f"{GRAFANA}/api/dashboards/uid/llm_learning_001", auth=AUTH)
data = r.json()
dash = data["dashboard"]

# New panel layout: AI Intelligence Center iframe at top, then historical charts
new_panels = [
    {
        "id": 20,
        "type": "text",
        "title": "",
        "gridPos": {"h": 28, "w": 24, "x": 0, "y": 0},
        "options": {
            "mode": "html",
            "content": '<iframe src="https://dashboard.fieslerfamily.com/ai/dashboard" style="width:100%;height:100%;border:none;background:#0f172a" frameborder="0"></iframe>',
        },
        "transparent": True,
    },
    {
        "id": 7,
        "type": "timeseries",
        "title": "🧠 AI Score Growth Over Time",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 28},
        "targets": [
            {"expr": "mining_guardian_knowledge_score{site='usa_188'}", "legendFormat": "AI Score"},
            {"expr": "mining_guardian_ai_data_depth{site='usa_188'}", "legendFormat": "Data Depth"},
            {"expr": "mining_guardian_ai_knowledge{site='usa_188'}", "legendFormat": "Knowledge"},
            {"expr": "mining_guardian_ai_experience{site='usa_188'}", "legendFormat": "Experience"},
        ],
        "datasource": {"type": "prometheus", "uid": "PBFA97CFB590B2093"},
        "fieldConfig": {
            "defaults": {"color": {"mode": "palette-classic"}, "custom": {"lineWidth": 2, "fillOpacity": 10}},
            "overrides": [
                {"matcher": {"id": "byName", "options": "AI Score"}, "properties": [{"id": "color", "value": {"fixedColor": "#06b6d4", "mode": "fixed"}}, {"id": "custom.lineWidth", "value": 3}]},
            ]
        },
    },
    {
        "id": 8,
        "type": "timeseries",
        "title": "🤖 AI Autonomy — Actions Over Time",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 28},
        "targets": [
            {"expr": "mining_guardian_actions_approved_total{site='usa_188'}", "legendFormat": "Human Approved"},
            {"expr": "mining_guardian_actions_auto_overnight_total{site='usa_188'}", "legendFormat": "Auto Executed"},
            {"expr": "mining_guardian_actions_denied_total{site='usa_188'}", "legendFormat": "Denied"},
            {"expr": "mining_guardian_actions_expired_total{site='usa_188'}", "legendFormat": "Expired"},
        ],
        "datasource": {"type": "prometheus", "uid": "PBFA97CFB590B2093"},
        "fieldConfig": {
            "defaults": {"color": {"mode": "palette-classic"}, "custom": {"lineWidth": 2, "fillOpacity": 10}},
            "overrides": [
                {"matcher": {"id": "byName", "options": "Auto Executed"}, "properties": [{"id": "color", "value": {"fixedColor": "#10b981", "mode": "fixed"}}]},
                {"matcher": {"id": "byName", "options": "Denied"}, "properties": [{"id": "color", "value": {"fixedColor": "#ef4444", "mode": "fixed"}}]},
            ]
        },
    },
    {
        "id": 9,
        "type": "timeseries",
        "title": "🏥 Fleet Health — AI Impact",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 36},
        "targets": [
            {"expr": "mining_guardian_fleet_online{site='usa_188'}", "legendFormat": "Online"},
            {"expr": "mining_guardian_fleet_offline{site='usa_188'}", "legendFormat": "Offline"},
            {"expr": "mining_guardian_fleet_issues{site='usa_188'}", "legendFormat": "Flagged"},
        ],
        "datasource": {"type": "prometheus", "uid": "PBFA97CFB590B2093"},
        "fieldConfig": {
            "defaults": {"color": {"mode": "palette-classic"}, "custom": {"lineWidth": 2, "fillOpacity": 10}},
            "overrides": [
                {"matcher": {"id": "byName", "options": "Online"}, "properties": [{"id": "color", "value": {"fixedColor": "#10b981", "mode": "fixed"}}]},
                {"matcher": {"id": "byName", "options": "Offline"}, "properties": [{"id": "color", "value": {"fixedColor": "#ef4444", "mode": "fixed"}}]},
                {"matcher": {"id": "byName", "options": "Flagged"}, "properties": [{"id": "color", "value": {"fixedColor": "#f59e0b", "mode": "fixed"}}]},
            ]
        },
    },
    {
        "id": 10,
        "type": "gauge",
        "title": "🎯 AI Autonomy Rate",
        "gridPos": {"h": 8, "w": 6, "x": 12, "y": 36},
        "targets": [
            {"expr": "mining_guardian_actions_auto_overnight_total{site='usa_188'} / (mining_guardian_actions_approved_total{site='usa_188'} + mining_guardian_actions_auto_overnight_total{site='usa_188'}) * 100", "legendFormat": "Auto %"},
        ],
        "datasource": {"type": "prometheus", "uid": "PBFA97CFB590B2093"},
        "fieldConfig": {
            "defaults": {
                "min": 0, "max": 100, "unit": "percent",
                "thresholds": {"steps": [
                    {"color": "#ef4444", "value": None},
                    {"color": "#f59e0b", "value": 20},
                    {"color": "#10b981", "value": 50},
                ]},
            }
        },
    },
    {
        "id": 12,
        "type": "timeseries",
        "title": "🔄 Restarts & Tickets Over Time",
        "gridPos": {"h": 8, "w": 6, "x": 18, "y": 36},
        "targets": [
            {"expr": "mining_guardian_restarts_total{site='usa_188'}", "legendFormat": "Total Restarts"},
            {"expr": "mining_guardian_tickets_created_total{site='usa_188'}", "legendFormat": "Tickets Created"},
        ],
        "datasource": {"type": "prometheus", "uid": "PBFA97CFB590B2093"},
        "fieldConfig": {
            "defaults": {"color": {"mode": "palette-classic"}, "custom": {"lineWidth": 2, "fillOpacity": 10}},
        },
    },
]

dash["panels"] = new_panels
dash["version"] = dash.get("version", 1) + 1

payload = {
    "dashboard": dash,
    "message": "Rebuilt: AI Intelligence Center iframe + historical trend charts",
    "overwrite": True,
}

r = requests.post(f"{GRAFANA}/api/dashboards/db", json=payload, auth=AUTH)
print(f"Status: {r.status_code}")
print(r.json())
