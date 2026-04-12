"""Inspect one Grafana dashboard JSON to understand panel structure."""
import sqlite3, json

c = sqlite3.connect('/var/lib/grafana/grafana.db')
row = c.execute("SELECT uid, title, data FROM dashboard WHERE uid='bfi3t0krwak1sd'").fetchone()
uid, title, data = row
d = json.loads(data)
print(f"=== {title} (uid={uid}) ===")
print(f"Top-level keys: {list(d.keys())}")
print(f"Schema version: {d.get('schemaVersion')}")
print(f"Panel count: {len(d.get('panels', []))}")
print()
print("First 3 panels (id, type, title, gridPos):")
for p in d.get('panels', [])[:3]:
    print(f"  id={p.get('id')} type={p.get('type')!r} title={p.get('title')!r} gridPos={p.get('gridPos')}")
print()
print("All panel gridPos.y values (to find the top of dashboard):")
ys = [p.get('gridPos', {}).get('y', 0) for p in d.get('panels', [])]
print(f"  min y: {min(ys) if ys else None}, max y: {max(ys) if ys else None}")
print(f"  panels at y=0: {sum(1 for y in ys if y == 0)}")
