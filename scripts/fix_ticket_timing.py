#!/usr/bin/env python3
"""Fix: Don't auto-ticket miners that were restarted in the last 30 minutes."""

with open("/root/Mining-Gaurdian/core/mining_guardian.py") as f:
    c = f.read()

# Add a time check to the failure candidates query
old_query = '''            candidates_failures = conn.execute("""
                SELECT miner_id, ip, model,
                       COUNT(*) as failure_count, 'failure_outcomes' as reason
                FROM miner_restarts
                WHERE outcome = 'FAILURE'
                GROUP BY miner_id
                HAVING failure_count >= ?
            """, (FAILURE_THRESHOLD,)).fetchall()'''

new_query = '''            # Don't count failures from restarts in the last 30 minutes (miner may still be booting)
            candidates_failures = conn.execute("""
                SELECT miner_id, ip, model,
                       COUNT(*) as failure_count, 'failure_outcomes' as reason
                FROM miner_restarts
                WHERE outcome = 'FAILURE'
                  AND restarted_at < datetime('now', '-30 minutes')
                GROUP BY miner_id
                HAVING failure_count >= ?
            """, (FAILURE_THRESHOLD,)).fetchall()'''

if old_query in c:
    c = c.replace(old_query, new_query)
    with open("/root/Mining-Gaurdian/core/mining_guardian.py", "w") as f:
        f.write(c)
    print("FIXED: Auto-ticket now ignores failures from restarts < 30 min ago")
else:
    print("ERROR: Could not find ticket query to fix")
