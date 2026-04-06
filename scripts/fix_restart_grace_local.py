#!/usr/bin/env python3
"""Add post-restart grace period to committed code."""
import os

# Detect path
repo = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian"
path = os.path.join(repo, "core/mining_guardian.py")

with open(path) as f:
    c = f.read()

old = '''        miner_id   = str(miner.get("id", "unknown"))
        ip         = miner.get("ip", "unknown")
        name       = miner.get("shortModel", miner.get("name", "unknown"))
        model_code = miner.get("model", "")
        status     = miner.get("status", "unknown")
        hashrate   = miner.get("hashrate", 0) or 0     # MH/s from AMS
        firmware   = miner.get("firmwareManufacturer", "") or ""'''

new = '''        miner_id   = str(miner.get("id", "unknown"))
        ip         = miner.get("ip", "unknown")
        name       = miner.get("shortModel", miner.get("name", "unknown"))
        model_code = miner.get("model", "")
        status     = miner.get("status", "unknown")
        hashrate   = miner.get("hashrate", 0) or 0     # MH/s from AMS
        firmware   = miner.get("firmwareManufacturer", "") or ""

        # ── Post-restart grace period (20 minutes) ───────────────────
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
                    _h = _re.search(r"(\\d+)h", uptime_str)
                    _m = _re.search(r"(\\d+)m", uptime_str)
                    if _h: uptime_secs += int(_h.group(1)) * 3600
                    if _m: uptime_secs += int(_m.group(1)) * 60
                if 0 < uptime_secs < 1200:  # < 20 minutes
                    logger.debug("[%s] Uptime %s < 20min — skipping actions", miner_id, uptime_str)
                    return None
            except Exception:
                pass'''

if old in c:
    c = c.replace(old, new)
    with open(path, "w") as f:
        f.write(c)
    print("FIXED: 20-min grace period added to committed code")
else:
    # Check if already applied
    if "Post-restart grace period" in c:
        print("Already applied")
    else:
        print("ERROR: Could not find target block")
