#!/usr/bin/env python3
"""
trigger_log_exports.py
BiXBiT Mining Guardian — Log Export Trigger

Runs separately from the main scan. Finds all online miners
with no existing logs in AMS and triggers log exports for them.

Once exports complete (~60s), run mining_guardian.py to collect them.

Usage:
    source venv/bin/activate
    export $(grep -v '^#' .env | xargs)
    python trigger_log_exports.py
"""

import os, sys, json, time, threading
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "core"), str(_ROOT / "clients"), str(_ROOT / "monitoring")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mining_guardian import AMSClient, GuardianConfig

DIVIDER = "━" * 60

def main():
    cfg_path = _ROOT / "config" / "config.json"
    if not cfg_path.exists():
        cfg_path = _ROOT / "config.json"
    config = GuardianConfig.from_file(str(cfg_path))
    client = AMSClient(config)

    print(f"\n{DIVIDER}")
    print("  Mining Guardian — Log Export Trigger")
    print(f"{DIVIDER}\n")

    # Step 1 — Fetch all miners
    print("  Fetching miner list...")
    miners = client.get_miners()
    online  = [m for m in miners if m.get("status") == "online"]
    offline = [m for m in miners if m.get("status") != "online"]
    print(f"  Found {len(miners)} miners — {len(online)} online, {len(offline)} offline\n")

    # Step 2 — Check which online miners have no existing logs
    print("  Checking existing logs...")
    needs_export = []
    has_logs     = []

    for miner in online:
        miner_id = miner["id"]
        model    = miner.get("shortModel", miner.get("name", "unknown"))
        ip       = miner.get("ip", "unknown")
        logs     = client.get_log_list(miner_id)
        ready    = [l for l in logs if l.get("status") == 2]
        if ready:
            has_logs.append(miner)
            print(f"  ✅ {ip:<18} {model:<14} — {len(ready)} log(s) available")
        else:
            needs_export.append(miner)
            print(f"  ❌ {ip:<18} {model:<14} — no logs, will trigger export")

    print(f"\n  Summary: {len(has_logs)} have logs | {len(needs_export)} need export\n")

    if not needs_export:
        print("  All online miners already have logs. Nothing to do.\n")
        print(f"{DIVIDER}\n")
        return

    # Step 3 — Trigger exports in batches of 5 to avoid overwhelming AMS
    print(f"  Triggering log exports for {len(needs_export)} miners (batches of 5)...")
    triggered = []
    failed    = []
    BATCH_SIZE = 5

    for i in range(0, len(needs_export), BATCH_SIZE):
        batch = needs_export[i:i+BATCH_SIZE]
        for miner in batch:
            miner_id = miner["id"]
            ip       = miner.get("ip", "unknown")
            model    = miner.get("shortModel", "unknown")
            success  = client.trigger_log_export(miner_id)
            if success:
                triggered.append(miner)
                print(f"  ✅ Triggered export for {ip} ({model})")
            else:
                failed.append(miner)
                print(f"  ⚠️  Export trigger failed for {ip} ({model}) — may have too many logs already")
        # Pause between batches to avoid rate limiting
        if i + BATCH_SIZE < len(needs_export):
            print(f"  Pausing 10s between batches...")
            time.sleep(10)

    print(f"\n  Triggered: {len(triggered)} | Failed: {len(failed)}\n")

    if not triggered:
        print("  No exports were triggered. Check AMS log limits.\n")
        print(f"{DIVIDER}\n")
        return

    # Step 4 — Wait for exports to complete (up to 5 minutes)
    print(f"  Waiting up to 5 minutes for exports to complete...")
    completed = []
    start = time.time()

    while time.time() - start < 300:
        time.sleep(10)
        elapsed = int(time.time() - start)
        still_pending = []

        for miner in triggered:
            miner_id = miner["id"]
            if any(m["id"] == miner_id for m in completed):
                continue
            logs  = client.get_log_list(miner_id)
            ready = [l for l in logs if l.get("status") == 2]
            if ready:
                completed.append(miner)
                ip    = miner.get("ip", "unknown")
                model = miner.get("shortModel", "unknown")
                print(f"  ✅ [{elapsed}s] {ip} ({model}) — log ready")
            else:
                still_pending.append(miner)

        if not still_pending:
            break
        print(f"  [{elapsed}s] Waiting on {len(still_pending)} more miners...")

    # Step 5 — Final report
    print(f"\n{DIVIDER}")
    print(f"  Done — {len(completed)} of {len(triggered)} exports completed")
    if completed:
        print(f"\n  ✅ Run mining_guardian.py now to collect these logs.")
    if len(completed) < len(triggered):
        remaining = len(triggered) - len(completed)
        print(f"  ⚠️  {remaining} exports still pending — run again in a few minutes.")
    print(f"{DIVIDER}\n")

if __name__ == "__main__":
    main()
