#!/usr/bin/env python3
"""
Two fixes for Wednesday training:

1. Replace 20-min timer grace period with AMS minerStatus check
   minerStatus 0 = mining (stable), anything else = not ready
   This adapts to each miner's actual boot time instead of fixed 20 min

2. Add structured pre/post restart log comparison to training prompts
   Claude gets explicit before/after sections for each restart
"""
import os, re

REPO = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian"

# ═══════════════════════════════════════════════════════════
# FIX 1: Replace uptime timer with minerStatus check
# ═══════════════════════════════════════════════════════════
mg_path = os.path.join(REPO, "core/mining_guardian.py")
with open(mg_path) as f:
    c = f.read()

old_grace = '''        # ── Post-restart grace period (20 minutes) ───────────────────
        # Skip action recommendations for recently restarted miners.
        # Check 1: MG-tracked restarts via elevated_until
        # Check 2: AMS uptime < 20 min (catches manual restarts)
        if self.db.is_elevated_monitoring(miner_id):
            logger.debug("[%s] Post-restart grace — elevated monitoring active", miner_id)
            return None
        uptime_str = str(miner.get("uptime", "") or "")
        if uptime_str and status == "online":
            try:
                import re as _re
                uptime_secs = 0
                if uptime_str.isdigit():
                    uptime_secs = int(uptime_str)
                elif "h" in uptime_str or "m" in uptime_str:
                    _h = _re.search(r"(\\\\d+)h", uptime_str)
                    _m = _re.search(r"(\\\\d+)m", uptime_str)
                    if _h: uptime_secs += int(_h.group(1)) * 3600
                    if _m: uptime_secs += int(_m.group(1)) * 60
                if 0 < uptime_secs < 1200:  # < 20 minutes
                    logger.debug("[%s] Uptime %s < 20min — skipping actions", miner_id, uptime_str)
                    return None
            except Exception:
                pass'''

# Try to find the actual text - might have slightly different escaping
if old_grace not in c:
    # Find the grace period block by marker
    marker = "Post-restart grace period"
    idx = c.find(marker)
    if idx > 0:
        # Find the start of the comment line
        line_start = c.rfind("\n", 0, idx) + 1
        # Find the end - look for the next non-grace-period code
        # The block ends at "temp_chip_raw" or the next main variable assignment
        end_marker = "temp_chip_raw"
        end_idx = c.find(end_marker, idx)
        if end_idx > 0:
            # Back up to the line before temp_chip_raw
            end_line = c.rfind("\n", 0, end_idx)
            old_block = c[line_start:end_line + 1]
            
            new_block = '''        # ── Post-restart grace period ─────────────────────────────────
        # Skip action recommendations for miners that aren't fully stable.
        # Check 1: MG-tracked restarts via elevated_until (3hr window)
        # Check 2: AMS minerStatus != 0 (initializing/starting/auto-tuning)
        #   minerStatus 0 = mining (stable, ready for actions)
        #   minerStatus 3 = auto-tuning (still calibrating, don't touch)
        #   minerStatus 6 = initializing (just booted, too early)
        #   Any non-zero = not ready for actions
        # Check 3: Uptime < 20 min as fallback if minerStatus unavailable
        if self.db.is_elevated_monitoring(miner_id):
            logger.debug("[%s] Post-restart grace — elevated monitoring active", miner_id)
            return None
        miner_status = miner.get("minerStatus")
        if miner_status is not None and miner_status != 0 and status == "online":
            logger.info("[%s] minerStatus=%s (not mining) — skipping actions", miner_id, miner_status)
            return None
        uptime_str = str(miner.get("uptime", "") or "")
        if uptime_str and status == "online":
            try:
                import re as _re
                uptime_secs = 0
                if uptime_str.isdigit():
                    uptime_secs = int(uptime_str)
                if 0 < uptime_secs < 1200:  # < 20 minutes fallback
                    logger.debug("[%s] Uptime %ss < 20min — skipping actions", miner_id, uptime_secs)
                    return None
            except Exception:
                pass
'''
            c = c[:line_start] + new_block + c[end_line + 1:]
            with open(mg_path, "w") as f:
                f.write(c)
            print("FIX 1: Replaced grace period with minerStatus check + uptime fallback")
        else:
            print("FIX 1: Could not find end marker")
    else:
        print("FIX 1: Grace period marker not found")
else:
    # Exact match found
    new_grace = old_grace  # placeholder - won't reach here based on testing
    print("FIX 1: Exact match (unexpected)")


# ═══════════════════════════════════════════════════════════
# FIX 2: Add pre/post log comparison to training prompt
# ═══════════════════════════════════════════════════════════
train_path = os.path.join(REPO, "ai/train_comprehensive.py")
with open(train_path) as f:
    tc = f.read()

# Add restart log comparison after the restart outcomes section
# Find the restart outcomes section
restart_marker = "--- OPERATOR DENIAL REASONS"
idx = tc.find(restart_marker)
if idx > 0:
    # Insert before denial reasons — add restart log comparison
    insert_point = tc.rfind("\n", 0, idx)
    
    new_section = '''
    # Feature 9: Pre/post restart log comparison for Claude
    # Pair pre-restart and post-restart logs so Claude can see what changed
    restart_logs = conn.execute("""
        SELECT ml.miner_id, ml.collected_at, ml.health_status, ml.log_file,
               LENGTH(ml.content) as content_len
        FROM miner_logs ml
        WHERE ml.health_status IN ('pre-restart-board-check', 'post-restart-board-check',
                                    'flagged', 'healthy')
          AND ml.collected_at >= datetime('now', '-7 days')
        ORDER BY ml.miner_id, ml.collected_at DESC
        LIMIT 40
    """).fetchall()
    
    if restart_logs:
        lines.append("\\n--- PRE/POST RESTART LOG COMPARISON ---")
        lines.append("Compare these log pairs to understand what changes after a restart.")
        lines.append("Look for: error codes that clear, boards that recover, voltage changes,")
        lines.append("chip counts that change, ASIC failures that persist vs resolve.")
        
        # Group by miner
        by_miner = {}
        for rl in restart_logs:
            mid = rl["miner_id"]
            if mid not in by_miner:
                by_miner[mid] = []
            by_miner[mid].append({
                "time": rl["collected_at"],
                "status": rl["health_status"],
                "file": rl["log_file"],
                "size": rl["content_len"],
            })
        
        for mid, logs in list(by_miner.items())[:10]:
            pre = [l for l in logs if "pre" in l["status"]]
            post = [l for l in logs if "post" in l["status"]]
            if pre and post:
                lines.append(f"  Miner {mid}: {len(pre)} pre-restart logs, {len(post)} post-restart logs")
                lines.append(f"    Pre: {pre[0]['time']} ({pre[0]['size']} bytes)")
                lines.append(f"    Post: {post[0]['time']} ({post[0]['size']} bytes)")

    # Also add restart outcome summary with hashrate deltas
    outcome_summary = conn.execute("""
        SELECT ip, model, outcome, hashrate_before, hashrate_after,
               recovery_time_scans, restarted_at, restart_type
        FROM miner_restarts
        WHERE outcome IS NOT NULL
          AND restarted_at >= datetime('now', '-7 days')
        ORDER BY restarted_at DESC
        LIMIT 20
    """).fetchall()
    
    if outcome_summary:
        lines.append("\\n--- RESTART OUTCOME DETAILS (last 7 days) ---")
        lines.append("For each restart: what was the hashrate before, what was it after,")
        lines.append("how many scans until recovery, and what type of restart was it.")
        lines.append("Use this to determine: which miners benefit from restarts vs need replacement.")
        success = [r for r in outcome_summary if r["outcome"] == "SUCCESS"]
        failure = [r for r in outcome_summary if r["outcome"] == "FAILURE"]
        lines.append(f"  Total: {len(success)} SUCCESS, {len(failure)} FAILURE")
        for r in outcome_summary:
            hr_before = f"{r['hashrate_before']:.0f}%" if r['hashrate_before'] else "?"
            hr_after = f"{r['hashrate_after']:.0f}%" if r['hashrate_after'] else "?"
            recovery = f"{r['recovery_time_scans']} scans" if r['recovery_time_scans'] else "N/A"
            lines.append(
                f"  [{r['restarted_at'][:10]}] {r['ip']} ({r['model'] or '?'}) "
                f"{r['outcome']} | HR: {hr_before} → {hr_after} | Recovery: {recovery} "
                f"| Type: {r['restart_type'] or '?'}"
            )

'''
    
    tc = tc[:insert_point] + new_section + tc[insert_point:]
    with open(train_path, "w") as f:
        f.write(tc)
    print("FIX 2: Added pre/post restart log comparison + outcome details to training prompt")
else:
    print("FIX 2: Could not find denial reasons marker")

print("\nDone — compile check next")
