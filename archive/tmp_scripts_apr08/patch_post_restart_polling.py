#!/usr/bin/env python3
"""Redesign the post-restart background thread to wait for the miner to be
FULLY UP AND MINING before triggering the fresh log export.

Per Bobby's operator note (Apr 8 2026 04:43 CDT):
  "AMS will not generate a new fresh log export until the miner is FULLY UP
   AND MINING — not in starting state, not in autotuning state. So it can
   be 5-35 minutes before it downloads."

The previous design used a fixed 75-second sleep before triggering the fresh
log export. This is wrong — at 75s the miner is still in starting/autotuning
state and AMS produces nothing. The new design polls AMS for the miner's
status every 30 seconds and only triggers the fresh log export once we see
minerStatus=0 (mining) AND hashrate > 0 for STABLE_CONFIRM consecutive polls.

If the miner doesn't reach the mining state within 40 minutes, we give up
and log a warning but don't crash.
"""

PATH = '/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py'

with open(PATH) as f:
    src = f.read()

old_block = '''        # Step 3 — spawn background thread for post-restart log capture.
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
        logger.info("[%s] Post-restart log capture scheduled (background, 75s)", miner_id)'''

new_block = '''        # Step 3 — spawn background thread for post-restart log capture.
        # OPERATOR RULE (Apr 8 2026): AMS will NOT generate a new fresh log
        # export until the miner is FULLY UP AND MINING — not in starting
        # state, not in autotuning state. This can take 5-35 minutes after
        # the reboot command. The thread polls AMS every 30s for the miner's
        # status and only triggers the fresh log export once we observe
        # minerStatus=0 AND hashrate > 0 on 2 consecutive polls. If the miner
        # does not reach mining state within 40 minutes, we give up cleanly.
        # Fire-and-forget; failures are logged but do not raise.
        def _post_restart_capture():
            import time as _time
            try:
                # Wait at least 60 seconds before the first status check —
                # the miner needs time to boot and reach the AMS at all.
                _time.sleep(60)

                max_wait_minutes = 40
                poll_interval_seconds = 30
                stable_confirm_polls = 2  # need 2 consecutive "mining" reads
                max_polls = (max_wait_minutes * 60) // poll_interval_seconds

                consecutive_mining = 0
                for poll_num in range(max_polls):
                    try:
                        all_miners = self.ams.get_miners()
                        current = next(
                            (m for m in all_miners if str(m.get("id")) == str(miner_id)),
                            None
                        )
                        if current is None:
                            logger.info("[%s] Post-restart wait poll %d: miner not in fleet list yet",
                                        miner_id, poll_num + 1)
                            consecutive_mining = 0
                        else:
                            status        = current.get("status", "?")
                            miner_status  = current.get("minerStatus", -1)
                            hashrate      = current.get("hashrate", 0) or 0
                            is_mining = (status == "online" and miner_status == 0 and hashrate > 0)
                            logger.info("[%s] Post-restart wait poll %d: status=%s minerStatus=%s hashrate=%s mining=%s",
                                        miner_id, poll_num + 1, status, miner_status, hashrate, is_mining)
                            if is_mining:
                                consecutive_mining += 1
                                if consecutive_mining >= stable_confirm_polls:
                                    elapsed_minutes = ((poll_num + 1) * poll_interval_seconds + 60) / 60
                                    logger.info("[%s] Miner is fully mining after %.1f min — capturing post-restart logs",
                                                miner_id, elapsed_minutes)
                                    self._collect_logs_nonblocking(miner_id, model, "post-restart")
                                    return
                            else:
                                consecutive_mining = 0
                    except Exception as poll_e:
                        logger.warning("[%s] Post-restart wait poll %d failed: %s", miner_id, poll_num + 1, poll_e)
                        consecutive_mining = 0

                    _time.sleep(poll_interval_seconds)

                logger.warning("[%s] Post-restart capture gave up after %d minutes — miner did not reach mining state",
                               miner_id, max_wait_minutes)
            except Exception as e:
                logger.warning("[%s] Post-restart log capture thread failed: %s", miner_id, e)

        t = threading.Thread(target=_post_restart_capture, daemon=True,
                             name=f"post-restart-{miner_id}")
        t.start()
        logger.info("[%s] Post-restart log capture scheduled (background, polls until miner is fully mining, max 40 min)",
                    miner_id)'''

if old_block not in src:
    print("ERROR: post-restart block not found exactly as expected")
    exit(1)

src = src.replace(old_block, new_block)

with open(PATH, 'w') as f:
    f.write(src)

print("PATCHED post-restart background thread:")
print("  - Waits at least 60s before first poll")
print("  - Polls AMS every 30s for miner status")
print("  - Triggers fresh log export only after 2 consecutive 'fully mining' reads")
print("  - Gives up cleanly after 40 min if miner never reaches mining state")
