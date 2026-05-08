#!/usr/bin/env bash
# tests/installer/test_p027_discovery_sink_perms.sh
#
# P-027 (2026-05-08) — postinstall.sh::step_normalize_discovery_sink_perms.
#
# Background. Live Mini install of build b1999c25346f on 2026-05-08
# brought up scanner/services cleanly but the scanner logged repeated:
#   discovery_sink: failed to persist ... [Errno 13] Permission denied:
#   '/Library/Application Support/MiningGuardian/cron_tracking/scanner_discovery/events-2026-05-08.jsonl'
# Inspection: dir was `miningguardian:staff` 0755 but
# `events-2026-05-08.jsonl` had been created `root:staff` 0644 by an
# earlier process and the next writer could not append. Manual repair:
#   chown -R miningguardian:staff <sink-dir>
#   chmod 0775 <sink-dir>
#   chmod 0664 <sink-dir>/events-*.jsonl
#   chmod 0664 <sink-dir>/latest_findings.json 2>/dev/null || true
# After repair + forced scanner run: exit 0, no new Permission denied,
# event count 12 → 24. P-022 sink persistence verified.
#
# This test asserts the new postinstall step:
#   1. exists in postinstall.sh and is wired into orchestration after
#      step_layout_install_root and before step_install_plists_and_bootstrap;
#   2. parses (bash -n);
#   3. on a fresh tmp install root, creates
#      `${MG_INSTALL_ROOT}/cron_tracking/scanner_discovery/` with mode
#      0775 and the documented chown target;
#   4. on an upgrade harness with pre-existing root-owned-shaped event
#      files, chmods them to 0664 (we cannot exercise root chown in CI,
#      but we can verify the chmod path and that the chown command
#      target is `${MG_INSTALL_OPERATOR_USER}:staff`).
#
# Run from repo root:
#     bash tests/installer/test_p027_discovery_sink_perms.sh
#
# Exits 0 on success, non-zero on first failed assertion.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. postinstall.sh parses"
# ---------------------------------------------------------------------
if bash -n "$POSTINSTALL" 2>/dev/null; then
    ok "postinstall.sh parses (bash -n)"
else
    fail "postinstall.sh has bash syntax errors"
fi

# ---------------------------------------------------------------------
section "2. step_normalize_discovery_sink_perms is defined and wired in"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '^step_normalize_discovery_sink_perms\(\)' "$POSTINSTALL"; then
    ok "step_normalize_discovery_sink_perms() defined"
else
    fail "step_normalize_discovery_sink_perms() missing"
fi
# P-027 marker comment so a regression that drops the rationale is visible.
if /usr/bin/grep -qF "P-027 (2026-05-08)" "$POSTINSTALL"; then
    ok "P-027 marker comment present"
else
    fail "P-027 (2026-05-08) marker missing — rationale at risk of drift"
fi
# Sink path must match core.discovery_sink default: cron_tracking/scanner_discovery.
if /usr/bin/grep -qF 'cron_tracking/scanner_discovery' "$POSTINSTALL"; then
    ok "step references cron_tracking/scanner_discovery path"
else
    fail "step does not reference cron_tracking/scanner_discovery"
fi
# Mode bits the manual repair locked in (0775 dirs, 0664 files).
if /usr/bin/grep -qF 'install -d -m 0775' "$POSTINSTALL" && \
   /usr/bin/grep -qF 'chmod 0775' "$POSTINSTALL"; then
    ok "step uses dir mode 0775"
else
    fail "step missing dir mode 0775"
fi
if /usr/bin/grep -qF 'chmod 0664 "$sink_dir"/events-*.jsonl' "$POSTINSTALL"; then
    ok "step chmod 0664 on events-*.jsonl"
else
    fail "step missing chmod 0664 on events-*.jsonl"
fi
if /usr/bin/grep -qF 'chmod 0664 "$sink_dir/latest_findings.json"' "$POSTINSTALL"; then
    ok "step chmod 0664 on latest_findings.json"
else
    fail "step missing chmod 0664 on latest_findings.json"
fi
# Recursive chown to operator user (matches `chown -R miningguardian:staff`).
if /usr/bin/grep -qF 'chown -R "${MG_INSTALL_OPERATOR_USER}:staff" "$sink_dir"' "$POSTINSTALL"; then
    ok "step chown -R \${MG_INSTALL_OPERATOR_USER}:staff on sink dir"
else
    fail "step missing recursive chown to MG_INSTALL_OPERATOR_USER:staff"
fi

# Orchestration order: must follow step_layout_install_root (so the
# install root + initial chown have already happened) and must precede
# step_install_plists_and_bootstrap (so the scanner LaunchDaemon has
# correct directory state on first fire).
order_block="$(/usr/bin/awk '
    /^    step_layout_install_root$/        { saw_layout = NR }
    /^    step_normalize_discovery_sink_perms$/ { saw_norm = NR }
    /^    step_install_plists_and_bootstrap$/   { saw_bootstrap = NR }
    END { print saw_layout, saw_norm, saw_bootstrap }
' "$POSTINSTALL")"
read -r layout_ln norm_ln bootstrap_ln <<<"$order_block"
if [[ -z "${layout_ln}" || -z "${norm_ln}" || -z "${bootstrap_ln}" ]]; then
    fail "orchestration: could not locate one of step_layout_install_root / step_normalize_discovery_sink_perms / step_install_plists_and_bootstrap (lines: '$order_block')"
elif (( layout_ln < norm_ln )) && (( norm_ln < bootstrap_ln )); then
    ok "orchestration order: layout < normalize < plists-bootstrap (${layout_ln} < ${norm_ln} < ${bootstrap_ln})"
else
    fail "orchestration order wrong: layout=${layout_ln} normalize=${norm_ln} bootstrap=${bootstrap_ln}"
fi

# ---------------------------------------------------------------------
section "3. Runtime: extract step body and run against a tmp install root"
# ---------------------------------------------------------------------
# We cannot exercise the real `chown` (would need root + a real
# `miningguardian` account). Instead we shim `chown` into a no-op that
# also LOGS its arguments so we can assert it was called with the right
# operator-user target. `install`, `chmod`, the `mkdir -p` paths all
# work as themselves in a tmp dir.

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAKE_INSTALL_ROOT="${TMP}/install_root"
mkdir -p "$FAKE_INSTALL_ROOT"

# Pre-populate an "upgrade-shape" sink with a root-owned-style file at
# 0644. The test does not require ownership to actually be root — it
# verifies the step CHMODs back to 0664 regardless of starting mode.
mkdir -p "${FAKE_INSTALL_ROOT}/cron_tracking/scanner_discovery"
upgrade_event="${FAKE_INSTALL_ROOT}/cron_tracking/scanner_discovery/events-2026-05-08.jsonl"
echo '{"kind":"unknown_model","ts":"2026-05-08T20:43:40Z"}' > "$upgrade_event"
chmod 0644 "$upgrade_event"
upgrade_latest="${FAKE_INSTALL_ROOT}/cron_tracking/scanner_discovery/latest_findings.json"
echo '{"events":[]}' > "$upgrade_latest"
chmod 0644 "$upgrade_latest"

# Extract the step function body verbatim and run it under shim env.
PROBE="${TMP}/probe.sh"
cat > "$PROBE" <<'EOF_PROBE'
#!/usr/bin/env bash
set -uo pipefail

# Minimal shims so the step runs standalone.
log() { printf 'log: %s\n' "$*"; }

# Capture chown calls without actually changing ownership.
chown_log_path="${CHOWN_LOG:?CHOWN_LOG must be set}"
chown() {
    printf '%s\n' "chown $*" >> "$chown_log_path"
    return 0
}
EOF_PROBE
chmod +x "$PROBE"

# Append the step body. Use awk to slice from `step_normalize_discovery_sink_perms() {` to the matching `}` on a line by itself.
/usr/bin/awk '
    /^step_normalize_discovery_sink_perms\(\) \{/ { capture=1 }
    capture { print }
    capture && /^\}/ { capture=0 }
' "$POSTINSTALL" >> "$PROBE"
echo 'step_normalize_discovery_sink_perms' >> "$PROBE"

CHOWN_LOG="${TMP}/chown.log"
: > "$CHOWN_LOG"

if MG_INSTALL_ROOT="$FAKE_INSTALL_ROOT" \
   MG_INSTALL_OPERATOR_USER="testuser" \
   CHOWN_LOG="$CHOWN_LOG" \
   bash "$PROBE" >"${TMP}/probe.out" 2>&1; then
    ok "step ran without error against tmp install root"
else
    fail "step failed: $(cat "${TMP}/probe.out")"
fi

# 3a. Sink directory was created and has mode 0775.
sink_dir="${FAKE_INSTALL_ROOT}/cron_tracking/scanner_discovery"
if [[ -d "$sink_dir" ]]; then
    sink_mode="$(stat -c '%a' "$sink_dir" 2>/dev/null || stat -f '%Lp' "$sink_dir" 2>/dev/null)"
    if [[ "$sink_mode" == "775" ]]; then
        ok "scanner_discovery dir created with mode 0775"
    else
        fail "scanner_discovery dir mode is ${sink_mode}, expected 775"
    fi
else
    fail "scanner_discovery dir was not created"
fi

# 3b. Parent cron_tracking dir mode 0775.
parent_dir="${FAKE_INSTALL_ROOT}/cron_tracking"
parent_mode="$(stat -c '%a' "$parent_dir" 2>/dev/null || stat -f '%Lp' "$parent_dir" 2>/dev/null)"
if [[ "$parent_mode" == "775" ]]; then
    ok "cron_tracking parent dir mode 0775"
else
    fail "cron_tracking dir mode is ${parent_mode}, expected 775"
fi

# 3c. The pre-existing 0644 event file was chmod'd to 0664.
event_mode="$(stat -c '%a' "$upgrade_event" 2>/dev/null || stat -f '%Lp' "$upgrade_event" 2>/dev/null)"
if [[ "$event_mode" == "664" ]]; then
    ok "upgrade event file healed: 0644 -> 0664"
else
    fail "upgrade event file mode is ${event_mode}, expected 664"
fi

# 3d. The pre-existing 0644 latest_findings.json was chmod'd to 0664.
latest_mode="$(stat -c '%a' "$upgrade_latest" 2>/dev/null || stat -f '%Lp' "$upgrade_latest" 2>/dev/null)"
if [[ "$latest_mode" == "664" ]]; then
    ok "upgrade latest_findings.json healed: 0644 -> 0664"
else
    fail "upgrade latest_findings.json mode is ${latest_mode}, expected 664"
fi

# 3e. chown was invoked with the operator user, recursively on the sink.
if /usr/bin/grep -qE 'chown -R testuser:staff .*/cron_tracking/scanner_discovery' "$CHOWN_LOG"; then
    ok "chown -R testuser:staff ran against the scanner_discovery dir"
else
    fail "chown -R testuser:staff against scanner_discovery dir not seen — chown.log:\n$(cat "$CHOWN_LOG")"
fi
# And on the parent + dir individually (initial chown).
if /usr/bin/grep -qE 'chown testuser:staff .*/cron_tracking .*/cron_tracking/scanner_discovery' "$CHOWN_LOG"; then
    ok "chown testuser:staff ran against parent + sink dir initial pass"
else
    fail "initial parent+sink chown to testuser:staff not seen — chown.log:\n$(cat "$CHOWN_LOG")"
fi

# 3f. Idempotency: re-running over the now-normalised tree must succeed.
: > "$CHOWN_LOG"
if MG_INSTALL_ROOT="$FAKE_INSTALL_ROOT" \
   MG_INSTALL_OPERATOR_USER="testuser" \
   CHOWN_LOG="$CHOWN_LOG" \
   bash "$PROBE" >"${TMP}/probe2.out" 2>&1; then
    ok "step is idempotent (second run succeeded)"
else
    fail "second run failed: $(cat "${TMP}/probe2.out")"
fi
event_mode2="$(stat -c '%a' "$upgrade_event" 2>/dev/null || stat -f '%Lp' "$upgrade_event" 2>/dev/null)"
if [[ "$event_mode2" == "664" ]]; then
    ok "second run kept event file at 0664"
else
    fail "second run changed event file mode to ${event_mode2}"
fi

# ---------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------
echo "  passed: ${pass_count}"
echo "  failed: ${fail_count}"

if (( fail_count > 0 )); then
    exit 1
fi
exit 0
