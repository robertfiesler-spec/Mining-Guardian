#!/usr/bin/env python3
"""Check Grafana Board Health dashboard variable config.

Credentials read from GRAFANA_PASSWORD / GRAFANA_USER / GRAFANA_URL env vars.
See `scripts/_grafana_auth.py` for the contract.
"""
import json
import sys
import urllib.request

from _grafana_auth import grafana_basic_auth_header, grafana_url

GRAFANA = grafana_url()
AUTH_HEADER = grafana_basic_auth_header()


def _get(path):
    req = urllib.request.Request(f"{GRAFANA}{path}")
    req.add_header("Authorization", AUTH_HEADER)
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


url = f"{GRAFANA}/api/dashboards/uid/board-health"
try:
    d = _get("/api/dashboards/uid/board-health")
except Exception:
    # Try alternate UIDs
    d = None
    for uid in ["board-health", "board_health", "boardhealth"]:
        try:
            d = _get(f"/api/dashboards/uid/{uid}")
            print(f"Found with uid: {uid}")
            break
        except Exception:
            continue
    if d is None:
        # List all dashboards
        dashes = _get("/api/search?type=dash-db")
        print("All dashboards:")
        for dd in dashes:
            print(f"  uid={dd.get('uid')}  title={dd.get('title')}")
        sys.exit(0)

dash = d.get("dashboard", {})
print(f"Title: {dash.get('title')}")

# Check templating variables
templating = dash.get("templating", {}).get("list", [])
for t in templating:
    name = t.get("name")
    ttype = t.get("type")
    query = t.get("query", "")
    ds = t.get("datasource", {})
    print(f"\nVariable: {name}")
    print(f"  Type: {ttype}")
    print(f"  Datasource: {ds}")
    print(f"  Query: {query}")

# Check panels and their datasources
panels = dash.get("panels", [])
print(f"\n{len(panels)} panels")
for p in panels[:5]:
    title = p.get("title", "untitled")
    ds = p.get("datasource", {})
    targets = p.get("targets", [])
    print(f"\nPanel: {title}")
    print(f"  Datasource: {ds}")
    if targets:
        print(f"  Query: {targets[0].get('expr', targets[0].get('rawSql', ''))[:120]}")
