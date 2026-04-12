import sqlite3, time

c = sqlite3.connect('/root/Mining-Gaurdian/guardian.db')

# Pick a healthy target that has NOT been touched recently
last_scan = c.execute('SELECT id FROM scans ORDER BY id DESC LIMIT 1').fetchone()[0]
print(f'Using scan #{last_scan}')

# Find healthy miners that are NOT in known_dead_boards and NOT recently restarted
candidates = list(c.execute('''
    SELECT mr.miner_id, mr.ip, mr.model, mr.hashrate_pct, mr.temp_chip
    FROM miner_readings mr
    WHERE mr.scan_id = ?
      AND mr.status = 'online'
      AND mr.hashrate_pct >= 95
      AND mr.hashrate_pct <= 110
      AND mr.miner_id NOT IN (SELECT miner_id FROM known_dead_boards)
      AND mr.miner_id NOT IN (
          SELECT DISTINCT miner_id FROM action_audit_log
          WHERE timestamp > datetime('now', '-3 hours')
      )
    ORDER BY mr.hashrate_pct DESC LIMIT 8
''', (last_scan,)))

print()
print('Top 8 candidates (healthy, not dead, not restarted in 3h):')
for r in candidates:
    print(f"  miner_id={r[0]:>6}  ip={r[1]:>15}  HR={r[2]}%  temp={r[3]}°C  ({r[2]})")

# Check current alert listener cooldowns to avoid conflict
print()
print('Current alert listener cooldowns:')
cd_rows = list(c.execute('SELECT miner_id, last_action, last_action_at FROM alert_listener_cooldown ORDER BY last_action_at DESC LIMIT 10'))
for r in cd_rows:
    print(f'  miner {r[0]}: action={r[1]} at={r[2]}')
