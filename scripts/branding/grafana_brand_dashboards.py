"""Add Mining Guardian wordmark header panel to all 6 dashboards.

For each dashboard:
  1. Read the JSON
  2. Push every existing panel down by 4 grid units (y += 4)
  3. Insert a new Text panel at y=0, x=0, w=24, h=4, with the wordmark HTML
  4. Bump 'version' so Grafana knows it changed
  5. Write back to the DB

Idempotent: if a panel with id=99999 already exists (our marker), skip the dashboard.
Backup: copies grafana.db to grafana.db.backup_<timestamp> before any writes.
"""
import sqlite3, json, shutil, time, sys

DB = "/var/lib/grafana/grafana.db"
MARKER_ID = 99999  # our header panel uses this so we can detect prior runs
LOGO_HEIGHT = 4    # grid units

# The HTML that goes in the Text panel.
# - transparent background so it blends with the dashboard theme
# - max-height keeps it from blowing up on large screens
# - object-fit:contain preserves the wordmark's aspect ratio
LOGO_HTML = '''<div style="display:flex; align-items:center; justify-content:center; height:100%; padding:0; margin:0;">
  <img src="/public/img/mining_guardian_wordmark.png"
       style="max-height:100%; max-width:100%; object-fit:contain;">
</div>'''

DASHBOARDS = [
    "bfi3t0krwak1sd",   # Main
    "efi3msabjg2kge",   # Fleet Overview
    "cfi3mt5a450xse",   # Per Miner
    "afi3p5mhapn9ce",   # Board Health
    "llm_learning_001", # AI & Learning
    "afi3q9w5ishz4f",   # Pool Stats
]

def make_header_panel():
    """Build a Grafana Text panel that renders the wordmark."""
    return {
        "id": MARKER_ID,
        "type": "text",
        "title": "",
        "transparent": True,
        "gridPos": {"x": 0, "y": 0, "w": 24, "h": LOGO_HEIGHT},
        "options": {
            "mode": "html",
            "content": LOGO_HTML,
        },
        "datasource": None,
    }

def patch_dashboard(uid, dry_run=False):
    """Read dashboard, inject header panel, write back."""
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT id, title, data, version FROM dashboard WHERE uid=?", (uid,)).fetchone()
    if not row:
        print(f"  [SKIP] uid={uid}: not found in DB")
        conn.close()
        return False
    db_id, title, data_json, version = row
    d = json.loads(data_json)
    panels = d.get("panels", [])

    # Idempotency: if the marker panel already exists, skip
    if any(p.get("id") == MARKER_ID for p in panels):
        print(f"  [SKIP] {title}: already has header panel (marker id={MARKER_ID})")
        conn.close()
        return False

    # Push every existing panel down
    for p in panels:
        gp = p.get("gridPos", {})
        gp["y"] = gp.get("y", 0) + LOGO_HEIGHT
        p["gridPos"] = gp

    # Insert header at the front
    panels.insert(0, make_header_panel())
    d["panels"] = panels

    # Bump version (Grafana uses this for optimistic concurrency)
    d["version"] = (d.get("version") or version) + 1
    new_data = json.dumps(d)

    if dry_run:
        print(f"  [DRY] {title}: would patch ({len(panels)} panels, version {version} -> {d['version']})")
        conn.close()
        return True

    # Write back to BOTH the data column AND the version column
    conn.execute(
        "UPDATE dashboard SET data=?, version=?, updated=datetime('now') WHERE id=?",
        (new_data, d["version"], db_id)
    )
    conn.commit()
    conn.close()
    print(f"  [OK]  {title}: patched ({len(panels)} panels, version -> {d['version']})")
    return True

def main():
    dry_run = "--dry-run" in sys.argv
    print(f"{'DRY RUN' if dry_run else 'LIVE RUN'}")
    print()

    if not dry_run:
        # Backup first
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup = f"{DB}.backup_{ts}"
        shutil.copy2(DB, backup)
        print(f"Backup created: {backup}")
        print()

    print("Patching dashboards...")
    patched = 0
    for uid in DASHBOARDS:
        if patch_dashboard(uid, dry_run=dry_run):
            patched += 1

    print()
    print(f"Result: {patched}/{len(DASHBOARDS)} dashboards patched")
    if not dry_run and patched > 0:
        print()
        print("NOTE: Grafana caches dashboards in memory. To see changes immediately:")
        print("  systemctl restart grafana-server")
        print("Or just hard-refresh the dashboard in your browser (Cmd+Shift+R).")

if __name__ == "__main__":
    main()
