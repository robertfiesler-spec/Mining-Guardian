#!/usr/bin/env python3
"""
Remove fallback to old logs — only fresh exports matter.
"""

with open("/root/Mining-Gaurdian/core/mining_guardian.py", "r") as f:
    content = f.read()

old_fallback_block = '''                    else:
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

new_no_fallback = '''                    else:
                        # Fresh export failed — mark for retry pass
                        # OPERATOR RULE: No fallback to old logs — fresh exports only
                        with counter_lock:
                            counters["failed"] += 1
                            failed_miners.append(entry)
                        logger.warning("Daily log: miner %s fresh export failed — will retry", miner_id)'''

if old_fallback_block in content:
    content = content.replace(old_fallback_block, new_no_fallback)
    print("Removed fallback to old logs ✓")
else:
    print("Could not find fallback block")

with open("/root/Mining-Gaurdian/core/mining_guardian.py", "w") as f:
    f.write(content)

print("Done.")
