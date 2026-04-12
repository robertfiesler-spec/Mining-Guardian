#!/usr/bin/env python3
"""Fix two bugs blocking the pre/post log capture pipeline.

Bug 1: _collect_logs_nonblocking uses signal.SIGALRM which only works on the
main thread. The new background-thread post-restart capture immediately fails
with "signal only works in main thread of the main interpreter".

Fix: detect whether we are on the main thread. If yes, use signal-based timeout
as before. If no, skip the signal entirely and rely on the underlying HTTP
timeouts and the collect_fresh_miner_logs internal max_wait_seconds for bounded
duration. The background thread is daemon=True so even a hang gets killed at
process exit.

Bug 2: save_logs deduplicates by (miner_id, log_file) only, ignoring
health_status. This means a log file already saved as 'healthy' earlier today
will silently fail to save again under 'pre-restart' or 'post-restart' labels.

Fix: include health_status in the dedup key so the same physical file can be
stored under multiple labels (it's the SAME file, but we want to capture the
fact that it was the state at this specific moment in the action lifecycle).
"""

PATH = '/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py'

with open(PATH) as f:
    src = f.read()

# ============================================================
# BUG 1 FIX: signal-in-thread in _collect_logs_nonblocking
# ============================================================

old_collect = '''    def _collect_logs_nonblocking(self, miner_id: str, model: str,
                                   label: str) -> dict:
        """
        Attempt log collection with a hard timeout.
        Returns log dict (possibly empty) — never raises, never hangs.
        If miner is offline or logs unavailable, returns {} immediately.
        """
        import signal

        def _timeout_handler(signum, frame):
            raise TimeoutError("log collection timed out")

        wants_fresh = label.startswith("pre-") or label.startswith("post-")
        # Fresh-log path needs more time than cached collection
        timeout = 120 if wants_fresh else self.LOG_COLLECT_TIMEOUT

        try:
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout)
            if wants_fresh:
                logger.info("[%s] Triggering FRESH log export for %s", miner_id, label)
                logs = self.ams.collect_fresh_miner_logs(int(miner_id), max_wait_seconds=90)
            else:
                logs = self.ams.collect_miner_logs(int(miner_id))
            signal.alarm(0)  # cancel alarm
            if logs:
                self.db.save_logs(miner_id, model, label, logs)
                logger.info("[%s] Logs collected (%s): %s files", miner_id, label, len(logs))
            else:
                logger.info("[%s] No logs available for %s — skipping", miner_id, label)
            return logs or {}
        except TimeoutError:
            signal.alarm(0)
            logger.warning("[%s] Log collection timed out after %ss (%s) — continuing",
                           miner_id, timeout, label)
            return {}
        except Exception as e:
            signal.alarm(0)
            logger.warning("[%s] Log collection failed (%s): %s — continuing", miner_id, label, e)
            return {}'''

new_collect = '''    def _collect_logs_nonblocking(self, miner_id: str, model: str,
                                   label: str) -> dict:
        """
        Attempt log collection with a hard timeout.
        Returns log dict (possibly empty) — never raises, never hangs.
        If miner is offline or logs unavailable, returns {} immediately.

        Bug fix (Apr 8 2026): signal.SIGALRM only works on the main thread of
        the main interpreter. When this function is called from a background
        thread (e.g. the post-restart capture spawned by execute_restart),
        signal.signal() raises ValueError immediately and we lose the entire
        capture. Fix: detect whether we are on the main thread and only use
        signal-based timeout in that case. Background threads rely on the
        underlying HTTP timeouts and collect_fresh_miner_logs's own
        max_wait_seconds parameter for bounded duration.
        """
        import signal
        import threading

        def _timeout_handler(signum, frame):
            raise TimeoutError("log collection timed out")

        wants_fresh = label.startswith("pre-") or label.startswith("post-")
        # Fresh-log path needs more time than cached collection
        timeout = 120 if wants_fresh else self.LOG_COLLECT_TIMEOUT

        on_main_thread = threading.current_thread() is threading.main_thread()
        signal_armed = False

        try:
            if on_main_thread:
                signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(timeout)
                signal_armed = True

            if wants_fresh:
                logger.info("[%s] Triggering FRESH log export for %s", miner_id, label)
                logs = self.ams.collect_fresh_miner_logs(int(miner_id), max_wait_seconds=90)
            else:
                logs = self.ams.collect_miner_logs(int(miner_id))

            if signal_armed:
                signal.alarm(0)  # cancel alarm

            if logs:
                self.db.save_logs(miner_id, model, label, logs)
                logger.info("[%s] Logs collected (%s): %s files", miner_id, label, len(logs))
            else:
                logger.info("[%s] No logs available for %s — skipping", miner_id, label)
            return logs or {}
        except TimeoutError:
            if signal_armed:
                signal.alarm(0)
            logger.warning("[%s] Log collection timed out after %ss (%s) — continuing",
                           miner_id, timeout, label)
            return {}
        except Exception as e:
            if signal_armed:
                signal.alarm(0)
            logger.warning("[%s] Log collection failed (%s): %s — continuing", miner_id, label, e)
            return {}'''

if old_collect not in src:
    print("ERROR: _collect_logs_nonblocking not found exactly as expected")
    # Show what's there for debugging
    import re
    m = re.search(r'def _collect_logs_nonblocking.*?(?=\n    def )', src, re.DOTALL)
    if m:
        print("Actual content found:")
        print(m.group()[:2000])
    exit(1)

src = src.replace(old_collect, new_collect)
print("BUG 1 FIXED: _collect_logs_nonblocking now thread-safe")

# ============================================================
# BUG 2 FIX: save_logs dedup ignoring health_status
# ============================================================

old_dedup = '''                # Dedup check — skip if this exact file was already stored
                existing = conn.execute(
                    "SELECT id FROM miner_logs WHERE miner_id=? AND log_file=?",
                    (miner_id, filename)
                ).fetchone()
                if existing:
                    logger.debug("[%s] Log already stored: %s — skipping", miner_id, filename)
                    continue'''

new_dedup = '''                # Dedup check — skip if this exact file was already stored
                # under the SAME health_status label. The same physical log file
                # may legitimately be stored under multiple labels (e.g. once as
                # 'healthy' from a routine scan and again as 'pre-restart' when
                # the operator approves a restart action) — those are distinct
                # observations of the system state and both have value.
                # Bug fix (Apr 8 2026): previously dedup was on (miner_id,
                # log_file) only, which silently dropped pre/post-restart saves
                # of files already captured under 'healthy'.
                existing = conn.execute(
                    "SELECT id FROM miner_logs WHERE miner_id=? AND log_file=? AND health_status=?",
                    (miner_id, filename, health_status)
                ).fetchone()
                if existing:
                    logger.debug("[%s] Log already stored under %s: %s — skipping",
                                 miner_id, health_status, filename)
                    continue'''

if old_dedup not in src:
    print("ERROR: save_logs dedup block not found exactly as expected")
    exit(1)

src = src.replace(old_dedup, new_dedup)
print("BUG 2 FIXED: save_logs dedup now includes health_status")

with open(PATH, 'w') as f:
    f.write(src)

print()
print("Both patches applied. Compile check next.")
