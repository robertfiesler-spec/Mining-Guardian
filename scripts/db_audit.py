#!/usr/bin/env python3
import sqlite3
conn = sqlite3.connect("guardian.db")

# Check miner_readings for what we track per scan
print("=== MINER_READINGS SAMPLE (1 row) ===")
r = conn.execute("SELECT * FROM miner_readings ORDER BY scanned_at DESC LIMIT 1").fetchone()
cols = [d[0] for d in conn.execute("PRAGMA table_info(miner_readings)").fetchall()]
for i, col in enumerate(cols):
    print(f"  {col}: {r[i]}")

# Check if we have error_codes populated
print("\n=== ERROR CODES (sample) ===")
errors = conn.execute("""
    SELECT error_codes, COUNT(*) as cnt 
    FROM miner_readings 
    WHERE error_codes IS NOT NULL AND error_codes != '' AND error_codes != '[]'
    GROUP BY error_codes 
    ORDER BY cnt DESC 
    LIMIT 10
""").fetchall()
for e in errors:
    print(f"  {e[0]}: {e[1]} occurrences")

# Check firmware versions
print("\n=== FIRMWARE VERSIONS ===")
fw = conn.execute("""
    SELECT firmware_manufacturer, firmware_version, COUNT(DISTINCT miner_id) as miners
    FROM miner_readings 
    WHERE firmware_version IS NOT NULL
    GROUP BY firmware_manufacturer, firmware_version
    ORDER BY miners DESC
""").fetchall()
for f in fw:
    print(f"  {f[0]} {f[1]}: {f[2]} miners")

# Check uptime tracking
print("\n=== UPTIME VALUES (sample) ===")
uptime = conn.execute("""
    SELECT uptime, COUNT(*) as cnt 
    FROM miner_readings 
    WHERE uptime IS NOT NULL 
    GROUP BY uptime 
    ORDER BY cnt DESC 
    LIMIT 10
""").fetchall()
for u in uptime:
    print(f"  {u[0]}: {u[1]}")
