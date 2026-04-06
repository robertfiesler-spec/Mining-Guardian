#!/usr/bin/env python3
"""Check Grafana Board Health dashboard variable config."""
import json, sys, urllib.request

url = "http://localhost:3000/api/dashboards/uid/board-health"
req = urllib.request.Request(url)
import base64
creds = base64.b64encode(b"admin:002300rf").decode()
req.add_header("Authorization", f"Basic {creds}")

try:
    resp = urllib.request.urlopen(req, timeout=10)
    d = json.loads(resp.read())
except Exception as e:
    # Try alternate UIDs
    for uid in ["board-health", "board_health", "boardhealth"]:
        try:
            req2 = urllib.request.Request(f"http://localhost:3000/api/dashboards/uid/{uid}")
            req2.add_header("Authorization", f"Basic {creds}")
            resp = urllib.request.urlopen(req2, timeout=10)
            d = json.loads(resp.read())
            print(f"Found with uid: {uid}")
            break
        except:
            continue
    else:
        # List all dashboards
        req3 = urllib.request.Request("http://localhost:3000/api/search?type=dash-db")
        req3.add_header("Authorization", f"Basic {creds}")
        resp = urllib.request.urlopen(req3, timeout=10)
        dashes = json.loads(resp.read())
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
