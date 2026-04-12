#!/usr/bin/env python3
"""Add post-restart and post-pdu-cycle log capture to execute_restart and execute_pdu_cycle.

For execute_restart: spawn a background thread that waits ~75 seconds (typical
restart-to-mining time for S19j Pro) then captures post-restart logs.

For execute_pdu_cycle: add the post-pdu-cycle capture inline after the existing
90-second wait, while the function is already paused for recovery verification.
"""

PATH = '/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py'

with open(PATH) as f:
    src = f.read()

# ============================================================
# PATCH 1: execute_restart — add post-restart capture in background thread
# ============================================================

old_execute_restart = '''    def execute_restart(self, issue: Dict[str, Any]) -> None:
        """
        Execute an approved firmware restart with pre-restart log collection.

        Flow:
          1. Attempt pre-restart log collection (non-blocking, 30s timeout)
          2. Restart miner via AMS
          3. Log the action to audit log

        Called when operator approves a RESTART action.
        """
        miner_id = issue["id"]
        ip       = issue["ip"]
        model    = issue["model"]

        logger.info("[%s] Executing approved firmware restart for %s @ %s", miner_id, model, ip)

        # Bug fix: respect dry_run — log intent but do not touch AMS
        if self.config.dry_run:
            logger.info("[%s] DRY RUN — firmware restart skipped (set dry_run: false to enable)", miner_id)
            return

        # Step 1 — collect pre-restart logs (skip silently if offline/unavailable)
        self._collect_logs_nonblocking(miner_id, model, "pre-restart")

        # Step 2 — restart via AMS
        try:
            self.ams.reboot_miner([miner_id])
            logger.info("[%s] Firmware restart sent via AMS", miner_id)
            self.db.record_restart(miner_id, ip, model, restart_type="MANUAL_APPROVED",
                                   hashrate_before=float(issue.get("hashrate_pct") or 0))
        except Exception as e:
            logger.error("[%s] Firmware restart failed: %s", miner_id, e)
'''

new_execute_restart = '''    def execute_restart(self, issue: Dict[str, Any]) -> None:
        """
        Execute an approved firmware restart with pre AND post log collection.

        Flow:
          1. Capture FRESH pre-restart logs (blocks up to 120s)
          2. Restart miner via AMS
          3. Spawn background thread that waits ~75s for the miner to come
             back online, then captures FRESH post-restart logs
          4. Record action to audit log

        Both pre and post logs are stored with distinct labels in miner_logs
        so the LLM can compare them when learning whether the restart actually
        helped. The background thread is fire-and-forget — failures there do
        not block this method or affect the main daemon loop.

        Called when operator approves a RESTART action OR overnight automation
        auto-approves it.
        """
        miner_id = issue["id"]
        ip       = issue["ip"]
        model    = issue["model"]

        logger.info("[%s] Executing approved firmware restart for %s @ %s", miner_id, model, ip)

        # Bug fix: respect dry_run — log intent but do not touch AMS
        if self.config.dry_run:
            logger.info("[%s] DRY RUN — firmware restart skipped (set dry_run: false to enable)", miner_id)
            return

        # Step 1 — collect FRESH pre-restart logs
        self._collect_logs_nonblocking(miner_id, model, "pre-restart")

        # Step 2 — restart via AMS
        try:
            self.ams.reboot_miner([miner_id])
            logger.info("[%s] Firmware restart sent via AMS", miner_id)
            self.db.record_restart(miner_id, ip, model, restart_type="MANUAL_APPROVED",
                                   hashrate_before=float(issue.get("hashrate_pct") or 0))
        except Exception as e:
            logger.error("[%s] Firmware restart failed: %s", miner_id, e)
            return

        # Step 3 — spawn background thread for post-restart log capture.
        # We wait 75 seconds for the miner to reboot and start mining, then
        # trigger a fresh log export that will contain the post-restart state.
        # This is fire-and-forget; failures are logged but do not raise.
        def _post_restart_capture():
            import time as _time
            try:
                _time.sleep(75)
                logger.info("[%s] Capturing post-restart logs (75s after reboot)", miner_id)
                self._collect_logs_nonblocking(miner_id, model, "post-restart")
            except Exception as e:
                logger.warning("[%s] Post-restart log capture thread failed: %s", miner_id, e)

        t = threading.Thread(target=_post_restart_capture, daemon=True,
                             name=f"post-restart-{miner_id}")
        t.start()
        logger.info("[%s] Post-restart log capture scheduled (background, 75s)", miner_id)
'''

if old_execute_restart not in src:
    print("ERROR: execute_restart not found exactly as expected")
    exit(1)

src = src.replace(old_execute_restart, new_execute_restart)
print("PATCHED execute_restart")

# ============================================================
# PATCH 2: execute_pdu_cycle — add post-pdu-cycle capture after recovery wait
# ============================================================

old_pdu_block = '''        # Step 1 — collect pre-restart logs (skip silently if offline/unavailable)
        self._collect_logs_nonblocking(miner_id, model, "pre-pdu-cycle")

        # Step 2 — power cycle via AMS
        import time
        try:
            self.ams.pdu_power_cycle(pdu_id, outlet)
            logger.info("[%s] PDU %s outlet %s — power cycled", miner_id, pdu_id, outlet)
        except Exception as e:
            logger.error("[%s] PDU cycle failed: %s", miner_id, e)
            return

        # Step 3 — wait 90 seconds then check if miner came back online
        logger.info("[%s] Waiting 90s for miner to recover after PDU cycle...", miner_id)
        time.sleep(90)

        # Re-verify miner status
        from miner_verify import verify_miner_online
        result = verify_miner_online(ip)'''

new_pdu_block = '''        # Step 1 — collect FRESH pre-pdu-cycle logs
        self._collect_logs_nonblocking(miner_id, model, "pre-pdu-cycle")

        # Step 2 — power cycle via AMS
        import time
        try:
            self.ams.pdu_power_cycle(pdu_id, outlet)
            logger.info("[%s] PDU %s outlet %s — power cycled", miner_id, pdu_id, outlet)
        except Exception as e:
            logger.error("[%s] PDU cycle failed: %s", miner_id, e)
            return

        # Step 3 — wait 90 seconds then check if miner came back online
        logger.info("[%s] Waiting 90s for miner to recover after PDU cycle...", miner_id)
        time.sleep(90)

        # Step 4 — collect FRESH post-pdu-cycle logs (now that miner has had
        # time to come back online and generate fresh log content)
        self._collect_logs_nonblocking(miner_id, model, "post-pdu-cycle")

        # Re-verify miner status
        from miner_verify import verify_miner_online
        result = verify_miner_online(ip)'''

if old_pdu_block not in src:
    print("ERROR: execute_pdu_cycle pre/post block not found exactly as expected")
    exit(1)

src = src.replace(old_pdu_block, new_pdu_block)
print("PATCHED execute_pdu_cycle")

with open(PATH, 'w') as f:
    f.write(src)

print("All patches applied")
