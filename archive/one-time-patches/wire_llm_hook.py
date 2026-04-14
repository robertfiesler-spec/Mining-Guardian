#!/usr/bin/env python3
"""
Wire local LLM analysis into the mining guardian scan loop.
This modifies mining_guardian.py to call the LLM after every scan.

The LLM runs in a background thread so it doesn't block the next scan.
Analysis gets posted to Slack and stored in knowledge.json.
"""
import os

REPO = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian"
path = os.path.join(REPO, "core/mining_guardian.py")

with open(path) as f:
    c = f.read()

# Find the end of the scan loop where we can hook in the LLM
# After the action diversity section, before the sleep
target = '            except Exception:\n                    logger.debug("Action diversity skipped (non-fatal)")'

if target in c:
    new_code = target + '''

            # ── Local LLM scan analysis (background thread) ──────────
            # Sends fleet data to Qwen 32B on RTX 4090 for real-time analysis.
            # Runs in background thread — never blocks the next scan.
            try:
                import threading
                from llm_scan_hook import run_post_scan_llm
                def _llm_analysis():
                    try:
                        run_post_scan_llm(scan_id, self.slack)
                    except Exception as ex:
                        logger.debug("LLM analysis thread error: %s", ex)
                threading.Thread(target=_llm_analysis, daemon=True).start()
            except Exception:
                pass  # LLM analysis is optional — never break the scan loop'''

    c = c.replace(target, new_code)
    with open(path, "w") as f:
        f.write(c)
    print("HOOKED: Local LLM analysis wired into scan loop (background thread)")
else:
    print("ERROR: Could not find hook point in scan loop")
    # Try alternate
    alt = 'logger.debug("Action diversity skipped (non-fatal)")'
    if alt in c:
        print("  Found alternate marker — need manual integration")
    else:
        print("  Neither marker found")
