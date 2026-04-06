#!/usr/bin/env python3
"""
Log collection strategy overhaul:

1. Healthy miners: 1 log every 24 hours (was every 6 hours for all)
2. Problem miners: collect pre/post restart logs (already works) + more frequent
3. Don't collect logs until minerStatus = 0 (mining) — no logs during boot/autotune
4. Training: send ALL logs from last 7 days to Claude, not just last 10
5. Local LLM should also compare pre/post logs in real-time (OpenClaw integration note)
"""
import os

REPO = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian"

# ═══════════════════════════════════════════════════════════
# FIX 1: Log collection intervals based on miner health
# ═══════════════════════════════════════════════════════════
mg_path = os.path.join(REPO, "core/mining_guardian.py")
with open(mg_path) as f:
    c = f.read()

old_log_collection = '''        collection_interval_seconds = 6 * 3600  # 6 hours'''

new_log_collection = '''        # Log collection intervals based on miner health:
        # Healthy miners: 1 log per 24 hours (baseline drift detection)
        # Flagged miners: 1 log per 6 hours (more frequent monitoring)
        # Pre/post restart logs are collected separately in execute_board_restart()
        HEALTHY_LOG_INTERVAL = 24 * 3600  # 24 hours
        FLAGGED_LOG_INTERVAL = 6 * 3600   # 6 hours'''

if old_log_collection in c:
    c = c.replace(old_log_collection, new_log_collection)
    print("FIX 1a: Log interval constants updated")
else:
    print("FIX 1a: Could not find old interval")

# Update the interval check to use health-based intervals
old_interval_check = '''            if last is not None and (now - last).total_seconds() < collection_interval_seconds:
                continue
            flagged = miner_id in {i["id"] for i in issues}
            health_status = "flagged" if flagged else "healthy"'''

new_interval_check = '''            flagged = miner_id in {i["id"] for i in issues}
            health_status = "flagged" if flagged else "healthy"
            interval = FLAGGED_LOG_INTERVAL if flagged else HEALTHY_LOG_INTERVAL
            if last is not None and (now - last).total_seconds() < interval:
                continue'''

if old_interval_check in c:
    c = c.replace(old_interval_check, new_interval_check)
    print("FIX 1b: Health-based interval check updated")
else:
    print("FIX 1b: Could not find old interval check")

# Add minerStatus check before log collection — don't download during boot/autotune
old_log_skip = '''            # Skip offline miners — no connection means no logs available
            if status == "offline":
                continue'''

new_log_skip = '''            # Skip offline miners — no connection means no logs available
            if status == "offline":
                continue
            # Skip miners that aren't fully mining yet — don't download during
            # initializing (6), starting, or auto-tuning (3). Wait for mining (0).
            miner_status_val = miner.get("minerStatus")
            if miner_status_val is not None and miner_status_val != 0:
                logger.debug("[%s] minerStatus=%s — not mining yet, skipping log collection", miner_id, miner_status_val)
                continue'''

if old_log_skip in c:
    c = c.replace(old_log_skip, new_log_skip)
    print("FIX 1c: minerStatus check added to log collection")
else:
    print("FIX 1c: Could not find offline skip block")

with open(mg_path, "w") as f:
    f.write(c)

# ═══════════════════════════════════════════════════════════
# FIX 2: Training sends ALL logs from last 7 days, not just 10
# ═══════════════════════════════════════════════════════════
train_path = os.path.join(REPO, "ai/train_comprehensive.py")
with open(train_path) as f:
    tc = f.read()

old_log_query = '''    logs = conn.execute("""
        SELECT collected_at, log_file, health_status, content
        FROM miner_logs WHERE miner_id = ?
        ORDER BY collected_at DESC LIMIT 10
    """, (miner_id,)).fetchall()'''

new_log_query = '''    # All logs from last 7 days — at least 1/day for healthy miners,
    # plus all pre/post restart logs for problem miners.
    # Claude needs the full picture to compare before/after restarts.
    logs = conn.execute("""
        SELECT collected_at, log_file, health_status, content
        FROM miner_logs WHERE miner_id = ?
          AND collected_at >= datetime('now', '-7 days')
        ORDER BY collected_at DESC
    """, (miner_id,)).fetchall()'''

if old_log_query in tc:
    tc = tc.replace(old_log_query, new_log_query)
    with open(train_path, "w") as f:
        f.write(tc)
    print("FIX 2: Training now sends ALL logs from last 7 days (was LIMIT 10)")
else:
    print("FIX 2: Could not find old log query in training")

print("\nDone — compile check next")
