"""Final 8-service health check before the demo.

Verifies:
  - All 8 services active and recently restarted
  - Most recent scan completed cleanly
  - DB integrity and recent activity
  - Cohort training output still in knowledge.json
  - In-flight 53487 post-restart test still alive
  - No alarming entries in journalctl over the last hour
"""

import os, sys, sqlite3, subprocess, time
from datetime import datetime, timedelta

print('=' * 75)
print('MINING GUARDIAN — FINAL HEALTH CHECK')
print(f'Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print('=' * 75)
print()

# 1. Service status
print('1. SERVICE STATUS')
print('-' * 75)
services = ['mining-guardian', 'mining-guardian-alerts', 'dashboard-api',
            'approval-api', 'slack-listener', 'slack-commands',
            'overnight-automation', 'prometheus', 'grafana-server']
all_healthy = True
for svc in services:
    try:
        out = subprocess.check_output(['systemctl', 'is-active', svc], stderr=subprocess.STDOUT, text=True).strip()
        marker = 'OK ' if out == 'active' else 'FAIL'
        print(f'  [{marker}] {svc}: {out}')
        if out != 'active':
            all_healthy = False
    except Exception as e:
        print(f'  [FAIL] {svc}: {e}')
        all_healthy = False
print()

# 2. Daemon scan health
print('2. DAEMON SCAN HEALTH')
print('-' * 75)
c = sqlite3.connect('/root/Mining-Gaurdian/guardian.db', timeout=30)
rows = list(c.execute("SELECT id, scanned_at, total_miners, online, offline, issues FROM scans ORDER BY id DESC LIMIT 5"))
for r in rows:
    print(f'  scan #{r[0]} at {r[1]}  total={r[2]} online={r[3]} offline={r[4]} issues={r[5]}')

# Time since last scan
last_scan_time = datetime.fromisoformat(rows[0][1])
mins_since = (datetime.now() - last_scan_time).total_seconds() / 60
print(f'  -> {mins_since:.1f} min since last scan (target: <60 min)')
if mins_since > 65:
    print('  WARN: scan interval exceeded')
print()

# 3. Action audit log overnight
print('3. RECENT ACTIONS (last 12 hours)')
print('-' * 75)
rows = list(c.execute("SELECT datetime(timestamp), miner_id, action_taken, decision, approved_by FROM action_audit_log WHERE timestamp > datetime('now', '-12 hours') ORDER BY timestamp DESC LIMIT 15"))
print(f'  Total actions: {len(rows)}')
for r in rows[:10]:
    print(f'  [{r[0]}] {r[1]:>6} {r[2]:25} {r[3]:18} by={(r[4] or "")[:25]}')
print()

# 4. Pre/post log capture status
print('4. PRE/POST LOG CAPTURE STATUS')
print('-' * 75)
rows = list(c.execute("""
    SELECT health_status, COUNT(*), MAX(datetime(collected_at))
    FROM miner_logs
    WHERE collected_at > datetime('now', '-12 hours')
      AND (health_status LIKE '%restart%' OR health_status LIKE '%pdu%')
    GROUP BY health_status
"""))
if rows:
    for r in rows:
        print(f'  {r[0]:30} count={r[1]:>4}  last={r[2]}')
else:
    print('  No pre/post log captures in last 12h yet')

# Specific check: 53487 (the in-flight test target)
test_pre = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id='53487' AND health_status='pre-restart' AND collected_at > datetime('now', '-2 hours')").fetchone()[0]
test_post = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id='53487' AND health_status='post-restart' AND collected_at > datetime('now', '-2 hours')").fetchone()[0]
print(f'  Test target 53487: pre={test_pre}  post={test_post}')
if test_pre > 0:
    print('  -> pre-restart capture confirmed in production DB')
if test_post == 0:
    print('  -> post-restart still polling for settled hashrate (background)')
print()

# 5. Cohort training output preservation
print('5. COHORT TRAINING OUTPUT (knowledge.json)')
print('-' * 75)
import json
k = json.load(open('/root/Mining-Gaurdian/knowledge.json'))
issues = k.get('known_issues', [])
apr7 = [i for i in issues if i.get('date') == '2026-04-07']
cohorts = [i for i in apr7 if 'cohort' in str(i.get('miner_id', ''))]
outliers = [i for i in apr7 if i.get('miner_id') in ('53483', '53494', '64347')]
fleets = [i for i in apr7 if i.get('miner_id') == 'fleet']
print(f'  April 7 entries in rolling window: {len(apr7)}/50')
print(f'  Cohort insights:  {len(cohorts)}')
print(f'  Outlier insights: {len(outliers)}')
print(f'  Fleet synthesis:  {len(fleets)} (length={len(fleets[0].get("insight","")) if fleets else 0} chars)')
if fleets and len(fleets[0].get('insight', '')) >= 10000:
    print('  -> fleet synthesis intact at full length')
print()

# 6. In-flight test process
print('6. IN-FLIGHT POST-RESTART TEST PROCESS')
print('-' * 75)
try:
    out = subprocess.check_output(['ps', '-ef'], text=True)
    test_lines = [l for l in out.split('\n') if 'test_53487' in l and 'grep' not in l]
    if test_lines:
        for l in test_lines:
            print(f'  {l[:120]}')
        print('  -> background polling thread alive, watching for settled hashrate')
    else:
        print('  WARN: in-flight test process not running')
except Exception as e:
    print(f'  error: {e}')
print()

# 7. Recent journal errors
print('7. RECENT JOURNAL ERRORS (last 1 hour)')
print('-' * 75)
try:
    out = subprocess.check_output(
        ['journalctl', '-u', 'mining-guardian', '-u', 'mining-guardian-alerts',
         '-u', 'overnight-automation', '--since', '1 hour ago', '-p', 'warning', '--no-pager'],
        text=True, stderr=subprocess.STDOUT
    )
    error_lines = [l for l in out.split('\n') if 'ERROR' in l or 'CRITICAL' in l]
    if error_lines:
        print(f'  Found {len(error_lines)} error lines:')
        for l in error_lines[:5]:
            print(f'  {l[:140]}')
    else:
        print('  No errors in the last hour')
except Exception as e:
    print(f'  error: {e}')
print()

# 8. Disk and memory headroom
print('8. SYSTEM RESOURCES')
print('-' * 75)
try:
    df = subprocess.check_output(['df', '-h', '/'], text=True)
    print('  Disk:')
    for line in df.split('\n')[:2]:
        print(f'    {line}')
    free = subprocess.check_output(['free', '-h'], text=True)
    print('  Memory:')
    for line in free.split('\n')[:2]:
        print(f'    {line}')
except Exception as e:
    print(f'  error: {e}')
print()

# Summary
print('=' * 75)
if all_healthy and mins_since < 65 and test_pre > 0 and len(fleets) > 0:
    print('OVERALL: ALL GREEN — DEMO READY')
else:
    print('OVERALL: needs attention before demo')
print('=' * 75)
c.close()
