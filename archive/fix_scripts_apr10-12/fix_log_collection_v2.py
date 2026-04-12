#!/usr/bin/env python3
"""
Comprehensive fix for daily log collection.

OPERATOR REQUIREMENTS (April 11 2026):
1. Every miner needs fresh logs EVERY day
2. Old logs are a waste — don't fall back to them
3. If trigger fails, retry after current scan completes
4. Send Slack report of miners that consistently fail log exports
5. Track persistent failures so Bobby can fix them physically

CHANGES:
1. Remove fallback to old logs — only fresh exports count
2. Add persistent failure tracking (new DB table)
3. Add Slack report of problem miners after collection completes
4. Improve retry logic
"""

# ===========================================================================
# PART 1: Add new DB table for tracking log collection failures
# ===========================================================================

DB_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS log_collection_failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    miner_id TEXT NOT NULL,
    ip TEXT,
    model TEXT,
    failure_date TEXT NOT NULL,
    failure_reason TEXT,
    consecutive_failures INTEGER DEFAULT 1,
    last_successful_log TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_log_failures_miner ON log_collection_failures(miner_id);
CREATE INDEX IF NOT EXISTS idx_log_failures_date ON log_collection_failures(failure_date);
'''

print("PART 1: DB table SQL for log_collection_failures")
print(DB_TABLE_SQL)
print()

# ===========================================================================
# PART 2: New collect_logs implementation
# ===========================================================================

NEW_COLLECT_LOGS = '''
    def collect_logs(self, miners: List[Dict], issues: List[Dict]) -> None:
        """Daily baseline log collection for every online miner.

        OPERATOR RULES (April 11 2026):
        - Every online miner MUST get fresh logs EVERY day
        - No fallback to old logs — fresh exports only
        - Retry failed miners after full sweep completes
        - Report problem miners to Slack so they can be fixed physically
        - Track persistent failures in DB
        """
        if not self.config.collect_logs:
            logger.debug("Log collection disabled — set collect_logs: true in config to enable")
            return

        existing = getattr(self, '_daily_log_thread', None)
        if existing is not None and existing.is_alive():
            logger.info("Daily log collection: previous thread still running, skipping")
            return

        # Build eligible miner list
        eligible = []
        for miner in miners:
            status = miner.get("status", "unknown")
            if status == "offline":
                continue
            miner_status_val = miner.get("minerStatus")
            if miner_status_val is not None and miner_status_val != 0:
                continue

            model = miner.get("shortModel", miner.get("name", "unknown"))
            profile_s = miner.get("currentProfile", "")
            if "TH/s" in profile_s and miner.get("name") and miner.get("name") != model:
                model = miner["name"]

            eligible.append({
                "id": str(miner.get("id", "")),
                "ip": miner.get("ip", ""),
                "model": model,
            })

        if not eligible:
            logger.debug("Daily log collection: no eligible miners")
            return

        logger.info("Daily log collection: spawning thread for %d miners", len(eligible))

        def _worker(miner_list):
            import concurrent.futures
            WORKERS = 15

            try:
                self.ams._ensure_token()
            except Exception as e:
                logger.warning("Daily log: token refresh failed: %s", e)

            counter_lock = _threading.Lock()
            counters = {"collected": 0, "failed": 0}
            failed_miners = []
            today = datetime.now().strftime('%Y-%m-%d')

            def _collect_one(entry):
                miner_id = entry["id"]
                ip = entry["ip"]
                model = entry["model"]
                if not miner_id:
                    return

                try:
                    logger.info("Daily log: %s (%s) — pulling fresh export", miner_id, model)
                    log_files = self.ams.collect_fresh_miner_logs(
                        int(miner_id),
                        max_wait_seconds=600,
                    )
                    if log_files:
                        self.db.save_logs(miner_id, model, "daily_baseline", log_files)
                        with counter_lock:
                            counters["collected"] += 1
                        logger.info("Daily log: %s SUCCESS, %d files", miner_id, len(log_files))
                        # Clear any previous failures on success
                        self._clear_log_failure(miner_id)
                    else:
                        with counter_lock:
                            counters["failed"] += 1
                            failed_miners.append(entry)
                        logger.warning("Daily log: %s FAILED — no files returned", miner_id)
                except Exception as e:
                    with counter_lock:
                        counters["failed"] += 1
                        failed_miners.append(entry)
                    logger.warning("Daily log: %s ERROR: %s", miner_id, e)

            # Pass 1: Parallel sweep
            logger.info("Daily log PASS 1: %d-way parallel sweep, %d miners", WORKERS, len(miner_list))
            start = time.time()
            with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
                futures = [ex.submit(_collect_one, e) for e in miner_list]
                for f in concurrent.futures.as_completed(futures):
                    try:
                        f.result()
                    except Exception:
                        pass

            logger.info("Daily log PASS 1 complete: %d collected, %d failed, %.1fs",
                        counters["collected"], counters["failed"], time.time() - start)

            # Pass 2: Retry failed miners with longer timeout
            if failed_miners:
                logger.info("Daily log PASS 2: retrying %d failed miners (20min timeout)", len(failed_miners))
                retry_collected = 0
                still_failed = []

                def _retry_one(entry):
                    nonlocal retry_collected
                    miner_id = entry["id"]
                    model = entry["model"]
                    try:
                        log_files = self.ams.collect_fresh_miner_logs(int(miner_id), max_wait_seconds=1200)
                        if log_files:
                            self.db.save_logs(miner_id, model, "daily_baseline_retry", log_files)
                            with counter_lock:
                                retry_collected += 1
                            logger.info("Daily log RETRY: %s SUCCESS", miner_id)
                            self._clear_log_failure(miner_id)
                            return True
                    except Exception as e:
                        logger.warning("Daily log RETRY: %s failed: %s", miner_id, e)
                    still_failed.append(entry)
                    return False

                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                    futures = [ex.submit(_retry_one, e) for e in failed_miners]
                    for f in concurrent.futures.as_completed(futures):
                        try:
                            f.result()
                        except Exception:
                            pass

                counters["collected"] += retry_collected
                counters["failed"] = len(still_failed)
                logger.info("Daily log PASS 2 complete: %d recovered, %d still failed",
                            retry_collected, len(still_failed))

                # Record persistent failures and send Slack report
                if still_failed:
                    self._record_log_failures(still_failed, today)
                    self._send_log_failure_report(still_failed)

            total = time.time() - start
            logger.info("Daily log FINAL: %d collected, %d failed, %.1fs",
                        counters["collected"], counters["failed"], total)

        import threading as _threading
        t = _threading.Thread(target=_worker, args=(eligible,), daemon=True)
        t.start()
        self._daily_log_thread = t
'''

print("PART 2: New collect_logs method (simplified, no old log fallback)")
print("Length:", len(NEW_COLLECT_LOGS), "chars")
print()

# ===========================================================================
# PART 3: Helper methods for failure tracking and Slack reporting
# ===========================================================================

HELPER_METHODS = '''
    def _clear_log_failure(self, miner_id: str) -> None:
        """Clear failure record when log collection succeeds."""
        try:
            with self.db._connect() as conn:
                conn.execute("DELETE FROM log_collection_failures WHERE miner_id = ?", (miner_id,))
        except Exception:
            pass

    def _record_log_failures(self, failed: List[Dict], date: str) -> None:
        """Record persistent log collection failures."""
        try:
            with self.db._connect() as conn:
                for entry in failed:
                    miner_id = entry["id"]
                    ip = entry.get("ip", "")
                    model = entry.get("model", "")
                    
                    # Check if already recorded today
                    existing = conn.execute(
                        "SELECT consecutive_failures FROM log_collection_failures WHERE miner_id = ? AND failure_date = ?",
                        (miner_id, date)
                    ).fetchone()
                    
                    if existing:
                        continue  # Already recorded today
                    
                    # Get previous consecutive count
                    prev = conn.execute(
                        "SELECT consecutive_failures FROM log_collection_failures WHERE miner_id = ? ORDER BY failure_date DESC LIMIT 1",
                        (miner_id,)
                    ).fetchone()
                    
                    consecutive = (prev[0] + 1) if prev else 1
                    
                    # Get last successful log
                    last_success = conn.execute(
                        "SELECT MAX(collected_at) FROM miner_logs WHERE miner_id = ?",
                        (miner_id,)
                    ).fetchone()
                    last_log = last_success[0] if last_success and last_success[0] else "never"
                    
                    conn.execute("""
                        INSERT INTO log_collection_failures 
                        (miner_id, ip, model, failure_date, consecutive_failures, last_successful_log)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (miner_id, ip, model, date, consecutive, last_log))
        except Exception as e:
            logger.warning("Failed to record log failures: %s", e)

    def _send_log_failure_report(self, failed: List[Dict]) -> None:
        """Send Slack report of miners with failed log collection."""
        if not failed:
            return
        
        try:
            # Get consecutive failure counts
            with self.db._connect() as conn:
                problem_miners = []
                for entry in failed:
                    miner_id = entry["id"]
                    row = conn.execute(
                        "SELECT consecutive_failures, last_successful_log FROM log_collection_failures WHERE miner_id = ? ORDER BY failure_date DESC LIMIT 1",
                        (miner_id,)
                    ).fetchone()
                    
                    consecutive = row[0] if row else 1
                    last_log = row[1] if row else "never"
                    
                    problem_miners.append({
                        "id": miner_id,
                        "ip": entry.get("ip", "?"),
                        "model": entry.get("model", "?"),
                        "consecutive": consecutive,
                        "last_log": last_log[:10] if last_log != "never" else "never"
                    })
            
            # Sort by consecutive failures (worst first)
            problem_miners.sort(key=lambda x: x["consecutive"], reverse=True)
            
            # Build Slack message
            lines = ["⚠️ *LOG COLLECTION FAILURES*", ""]
            lines.append("These miners failed log export — may need physical inspection:")
            lines.append("")
            
            for m in problem_miners:
                emoji = "🔴" if m["consecutive"] >= 3 else "🟡"
                lines.append(f"{emoji} `{m['ip']}` ({m['model'][:15]}) — {m['consecutive']} consecutive failures, last log: {m['last_log']}")
            
            lines.append("")
            lines.append("_Check AMS for export errors, verify miner storage, or collect logs via SSH._")
            
            message = "\\n".join(lines)
            
            # Send to Slack
            self.slack.post_message(message, channel="#mining-guardian")
            logger.info("Sent log failure report to Slack: %d problem miners", len(problem_miners))
            
        except Exception as e:
            logger.warning("Failed to send log failure report: %s", e)
'''

print("PART 3: Helper methods for tracking/reporting")
print("Length:", len(HELPER_METHODS), "chars")
