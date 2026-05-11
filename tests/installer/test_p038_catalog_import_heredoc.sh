#!/usr/bin/env bash
# tests/installer/test_p038_catalog_import_heredoc.sh
#
# P-038 item #1 (2026-05-11) — catalog_import shell heredoc bug in
# `intelligence-catalog/tools/run_daily_catalog_import.sh`.
#
# Background. P-022 (2026-05-08) wired scanner_discovery surface reporting
# into this daily wrapper so the operator sees how many unique events
# the scanner has captured. The author wrote the JSON-event counter as a
# Python heredoc and intended to pass the JSON path as sys.argv[1] to
# the Python process:
#
#     count="$("$VENV_PYTHON" - <<'PYEOF'
#     import json, sys
#     ...
#     PYEOF
#     "$SCANNER_DISCOVERY_LATEST")"
#
# The bug is the line AFTER `PYEOF`. Bash terminates the heredoc on the
# `PYEOF` line and then treats the bare-quoted `"$SCANNER_DISCOVERY_LATEST"`
# on the next line as a separate command. Bash tries to *execute* the
# JSON path itself, which is not an executable file, so the subshell
# exits with `Permission denied` and the wrapper exits 126. The Python
# heredoc, even if it had run, would have IndexError'd on `sys.argv[1]`
# because no argument was ever passed to it.
#
# Live evidence captured on the Mini before writing the fix
# (`/Library/Application Support/MiningGuardian/logs/scheduled/`):
#   catalog_import.last-run.json  → exit_code: 126 (Permission denied
#                                   in shell convention).
#   catalog_import.err.log        → four consecutive days of identical
#                                   `line 86: <path>/latest_findings.json:
#                                   Permission denied` (May 8, 9, 10, 11).
#
# Root cause is purely the script shape. The launcher, env handling, and
# plist are all fine.
#
# P-038 item #1 fix:
#   1. Pass the JSON path as a positional argument to the Python process
#      ON THE SAME LINE as the heredoc redirection. The canonical bash
#      form is:
#
#          count="$("$VENV_PYTHON" - "$SCANNER_DISCOVERY_LATEST" <<'PYEOF'
#          ...
#          PYEOF
#          )"
#
#      Arguments go before the heredoc redirection on the launching line.
#      The `<<'PYEOF'` is just the stdin redirect for the python process.
#   2. Drop the stray dead `if [[ ! -d "$SWEEP_DIR" ]]` block at line 46
#      that did nothing but log an INFO line and fall through (the same
#      guard reappears at line 87 with the correct `exit 0`). Removing it
#      eliminates a confusing duplicate log line and keeps the no-CSV
#      flow tidy.
#
# This test asserts:
#   1. The script parses cleanly (`bash -n`).
#   2. No bare-quoted line follows the `PYEOF` heredoc terminator.
#      (Static regression — the exact bug shape must never reappear.)
#   3. The Python heredoc's launching line passes
#      `"$SCANNER_DISCOVERY_LATEST"` as a positional argument BEFORE
#      `<<'PYEOF'`.
#   4. The duplicate dead `if [[ ! -d "$SWEEP_DIR" ]]` log-only block
#      that falls through is removed (the guarded `exit 0` form survives).
#   5. Functional smoke — running the script against a temp tree with a
#      fixture `latest_findings.json` exits 0, prints the
#      `INFO scanner_discovery findings present` line, and reports the
#      correct unique-events count from the JSON's `events` key.
#   6. Functional smoke — running the script against a temp tree with
#      NO `latest_findings.json` exits 0 and prints the
#      `INFO no scanner_discovery findings yet` line.
#   7. Functional smoke — counter-test that the OLD broken shape
#      (`<<'PYEOF' ... PYEOF\n"$path")"`) fails when invoked under
#      `bash -e`, proving this test catches the regression.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TARGET="${REPO_ROOT}/intelligence-catalog/tools/run_daily_catalog_import.sh"

PASS=0
FAIL=0

ok() {
    printf "  OK  %s\n" "$1"
    PASS=$((PASS + 1))
}

bad() {
    printf "  FAIL %s\n" "$1"
    FAIL=$((FAIL + 1))
}

# ----- §1 source presence + bash -n parses -----

echo "§1 source presence and bash -n"
if [[ -f "$TARGET" ]]; then
    ok "target present: ${TARGET#${REPO_ROOT}/}"
else
    bad "target missing: ${TARGET#${REPO_ROOT}/}"
    echo
    echo "Summary: ${PASS} passed, ${FAIL} failed"
    exit 1
fi

if bash -n "$TARGET" 2>/dev/null; then
    ok "bash -n parses"
else
    bad "bash -n failed; this means the script has a syntax error"
fi

# ----- §2 no bare-quoted line follows PYEOF -----

echo
echo "§2 heredoc terminator is not followed by a bare-quoted command"
# The bug shape: a line that ends with the PYEOF terminator and the
# IMMEDIATELY NEXT line is a bare quoted expansion ($"..." or "$..."`)
# — that next line is being treated as a separate command. Use awk to
# inspect the line right after a heredoc terminator.
broken_lines="$(awk '
    /^[[:space:]]*PYEOF[[:space:]]*$/ {
        next_idx = NR + 1
        getline next_line
        # The fix puts the arg on the launching line BEFORE <<PYEOF.
        # After PYEOF, the next line should close the command sub:
        # `)"` or `)`. A bare `"$..."` or `"$VAR"` line is the bug.
        if (next_line ~ /^[[:space:]]*"\$[A-Za-z_][A-Za-z0-9_]*"[[:space:]]*\)[[:space:]]*"[[:space:]]*$/) {
            print NR ": " next_line
        }
    }
' "$TARGET")"
if [[ -z "$broken_lines" ]]; then
    ok 'no bare-quoted "$VAR")" line follows PYEOF'
else
    bad "bare-quoted expansion follows PYEOF (the P-038 #1 bug):"
    printf "      %s\n" "$broken_lines"
fi

# ----- §3 path argument is on the heredoc launching line -----

echo
echo "§3 SCANNER_DISCOVERY_LATEST passed as positional arg on the launching line"
launching_line="$(grep -n -E '"[$]VENV_PYTHON"[[:space:]]+-[[:space:]]+.*<<[[:space:]]*'"'"'PYEOF'"'"'' "$TARGET" || true)"
if [[ -z "$launching_line" ]]; then
    bad "could not find the launching line; expected pattern: \"\$VENV_PYTHON\" - ... <<'PYEOF'"
else
    if echo "$launching_line" | grep -q '"\$SCANNER_DISCOVERY_LATEST"' ; then
        ok "launching line passes \"\$SCANNER_DISCOVERY_LATEST\" before <<'PYEOF'"
    else
        bad "launching line does NOT pass \"\$SCANNER_DISCOVERY_LATEST\" before <<'PYEOF':"
        printf "      %s\n" "$launching_line"
    fi
fi

# ----- §4 no duplicate dead `if [[ ! -d "$SWEEP_DIR" ]]` log-only block -----

echo
echo "§4 no duplicate dead SWEEP_DIR log-only block"
# The fix removes the pre-scanner_discovery occurrence that only logged
# and fell through. The post-scanner_discovery occurrence with `exit 0`
# is the canonical guard. Count must be exactly 1.
sweep_guard_count="$(grep -c '\[\[ ! -d "\$SWEEP_DIR" \]\]' "$TARGET" || true)"
if [[ "$sweep_guard_count" == "1" ]]; then
    ok "exactly one SWEEP_DIR existence guard (the one followed by exit 0)"
else
    bad "expected exactly 1 SWEEP_DIR guard, found ${sweep_guard_count}"
fi

# The single surviving guard must be followed by `exit 0` (not a bare
# log + fall-through).
if awk '
    /\[\[ ! -d "\$SWEEP_DIR" \]\]/ {
        getline next_a
        getline next_b
        getline next_c
        if (next_a ~ /exit 0/ || next_b ~ /exit 0/ || next_c ~ /exit 0/) {
            found = 1
        }
    }
    END { exit (found ? 0 : 1) }
' "$TARGET"; then
    ok "surviving SWEEP_DIR guard is followed by exit 0"
else
    bad "surviving SWEEP_DIR guard does NOT exit 0 (fall-through bug)"
fi

# ----- §5 functional smoke: latest_findings.json present, count correct -----

echo
echo "§5 functional smoke — fixture latest_findings.json"
TMP="$(mktemp -d -t p038_catalog_import.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

# Build a fake INSTALL_ROOT tree the script will see.
mkdir -p "${TMP}/cron_tracking/scanner_discovery"
mkdir -p "${TMP}/venv/bin"

# Real python3 — symlinked into the fake venv so [[ -x "$VENV_PYTHON" ]]
# passes.
PYTHON3="$(command -v python3 || true)"
if [[ -z "$PYTHON3" ]]; then
    bad "python3 not in PATH; cannot run functional smoke"
else
    ln -s "$PYTHON3" "${TMP}/venv/bin/python"
    ok "fake venv with python3 symlink in place"

    # Fixture with 7 events under the "events" key.
    cat > "${TMP}/cron_tracking/scanner_discovery/latest_findings.json" <<'JSON_FIXTURE'
{
  "events": {
    "evt-1": {"model": "S19j Pro"},
    "evt-2": {"model": "S21 Hydro"},
    "evt-3": {"model": "Auradine AH3880"},
    "evt-4": {"model": "S19 XP"},
    "evt-5": {"model": "Whatsminer M50"},
    "evt-6": {"model": "Antminer T21"},
    "evt-7": {"model": "Avalon A1466"}
  }
}
JSON_FIXTURE

    # Run the script. SWEEP_DIR is absent, so the script exits 0 after
    # reporting the scanner_discovery presence + count.
    output_file="${TMP}/run.out"
    err_file="${TMP}/run.err"
    if MG_INSTALL_ROOT="$TMP" bash "$TARGET" > "$output_file" 2> "$err_file"; then
        ok "script exits 0 with fixture latest_findings.json"
    else
        rc=$?
        bad "script exited non-zero (${rc}) with fixture latest_findings.json"
        printf "      stderr: %s\n" "$(head -3 "$err_file")"
    fi

    if grep -q 'INFO scanner_discovery findings present' "$output_file"; then
        ok "output contains 'INFO scanner_discovery findings present'"
    else
        bad "output missing 'INFO scanner_discovery findings present' line"
    fi

    # The count printed must be 7 (the fixture's events key count).
    if grep -E ': 7 unique events' "$output_file" > /dev/null; then
        ok "output reports 7 unique events (matches fixture)"
    else
        bad "output does not report 7 unique events:"
        printf "      %s\n" "$(grep scanner_discovery "$output_file" | head -1)"
    fi

    # ----- §6 functional smoke: no latest_findings.json -----

    echo
    echo "§6 functional smoke — no latest_findings.json"
    rm -f "${TMP}/cron_tracking/scanner_discovery/latest_findings.json"
    if MG_INSTALL_ROOT="$TMP" bash "$TARGET" > "$output_file" 2> "$err_file"; then
        ok "script exits 0 when latest_findings.json is absent"
    else
        rc=$?
        bad "script exited non-zero (${rc}) when latest_findings.json absent"
        printf "      stderr: %s\n" "$(head -3 "$err_file")"
    fi
    if grep -q 'INFO no scanner_discovery findings yet' "$output_file"; then
        ok "output contains 'INFO no scanner_discovery findings yet'"
    else
        bad "output missing 'INFO no scanner_discovery findings yet' line"
    fi
fi

# ----- §7 counter-test: the OLD broken shape would fail bash -e -----

echo
echo "§7 counter-test — OLD broken shape would fail"
broken_repro="${TMP}/broken_repro.sh"
cat > "$broken_repro" <<'BROKEN'
#!/bin/bash
set -euo pipefail
PYEOF_JSON="$1"
count="$(python3 - <<'PYEOF'
import json, sys
try:
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        data = json.load(f)
    events = data.get("events", {}) if isinstance(data, dict) else {}
    print(len(events))
except Exception:
    print(0)
PYEOF
"$PYEOF_JSON")"
echo "count=$count"
BROKEN
chmod +x "$broken_repro"

# This SHOULD fail the way the Mini's catalog_import.err.log shows —
# bash treats "$PYEOF_JSON" as a command and tries to execute the JSON
# path. The exact exit code is shell-version-dependent (126/127), but
# the run must NOT succeed.
mkdir -p "${TMP}/cron_tracking/scanner_discovery"
cat > "${TMP}/cron_tracking/scanner_discovery/latest_findings.json" <<'EOF'
{"events": {"e1": {}}}
EOF
if bash "$broken_repro" "${TMP}/cron_tracking/scanner_discovery/latest_findings.json" > /dev/null 2>&1; then
    bad "OLD broken shape unexpectedly SUCCEEDED — counter-test is not catching the bug"
else
    ok "OLD broken shape fails as expected (counter-test confirms test surface)"
fi

# ----- summary -----

echo
echo "================================================="
echo "Summary: ${PASS} passed, ${FAIL} failed"
echo "================================================="
if [[ "$FAIL" -gt 0 ]]; then
    exit 1
fi
exit 0
