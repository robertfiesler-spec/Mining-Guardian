#!/usr/bin/env python3
"""Add pre/post restart log comparison + outcome details to training prompt.
Inserts before the CROSS-MINER ANALYSIS section."""
import os

REPO = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian"
path = os.path.join(REPO, "ai/train_comprehensive.py")

with open(path) as f:
    c = f.read()

# Insert before the CROSS-MINER ANALYSIS section
target = '    lines.append(\n        "\\n=== CROSS-MINER ANALYSIS REQUESTED ===\\n"'

new_section = '''    # ── Pre/post restart log comparison for Claude ──────────────────
    # Pair restart logs so Claude sees what changed after each restart
    restart_logs = conn.execute("""
        SELECT ml.miner_id, ml.health_status, ml.collected_at,
               LENGTH(ml.content) as content_len
        FROM miner_logs ml
        WHERE ml.health_status LIKE '%restart%'
          AND ml.collected_at >= datetime('now', '-7 days')
        ORDER BY ml.miner_id, ml.collected_at DESC
        LIMIT 40
    """).fetchall()

    if restart_logs:
        lines.append("\\n--- PRE/POST RESTART LOG COMPARISON ---")
        lines.append("Compare these log pairs to understand what changes after a restart.")
        lines.append("Look for: error codes that clear, boards that recover, voltage changes,")
        lines.append("chip counts that change, ASIC failures that persist vs resolve.")
        by_miner = {}
        for rl in restart_logs:
            mid = rl["miner_id"]
            if mid not in by_miner:
                by_miner[mid] = []
            by_miner[mid].append(rl)
        for mid, logs in list(by_miner.items())[:10]:
            pre = [l for l in logs if "pre" in l["health_status"]]
            post = [l for l in logs if "post" in l["health_status"]]
            if pre and post:
                lines.append(
                    f"  Miner {mid}: {len(pre)} pre-restart + {len(post)} post-restart logs "
                    f"(pre: {pre[0]['collected_at'][:16]}, post: {post[0]['collected_at'][:16]})"
                )

    # ── Restart outcome details with hashrate deltas ─────────────────
    outcome_rows = conn.execute("""
        SELECT ip, model, outcome, hashrate_before, hashrate_after,
               recovery_time_scans, restarted_at, restart_type
        FROM miner_restarts
        WHERE outcome IS NOT NULL
          AND restarted_at >= datetime('now', '-7 days')
        ORDER BY restarted_at DESC LIMIT 20
    """).fetchall()

    if outcome_rows:
        success = [r for r in outcome_rows if r["outcome"] == "SUCCESS"]
        failure = [r for r in outcome_rows if r["outcome"] == "FAILURE"]
        lines.append("\\n--- RESTART OUTCOME DETAILS (last 7 days) ---")
        lines.append(f"Total: {len(success)} SUCCESS, {len(failure)} FAILURE")
        lines.append("Use this to determine which miners benefit from restarts vs need replacement.")
        for r in outcome_rows:
            hr_b = f"{r['hashrate_before']:.0f}%" if r['hashrate_before'] else "?"
            hr_a = f"{r['hashrate_after']:.0f}%" if r['hashrate_after'] else "?"
            rec = f"{r['recovery_time_scans']} scans" if r['recovery_time_scans'] else "N/A"
            lines.append(
                f"  [{r['restarted_at'][:10]}] {r['ip']} {r['outcome']} "
                f"HR: {hr_b} -> {hr_a} | Recovery: {rec} | {r['restart_type'] or '?'}"
            )

'''

if target in c:
    c = c.replace(target, new_section + target)
    with open(path, "w") as f:
        f.write(c)
    print("FIXED: Added restart log comparison + outcome details before CROSS-MINER section")
else:
    print("ERROR: Could not find CROSS-MINER insertion point")
