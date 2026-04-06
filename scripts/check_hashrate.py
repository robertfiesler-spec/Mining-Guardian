#!/usr/bin/env python3
"""Check if hashrate % is corrected in the latest scan."""
import sqlite3
c = sqlite3.connect("guardian.db", timeout=30)
c.row_factory = sqlite3.Row
scan = c.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
rows = c.execute(
    "SELECT ip, model, hashrate_pct, current_profile FROM miner_readings "
    "WHERE scan_id=? AND hashrate_pct > 105 ORDER BY hashrate_pct DESC LIMIT 10",
    (scan["id"],)
).fetchall()
if rows:
    print("MINERS ABOVE 105%:")
    for r in rows:
        print(f"  {r['ip']:20s} {r['hashrate_pct']:6.1f}%  profile={r['current_profile'] or 'EMPTY'}")
else:
    print("No miners above 105% — hashrate fix working!")

print("\nSAMPLE OF NORMAL MINERS:")
normal = c.execute(
    "SELECT ip, model, hashrate_pct, current_profile FROM miner_readings "
    "WHERE scan_id=? AND hashrate_pct BETWEEN 80 AND 105 ORDER BY hashrate_pct DESC LIMIT 5",
    (scan["id"],)
).fetchall()
for r in normal:
    print(f"  {r['ip']:20s} {r['hashrate_pct']:6.1f}%  profile={r['current_profile'] or 'EMPTY'}")
c.close()
