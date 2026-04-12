import sqlite3
from collections import Counter

c = sqlite3.connect('/root/Mining-Gaurdian/guardian.db')

print('=' * 70)
print('OVERNIGHT INVESTIGATION')
print('=' * 70)
print()

# Check the audit log for overnight actions
print('--- Action Audit Log: actions in last 12 hours ---')
rows = list(c.execute("""
    SELECT datetime(timestamp), miner_id, ip, action_taken, decision, approved_by, notes
    FROM action_audit_log
    WHERE timestamp > datetime('now', '-12 hours')
    ORDER BY timestamp
"""))
print(f'Total actions in audit log last 12h: {len(rows)}')
for r in rows[:30]:
    when, mid, ip, action, decision, who, notes = r
    print(f'  [{when}] {mid:6} {ip:18} {action:35} {decision:12} by={who or "?"}')
print()

# Check restart_outcomes table
print('--- Restart Outcomes in last 12 hours ---')
try:
    rows = list(c.execute("""
        SELECT datetime(timestamp), miner_id, outcome, hashrate_before, hashrate_after, notes
        FROM restart_outcomes
        WHERE timestamp > datetime('now', '-12 hours')
        ORDER BY timestamp
    """))
    print(f'Total restart outcomes last 12h: {len(rows)}')
    for r in rows[:30]:
        print(f'  {r}')
except Exception as e:
    print(f'  table error: {e}')
print()

# All distinct health_status labels in the last 12 hours
print('--- All log label types in last 12 hours ---')
rows = list(c.execute("""
    SELECT health_status, COUNT(*) FROM miner_logs
    WHERE collected_at > datetime('now', '-12 hours')
    GROUP BY health_status
    ORDER BY COUNT(*) DESC
"""))
for r in rows:
    print(f'  {r[0]:40} {r[1]} entries')
print()

# Total logs collected in last 12h
total = c.execute("SELECT COUNT(*) FROM miner_logs WHERE collected_at > datetime('now', '-12 hours')").fetchone()[0]
print(f'TOTAL logs collected last 12h: {total}')
print()

# Check overnight automation table if it exists
print('--- Tables in DB ---')
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print(f'  {len(tables)} tables: {", ".join(tables[:20])}')
if len(tables) > 20:
    print(f'  ... and {len(tables) - 20} more')
