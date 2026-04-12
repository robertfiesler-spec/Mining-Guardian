#!/usr/bin/env python3
"""Apply the same poll-until-mining pattern to execute_pdu_cycle.

The current code waits 90s then immediately tries to capture post-pdu-cycle
logs — same flaw as the original execute_restart. AMS won't produce a fresh
log until the miner is fully back to mining state.

Fix: same background-thread-with-polling approach, but with a longer max wait
because PDU cycles can take longer to recover than firmware restarts (the
miner has to fully cold-boot, not just reboot the firmware).
"""

PATH = '/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py'

with open(PATH) as f:
    src = f.read()

old_block = '''        # Step 3 — wait 90 seconds then check if miner came back online
        logger.info("[%s] Waiting 90s for miner to recover after PDU cycle...", miner_id)
        time.sleep(90)

        # Step 4 — collect FRESH post-pdu-cycle logs (now that miner has had
        # time to come back online and generate fresh log content)
        self._collect_logs_nonblocking(miner_id, model, "post-pdu-cycle")

        # Re-verify miner status
        from miner_verify import verify_miner_online
        result = verify_miner_online(ip)'''

new_block = '''        # Step 3 — wait 90 seconds for the miner to come back online enough
        # to do a basic TCP-level verification. The fresh post-pdu-cycle log
        # capture happens in the background once the miner is fully mining
        # (see step 5 below).
        logger.info("[%s] Waiting 90s for miner to recover after PDU cycle...", miner_id)
        time.sleep(90)

        # Step 4 — re-verify miner status (TCP-level check)
        from miner_verify import verify_miner_online
        result = verify_miner_online(ip)

        # Step 5 — spawn background thread for FRESH post-pdu-cycle log capture.
        # OPERATOR RULE (Apr 8 2026): AMS will not generate a new fresh log
        # export until the miner is FULLY UP AND MINING — not in starting,
        # not in autotuning state. PDU cycles take even longer than firmware
        # restarts because the miner cold-boots from power-off. Max wait:
        # 50 minutes (vs 40 for firmware restart).
        if result.get("actually_online"):
            def _post_pdu_capture():
                import time as _time
                try:
                    # Already waited 90s above; wait another 90s before first poll
                    _time.sleep(90)

                    max_wait_minutes = 50
                    poll_interval_seconds = 30
                    stable_confirm_polls = 2
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
                                consecutive_mining = 0
                            else:
                                status        = current.get("status", "?")
                                miner_status  = current.get("minerStatus", -1)
                                hashrate      = current.get("hashrate", 0) or 0
                                is_mining = (status == "online" and miner_status == 0 and hashrate > 0)
                                logger.info("[%s] Post-PDU wait poll %d: status=%s minerStatus=%s hashrate=%s mining=%s",
                                            miner_id, poll_num + 1, status, miner_status, hashrate, is_mining)
                                if is_mining:
                                    consecutive_mining += 1
                                    if consecutive_mining >= stable_confirm_polls:
                                        elapsed_minutes = ((poll_num + 1) * poll_interval_seconds + 180) / 60
                                        logger.info("[%s] Miner is fully mining after %.1f min — capturing post-pdu-cycle logs",
                                                    miner_id, elapsed_minutes)
                                        self._collect_logs_nonblocking(miner_id, model, "post-pdu-cycle")
                                        return
                                else:
                                    consecutive_mining = 0
                        except Exception as poll_e:
                            logger.warning("[%s] Post-PDU wait poll %d failed: %s", miner_id, poll_num + 1, poll_e)
                            consecutive_mining = 0

                        _time.sleep(poll_interval_seconds)

                    logger.warning("[%s] Post-PDU capture gave up after %d minutes", miner_id, max_wait_minutes)
                except Exception as e:
                    logger.warning("[%s] Post-PDU log capture thread failed: %s", miner_id, e)

            t = threading.Thread(target=_post_pdu_capture, daemon=True,
                                 name=f"post-pdu-{miner_id}")
            t.start()
            logger.info("[%s] Post-PDU log capture scheduled (background, polls until mining, max 50 min)",
                        miner_id)
        else:
            logger.info("[%s] Skipping post-PDU log capture — miner did not come back online", miner_id)'''

if old_block not in src:
    print("ERROR: post-pdu block not found")
    exit(1)

src = src.replace(old_block, new_block)

with open(PATH, 'w') as f:
    f.write(src)

print("PATCHED execute_pdu_cycle: post-pdu now uses poll-until-mining pattern")
