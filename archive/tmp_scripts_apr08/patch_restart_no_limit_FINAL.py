#!/usr/bin/env python3
"""Final fix: replace the post-restart block (currently has 40-min cap) with
the no-limit poll-until-settled version. Match against the EXACT current
content of the file."""

PATH = '/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py'

with open(PATH) as f:
    src = f.read()

# Match the actual 40-min version that's currently in the file
old = '''        # Step 3 — spawn background thread for post-restart log capture.
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

new = '''        # Step 3 — spawn background thread for post-restart log capture.
        # OPERATOR RULE (Bobby, Apr 8 2026): NO maximum wait time. Bobby has
        # seen miners take 5-6 HOURS to reach fully-mining-with-settled-hashrate
        # state. The number one goal is capturing the log AT THE RIGHT MOMENT
        # (not capturing it quickly). Settled hashrate detection: track the
        # last 4 hashrate readings; the miner is "settled" when the standard
        # deviation of those 4 readings is within 5% of their mean.
        # Fire-and-forget daemon thread; failures are logged but do not raise.
        # If the parent process exits before the capture completes, the daemon
        # thread is killed and we accept the post-capture gap for that one
        # action (the action itself is already in the audit log).
        def _post_restart_capture():
            import time as _time
            from collections import deque
            try:
                # Wait 60s before first poll — even reaching AMS takes time
                _time.sleep(60)

                poll_interval_seconds = 60
                history_size = 4
                settled_tolerance_pct = 5.0
                hashrate_history = deque(maxlen=history_size)
                poll_num = 0
                start_time = _time.time()

                while True:  # NO maximum — wait as long as it takes
                    poll_num += 1
                    try:
                        all_miners = self.ams.get_miners()
                        current = next(
                            (m for m in all_miners if str(m.get("id")) == str(miner_id)),
                            None
                        )
                        if current is None:
                            logger.info("[%s] Post-restart poll %d: miner not in fleet list yet",
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
                                        logger.info("[%s] Post-restart poll %d (%.1f min): mining=True hashrate=%.1f mean=%.1f stddev=%.2f%% settled=%s",
                                                    miner_id, poll_num, elapsed_min, hashrate, mean_hr, stddev_pct, is_settled)
                                        if is_settled:
                                            logger.info("[%s] Miner is fully mining with SETTLED hashrate after %.1f min — capturing post-restart logs",
                                                        miner_id, elapsed_min)
                                            self._collect_logs_nonblocking(miner_id, model, "post-restart")
                                            return
                                    else:
                                        hashrate_history.clear()
                                else:
                                    elapsed_min = (_time.time() - start_time) / 60
                                    logger.info("[%s] Post-restart poll %d (%.1f min): mining=True hashrate=%.1f (building history %d/%d)",
                                                miner_id, poll_num, elapsed_min, hashrate, len(hashrate_history), history_size)
                            else:
                                elapsed_min = (_time.time() - start_time) / 60
                                logger.info("[%s] Post-restart poll %d (%.1f min): status=%s minerStatus=%s hashrate=%s — not yet mining",
                                            miner_id, poll_num, elapsed_min, status, miner_status, hashrate)
                                hashrate_history.clear()
                    except Exception as poll_e:
                        logger.warning("[%s] Post-restart poll %d failed: %s", miner_id, poll_num, poll_e)
                        hashrate_history.clear()

                    _time.sleep(poll_interval_seconds)
            except Exception as e:
                logger.warning("[%s] Post-restart log capture thread failed: %s", miner_id, e)

        t = threading.Thread(target=_post_restart_capture, daemon=True,
                             name=f"post-restart-{miner_id}")
        t.start()
        logger.info("[%s] Post-restart log capture scheduled (background, polls until hashrate is fully settled — NO max wait)",
                    miner_id)'''

if old not in src:
    print("ERROR: post-restart block not found exactly as expected")
    exit(1)

src = src.replace(old, new)
with open(PATH, 'w') as f:
    f.write(src)
print("PATCHED execute_restart: NO max wait, settled hashrate detection")
