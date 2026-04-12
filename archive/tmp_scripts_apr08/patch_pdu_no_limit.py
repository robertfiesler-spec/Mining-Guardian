#!/usr/bin/env python3
"""Apply no-limit poll-until-settled to execute_pdu_cycle (current state version)."""

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
        # to do basic TCP-level verification. The fresh post-pdu-cycle log
        # capture happens in the background once the miner is fully mining
        # with settled hashrate (see step 5).
        logger.info("[%s] Waiting 90s for miner to recover after PDU cycle...", miner_id)
        time.sleep(90)

        # Step 4 — re-verify miner status (TCP-level check)
        from miner_verify import verify_miner_online
        result = verify_miner_online(ip)

        # Step 5 — spawn background thread for FRESH post-pdu-cycle log capture.
        # OPERATOR RULE (Bobby, Apr 8 2026): NO maximum wait. Wait as long as
        # it takes for the miner to be fully mining with settled hashrate.
        # Bobby has seen this take 5-6 hours.
        if result.get("actually_online"):
            def _post_pdu_capture():
                import time as _time
                from collections import deque
                try:
                    _time.sleep(60)  # extra cushion before first poll

                    poll_interval_seconds = 60
                    history_size = 4
                    settled_tolerance_pct = 5.0
                    hashrate_history = deque(maxlen=history_size)
                    poll_num = 0
                    start_time = _time.time()

                    while True:  # NO maximum
                        poll_num += 1
                        try:
                            all_miners = self.ams.get_miners()
                            current = next(
                                (m for m in all_miners if str(m.get("id")) == str(miner_id)),
                                None
                            )
                            if current is None:
                                logger.info("[%s] Post-PDU poll %d: miner not in fleet list yet",
                                            miner_id, poll_num)
                                hashrate_history.clear()
                            else:
                                status        = current.get("status", "?")
                                miner_status  = current.get("minerStatus", -1)
                                hashrate      = current.get("hashrate", 0) or 0
                                is_mining = (status == "online" and miner_status == 0 and hashrate > 0)

                                if is_mining:
                                    hashrate_history.append(float(hashrate))
                                    if len(hashrate_history) == history_size:
                                        mean_hr = sum(hashrate_history) / len(hashrate_history)
                                        if mean_hr > 0:
                                            variance = sum((h - mean_hr) ** 2 for h in hashrate_history) / len(hashrate_history)
                                            stddev = variance ** 0.5
                                            stddev_pct = (stddev / mean_hr) * 100
                                            is_settled = stddev_pct < settled_tolerance_pct
                                            elapsed_min = (_time.time() - start_time) / 60
                                            logger.info("[%s] Post-PDU poll %d (%.1f min): mining=True hashrate=%.1f mean=%.1f stddev=%.2f%% settled=%s",
                                                        miner_id, poll_num, elapsed_min, hashrate, mean_hr, stddev_pct, is_settled)
                                            if is_settled:
                                                logger.info("[%s] Miner is fully mining with SETTLED hashrate after %.1f min — capturing post-pdu-cycle logs",
                                                            miner_id, elapsed_min)
                                                self._collect_logs_nonblocking(miner_id, model, "post-pdu-cycle")
                                                return
                                        else:
                                            hashrate_history.clear()
                                    else:
                                        elapsed_min = (_time.time() - start_time) / 60
                                        logger.info("[%s] Post-PDU poll %d (%.1f min): mining=True hashrate=%.1f (building history %d/%d)",
                                                    miner_id, poll_num, elapsed_min, hashrate, len(hashrate_history), history_size)
                                else:
                                    elapsed_min = (_time.time() - start_time) / 60
                                    logger.info("[%s] Post-PDU poll %d (%.1f min): status=%s minerStatus=%s hashrate=%s — not yet mining",
                                                miner_id, poll_num, elapsed_min, status, miner_status, hashrate)
                                    hashrate_history.clear()
                        except Exception as poll_e:
                            logger.warning("[%s] Post-PDU poll %d failed: %s", miner_id, poll_num, poll_e)
                            hashrate_history.clear()

                        _time.sleep(poll_interval_seconds)
                except Exception as e:
                    logger.warning("[%s] Post-PDU log capture thread failed: %s", miner_id, e)

            t = threading.Thread(target=_post_pdu_capture, daemon=True,
                                 name=f"post-pdu-{miner_id}")
            t.start()
            logger.info("[%s] Post-PDU log capture scheduled (background, polls until settled — NO max wait)",
                        miner_id)
        else:
            logger.info("[%s] Skipping post-PDU log capture — miner did not come back online", miner_id)'''

if old_block not in src:
    print("ERROR: post-pdu block not found")
    # Show what's there
    idx = src.find('Step 3 — wait 90 seconds')
    print(src[idx:idx+600])
    exit(1)

src = src.replace(old_block, new_block)

with open(PATH, 'w') as f:
    f.write(src)

print("PATCHED execute_pdu_cycle: no-limit poll-until-settled")
