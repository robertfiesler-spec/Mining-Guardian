import sqlite3
c = sqlite3.connect('/root/Mining-Gaurdian/guardian.db')

# Find ALL miner_id values that contain 53519
print("Any rows with 53519 in miner_id (LIKE):")
rows = list(c.execute("SELECT miner_id, log_file, health_status, datetime(collected_at) FROM miner_logs WHERE miner_id LIKE '%53519%' ORDER BY collected_at DESC LIMIT 10"))
for r in rows:
    print(" ", r)

print()
print("Last 10 log entries in DB (any miner):")
rows = list(c.execute("SELECT miner_id, log_file, health_status, datetime(collected_at) FROM miner_logs ORDER BY collected_at DESC LIMIT 10"))
for r in rows:
    print(" ", r)

print()
print("Any rows with health_status containing 'pre-restart':")
rows = list(c.execute("SELECT miner_id, log_file, health_status, datetime(collected_at) FROM miner_logs WHERE health_status LIKE '%pre-restart%' OR health_status LIKE '%post-restart%' ORDER BY collected_at DESC LIMIT 10"))
for r in rows:
    print(" ", r)
