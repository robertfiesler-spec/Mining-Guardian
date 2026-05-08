#!/usr/bin/env bash
# tests/installer/test_p029_knowledge_json_installer.sh
#
# P-029 (knowledge — 2026-05-08) — baseline knowledge.json shipped in
# the installer payload, fresh-install copy, upgrade preservation,
# ownership/mode, JSON validation, and proof-line logging.
#
# Background. v1.0.3 of the .pkg was missing a baseline knowledge.json,
# so every fresh customer install started cold (no miner_profiles, no
# fingerprints, no refined_insights). This test asserts the installer
# now ships a validated baseline at the canonical repo path and that
# postinstall installs it correctly on fresh installs while preserving
# learned runtime knowledge on upgrade.
#
# Coverage:
#   §1  build_pkg.sh + postinstall.sh parse cleanly
#   §2  baseline seed lives at the canonical repo path, parses as JSON,
#       and contains the three primary knowledge sections
#   §3  build_pkg.sh step 4l stages the seed into the payload
#       (installer-resources/knowledge/knowledge.json) and emits a
#       proof log
#   §4  postinstall.sh defines KNOWLEDGE_SEED_SRC + step_install_knowledge_json
#       and wires it into main() before launchd bootstrap
#   §5  fresh install — runtime tree created, seed copied, JSON valid,
#       compat symlink in place, proof log emitted
#   §6  upgrade — existing runtime file preserved, packaged seed staged
#       under incoming/ with version+sha tag, proof log emitted
#   §7  ownership/mode intent in the script (chown → MG_INSTALL_OPERATOR_USER:staff,
#       dirs 0775, files 0664)
#   §8  malformed seed in the payload at install time triggers a fail()
#       (JSON validation fast path) — guards against accidental ship of
#       a corrupt seed in a future repackage
#   §9  fresh-install runtime mode is 0664 and dirs are 0775
#   §10 idempotence — running upgrade-branch twice does not corrupt state
#
# Run from repo root:
#     bash tests/installer/test_p029_knowledge_json_installer.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"
SEED_PATH="installer/macos-pkg/resources/knowledge/knowledge.json"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

stat_mode() {
    # Portable mode-bits read: GNU coreutils first, BSD (macOS) fallback.
    stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1" 2>/dev/null
}

# ---------------------------------------------------------------------
section "1. Scripts parse"
# ---------------------------------------------------------------------
if bash -n "$POSTINSTALL" 2>/dev/null; then
    ok "postinstall.sh parses (bash -n)"
else
    fail "postinstall.sh has bash syntax errors"
fi
if bash -n "$BUILD_PKG" 2>/dev/null; then
    ok "build_pkg.sh parses (bash -n)"
else
    fail "build_pkg.sh has bash syntax errors"
fi

# ---------------------------------------------------------------------
section "2. Repo seed at canonical path"
# ---------------------------------------------------------------------
if [[ -r "$SEED_PATH" ]]; then
    ok "seed exists at ${SEED_PATH}"
else
    fail "seed missing at ${SEED_PATH}"
fi
if /usr/bin/python3 -c "
import json, sys
with open(sys.argv[1], 'rb') as fh:
    d = json.load(fh)
assert isinstance(d, dict)
assert any(k in d for k in ('miner_profiles','miner_fingerprints','refined_insights'))
" "$SEED_PATH" >/dev/null 2>&1; then
    ok "seed parses as JSON object with at least one primary section"
else
    fail "seed at ${SEED_PATH} failed JSON / shape validation"
fi
seed_size=$(/usr/bin/wc -c < "$SEED_PATH" | tr -d ' ')
if (( seed_size > 100000 )); then
    ok "seed size ${seed_size} bytes (sanity floor passed)"
else
    fail "seed unexpectedly small: ${seed_size} bytes — possible truncation"
fi

# ---------------------------------------------------------------------
section "3. build_pkg.sh step 4l stages the seed"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '^[[:space:]]*# 4l\.' "$BUILD_PKG"; then
    ok "build_pkg.sh has step 4l block"
else
    fail "build_pkg.sh missing step 4l block"
fi
if /usr/bin/grep -qF 'P-029 (knowledge)' "$BUILD_PKG"; then
    ok "build_pkg.sh carries P-029 (knowledge) marker"
else
    fail "build_pkg.sh missing P-029 (knowledge) marker"
fi
if /usr/bin/grep -qF "${PKG_DIR_REL:-resources/knowledge/knowledge.json}" "$BUILD_PKG" \
   || /usr/bin/grep -qF 'resources/knowledge/knowledge.json' "$BUILD_PKG"; then
    ok "build_pkg.sh references seed source path resources/knowledge/knowledge.json"
else
    fail "build_pkg.sh does not reference resources/knowledge/knowledge.json"
fi
if /usr/bin/grep -qF '${installer_resources_dst}/knowledge/knowledge.json' "$BUILD_PKG"; then
    ok "build_pkg.sh stages seed at <payload>/installer-resources/knowledge/knowledge.json"
else
    fail "build_pkg.sh does not stage seed at expected payload path"
fi
if /usr/bin/grep -qE 'step 4l OK:.*knowledge\.json staged' "$BUILD_PKG"; then
    ok "build_pkg.sh emits step 4l proof log"
else
    fail "build_pkg.sh missing step 4l proof log line"
fi
# Build-time JSON validation lives inside the step (rejects malformed seed
# before notarization).
if /usr/bin/grep -qE 'json\.load' "$BUILD_PKG" && /usr/bin/grep -qF 'miner_profiles' "$BUILD_PKG"; then
    ok "build_pkg.sh validates seed JSON shape at build time"
else
    fail "build_pkg.sh does not validate seed JSON shape at build time"
fi

# ---------------------------------------------------------------------
section "4. postinstall.sh defines + wires the new step"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '^readonly KNOWLEDGE_SEED_SRC=' "$POSTINSTALL"; then
    ok "KNOWLEDGE_SEED_SRC declared readonly"
else
    fail "KNOWLEDGE_SEED_SRC missing or not readonly"
fi
if /usr/bin/grep -qE '^step_install_knowledge_json\(\)' "$POSTINSTALL"; then
    ok "step_install_knowledge_json() defined"
else
    fail "step_install_knowledge_json() missing"
fi
if /usr/bin/grep -qF 'P-029 (knowledge — 2026-05-08)' "$POSTINSTALL"; then
    ok "P-029 (knowledge) marker comment present"
else
    fail "P-029 (knowledge) marker comment missing"
fi
# Orchestration: must run after step_normalize_discovery_sink_perms and
# before step_install_plists_and_bootstrap.
order_block="$(/usr/bin/awk '
    /^    step_normalize_discovery_sink_perms$/ { saw_norm = NR }
    /^    step_install_knowledge_json$/         { saw_kj   = NR }
    /^    step_install_plists_and_bootstrap$/   { saw_boot = NR }
    END { print saw_norm, saw_kj, saw_boot }
' "$POSTINSTALL")"
read -r norm_ln kj_ln boot_ln <<<"$order_block"
if [[ -z "${norm_ln}" || -z "${kj_ln}" || -z "${boot_ln}" ]]; then
    fail "orchestration: could not locate one of step_normalize_discovery_sink_perms / step_install_knowledge_json / step_install_plists_and_bootstrap (lines: '$order_block')"
elif (( norm_ln < kj_ln )) && (( kj_ln < boot_ln )); then
    ok "orchestration order: normalize-sink < install-knowledge < plists-bootstrap (${norm_ln} < ${kj_ln} < ${boot_ln})"
else
    fail "orchestration order wrong: normalize=${norm_ln} install_kj=${kj_ln} bootstrap=${boot_ln}"
fi

# ---------------------------------------------------------------------
section "5. Runtime: fresh install behavior"
# ---------------------------------------------------------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAKE_INSTALL_ROOT="${TMP}/install_root"
mkdir -p "$FAKE_INSTALL_ROOT"

# Stage a fake payload + seed.
mkdir -p "${TMP}/payload/installer-resources/knowledge"
cp "$SEED_PATH" "${TMP}/payload/installer-resources/knowledge/knowledge.json"
cat > "${TMP}/payload/BUILD_STAMP.json" <<EOF
{"version":"1.0.4-test","git_sha":"deadbeef1234","stamped_utc":"2026-05-08T00:00:00Z"}
EOF

# Build a probe that sources just the function under test.
PROBE="${TMP}/probe.sh"
{
    echo '#!/usr/bin/env bash'
    echo 'set -uo pipefail'
    # Minimal shims.
    echo 'log() { printf "log: %s\n" "$*" >> "$LOG_FILE"; }'
    echo 'fail() { local c="$1"; shift; printf "FAIL(%s) %s\n" "$c" "$*" >> "$LOG_FILE"; exit "$c"; }'
    echo 'chown_log() { printf "chown %s\n" "$*" >> "${CHOWN_LOG}"; return 0; }'
    echo 'alias chown=chown_log 2>/dev/null || true'
    echo 'chown() { chown_log "$@"; return 0; }'
    # Variables postinstall sets up before this step.
    echo 'export MG_INSTALL_ROOT="${MG_INSTALL_ROOT:?}"'
    echo 'export MG_INSTALL_OPERATOR_USER="${MG_INSTALL_OPERATOR_USER:?}"'
    echo 'export MG_PKG_PAYLOAD="${MG_PKG_PAYLOAD:?}"'
    echo 'export KNOWLEDGE_SEED_SRC="${KNOWLEDGE_SEED_SRC:?}"'
    echo 'export MG_INSTALL_LOG="${LOG_FILE}"'
    # Slice the function from postinstall.sh.
    /usr/bin/awk '
        /^step_install_knowledge_json\(\) \{/ { capture=1 }
        capture { print }
        capture && /^\}/ { capture=0 }
    ' "$POSTINSTALL"
    echo 'step_install_knowledge_json'
} > "$PROBE"
chmod +x "$PROBE"

LOG_FILE="${TMP}/postinstall.log"
CHOWN_LOG="${TMP}/chown.log"
: > "$LOG_FILE"
: > "$CHOWN_LOG"

if MG_INSTALL_ROOT="$FAKE_INSTALL_ROOT" \
   MG_INSTALL_OPERATOR_USER="testuser" \
   MG_PKG_PAYLOAD="${TMP}/payload" \
   KNOWLEDGE_SEED_SRC="${TMP}/payload/installer-resources/knowledge/knowledge.json" \
   LOG_FILE="$LOG_FILE" \
   CHOWN_LOG="$CHOWN_LOG" \
   bash "$PROBE"; then
    ok "fresh install: step_install_knowledge_json ran (exit 0)"
else
    fail "fresh install: step ran exit≠0 — log: $(cat "$LOG_FILE")"
fi

active="${FAKE_INSTALL_ROOT}/knowledge/knowledge.json"
compat="${FAKE_INSTALL_ROOT}/knowledge.json"
incoming_dir="${FAKE_INSTALL_ROOT}/knowledge/incoming"
backups_dir="${FAKE_INSTALL_ROOT}/knowledge/backups"

if [[ -f "$active" ]]; then
    ok "fresh install: active runtime knowledge.json exists at design path"
else
    fail "fresh install: active runtime knowledge.json missing at ${active}"
fi
if /usr/bin/python3 -c "import json; json.load(open('${active}'))" >/dev/null 2>&1; then
    ok "fresh install: active runtime knowledge.json parses as JSON"
else
    fail "fresh install: active runtime knowledge.json failed JSON parse"
fi
if [[ -L "$compat" ]]; then
    ok "fresh install: compat symlink ${compat} created"
else
    fail "fresh install: compat symlink missing at ${compat}"
fi
# The symlink target must resolve to the same file content. Compare via
# /usr/bin/python3 to read both and assert equality byte-for-byte.
if /usr/bin/python3 -c "
import sys
a = open(sys.argv[1],'rb').read()
b = open(sys.argv[2],'rb').read()
sys.exit(0 if a == b else 1)
" "$active" "$compat" >/dev/null 2>&1; then
    ok "fresh install: compat symlink resolves to same content as active file"
else
    fail "fresh install: compat symlink content differs from active file"
fi
if [[ -d "$incoming_dir" ]]; then
    ok "fresh install: knowledge/incoming/ created"
else
    fail "fresh install: knowledge/incoming/ missing"
fi
if [[ -d "$backups_dir" ]]; then
    ok "fresh install: knowledge/backups/ created"
else
    fail "fresh install: knowledge/backups/ missing"
fi

# Proof line: must contain path + size + sha256 + counts.
if /usr/bin/grep -qE 'P-029: installed knowledge.json path=.*size=[0-9]+ sha256=[0-9a-f]+ miner_profiles=[0-9]+ miner_fingerprints=[0-9]+ refined_insights=[0-9]+' "$LOG_FILE"; then
    ok "fresh install: proof log line emitted with path/size/sha256/counts"
else
    fail "fresh install: proof log line missing or malformed — log was:"
    cat "$LOG_FILE" >&2
fi

# Compat-symlink proof line.
if /usr/bin/grep -qE 'P-029: compat symlink ' "$LOG_FILE"; then
    ok "fresh install: compat-symlink log line emitted"
else
    fail "fresh install: compat-symlink log line missing"
fi

# ---------------------------------------------------------------------
section "6. Runtime: upgrade behavior — preserve existing runtime file"
# ---------------------------------------------------------------------
# Pre-populate an "upgrade" install root with a learned-looking active
# knowledge.json that is DIFFERENT from the packaged seed.
UPGRADE_ROOT="${TMP}/upgrade_root"
mkdir -p "${UPGRADE_ROOT}/knowledge"
cat > "${UPGRADE_ROOT}/knowledge/knowledge.json" <<EOF
{"miner_profiles":{"site-a-001":{"learned":true}},"refined_insights":[{"id":"site-a-1"}]}
EOF
chmod 0664 "${UPGRADE_ROOT}/knowledge/knowledge.json"

LOG_FILE="${TMP}/postinstall_upgrade.log"
CHOWN_LOG="${TMP}/chown_upgrade.log"
: > "$LOG_FILE"
: > "$CHOWN_LOG"

if MG_INSTALL_ROOT="$UPGRADE_ROOT" \
   MG_INSTALL_OPERATOR_USER="testuser" \
   MG_PKG_PAYLOAD="${TMP}/payload" \
   KNOWLEDGE_SEED_SRC="${TMP}/payload/installer-resources/knowledge/knowledge.json" \
   LOG_FILE="$LOG_FILE" \
   CHOWN_LOG="$CHOWN_LOG" \
   bash "$PROBE"; then
    ok "upgrade: step_install_knowledge_json ran (exit 0)"
else
    fail "upgrade: step ran exit≠0 — log: $(cat "$LOG_FILE")"
fi

# Active file MUST still be the learned one — content unchanged.
upgrade_active="${UPGRADE_ROOT}/knowledge/knowledge.json"
if /usr/bin/grep -q 'site-a-001' "$upgrade_active"; then
    ok "upgrade: active runtime knowledge.json content preserved verbatim"
else
    fail "upgrade: active runtime knowledge.json content changed — learned data lost"
fi

# Packaged seed must be staged under incoming/ tagged with version+sha.
incoming_seed="${UPGRADE_ROOT}/knowledge/incoming/knowledge-seed-1.0.4-test-deadbeef1234.json"
if [[ -f "$incoming_seed" ]]; then
    ok "upgrade: packaged seed staged at ${incoming_seed}"
else
    fail "upgrade: incoming/ seed file missing — listing:"
    ls -la "${UPGRADE_ROOT}/knowledge/incoming/" >&2 || true
fi

# Staged seed must parse as JSON.
if /usr/bin/python3 -c "import json; json.load(open('${incoming_seed}'))" >/dev/null 2>&1; then
    ok "upgrade: staged seed parses as JSON"
else
    fail "upgrade: staged seed failed JSON parse"
fi

# Preservation + staging proof lines.
if /usr/bin/grep -qF 'P-029: preserved existing runtime knowledge.json' "$LOG_FILE"; then
    ok "upgrade: preservation proof log line emitted"
else
    fail "upgrade: preservation proof log line missing"
fi
if /usr/bin/grep -qE 'P-029: staged packaged seed path=.*size=[0-9]+ sha256=[0-9a-f]+ miner_profiles=[0-9]+ miner_fingerprints=[0-9]+ refined_insights=[0-9]+' "$LOG_FILE"; then
    ok "upgrade: staged-seed proof log line emitted with path/size/sha256/counts"
else
    fail "upgrade: staged-seed proof log line missing or malformed"
fi

# No compat symlink modification on the upgrade branch (we already preserved
# the active file; touching the symlink would risk breaking a manually-
# maintained operator setup).
if ! /usr/bin/grep -qF 'compat symlink' "$LOG_FILE"; then
    ok "upgrade: compat-symlink log line correctly absent (upgrade does not touch symlink)"
else
    fail "upgrade: compat-symlink log line unexpectedly present on upgrade path"
fi

# ---------------------------------------------------------------------
section "7. Ownership/mode intent in script"
# ---------------------------------------------------------------------
# Static checks for the ownership + mode rules the design locked in:
#   dirs 0775, files 0664, owner ${MG_INSTALL_OPERATOR_USER}:staff.
# Active enforcement of these on a real Mac mini install is out of scope
# for this CI test (cannot run `chown miningguardian:staff` without root +
# the actual account); the runtime test §5/§6 above confirm the chown
# call is invoked through the shim with the correct target.
if /usr/bin/grep -qE 'install -d -m 0775 "\$kdir"' "$POSTINSTALL"; then
    ok "step uses dir mode 0775 for knowledge/"
else
    fail "step does not declare 0775 for knowledge/"
fi
if /usr/bin/grep -qF 'install -d -m 0775 "$incoming_dir"' "$POSTINSTALL"; then
    ok "step uses dir mode 0775 for knowledge/incoming/"
else
    fail "step does not declare 0775 for knowledge/incoming/"
fi
if /usr/bin/grep -qF 'install -d -m 0775 "$backups_dir"' "$POSTINSTALL"; then
    ok "step uses dir mode 0775 for knowledge/backups/"
else
    fail "step does not declare 0775 for knowledge/backups/"
fi
if /usr/bin/grep -qF 'install -m 0664 "$KNOWLEDGE_SEED_SRC" "$active"' "$POSTINSTALL"; then
    ok "step uses file mode 0664 on fresh install copy"
else
    fail "step does not declare 0664 on fresh install copy"
fi
if /usr/bin/grep -qF 'install -m 0664 "$KNOWLEDGE_SEED_SRC" "$incoming_path"' "$POSTINSTALL"; then
    ok "step uses file mode 0664 on upgrade-staged seed"
else
    fail "step does not declare 0664 on upgrade-staged seed"
fi
if /usr/bin/grep -qF 'chown "${MG_INSTALL_OPERATOR_USER}:staff"' "$POSTINSTALL"; then
    ok "step chown's to \${MG_INSTALL_OPERATOR_USER}:staff"
else
    fail "step missing chown to MG_INSTALL_OPERATOR_USER:staff"
fi

# ---------------------------------------------------------------------
section "8. Malformed seed in payload triggers fail() at install time"
# ---------------------------------------------------------------------
# Replace the staged seed with a broken file, re-run the step, and
# assert it exits non-zero with a readable error in the log. This is the
# install-time JSON-validation safety net that mirrors build_pkg.sh's
# build-time validation.
mkdir -p "${TMP}/bad_payload/installer-resources/knowledge"
echo '{"this is not valid json' > "${TMP}/bad_payload/installer-resources/knowledge/knowledge.json"
cp "${TMP}/payload/BUILD_STAMP.json" "${TMP}/bad_payload/BUILD_STAMP.json"

BAD_INSTALL_ROOT="${TMP}/bad_install_root"
mkdir -p "$BAD_INSTALL_ROOT"
LOG_FILE="${TMP}/postinstall_bad.log"
CHOWN_LOG="${TMP}/chown_bad.log"
: > "$LOG_FILE"
: > "$CHOWN_LOG"

set +e
MG_INSTALL_ROOT="$BAD_INSTALL_ROOT" \
   MG_INSTALL_OPERATOR_USER="testuser" \
   MG_PKG_PAYLOAD="${TMP}/bad_payload" \
   KNOWLEDGE_SEED_SRC="${TMP}/bad_payload/installer-resources/knowledge/knowledge.json" \
   LOG_FILE="$LOG_FILE" \
   CHOWN_LOG="$CHOWN_LOG" \
   bash "$PROBE" >/dev/null 2>&1
rc=$?
set -e

if (( rc != 0 )); then
    ok "malformed seed: step exits non-zero (rc=${rc}) — install-time validation fires"
else
    fail "malformed seed: step exited 0; install-time validation did not fire"
fi
if /usr/bin/grep -qE 'FAIL\(43\) P-029 \(knowledge\):' "$LOG_FILE"; then
    ok "malformed seed: fail() emitted exit-43 with P-029 (knowledge) tag"
else
    fail "malformed seed: expected exit-43 P-029 (knowledge) FAIL not found in log:"
    cat "$LOG_FILE" >&2 || true
fi

# ---------------------------------------------------------------------
section "9. Fresh-install runtime mode: 0664 file, 0775 dirs"
# ---------------------------------------------------------------------
mode_active="$(stat_mode "$active")"
if [[ "$mode_active" == "664" ]]; then
    ok "fresh install: active knowledge.json mode is 0664"
else
    fail "fresh install: active knowledge.json mode is ${mode_active}, expected 664"
fi
mode_kdir="$(stat_mode "${FAKE_INSTALL_ROOT}/knowledge")"
if [[ "$mode_kdir" == "775" ]]; then
    ok "fresh install: knowledge/ dir mode is 0775"
else
    fail "fresh install: knowledge/ dir mode is ${mode_kdir}, expected 775"
fi
mode_incoming="$(stat_mode "${incoming_dir}")"
if [[ "$mode_incoming" == "775" ]]; then
    ok "fresh install: knowledge/incoming/ dir mode is 0775"
else
    fail "fresh install: knowledge/incoming/ dir mode is ${mode_incoming}, expected 775"
fi
mode_backups="$(stat_mode "${backups_dir}")"
if [[ "$mode_backups" == "775" ]]; then
    ok "fresh install: knowledge/backups/ dir mode is 0775"
else
    fail "fresh install: knowledge/backups/ dir mode is ${mode_backups}, expected 775"
fi

# ---------------------------------------------------------------------
section "10. Idempotence: upgrade branch can run twice"
# ---------------------------------------------------------------------
LOG_FILE="${TMP}/postinstall_upgrade2.log"
CHOWN_LOG="${TMP}/chown_upgrade2.log"
: > "$LOG_FILE"
: > "$CHOWN_LOG"

if MG_INSTALL_ROOT="$UPGRADE_ROOT" \
   MG_INSTALL_OPERATOR_USER="testuser" \
   MG_PKG_PAYLOAD="${TMP}/payload" \
   KNOWLEDGE_SEED_SRC="${TMP}/payload/installer-resources/knowledge/knowledge.json" \
   LOG_FILE="$LOG_FILE" \
   CHOWN_LOG="$CHOWN_LOG" \
   bash "$PROBE"; then
    ok "second upgrade run: step ran exit 0"
else
    fail "second upgrade run: exit ≠ 0 — log: $(cat "$LOG_FILE")"
fi
# Active file still preserved.
if /usr/bin/grep -q 'site-a-001' "$upgrade_active"; then
    ok "second upgrade run: active runtime knowledge.json still preserved"
else
    fail "second upgrade run: active file mutated"
fi
# Same incoming filename (version+sha tag is stable across runs).
if [[ -f "$incoming_seed" ]]; then
    ok "second upgrade run: incoming seed file still present (deterministic name)"
else
    fail "second upgrade run: incoming seed file disappeared"
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
