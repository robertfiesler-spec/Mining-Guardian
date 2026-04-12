import sqlite3
from collections import defaultdict

c = sqlite3.connect('/root/Mining-Gaurdian/guardian.db')

# Find all log entries with pre-restart or post-restart labels from last 12 hours
print('=' * 70)
print('RESTART PRE/POST LOG MATCHING — last 12 hours')
print('=' * 70)
print()

rows = list(c.execute("""
    SELECT miner_id, model, health_status, log_file, datetime(collected_at), LENGTH(content) as size
    FROM miner_logs
    WHERE collected_at > datetime('now', '-12 hours')
      AND (health_status LIKE '%restart%' OR health_status LIKE '%pdu%')
    ORDER BY miner_id, collected_at
"""))

print(f'Total restart-related log captures in last 12h: {len(rows)}')
print()

# Group by miner_id
by_miner = defaultdict(list)
for r in rows:
    by_miner[r[0]].append(r)

print(f'Unique miners with restart logs: {len(by_miner)}')
print()

# For each miner, check if they have BOTH pre and post for each restart
matched = 0
unmatched_pre_only = 0
unmatched_post_only = 0
both_count = 0

for miner_id, entries in sorted(by_miner.items()):
    pre_entries = [e for e in entries if 'pre' in e[2].lower()]
    post_entries = [e for e in entries if 'post' in e[2].lower()]
    
    has_pre = len(pre_entries) > 0
    has_post = len(post_entries) > 0
    
    status = ''
    if has_pre and has_post:
        both_count += 1
        status = '✓ MATCHED (pre AND post)'
    elif has_pre and not has_post:
        unmatched_pre_only += 1
        status = '✗ PRE ONLY (no post-restart logs captured)'
    elif has_post and not has_pre:
        unmatched_post_only += 1
        status = '✗ POST ONLY (no pre-restart logs)'
    
    print(f'Miner {miner_id} ({entries[0][1]}): {len(entries)} entries — {status}')
    for e in entries:
        label = e[2]
        when = e[4]
        size = e[5]
        fname = e[3]
        print(f'    [{when}] {label:35} {fname[:40]:40} {size} bytes')
    print()

print('=' * 70)
print(f'SUMMARY')
print(f'  Miners with BOTH pre and post:  {both_count}')
print(f'  Miners with PRE only:           {unmatched_pre_only}')
print(f'  Miners with POST only:          {unmatched_post_only}')
print('=' * 70)
