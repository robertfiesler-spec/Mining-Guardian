"""Live test of the new pre+post fresh log capture pipeline.

Round 2: targets miner 53507 (fresh, untouched). Tests both bug fixes:
  1. signal-in-thread fix in _collect_logs_nonblocking
  2. dedup-by-health-status fix in save_logs
"""

import sys, sqlite3, time
sys.path.insert(0, '/root/Mining-Gaurdian/core')
sys.path.insert(0, '/root/Mining-Gaurdian/api')
sys.path.insert(0, '/root/Mining-Gaurdian/ai')

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

from mining_guardian import GuardianConfig, MiningGuardian

cfg = GuardianConfig.from_file('/root/Mining-Gaurdian/config.json')
cfg.dry_run = False

TARGET_MINER_ID = '53507'
TARGET_IP = '192.168.188.192'
TARGET_MODEL = 'Antminer S19JPro'

print('=' * 70)
print('LIVE PRE+POST RESTART TEST — ROUND 2 (after bug fixes)')
print('=' * 70)
print(f'Target: miner {TARGET_MINER_ID} at {TARGET_IP} ({TARGET_MODEL})')
print()

c = sqlite3.connect('/root/Mining-Gaurdian/guardian.db', timeout=30)

# Snapshot state BEFORE
total_before = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=?", (TARGET_MINER_ID,)).fetchone()[0]
pre_before = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=? AND health_status='pre-restart'", (TARGET_MINER_ID,)).fetchone()[0]
post_before = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=? AND health_status='post-restart'", (TARGET_MINER_ID,)).fetchone()[0]
print(f'BEFORE: total={total_before}  pre-restart={pre_before}  post-restart={post_before}')

# Build the guardian and execute restart
guardian = MiningGuardian(cfg)

issue = {
    'id': TARGET_MINER_ID,
    'ip': TARGET_IP,
    'model': TARGET_MODEL,
    'hashrate_pct': 96.4,
}

print()
print(f'Calling execute_restart() at {time.strftime("%H:%M:%S")}')
t0 = time.time()
guardian.execute_restart(issue)
elapsed = time.time() - t0
print(f'execute_restart returned in {elapsed:.1f}s')

# Poll for ~150 seconds for both pre and post to land
print()
print('Polling for pre and post log entries (max 150s)...')
deadline = time.time() + 150
last_state = None
while time.time() < deadline:
    time.sleep(10)
    pre_now = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=? AND health_status='pre-restart'", (TARGET_MINER_ID,)).fetchone()[0]
    post_now = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=? AND health_status='post-restart'", (TARGET_MINER_ID,)).fetchone()[0]
    state = (pre_now, post_now)
    elapsed_test = int(time.time() - t0)
    print(f'  [{elapsed_test:>3}s] pre-restart={pre_now}  post-restart={post_now}')
    if state != last_state:
        last_state = state
    if pre_now > 0 and post_now > 0:
        print('  Both pre AND post landed!')
        break

print()
print('=' * 70)
print('FINAL STATE')
print('=' * 70)

pre_rows = list(c.execute("SELECT log_file, LENGTH(content), datetime(collected_at) FROM miner_logs WHERE miner_id=? AND health_status='pre-restart' ORDER BY collected_at DESC LIMIT 5", (TARGET_MINER_ID,)))
post_rows = list(c.execute("SELECT log_file, LENGTH(content), datetime(collected_at) FROM miner_logs WHERE miner_id=? AND health_status='post-restart' ORDER BY collected_at DESC LIMIT 5", (TARGET_MINER_ID,)))

print(f'PRE-RESTART entries ({len(pre_rows)}):')
for r in pre_rows:
    fname = r[0][:55]
    print(f'  {r[2]}  {fname:55} {r[1]:>10} bytes')

print()
print(f'POST-RESTART entries ({len(post_rows)}):')
for r in post_rows:
    fname = r[0][:55]
    print(f'  {r[2]}  {fname:55} {r[1]:>10} bytes')

# Sanity check: pre and post should be DIFFERENT files (different timestamps)
if pre_rows and post_rows:
    pre_files = set(r[0] for r in pre_rows)
    post_files = set(r[0] for r in post_rows)
    overlap = pre_files & post_files
    if overlap:
        print(f'  WARNING: {len(overlap)} files appear in BOTH pre and post (same physical file, different label rows)')
    else:
        print(f'  Pre and post are entirely DIFFERENT physical files (different reboot snapshot)')

passed = len(pre_rows) > 0 and len(post_rows) > 0
print()
print('=' * 70)
print('RESULT: ' + ('✓ PASS — pre AND post logs captured' if passed else '✗ FAIL'))
print('=' * 70)
c.close()
