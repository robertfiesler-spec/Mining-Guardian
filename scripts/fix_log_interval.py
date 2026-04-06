#!/usr/bin/env python3
"""Fix the remaining log interval reference."""
path = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py"
with open(path) as f:
    c = f.read()

old = '''            # Collect every 6 hours per miner
            last = self.db.last_log_collected(miner_id)
            if last is not None and (now - last).total_seconds() < collection_interval_seconds:
                continue
            flagged = miner_id in {i["id"] for i in issues}
            health_status = "flagged" if flagged else "healthy"'''

new = '''            # Check health status first to determine collection interval
            flagged = miner_id in {i["id"] for i in issues}
            health_status = "flagged" if flagged else "healthy"
            interval = FLAGGED_LOG_INTERVAL if flagged else HEALTHY_LOG_INTERVAL
            last = self.db.last_log_collected(miner_id)
            if last is not None and (now - last).total_seconds() < interval:
                continue'''

if old in c:
    c = c.replace(old, new)
    with open(path, "w") as f:
        f.write(c)
    print("FIXED: Health-based log collection intervals")
else:
    print("ERROR: Pattern not found")
