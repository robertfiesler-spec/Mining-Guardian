#!/usr/bin/env python3
"""Check a specific Grafana dashboard variable config by UID.

Credentials read from GRAFANA_PASSWORD / GRAFANA_USER / GRAFANA_URL env vars.
See `scripts/_grafana_auth.py` for the contract.
"""
import json
import urllib.request

from _grafana_auth import grafana_basic_auth_header, grafana_url

GRAFANA = grafana_url()
AUTH_HEADER = grafana_basic_auth_header()
UID = "afi3p5mhapn9ce"

req = urllib.request.Request(f"{GRAFANA}/api/dashboards/uid/{UID}")
req.add_header("Authorization", AUTH_HEADER)

resp = urllib.request.urlopen(req, timeout=10)
d = json.loads(resp.read())
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
    print(f"  Datasource: {json.dumps(ds)}")
    print(f"  Query: {query}")
    if t.get("options"):
        print(f"  Options: {[o.get('text','?') for o in t['options'][:5]]}")
    if t.get("current"):
        print(f"  Current: {t['current']}")

# Check panels datasources
panels = dash.get("panels", [])
print(f"\n{len(panels)} panels total")
for p in panels[:3]:
    title = p.get("title", "untitled")
    ds = p.get("datasource", {})
    targets = p.get("targets", [])
    print(f"\nPanel: {title}")
    print(f"  Datasource: {json.dumps(ds)}")
    if targets:
        for t in targets[:1]:
            q = t.get("expr", t.get("rawSql", t.get("query", "")))
            print(f"  Query: {str(q)[:200]}")
