"""Live test of the new pre+post fresh log capture pipeline."""

import sys, sqlite3, time
sys.path.insert(0, '/root/Mining-Gaurdian/core')
sys.path.insert(0, '/root/Mining-Gaurdian/api')
sys.path.insert(0, '/root/Mining-Gaurdian/ai')

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

from mining_guardian import GuardianConfig, MiningGuardian

cfg = GuardianConfig.from_file('/root/Mining-Gaurdian/config.json')
cfg.dry_run = False  # Force the actual AMS call to go through

TARGET_MINER_ID = '53519'
TARGET_IP = '192.168.188.234'
TARGET_MODEL = 'Antminer S19JPro'

print('=' * 70)
print('LIVE PRE+POST RESTART TEST — NEW CODE PATH')
print('=' * 70)
print(f'Target: miner {TARGET_MINER_ID} at {TARGET_IP} ({TARGET_MODEL})')
print()

c = sqlite3.connect('/root/Mining-Gaurdian/guardian.db', timeout=30)
before_count = c.execute('SELECT COUNT(*) FROM miner_logs WHERE miner_id=?', (TARGET_MINER_ID,)).fetchone()[0]
print(f'Step 0: logs in DB BEFORE: {before_count}')

# Build a MiningGuardian instance
guardian = MiningGuardian(cfg)

# Issue dict in the shape execute_restart expects
issue = {
    'id': TARGET_MINER_ID,
    'ip': TARGET_IP,
    'model': TARGET_MODEL,
    'hashrate_pct': 102.9,
}

print()
print('Step 1+2+3: calling execute_restart() (new code path)')
print('  - Pre-restart fresh log capture (blocks until fresh log returns)')
print('  - AMS reboot')
print('  - Background thread for post-restart capture in 75s')
print()
t0 = time.time()
guardian.execute_restart(issue)
elapsed = time.time() - t0
print(f'execute_restart returned in {elapsed:.1f}s')

# Wait for the background post-restart thread to finish (75s sleep + ~30s capture)
print()
print('Step 4: waiting up to 180s for background post-restart thread to complete...')
for i in range(18):
    time.sleep(10)
    after_count = c.execute('SELECT COUNT(*) FROM miner_logs WHERE miner_id=?', (TARGET_MINER_ID,)).fetchone()[0]
    delta = after_count - before_count
    pre_count = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=? AND health_status='pre-restart'", (TARGET_MINER_ID,)).fetchone()[0]
    post_count = c.execute("SELECT COUNT(*) FROM miner_logs WHERE miner_id=? AND health_status='post-restart'", (TARGET_MINER_ID,)).fetchone()[0]
    print(f'  [{(i+1)*10}s] total logs: {after_count} (delta {delta:+}), pre-restart: {pre_count}, post-restart: {post_count}')
    if pre_count > 0 and post_count > 0:
        print('  Both pre and post landed!')
        break

print()
print('=' * 70)
print('FINAL CHECK')
print('=' * 70)
final_pre = list(c.execute("SELECT log_file, LENGTH(content), datetime(collected_at) FROM miner_logs WHERE miner_id=? AND health_status='pre-restart' ORDER BY collected_at DESC LIMIT 5", (TARGET_MINER_ID,)))
final_post = list(c.execute("SELECT log_file, LENGTH(content), datetime(collected_at) FROM miner_logs WHERE miner_id=? AND health_status='post-restart' ORDER BY collected_at DESC LIMIT 5", (TARGET_MINER_ID,)))

print('PRE-RESTART entries:')
for r in final_pre:
    print(f"  {r[2]}  {r[0][:50]:50} {r[1]:>10} bytes")

print()
print('POST-RESTART entries:')
for r in final_post:
    print(f"  {r[2]}  {r[0][:50]:50} {r[1]:>10} bytes")

passed = len(final_pre) > 0 and len(final_post) > 0
print()
print('=' * 70)
print('RESULT: ' + ('PASS — pre AND post logs captured' if passed else 'FAIL'))
print('=' * 70)
c.close()
