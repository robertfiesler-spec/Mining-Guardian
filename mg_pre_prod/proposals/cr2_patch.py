#!/usr/bin/env python3
"""
CR-2 Patch Script — defensive _parse_hashrate_pct helper + 3 site replacements.

Pattern follows CRIT-1a-2's all-or-nothing exact-match approach with auto-rollback.

Targets (verified against snapshot f18ad86 of core/mining_guardian.py):
    Helper insertion point: after `logger = _setup_logging()` at line 49
    Site 1: line 4081  -- Dead board restart, record_restart kwarg
    Site 2: line 4386  -- Physical inspection record_restart
    Site 3: line 4448  -- Manual approved firmware restart

Usage (from repo root on ROBS-PC):
    cd C:\\Users\\User\\Mining-Guardian
    python mg_pre_prod\\proposals\\cr2_patch.py        # dry-run, prints diff
    python mg_pre_prod\\proposals\\cr2_patch.py --apply  # write + verify

The script:
  1. Reads core/mining_guardian.py
  2. Verifies all 3 target lines + helper insertion anchor exist EXACTLY
  3. If any anchor mismatches: aborts with a clear error, file untouched
  4. Otherwise applies all 4 edits in-memory, py_compile-checks the result
  5. Writes the patched file (only on --apply)
  6. Re-greps to verify zero `float(issue.get("hashrate_pct") or 0)` patterns remain
  7. Re-greps to confirm 3 `_parse_hashrate_pct(issue.get("hashrate_pct"))` patterns added
"""

from __future__ import annotations

import argparse
import py_compile
import shutil
import sys
import tempfile
from pathlib import Path

TARGET = Path("core/mining_guardian.py")

# ---------------------------------------------------------------------------
# Edit 1 — Insert _parse_hashrate_pct helper.
# Anchor: the line `logger = _setup_logging()`, which is unique in the file.
# We insert the helper IMMEDIATELY AFTER this line, with a leading blank line.
# ---------------------------------------------------------------------------
HELPER_ANCHOR = "logger = _setup_logging()\n"

HELPER_BLOCK = '''

def _parse_hashrate_pct(val) -> float:
    """Convert hashrate_pct display string to float, safely.

    The hashrate_pct field can be:
      "80.5%"       -> 80.5
      "N/A"         -> 0.0  (AMS-SYNC miners — see line 3548 of this file)
      "0%"          -> 0.0
      ""  / None    -> 0.0
      80.5  / 80    -> 80.5  (numeric passthrough)

    Why this helper exists (CR-2):
      Three call sites used the unsafe pattern float(<dict>.get(...) or 0)
      which crashes with ValueError on "N/A" and "80.5%" because both are
      truthy strings that float() cannot parse. The crash happened AFTER
      the AMS reboot command was sent but BEFORE record_restart wrote --
      leaving no audit trail of the action.
    """
    if val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().rstrip("%").strip()
    if not s or s.upper() in ("N/A", "NA", "NONE", "NULL", "UNKNOWN"):
        return 0.0
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0
'''

# ---------------------------------------------------------------------------
# Edits 2, 3, 4 — Replace the 3 unsafe float() call sites.
# Each "old" string is the FULL LINE (with leading whitespace) so the match
# is unambiguous. Each "new" string preserves indentation + paren count.
# ---------------------------------------------------------------------------
SITE_EDITS = [
    # Site 1 -- line 4081 -- Dead board restart, kwarg form (no trailing paren on its line)
    {
        "label": "Site 1 (line ~4081, dead-board restart record)",
        "old": '                hashrate_before=float(issue.get("hashrate_pct") or 0)\n',
        "new": '                hashrate_before=_parse_hashrate_pct(issue.get("hashrate_pct"))\n',
    },
    # Site 2 -- line 4386 -- Physical inspection record_restart.
    # Anchor uses TWO lines because the trailing-)) line is a substring-prefix
    # of Site 3's line (Site 3 has 4 more leading spaces). Two-line context
    # makes the match unique.
    {
        "label": "Site 2 (line ~4386, physical inspection record)",
        "old": (
            '        self.db.record_restart(miner_id, ip, model, reason,\n'
            '                               hashrate_before=float(issue.get("hashrate_pct") or 0))\n'
        ),
        "new": (
            '        self.db.record_restart(miner_id, ip, model, reason,\n'
            '                               hashrate_before=_parse_hashrate_pct(issue.get("hashrate_pct")))\n'
        ),
    },
    # Site 3 -- line 4448 -- Manual approved firmware restart.
    # Anchor uses TWO lines for the same reason.
    {
        "label": "Site 3 (line ~4448, manual approved firmware restart)",
        "old": (
            '            self.db.record_restart(miner_id, ip, model, restart_type="MANUAL_APPROVED",\n'
            '                                   hashrate_before=float(issue.get("hashrate_pct") or 0))\n'
        ),
        "new": (
            '            self.db.record_restart(miner_id, ip, model, restart_type="MANUAL_APPROVED",\n'
            '                                   hashrate_before=_parse_hashrate_pct(issue.get("hashrate_pct")))\n'
        ),
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="CR-2 defensive hashrate parser patch")
    parser.add_argument("--apply", action="store_true",
                        help="Write changes to disk. Without this flag, runs in dry-run mode.")
    parser.add_argument("--repo-root", type=str, default=".",
                        help="Path to Mining-Guardian repo root (default: cwd)")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    target_path = repo_root / TARGET
    if not target_path.exists():
        print(f"ERROR: target file not found: {target_path}", file=sys.stderr)
        print(f"  Run from the Mining-Guardian repo root, or pass --repo-root <path>",
              file=sys.stderr)
        return 2

    print(f"[CR-2] Patching: {target_path}")

    original = target_path.read_text(encoding="utf-8")
    patched = original

    # Pre-flight: verify every anchor exists exactly once
    failures: list[str] = []

    if HELPER_ANCHOR not in patched:
        failures.append(f"Helper anchor not found: {HELPER_ANCHOR.strip()!r}")
    elif patched.count(HELPER_ANCHOR) > 1:
        failures.append(
            f"Helper anchor matched {patched.count(HELPER_ANCHOR)} times — must be unique"
        )

    if "_parse_hashrate_pct" in patched:
        failures.append(
            "Helper _parse_hashrate_pct already present — CR-2 may already be applied. "
            "Aborting to prevent duplicate insertion."
        )

    for edit in SITE_EDITS:
        n = patched.count(edit["old"])
        if n == 0:
            failures.append(f"{edit['label']}: anchor not found")
        elif n > 1:
            failures.append(f"{edit['label']}: anchor matched {n} times — must be unique")

    if failures:
        print("\n[CR-2] PRE-FLIGHT FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        print("\nNo changes written. File untouched.", file=sys.stderr)
        return 1

    print("[CR-2] All 4 anchors verified unique. Applying edits in-memory...")

    # Apply edits in order: helper first (uses the anchor + insert), then 3 sites
    patched = patched.replace(
        HELPER_ANCHOR,
        HELPER_ANCHOR + HELPER_BLOCK,
        1,
    )

    for edit in SITE_EDITS:
        patched = patched.replace(edit["old"], edit["new"], 1)
        print(f"  ✓ {edit['label']}")

    # Sanity: byte-level diff summary
    added_lines = patched.count("\n") - original.count("\n")
    print(f"[CR-2] Net line delta: {added_lines:+d}")

    # Compile-check the patched bytes BEFORE touching disk
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", encoding="utf-8", delete=False
    ) as tmp:
        tmp.write(patched)
        tmp_path = Path(tmp.name)
    try:
        py_compile.compile(str(tmp_path), doraise=True)
        print("[CR-2] py_compile: OK")
    except py_compile.PyCompileError as e:
        print(f"[CR-2] py_compile FAILED on patched bytes:\n  {e}", file=sys.stderr)
        return 3
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    # Final post-patch invariants.
    # Count patterns by line so substring overlap (the 2-paren form contains
    # the 1-paren form) doesn't inflate counts.
    bad_pattern = 'float(issue.get("hashrate_pct") or 0)'
    helper_pattern = '_parse_hashrate_pct(issue.get("hashrate_pct"))'
    remaining_lines = [
        ln for ln in patched.split("\n")
        if bad_pattern in ln and "_parse_hashrate_pct" not in ln  # skip our own docstring/code
    ]
    helper_lines = [
        ln for ln in patched.split("\n")
        if helper_pattern in ln and "def _parse_hashrate_pct" not in ln  # skip the def
    ]
    if len(remaining_lines) != 0:
        print(f"[CR-2] INVARIANT FAILED: {len(remaining_lines)} unsafe float() patterns remain:",
              file=sys.stderr)
        for ln in remaining_lines:
            print(f"    {ln.strip()}", file=sys.stderr)
        return 4
    if len(helper_lines) != 3:
        print(f"[CR-2] INVARIANT FAILED: expected 3 helper call sites, found {len(helper_lines)}",
              file=sys.stderr)
        for ln in helper_lines:
            print(f"    {ln.strip()}", file=sys.stderr)
        return 4
    print(f"[CR-2] Invariants OK: 0 unsafe patterns remain, 3 helper call sites inserted.")

    if not args.apply:
        print("\n[CR-2] DRY RUN complete. Re-run with --apply to write changes.")
        print(f"       Backup: target file will be copied to {target_path}.pre_cr2_backup")
        return 0

    # Apply: backup then atomic-ish write
    backup_path = target_path.with_suffix(target_path.suffix + ".pre_cr2_backup")
    shutil.copy2(target_path, backup_path)
    print(f"[CR-2] Backup written: {backup_path}")

    target_path.write_text(patched, encoding="utf-8")
    print(f"[CR-2] Patched file written: {target_path}")
    print(f"[CR-2] To rollback: copy {backup_path} -> {target_path}")
    print("\n[CR-2] DONE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
