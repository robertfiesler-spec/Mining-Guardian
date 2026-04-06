#!/usr/bin/env python3
"""Fix the LLM hook indentation in mining_guardian.py."""
import os

path = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py"
with open(path) as f:
    c = f.read()

# The hook was inserted at the wrong indentation level
# It needs to be OUTSIDE the inner try/except but INSIDE the outer try
old = '''            except Exception:
                    logger.debug("Action diversity skipped (non-fatal)")

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
                pass  # LLM analysis is optional — never break the scan loop
            except Exception:
                logger.exception("Guardian loop error")'''

new = '''            except Exception:
                    logger.debug("Action diversity skipped (non-fatal)")

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
                    pass  # LLM analysis is optional — never break the scan loop

            except Exception:
                logger.exception("Guardian loop error")'''

if old in c:
    c = c.replace(old, new)
    with open(path, "w") as f:
        f.write(c)
    print("FIXED: LLM hook indentation corrected")
else:
    print("ERROR: Could not find exact block")
