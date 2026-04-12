"""Final live test — runs against miner 53487 with NO max wait.

Pre-restart capture should land in the production DB within ~30 seconds.
Post-restart capture will land whenever the miner reaches fully-mining
state with settled hashrate (could be 5 min or 6 hours).

The parent process keeps running and prints heartbeats every 5 minutes,
watching for the post-restart entry to land.
"""

import os, sys, sqlite3, time

# CRITICAL: chdir before importing so guardian.db resolves correctly
os.chdir('/root/Mining-Gaurdian')
sys.path.insert(0, '/root/Mining-Gaurdian/core')
sys.path.insert(0, '/root/Mining-Gaurdian/api')
sys.path.insert(0, '/root/Mining-Gaurdian/ai')

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

from mining_guardian import GuardianConfig, MiningGuardian

cfg = GuardianConfig.from_file('/root/Mining-Gaurdian/config.json')
cfg.dry_run = False

TARGET = '53487'
TARGET_IP = '192.168.188.57'
TARGET_MODEL = 'Antminer S19JPro'

print('=' * 70)
print('LIVE TEST — NO MAX WAIT VERSION')
print(f'Target: {TARGET} at {TARGET_IP}')
print(f'PID: {os.getpid()}, cwd: {os.getcwd()}')
print('=' * 70)

c = sqlite3.connect('/root/Mining-Gaurdian/guardian.db', timeout=30)
pre_before = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=? AND health_status='pre-restart'", (TARGET,)).fetchone()[0]
post_before = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=? AND health_status='post-restart'", (TARGET,)).fetchone()[0]
print(f'BEFORE: pre={pre_before}  post={post_before}')

guardian = MiningGuardian(cfg)
issue = {'id': TARGET, 'ip': TARGET_IP, 'model': TARGET_MODEL, 'hashrate_pct': 102.1}

t0 = time.time()
print(f'\nCalling execute_restart at {time.strftime("%H:%M:%S")}')
guardian.execute_restart(issue)
print(f'execute_restart returned in {time.time()-t0:.1f}s')

pre_after = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=? AND health_status='pre-restart'", (TARGET,)).fetchone()[0]
print(f'\nPRE-RESTART check: {pre_after} entries (was {pre_before})')
if pre_after > pre_before:
    print('  ✓ pre-restart capture confirmed in production DB')
else:
    print('  ✗ pre-restart did NOT land — abort')
    sys.exit(1)

print('\n' + '=' * 70)
print('WAITING FOR POST-RESTART (background polling thread)')
print('Heartbeat every 5 min. Test will run until post-restart lands.')
print('=' * 70)

heartbeat = 0
while True:
    time.sleep(300)
    heartbeat += 1
    elapsed_min = (time.time() - t0) / 60
    post_now = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=? AND health_status='post-restart'", (TARGET,)).fetchone()[0]
    print(f'[heartbeat {heartbeat}, +{elapsed_min:.1f} min] post-restart entries: {post_now}')
    if post_now > post_before:
        rows = list(c.execute("SELECT log_file, LENGTH(content), datetime(collected_at) FROM miner_logs WHERE miner_id=? AND health_status='post-restart' ORDER BY collected_at DESC LIMIT 5", (TARGET,)))
        print('\nPOST-RESTART LANDED:')
        for r in rows:
            print(f'  {r[2]}  {r[0]:50} {r[1]:>10} bytes')
        print('\n✓ FULL PRE+POST PIPELINE PROVEN END-TO-END')
        break
