#!/usr/bin/env python3
"""
Add Slack report for failed log collection miners.

This patch:
1. Tracks which miners still fail after retry pass
2. Sends Slack report with problem miners list
"""

with open("/root/Mining-Gaurdian/core/mining_guardian.py", "r") as f:
    content = f.read()

# =============================================================================
# PATCH 1: Track still-failed miners after retry
# =============================================================================

old_retry_block = '''                # Run retries with fewer workers to be gentler
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=5,  # Fewer workers for retry
                    thread_name_prefix="daily-log-retry",
                ) as executor:
                    futures = [executor.submit(_retry_one, entry) for entry in failed_miners]
                    for fut in concurrent.futures.as_completed(futures):
                        try:
                            fut.result()
                        except Exception as fe:
                            logger.warning("Daily log RETRY: worker raised: %s", fe)

                retry_elapsed = time.time() - retry_start
                logger.info(
                    "Daily log RETRY complete: %d recovered, %d still failed, %.1fs",
                    retry_counters["collected"], retry_counters["failed"], retry_elapsed,
                )
                # Update main counters
                counters["collected"] += retry_counters["collected"]
                counters["failed"] = retry_counters["failed"]  # Only count final failures'''

new_retry_block = '''                # Track miners that still fail after retry
                still_failed_miners = []
                
                def _retry_one_tracked(entry):
                    miner_id = entry["id"]
                    model = entry["model"]
                    ip = entry.get("ip", "")
                    try:
                        logger.info("Daily log RETRY: pulling miner %s (%s)", miner_id, model)
                        log_files = self.ams.collect_fresh_miner_logs(
                            int(miner_id),
                            max_wait_seconds=1200,
                        )
                        if log_files:
                            self.db.save_logs(miner_id, model, "daily_baseline_retry", log_files)
                            with counter_lock:
                                retry_counters["collected"] += 1
                            logger.info("Daily log RETRY: miner %s SUCCESS", miner_id)
                            return True
                        else:
                            with counter_lock:
                                retry_counters["failed"] += 1
                            still_failed_miners.append({"id": miner_id, "ip": ip, "model": model})
                            logger.warning("Daily log RETRY: miner %s still no files", miner_id)
                            return False
                    except Exception as e:
                        with counter_lock:
                            retry_counters["failed"] += 1
                        still_failed_miners.append({"id": miner_id, "ip": ip, "model": model})
                        logger.warning("Daily log RETRY: miner %s failed: %s", miner_id, e)
                        return False

                # Run retries with fewer workers
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=5,
                    thread_name_prefix="daily-log-retry",
                ) as executor:
                    futures = [executor.submit(_retry_one_tracked, entry) for entry in failed_miners]
                    for fut in concurrent.futures.as_completed(futures):
                        try:
                            fut.result()
                        except Exception as fe:
                            logger.warning("Daily log RETRY: worker raised: %s", fe)

                retry_elapsed = time.time() - retry_start
                logger.info(
                    "Daily log RETRY complete: %d recovered, %d still failed, %.1fs",
                    retry_counters["collected"], retry_counters["failed"], retry_elapsed,
                )
                
                # Send Slack report if there are persistent failures
                if still_failed_miners:
                    self._send_log_failure_slack_report(still_failed_miners)
                
                # Update main counters
                counters["collected"] += retry_counters["collected"]
                counters["failed"] = retry_counters["failed"]'''

if old_retry_block in content:
    content = content.replace(old_retry_block, new_retry_block)
    print("PATCH 1: Added still_failed_miners tracking ✓")
else:
    print("PATCH 1: Could not find retry block")
    if "still_failed_miners" in content:
        print("  (may already be patched)")

with open("/root/Mining-Gaurdian/core/mining_guardian.py", "w") as f:
    f.write(content)

print("Done. Now need to add _send_log_failure_slack_report method.")
