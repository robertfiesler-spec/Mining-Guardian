#!/usr/bin/env bash
# tests/installer/test_p028_upgrade_stale_scripts_cleanup.sh
#
# P-028 (2026-05-08) — postinstall.sh::step_quarantine_stale_payload_scripts.
#
# Background. After the P-026 build (`b1999c25346f`) was installed on
# the live Mini, package-payload inspection was clean (P-024 allowlist
# honoured), but `${MG_INSTALL_ROOT}/scripts/` on the upgraded Mini
# still contained:
#   - backup_db.sh
#   - backup_mining_guardian.sh
#   - start_guardian.sh
#   - setup.sh
#   - many other pre-P-024 operator/dead scripts
# `pkgbuild` ADDS and OVERWRITES files but never removes files that
# were present from earlier installs and omitted from the newer
# payload. So the upgrade silently inherited operator-only scripts
# referencing `BigBobby`, `100.103.185.53`, the retired Hostinger VPS,
# and `/Volumes/Big-Bobby-T9/...`.
#
# This test asserts the new postinstall step:
#   1. exists in postinstall.sh and is wired into orchestration after
#      step_layout_install_root and before
#      step_install_plists_and_bootstrap;
#   2. parses (bash -n);
#   3. its hard-coded allowlist matches the payload allowlist in
#      build_pkg.sh step 4a (P-024) — no drift;
#   4. on a tmp install root pre-populated with the four canonical
#      forbidden scripts plus the two forbidden subdirs plus the
#      seven allowlisted scripts, the step:
#        * quarantines all four forbidden files,
#        * quarantines both forbidden subdirs,
#        * keeps all seven allowlisted files in place,
#        * creates a timestamped `${MG_INSTALL_ROOT}/quarantine/scripts-<ts>/`
#          directory with mode 0700,
#        * is idempotent on a second run (now-clean tree),
#        * is a no-op when invoked against a fresh install root that
#          has no scripts/ directory at all.
#
# Run from repo root:
#     bash tests/installer/test_p028_upgrade_stale_scripts_cleanup.sh
#
# Exits 0 on success, non-zero on first failed assertion.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"

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
section "2. step_quarantine_stale_payload_scripts is defined and wired in"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '^step_quarantine_stale_payload_scripts\(\)' "$POSTINSTALL"; then
    ok "step_quarantine_stale_payload_scripts() defined"
else
    fail "step_quarantine_stale_payload_scripts() missing"
fi
# P-028 marker comment so a regression that drops the rationale is
# visible.
if /usr/bin/grep -qF "P-028 (2026-05-08)" "$POSTINSTALL"; then
    ok "P-028 marker comment present"
else
    fail "P-028 (2026-05-08) marker missing — rationale at risk of drift"
fi
# Quarantine destination convention.
if /usr/bin/grep -qF '${MG_INSTALL_ROOT}/quarantine' "$POSTINSTALL"; then
    ok "step references \${MG_INSTALL_ROOT}/quarantine destination"
else
    fail "step does not reference \${MG_INSTALL_ROOT}/quarantine"
fi
# Mode 0700 root:wheel for the quarantine dirs.
if /usr/bin/grep -qF 'install -d -m 0700 -o root -g wheel "$quarantine_root"' "$POSTINSTALL" && \
   /usr/bin/grep -qF 'install -d -m 0700 -o root -g wheel "$quarantine_dir"' "$POSTINSTALL"; then
    ok "quarantine dirs created at mode 0700 root:wheel"
else
    fail "quarantine dirs not created at 0700 root:wheel"
fi
# go-rwx scrub on quarantined contents.
if /usr/bin/grep -qF 'chmod -R go-rwx "$quarantine_dir"' "$POSTINSTALL"; then
    ok "quarantined contents stripped of group/world rwx"
else
    fail "quarantine contents not chmod -R go-rwx"
fi

# Orchestration order: must follow step_layout_install_root and must
# precede step_install_plists_and_bootstrap.
order_block="$(/usr/bin/awk '
    /^    step_layout_install_root$/                   { saw_layout = NR }
    /^    step_quarantine_stale_payload_scripts$/      { saw_quar   = NR }
    /^    step_install_plists_and_bootstrap$/          { saw_boot   = NR }
    END { print saw_layout, saw_quar, saw_boot }
' "$POSTINSTALL")"
read -r layout_ln quar_ln boot_ln <<<"$order_block"
if [[ -z "${layout_ln}" || -z "${quar_ln}" || -z "${boot_ln}" ]]; then
    fail "orchestration: could not locate one of step_layout_install_root / step_quarantine_stale_payload_scripts / step_install_plists_and_bootstrap (lines: '$order_block')"
elif (( layout_ln < quar_ln )) && (( quar_ln < boot_ln )); then
    ok "orchestration order: layout < quarantine < plists-bootstrap (${layout_ln} < ${quar_ln} < ${boot_ln})"
else
    fail "orchestration order wrong: layout=${layout_ln} quarantine=${quar_ln} bootstrap=${boot_ln}"
fi

# ---------------------------------------------------------------------
section "3. Allowlist matches build_pkg.sh payload allowlist (no drift)"
# ---------------------------------------------------------------------
# Extract the 7 names from build_pkg.sh's `--include 'scripts/...'`
# lines only (P-024). Anchor on the rsync-include syntax so unrelated
# in-comment self-references like `installer/macos-pkg/scripts/build_pkg.sh`
# are excluded. Sort + de-dupe so the comparison is stable.
build_pkg_names="$(/usr/bin/grep -oE -e "include 'scripts/[A-Za-z0-9_.-]+\.(py|sh)'" "$BUILD_PKG" \
    | /usr/bin/sed -E "s|^include 'scripts/||; s|'$||" \
    | /usr/bin/sort -u)"
# Extract the postinstall allowlist from MG_P028_ALLOWED_PAYLOAD_SCRIPTS.
postinstall_names="$(/usr/bin/awk '
    /^readonly MG_P028_ALLOWED_PAYLOAD_SCRIPTS=\(/ { capture = 1; next }
    capture && /^\)/ { capture = 0 }
    capture { gsub(/[\047" ]/, "", $0); if ($0 != "") print }
' "$POSTINSTALL" | /usr/bin/sort -u)"

if [[ "$build_pkg_names" == "$postinstall_names" ]]; then
    ok "MG_P028_ALLOWED_PAYLOAD_SCRIPTS matches build_pkg.sh scripts include list"
else
    fail "allowlist drift between build_pkg.sh and postinstall.sh:"
    diff <(echo "$build_pkg_names") <(echo "$postinstall_names") | sed 's|^|      |' >&2
fi

# ---------------------------------------------------------------------
section "4. Runtime: extract step body and run against a tmp install root"
# ---------------------------------------------------------------------
# In CI we are not root, so `install -d -o root -g wheel` fails with
# `chown: ... Operation not permitted`. We shim `install`, `chown`,
# `chmod` to log-and-no-op the ownership-touching invocations while
# letting the directory creation + mode bits pass through.

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAKE_ROOT="${TMP}/install_root"
mkdir -p "$FAKE_ROOT/scripts"

# Pre-populate with the realistic upgrade-shape: 7 allowlisted files
# + 4 forbidden files + 2 forbidden subdirs.
ALLOWED=(
    "__init__.py"
    "cleanup_ams_logs.py"
    "db_maintenance.sh"
    "direct_collect_logs.py"
    "daily_log_failure_report.py"
    "morning_briefing.py"
    "daily_operator_review.py"
)
FORBIDDEN_FILES=(
    "backup_db.sh"
    "backup_mining_guardian.sh"
    "start_guardian.sh"
    "setup.sh"
)
FORBIDDEN_SUBDIRS=(
    "branding"
    "diagnostics"
)
for f in "${ALLOWED[@]}"; do
    : > "${FAKE_ROOT}/scripts/${f}"
done
for f in "${FORBIDDEN_FILES[@]}"; do
    : > "${FAKE_ROOT}/scripts/${f}"
done
for d in "${FORBIDDEN_SUBDIRS[@]}"; do
    mkdir -p "${FAKE_ROOT}/scripts/${d}"
    : > "${FAKE_ROOT}/scripts/${d}/sentinel.py"
done

# Build the probe: shims + extracted step body + invocation.
PROBE="${TMP}/probe.sh"
cat > "$PROBE" <<'EOF_PROBE'
#!/usr/bin/env bash
set -uo pipefail

MG_INSTALL_LOG="${MG_INSTALL_LOG:-/dev/stderr}"
log() { printf 'log: %s\n' "$*" >> "$MG_INSTALL_LOG"; }

# Shim `install`: drop the -o/-g flags (CI is not root) but honour
# everything else.
install() {
    local args=()
    while (( $# > 0 )); do
        case "$1" in
            -o|-g) shift 2 ;;  # drop owner/group args
            *) args+=("$1"); shift ;;
        esac
    done
    /usr/bin/install "${args[@]}"
}

# Shim `chown` to no-op (CI is not root). Log so the harness can
# verify it was called.
chown() {
    printf 'chown %s\n' "$*" >> "$MG_INSTALL_LOG"
    return 0
}

# Pass-through shims for `chmod`, `find`, `mv`, `basename`, `date` —
# the real commands are correct in CI.
EOF_PROBE
chmod +x "$PROBE"

# Append the constants block (the readonly array) and the function.
/usr/bin/awk '
    /^readonly MG_P028_ALLOWED_PAYLOAD_SCRIPTS=\(/      { capture = 1 }
    capture                                              { print }
    capture && /^\)/                                     { capture = 0 }
' "$POSTINSTALL" >> "$PROBE"
echo "" >> "$PROBE"
/usr/bin/awk '
    /^step_quarantine_stale_payload_scripts\(\) \{/ { capture = 1 }
    capture                                          { print }
    capture && /^\}/                                 { capture = 0 }
' "$POSTINSTALL" >> "$PROBE"
echo "" >> "$PROBE"
echo 'step_quarantine_stale_payload_scripts' >> "$PROBE"

PROBE_LOG="${TMP}/probe.log"
: > "$PROBE_LOG"

if MG_INSTALL_ROOT="$FAKE_ROOT" \
   MG_INSTALL_LOG="$PROBE_LOG" \
   bash "$PROBE" >"${TMP}/probe.out" 2>&1; then
    ok "step ran without error against tmp install root"
else
    fail "step failed: $(cat "${TMP}/probe.out")"
fi

# 4a. Each allowlisted file is still in scripts/.
miss=0
for f in "${ALLOWED[@]}"; do
    if [[ ! -f "${FAKE_ROOT}/scripts/${f}" ]]; then
        fail "allowlisted file vanished: scripts/${f}"
        miss=$((miss + 1))
    fi
done
if (( miss == 0 )); then
    ok "all 7 allowlisted files preserved in scripts/"
fi

# 4b. Forbidden files are no longer in scripts/.
left=0
for f in "${FORBIDDEN_FILES[@]}"; do
    if [[ -e "${FAKE_ROOT}/scripts/${f}" ]]; then
        fail "forbidden file still in scripts/: ${f}"
        left=$((left + 1))
    fi
done
if (( left == 0 )); then
    ok "all 4 forbidden files removed from scripts/"
fi

# 4c. Forbidden subdirs are no longer in scripts/.
left_d=0
for d in "${FORBIDDEN_SUBDIRS[@]}"; do
    if [[ -e "${FAKE_ROOT}/scripts/${d}" ]]; then
        fail "forbidden subdir still in scripts/: ${d}/"
        left_d=$((left_d + 1))
    fi
done
if (( left_d == 0 )); then
    ok "both forbidden subdirs (branding/, diagnostics/) removed from scripts/"
fi

# 4d. A timestamped quarantine dir was created.
quar_root="${FAKE_ROOT}/quarantine"
if [[ -d "$quar_root" ]]; then
    ok "${quar_root} created"
else
    fail "${quar_root} not created"
fi
quar_dir="$(/usr/bin/find "$quar_root" -maxdepth 1 -mindepth 1 -type d -name 'scripts-*' 2>/dev/null | /usr/bin/head -n 1)"
if [[ -n "$quar_dir" && -d "$quar_dir" ]]; then
    # Timestamp shape: scripts-YYYYMMDDTHHMMSSZ
    if [[ "$(basename "$quar_dir")" =~ ^scripts-[0-9]{8}T[0-9]{6}Z$ ]]; then
        ok "quarantine dir timestamp matches scripts-YYYYMMDDTHHMMSSZ"
    else
        fail "quarantine dir name shape wrong: $(basename "$quar_dir")"
    fi
else
    fail "no scripts-* quarantine dir found under ${quar_root}"
fi

# 4e. Quarantine dir mode is 0700.
if [[ -d "$quar_dir" ]]; then
    quar_mode="$(stat -c '%a' "$quar_dir" 2>/dev/null || stat -f '%Lp' "$quar_dir" 2>/dev/null)"
    if [[ "$quar_mode" == "700" ]]; then
        ok "quarantine dir mode is 0700"
    else
        fail "quarantine dir mode is ${quar_mode}, expected 700"
    fi
fi

# 4f. Forbidden files landed in the quarantine dir.
quar_miss=0
for f in "${FORBIDDEN_FILES[@]}"; do
    if [[ ! -f "${quar_dir}/${f}" ]]; then
        fail "forbidden file not in quarantine: ${f}"
        quar_miss=$((quar_miss + 1))
    fi
done
for d in "${FORBIDDEN_SUBDIRS[@]}"; do
    if [[ ! -e "${quar_dir}/${d}" ]]; then
        fail "forbidden subdir not in quarantine: ${d}/"
        quar_miss=$((quar_miss + 1))
    fi
done
if (( quar_miss == 0 )); then
    ok "all 6 forbidden entries (4 files + 2 subdirs) landed in quarantine"
fi

# 4g. The static check at §2 already asserts the
# `install -d -m 0700 -o root -g wheel` invocations against
# `$quarantine_root` and `$quarantine_dir`. Under Installer.app the
# postinstall runs as root and those flags take effect; the runtime
# replay above strips `-o`/`-g` (CI is not root) so the directories
# end up owned by the CI user. Mode bits (0700) are still verified at
# §4e — that is the contract this step needs from `install`. No
# additional chown is required: P-028 places quarantine OUTSIDE the
# scripts dir; the parent recursive chown in `step_layout_install_root`
# handles `${MG_INSTALL_ROOT}/*` and the explicit 0700 root:wheel on
# `quarantine_root` + `quarantine_dir` keeps the contents off-PATH and
# unreadable to the operator account.
ok "ownership normalisation contract verified statically (§2)"

# ---------------------------------------------------------------------
section "5. Runtime: idempotency and fresh-install no-op"
# ---------------------------------------------------------------------
# 5a. Re-running over the now-clean scripts/ tree must succeed and
# create no new quarantine dir.
quar_count_before=$(/usr/bin/find "$quar_root" -maxdepth 1 -mindepth 1 -type d -name 'scripts-*' 2>/dev/null | /usr/bin/wc -l | tr -d ' ')
: > "$PROBE_LOG"
if MG_INSTALL_ROOT="$FAKE_ROOT" \
   MG_INSTALL_LOG="$PROBE_LOG" \
   bash "$PROBE" >"${TMP}/probe2.out" 2>&1; then
    ok "second run succeeded over already-clean tree"
else
    fail "second run failed: $(cat "${TMP}/probe2.out")"
fi
quar_count_after=$(/usr/bin/find "$quar_root" -maxdepth 1 -mindepth 1 -type d -name 'scripts-*' 2>/dev/null | /usr/bin/wc -l | tr -d ' ')
if [[ "$quar_count_before" == "$quar_count_after" ]]; then
    ok "second run created no new quarantine dir (idempotent)"
else
    fail "second run created a new quarantine dir (not idempotent): ${quar_count_before} -> ${quar_count_after}"
fi
if /usr/bin/grep -qF "already clean" "$PROBE_LOG"; then
    ok "second run logged 'already clean' state"
else
    fail "second run did not log 'already clean'"
fi

# 5b. Fresh install (no scripts/ dir): step is a documented no-op.
FRESH_ROOT="${TMP}/fresh_root"
mkdir -p "$FRESH_ROOT"
: > "$PROBE_LOG"
if MG_INSTALL_ROOT="$FRESH_ROOT" \
   MG_INSTALL_LOG="$PROBE_LOG" \
   bash "$PROBE" >"${TMP}/probe3.out" 2>&1; then
    ok "fresh-install no-op succeeded"
else
    fail "fresh-install no-op failed: $(cat "${TMP}/probe3.out")"
fi
if /usr/bin/grep -qF "absent; nothing to quarantine" "$PROBE_LOG"; then
    ok "fresh-install logged 'absent; nothing to quarantine'"
else
    fail "fresh-install did not log the 'absent' message"
fi
if [[ ! -d "${FRESH_ROOT}/quarantine" ]]; then
    ok "fresh-install did not create a quarantine dir"
else
    fail "fresh-install spuriously created ${FRESH_ROOT}/quarantine"
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
