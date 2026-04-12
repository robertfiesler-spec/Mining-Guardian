"""Live test of pre+post fresh log capture, with the parent process kept alive
indefinitely so the background polling thread can finish (it may take hours).

Key fixes vs the previous version:
  1. chdir into /root/Mining-Gaurdian BEFORE creating GuardianDB so the relative
     'guardian.db' path resolves to the production DB
  2. Keep the parent process alive in a sleep loop, watching for the post-restart
     entry to land. NEVER exit on its own — the background polling thread is
     daemon=True so it dies with the parent.
  3. Print a heartbeat every 60 seconds with current state
"""

import os
import sys
import sqlite3
import time

# CRITICAL: must chdir before importing/instantiating MiningGuardian so
# GuardianDB() with default db_path='guardian.db' resolves to the production DB
os.chdir('/root/Mining-Gaurdian')

sys.path.insert(0, '/root/Mining-Gaurdian/core')
sys.path.insert(0, '/root/Mining-Gaurdian/api')
sys.path.insert(0, '/root/Mining-Gaurdian/ai')

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

from mining_guardian import GuardianConfig, MiningGuardian

cfg = GuardianConfig.from_file('/root/Mining-Gaurdian/config.json')
cfg.dry_run = False

TARGET_MINER_ID = '53489'
TARGET_IP = '192.168.188.60'
TARGET_MODEL = 'Antminer S19JPro'

print('=' * 70)
print('LIVE PRE+POST RESTART TEST — FINAL VERSION')
print('  - Production DB (chdir fixed)')
print('  - No max wait (kept alive indefinitely for hours if needed)')
print('  - Settled hashrate detection')
print('=' * 70)
print(f'Target: miner {TARGET_MINER_ID} at {TARGET_IP} ({TARGET_MODEL})')
print(f'Working dir: {os.getcwd()}')
print(f'Test PID: {os.getpid()}')
print()

c = sqlite3.connect('/root/Mining-Gaurdian/guardian.db', timeout=30)

# State before
total_before = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=?", (TARGET_MINER_ID,)).fetchone()[0]
pre_before = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=? AND health_status='pre-restart'", (TARGET_MINER_ID,)).fetchone()[0]
post_before = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=? AND health_status='post-restart'", (TARGET_MINER_ID,)).fetchone()[0]
print(f'BEFORE: total={total_before}  pre-restart={pre_before}  post-restart={post_before}')
print()

# Build the guardian
guardian = MiningGuardian(cfg)

issue = {
    'id': TARGET_MINER_ID,
    'ip': TARGET_IP,
    'model': TARGET_MODEL,
    'hashrate_pct': 102.6,
}

print(f'Calling execute_restart() at {time.strftime("%H:%M:%S")}')
print('  This will: capture pre-restart logs, reboot via AMS, spawn background polling thread')
print()
t0 = time.time()
guardian.execute_restart(issue)
elapsed = time.time() - t0
print()
print(f'execute_restart returned in {elapsed:.1f}s — pre-restart capture done, post is in background')
print()

# Verify pre landed
pre_after = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=? AND health_status='pre-restart'", (TARGET_MINER_ID,)).fetchone()[0]
print(f'Pre-restart entries in DB: {pre_after} (delta {pre_after - pre_before:+})')
if pre_after > pre_before:
    print('  PASS — pre-restart capture confirmed in production DB')
else:
    print('  WARNING — pre-restart did not land in production DB')

# Now sleep forever, watching for post to land
print()
print('=' * 70)
print('NOW WATCHING FOR POST-RESTART CAPTURE TO LAND')
print('Heartbeat every 5 minutes. Process will run until killed.')
print('=' * 70)
print()

heartbeat_count = 0
while True:
    time.sleep(300)  # 5 minutes
    heartbeat_count += 1
    elapsed_min = (time.time() - t0) / 60
    post_now = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=? AND health_status='post-restart'", (TARGET_MINER_ID,)).fetchone()[0]
    print(f'[heartbeat {heartbeat_count}, +{elapsed_min:.1f} min] post-restart entries: {post_now} (was {post_before})')
    if post_now > post_before:
        # Got it! Show details
        rows = list(c.execute(
            "SELECT log_file, LENGTH(content), datetime(collected_at) FROM miner_logs "
            "WHERE miner_id=? AND health_status='post-restart' ORDER BY collected_at DESC LIMIT 5",
            (TARGET_MINER_ID,)
        ))
        print()
        print('POST-RESTART LANDED:')
        for r in rows:
            print(f'  {r[2]}  {r[0]:50} {r[1]:>10} bytes')
        print()
        print('SUCCESS — exiting test after capturing post-restart')
        break
