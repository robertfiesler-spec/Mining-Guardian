#!/usr/bin/env python3
"""Check Grafana Board Health dashboard variable config."""
import json, urllib.request, base64

uid = "afi3p5mhapn9ce"
url = f"http://localhost:3000/api/dashboards/uid/{uid}"
req = urllib.request.Request(url)
creds = base64.b64encode(b"admin:002300rf").decode()
req.add_header("Authorization", f"Basic {creds}")

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
