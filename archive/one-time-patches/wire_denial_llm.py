#!/usr/bin/env python3
"""Wire LLM denial processing into slack_approval_listener.py."""
import os

REPO = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian"
path = os.path.join(REPO, "api/slack_approval_listener.py")

with open(path) as f:
    c = f.read()

old = '                logger.info("Denial reason captured from %s: %s", user_name, reason[:80])'

new = '''                logger.info("Denial reason captured from %s: %s", user_name, reason[:80])
                # Send to local LLM for immediate rule extraction
                try:
                    import sys
                    from pathlib import Path
                    _ai = str(Path(__file__).resolve().parent.parent / "ai")
                    if _ai not in sys.path:
                        sys.path.insert(0, _ai)
                    from llm_scan_hook import run_denial_processing_llm
                    # Get miner IP from the pending approval
                    conn_d = get_db()
                    denied_miner = conn_d.execute(
                        "SELECT ip, action_type FROM pending_approvals WHERE thread_ts=? LIMIT 1",
                        (thread_ts,)
                    ).fetchone()
                    conn_d.close()
                    if denied_miner:
                        import threading
                        threading.Thread(
                            target=run_denial_processing_llm,
                            args=(denied_miner["ip"], denied_miner["action_type"], reason),
                            daemon=True
                        ).start()
                except Exception as ex:
                    logger.debug("LLM denial processing failed: %s", ex)'''

if old in c:
    c = c.replace(old, new)
    with open(path, "w") as f:
        f.write(c)
    print("HOOKED: Denial reason LLM processing wired into Slack listener")
else:
    print("ERROR: Could not find hook point")
