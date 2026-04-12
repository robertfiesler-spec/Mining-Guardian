import sqlite3
c = sqlite3.connect('/root/Mining-Gaurdian/guardian.db')

last_scan = c.execute('SELECT id FROM scans ORDER BY id DESC LIMIT 1').fetchone()[0]
print(f'Latest scan: #{last_scan}')

# Pick a fresh healthy target — NOT 53519, NOT recently restarted, NOT in cooldown
candidates = list(c.execute('''
    SELECT mr.miner_id, mr.ip, mr.model, mr.hashrate_pct, mr.temp_chip
    FROM miner_readings mr
    WHERE mr.scan_id = ?
      AND mr.status = 'online'
      AND mr.hashrate_pct >= 95
      AND mr.hashrate_pct <= 110
      AND mr.miner_id != '53519'
      AND mr.miner_id NOT IN (SELECT miner_id FROM known_dead_boards)
      AND mr.miner_id NOT IN (
          SELECT DISTINCT miner_id FROM action_audit_log
          WHERE timestamp > datetime('now', '-3 hours')
      )
      AND mr.miner_id NOT IN (
          SELECT DISTINCT miner_id FROM alert_listener_cooldown
      )
    ORDER BY mr.temp_chip DESC LIMIT 5
''', (last_scan,)))

print()
print('Top 5 candidates (clean, healthy, not recently touched):')
for r in candidates:
    print(f"  miner_id={r[0]:>6}  ip={r[1]:>15}  model={r[2]:<22}  HR={r[3]}%  temp={r[4]}°C")

if candidates:
    target = candidates[0]
    print()
    print(f"PICKING: miner {target[0]} at {target[1]}")
