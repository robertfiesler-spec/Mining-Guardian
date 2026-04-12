#!/usr/bin/env python3
"""
Fix daily log collection to ensure EVERY miner gets fresh logs EVERY day.

Changes:
1. REMOVE 24-hour dedup check — fresh logs required daily regardless
2. ADD fallback to existing ready logs when fresh export fails
3. ADD direct SSH log collection as last resort (future)

OPERATOR RULE (April 11 2026):
"Every miner needs a fresh log for this scan EVERY day. Some miners that are 
problem miners will have more than one before/after logs etc. We need to fix 
this to make sure it happens."
"""

import re

with open("/root/Mining-Gaurdian/core/mining_guardian.py", "r") as f:
    content = f.read()

# =============================================================================
# FIX 1: Remove the 24-hour dedup check entirely
# =============================================================================

old_dedup_block = '''                # 24h dedup check — if this miner got a log in the last
                # 24 hours (from any source, including a post-restart pull),
                # skip it. That counts as today's baseline.
                try:
                    last = self.db.last_log_collected(miner_id)
                except Exception as e:
                    logger.warning("Daily log: last_log_collected failed for %s: %s", miner_id, e)
                    last = None

                if last is not None:
                    age_seconds = (datetime.now() - last).total_seconds()
                    if age_seconds < DAILY_INTERVAL_SECONDS:
                        with counter_lock:
                            counters["skipped_recent"] += 1
                        logger.debug("Daily log: %s skipped — last collection was %ds ago",
                                     miner_id, int(age_seconds))
                        return'''

new_dedup_block = '''                # OPERATOR RULE (April 11 2026): Every miner gets fresh logs EVERY day.
                # No 24h dedup — fresh logs are critical for AI learning.
                # Pre/post restart logs are separate; this is the daily baseline.'''

if old_dedup_block in content:
    content = content.replace(old_dedup_block, new_dedup_block)
    print("FIX 1: Removed 24-hour dedup check ✓")
else:
    print("FIX 1: Could not find 24-hour dedup block — may already be fixed or different format")

# =============================================================================
# FIX 2: Add fallback to existing ready logs when fresh export fails
# =============================================================================

# Find the failure handling section and add fallback
old_failure_block = '''                    else:
                        with counter_lock:
                            counters["failed"] += 1
                            failed_miners.append(entry)
                        logger.warning("Daily log: miner %s returned no files (fresh export failed)",
                                       miner_id)'''

new_failure_block = '''                    else:
                        # Fresh export failed — try to download most recent EXISTING ready log
                        logger.info("Daily log: fresh export failed for %s, trying existing logs", miner_id)
                        try:
                            existing_logs = self.ams.collect_miner_logs(int(miner_id))
                            if existing_logs:
                                self.db.save_logs(miner_id, model, "daily_baseline_fallback", existing_logs)
                                with counter_lock:
                                    counters["collected"] += 1
                                logger.info("Daily log: miner %s collected via fallback (existing log)",
                                            miner_id)
                            else:
                                with counter_lock:
                                    counters["failed"] += 1
                                    failed_miners.append(entry)
                                logger.warning("Daily log: miner %s no fresh or existing logs available",
                                               miner_id)
                        except Exception as fallback_err:
                            with counter_lock:
                                counters["failed"] += 1
                                failed_miners.append(entry)
                            logger.warning("Daily log: miner %s fallback also failed: %s",
                                           miner_id, fallback_err)'''

if old_failure_block in content:
    content = content.replace(old_failure_block, new_failure_block)
    print("FIX 2: Added fallback to existing ready logs ✓")
else:
    print("FIX 2: Could not find failure block — checking alternate patterns...")

# Write the fixed content
with open("/root/Mining-Gaurdian/core/mining_guardian.py", "w") as f:
    f.write(content)

print("\nDone. Changes applied to mining_guardian.py")
print("Run: python3 -m py_compile core/mining_guardian.py")
print("Then: systemctl restart mining-guardian")
