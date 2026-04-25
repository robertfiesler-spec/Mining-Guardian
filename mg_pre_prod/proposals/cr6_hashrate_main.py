#!/usr/bin/env python3
"""
CR-6 hashrate parser hotfix — translated to main line numbers.

Original CR-2 work (commit 9e705f7 on audit branch) targeted lines
4108/4413/4475 of audit's mining_guardian.py. Main's mining_guardian.py is a
different file (2473 lines vs audit's 5500+). The same bug exists at:

  • main L924    — execute_board_restart    (Dead board restart path)
  • main L1291   — execute_restart           (MANUAL_APPROVED restart path)

(Audit's third site — the 'Dead hashboard physical inspection' path — does not
exist on main as a separate code path.)

Bug:
  hashrate_pct can be "N/A", "80.5%", "0%", or "" depending on miner state.
  `float(issue.get("hashrate_pct") or 0)` raises ValueError on "N/A" and "80.5%"
  AFTER the AMS reboot command is sent but BEFORE record_restart writes — so
  the action happens with no audit trail.

Fix:
  Add `_parse_hashrate_pct()` helper near the top of the file. Replace both
  unsafe sites with helper calls.

Usage:
  python3 cr6_hashrate_main.py --dry-run
  python3 cr6_hashrate_main.py --apply

Idempotent. sha256-pinned to main @ b28c8a7.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

# Pin: this is the sha256 of main b28c8a7's core/mining_guardian.py
EXPECTED_SHA = "dbc873b9336773ef5052fa08a4aa3e6ac1eac82061d04b48626e393f9cb2fbea"

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "core" / "mining_guardian.py"

HELPER = '''

def _parse_hashrate_pct(val) -> float:
    """Convert hashrate_pct to float, safely. Handles "80.5%", "N/A", "0%", None.

    Without this, the unsafe `float(...)` pattern previously used at the call
    sites raises ValueError on truthy non-numeric strings ("N/A", "80.5%")
    AFTER AMS reboot is sent but BEFORE record_restart writes — leaving no
    audit trail. CR-6 fix.
    """
    if val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().rstrip("%")
    if not s or s.upper() in ("N/A", "NA", "NONE"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0
'''

OLD_PATTERN = "float(issue.get(\"hashrate_pct\") or 0)"
NEW_PATTERN = "_parse_hashrate_pct(issue.get(\"hashrate_pct\"))"


def main() -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    p.add_argument("--repo-root", default=str(REPO_ROOT))
    p.add_argument("--skip-sha-check", action="store_true",
                   help="bypass main-version sha256 check (use carefully)")
    args = p.parse_args()

    target = Path(args.repo_root) / "core" / "mining_guardian.py"
    if not target.exists():
        print(f"ERROR: {target} not found", file=sys.stderr)
        return 1

    text = target.read_text(encoding="utf-8")
    actual_sha = hashlib.sha256(text.encode()).hexdigest()
    print(f"Target: {target}")
    print(f"sha256: {actual_sha}")
    print(f"Expected (main b28c8a7): {EXPECTED_SHA}")

    if actual_sha != EXPECTED_SHA and not args.skip_sha_check:
        # Already-patched files won't match either; check if helper is present
        if "_parse_hashrate_pct" in text and OLD_PATTERN not in text:
            print("File already patched — no-op.")
            return 0
        print("WARNING: file does not match expected main b28c8a7. Use --skip-sha-check to override.")
        return 2

    print(f"\nMode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print("=" * 60)

    # Insertion point: after the FIRST top-level import block
    if "_parse_hashrate_pct" in text:
        print("[skip] helper already present")
    else:
        lines = text.splitlines(keepends=True)
        in_block = False
        end_idx = 0
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if (stripped.startswith(("import ", "from "))
                    and not line.startswith(" ")):
                in_block = True
                end_idx = i
            elif in_block and stripped and not stripped.startswith("#"):
                break
        lines.insert(end_idx + 1, HELPER)
        text = "".join(lines)
        print(f"[insert] helper after line {end_idx + 1}")

    # Replace both call sites
    occurrences = text.count(OLD_PATTERN)
    if occurrences == 0:
        print("[skip] no unsafe sites — already patched?")
    else:
        text = text.replace(OLD_PATTERN, NEW_PATTERN)
        print(f"[patch] replaced {occurrences} site(s)")

    print("=" * 60)

    if args.apply:
        target.write_text(text, encoding="utf-8")
        new_sha = hashlib.sha256(text.encode()).hexdigest()
        print(f"Wrote: {target}")
        print(f"New sha256: {new_sha}")

        # Verify
        import py_compile
        try:
            py_compile.compile(str(target), doraise=True)
            print("py_compile: OK")
        except py_compile.PyCompileError as e:
            print(f"py_compile: FAILED — {e}", file=sys.stderr)
            return 3

        # Verify literal patterns gone
        if OLD_PATTERN in target.read_text(encoding="utf-8"):
            print(f"WARNING: unsafe pattern still present", file=sys.stderr)
            return 4
        print("Verification: unsafe pattern fully removed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
