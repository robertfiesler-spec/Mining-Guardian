#!/usr/bin/env python3
"""
Fix offline miner restart logic.

PROBLEM: System recommends RESTART for truly offline miners, but firmware
restart requires network connectivity. If miner has no power, restart
command can't reach it.

FIX: For confirmed-offline miners:
  - If has PDU → PDU_CYCLE (power cycle will restore)
  - If no PDU → PHYSICAL_INSPECTION (can't reach remotely)

Firmware RESTART is only valid when miner is REACHABLE but underperforming.
"""

with open("/root/Mining-Gaurdian/core/mining_guardian.py", "r") as f:
    content = f.read()

old_logic = '''                if offline_restarts == 0:
                    # First time offline — firmware restart always first regardless of model
                    action = "RESTART"
                    issues[-1] = "OFFLINE — attempting firmware restart"

                elif has_pdu and offline_pdu_cycles == 0:
                    # Has PDU + restart tried → power cycle next
                    action     = "PDU_CYCLE"
                    pdu_action = f"PDU {pdu_id} → Outlet {outlet_index}"
                    issues[-1] = (
                        "OFFLINE — firmware restart attempted, trying PDU power cycle "
                        "(possible bad PSU or needs hard reset)"
                    )

                else:
                    # No PDU (S19JPros etc.) + restart tried, OR PDU cycle already tried
                    # → needs physical inspection, likely bad PSU or control board
                    action = "PHYSICAL_CYCLE"
                    if not has_pdu:
                        issues[-1] = (
                            "OFFLINE — restart attempted, no PDU access. "
                            "Likely bad PSU or control board — physical inspection required"
                        )
                    else:
                        issues[-1] = (
                            "OFFLINE — restart + PDU cycle both failed. "
                            "Bad PSU, bad control board, or blown fuse — physical inspection required"
                        )'''

new_logic = '''                # OPERATOR RULE: Firmware restart requires network connectivity.
                # If miner is truly offline (unreachable), restart command can't reach it.
                # Go straight to PDU cycle (if available) or physical inspection.
                
                if has_pdu and offline_pdu_cycles == 0:
                    # Has PDU → power cycle is the correct first action for offline miner
                    action     = "PDU_CYCLE"
                    pdu_action = f"PDU {pdu_id} → Outlet {outlet_index}"
                    issues[-1] = (
                        "OFFLINE — miner unreachable. PDU power cycle recommended "
                        "(firmware restart won't work without power)"
                    )

                elif has_pdu and offline_pdu_cycles > 0:
                    # PDU cycle already tried → needs physical inspection
                    action = "PHYSICAL_INSPECTION"
                    issues[-1] = (
                        "OFFLINE — PDU cycle attempted but miner still offline. "
                        "Bad PSU, bad control board, or blown fuse — physical inspection required"
                    )

                else:
                    # No PDU access (S19JPros etc.) → can't recover remotely
                    action = "PHYSICAL_INSPECTION"
                    issues[-1] = (
                        "OFFLINE — no PDU access, cannot recover remotely. "
                        "Physical inspection required — likely bad PSU or control board"
                    )'''

if old_logic in content:
    content = content.replace(old_logic, new_logic)
    with open("/root/Mining-Gaurdian/core/mining_guardian.py", "w") as f:
        f.write(content)
    print("SUCCESS: Fixed offline miner restart logic")
    print("  - Removed RESTART for truly offline miners")
    print("  - PDU_CYCLE is now first action if PDU available")
    print("  - PHYSICAL_INSPECTION if no PDU or PDU cycle failed")
else:
    print("ERROR: Could not find the offline restart logic block")
