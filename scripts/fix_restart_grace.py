#!/usr/bin/env python3
"""
Add post-restart grace period: if a miner is in elevated monitoring (recently restarted),
set action to MONITOR only — no restarts, no profile changes. Also handles manual restarts
by checking if uptime is less than 20 minutes.
"""

with open("/root/Mining-Gaurdian/core/mining_guardian.py") as f:
    c = f.read()

# Add elevated monitoring check at the top of _analyze_miner
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

        # ── Post-restart grace period ────────────────────────────────
        # If this miner was recently restarted (by MG or manually), give it
        # 20 minutes to stabilize. Don't recommend restarts or profile changes.
        # Check 1: MG-tracked restarts via elevated_until
        # Check 2: AMS uptime < 20 min (catches manual restarts)
        if self.db.is_elevated_monitoring(miner_id):
            logger.debug("[%s] Post-restart grace period — skipping action recommendations", miner_id)
            return None  # fully suppress — still collecting data in miner_readings
        uptime_str = str(miner.get("uptime", "") or "")
        if uptime_str and status == "online":
            # Parse uptime — AMS reports in seconds or "Xh Ym" format
            try:
                uptime_secs = 0
                if uptime_str.isdigit():
                    uptime_secs = int(uptime_str)
                elif "h" in uptime_str or "m" in uptime_str:
                    import re
                    hours = re.search(r"(\\d+)h", uptime_str)
                    mins = re.search(r"(\\d+)m", uptime_str)
                    if hours: uptime_secs += int(hours.group(1)) * 3600
                    if mins: uptime_secs += int(mins.group(1)) * 60
                if 0 < uptime_secs < 1200:  # less than 20 minutes
                    logger.debug("[%s] Uptime %s — recently booted, skipping actions", miner_id, uptime_str)
                    return None
            except Exception:
                pass'''

if old in c:
    c = c.replace(old, new)
    with open("/root/Mining-Gaurdian/core/mining_guardian.py", "w") as f:
        f.write(c)
    print("FIXED: 20-minute post-restart grace period added")
else:
    print("ERROR: Could not find target block")
