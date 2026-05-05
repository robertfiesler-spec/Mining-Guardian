#!/usr/bin/env bash
# tests/installer/test_postinstall_helper_user_resolver.sh
#
# D-18 P-018 — installer helper libs (install_colima.sh, install_ollama.sh)
# must resolve the operator account via the same `_op_user` chain that
# postinstall.sh exports as `MG_INSTALL_OPERATOR_USER`. The legacy
# `${SUDO_USER:-${USER}}` pattern resolved to `root` under Installer.app
# (USER=root, SUDO_USER unset) and would have:
#   * pointed `colima start` at /Users/root (does not exist),
#   * run `sudo -u root colima start` (wrong owner — colima state ends
#     up in /var/root/.colima rather than the operator's home),
#   * run `sudo -u root docker load` (cannot read the operator's docker
#     socket, which `colima start` created in the operator's home),
#   * pulled the LLM into /var/root/.ollama instead of the operator's
#     ~/.ollama (invisible to the launchd ollama service that runs as
#     the operator).
#
# P-016 fixed the same pattern in postinstall.sh; B-12 in
# `docs/LATENT_BUGS.md` tracked the unfixed helper-lib half. This test
# is the gate that B-12 stays closed.
#
# This test asserts:
#   1. No command-line `${SUDO_USER:-${USER}}` use remains in either
#      helper lib (comments are allowed for forensic context).
#   2. Each helper defines `_op_user` and consumes MG_INSTALL_OPERATOR_USER
#      as its first probe.
#   3. Each helper has the four documented probes (MG_INSTALL_OPERATOR_USER,
#      SUDO_USER, /dev/console, /Users/*/Desktop scan).
#   4. Each helper's `_op_user` refuses to silently return `root`.
#   5. Runtime: `_op_user` returns the exported `MG_INSTALL_OPERATOR_USER`
#      when set non-root.
#   6. Runtime: `_op_user` falls back to the Desktop scan when
#      MG_INSTALL_OPERATOR_USER is unset, SUDO_USER is unset, USER=root,
#      and /dev/console owner is `root` (the Installer.app environment).
#   7. Runtime: `_op_user` exits non-zero rather than returning `root`
#      when all probes fail (no console user, no Desktop conf anywhere).
#   8. P-018 reference present in each helper.
#   9. bash -n parse on both helpers.
#
# Run from repo root:
#     bash tests/installer/test_postinstall_helper_user_resolver.sh
#
# Exits 0 on success, non-zero on first failed assertion.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

COLIMA_LIB="installer/macos-pkg/scripts/lib/install_colima.sh"
OLLAMA_LIB="installer/macos-pkg/scripts/lib/install_ollama.sh"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# A grep for `${SUDO_USER:-${USER}}` substantive uses — strips off the
# `<file>:<line>:` prefix and excludes lines whose first non-whitespace
# character is `#` (i.e. shell comments, where the doc references live).
_n_legacy_uses() {
    local f="$1"
    # `grep -nE` prints `<line>:<content>`; sed strips the `<line>:`
    # prefix so the comment-line filter sees the original first column.
    /usr/bin/grep -nE 'SUDO_USER:-\$\{USER\}' "$f" 2>/dev/null \
        | /usr/bin/sed -E 's/^[0-9]+://' \
        | /usr/bin/grep -cvE '^[[:space:]]*#' || true
}

# ---------------------------------------------------------------------
section "1. Legacy \${SUDO_USER:-\${USER}} command-line uses eliminated"
# ---------------------------------------------------------------------
for f in "$COLIMA_LIB" "$OLLAMA_LIB"; do
    n="$(_n_legacy_uses "$f")"
    if [[ "${n:-0}" -eq 0 ]]; then
        ok "no command-line legacy uses in $(basename "$f")"
    else
        fail "${n} command-line legacy use(s) still in $(basename "$f")"
    fi
done

# ---------------------------------------------------------------------
section "2. _op_user defined and prefers MG_INSTALL_OPERATOR_USER"
# ---------------------------------------------------------------------
for f in "$COLIMA_LIB" "$OLLAMA_LIB"; do
    if /usr/bin/grep -q '^_op_user()' "$f"; then
        ok "_op_user() defined in $(basename "$f")"
    else
        fail "_op_user() missing from $(basename "$f")"
    fi
    if /usr/bin/grep -q 'MG_INSTALL_OPERATOR_USER:-' "$f"; then
        ok "$(basename "$f") consults MG_INSTALL_OPERATOR_USER"
    else
        fail "$(basename "$f") never reads MG_INSTALL_OPERATOR_USER — postinstall export goes unused"
    fi
done

# ---------------------------------------------------------------------
section "3. Four documented probes present in each helper"
# ---------------------------------------------------------------------
for f in "$COLIMA_LIB" "$OLLAMA_LIB"; do
    base="$(basename "$f")"
    if /usr/bin/grep -q 'SUDO_USER:-' "$f"; then
        ok "${base} probe 2: SUDO_USER fallback (guarded :-)"
    else
        fail "${base} probe 2: SUDO_USER fallback missing"
    fi
    if /usr/bin/grep -q "stat -f '%Su' /dev/console" "$f"; then
        ok "${base} probe 3: /dev/console owner via stat -f '%Su'"
    else
        fail "${base} probe 3: /dev/console probe missing"
    fi
    if /usr/bin/grep -q '/Users/\*' "$f" \
            && /usr/bin/grep -q 'MiningGuardian.conf' "$f"; then
        ok "${base} probe 4: /Users/*/Desktop/MiningGuardian.conf scan"
    else
        fail "${base} probe 4: /Users/*/Desktop scan missing"
    fi
done

# ---------------------------------------------------------------------
section "4. _op_user refuses to silently return root"
# ---------------------------------------------------------------------
for f in "$COLIMA_LIB" "$OLLAMA_LIB"; do
    base="$(basename "$f")"
    # Both fallback chains explicitly skip a value of "root" before
    # returning. Spot-check by counting `!= "root"` guards.
    n="$(/usr/bin/grep -cE '!=[[:space:]]*"root"' "$f" || true)"
    if [[ "${n:-0}" -ge 3 ]]; then
        ok "${base} guards against returning 'root' (${n} != \"root\" checks)"
    else
        fail "${base} only ${n} != \"root\" check(s) — needs ≥3 (MG_INSTALL_OPERATOR_USER, SUDO_USER, /dev/console)"
    fi
    if /usr/bin/grep -q 'refusing to run' "$f"; then
        ok "${base} _die's with explicit refusal message when no operator found"
    else
        fail "${base} missing explicit 'refusing to run' fail-loud message"
    fi
done

# ---------------------------------------------------------------------
section "5. P-018 audit marker present in each helper"
# ---------------------------------------------------------------------
for f in "$COLIMA_LIB" "$OLLAMA_LIB"; do
    if /usr/bin/grep -q 'P-018' "$f"; then
        ok "$(basename "$f") cites P-018"
    else
        fail "$(basename "$f") missing P-018 citation"
    fi
done

# ---------------------------------------------------------------------
section "6. bash -n parse"
# ---------------------------------------------------------------------
for f in "$COLIMA_LIB" "$OLLAMA_LIB"; do
    if bash -n "$f" 2>/dev/null; then
        ok "$(basename "$f") parses"
    else
        fail "$(basename "$f") has bash syntax errors"
    fi
done

# ---------------------------------------------------------------------
section "7. Runtime: _op_user prefers MG_INSTALL_OPERATOR_USER"
# ---------------------------------------------------------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Extract just the _op_user function body from a helper into a small
# driver that exercises it under controlled env. Both helpers carry the
# same resolver, so we test from install_colima.sh as the reference.
EXTRACT_OP="${TMP}/op_user.sh"
{
    echo '#!/usr/bin/env bash'
    echo 'set -uo pipefail'
    # _log + _die need to exist for the resolver to fail closed.
    echo '_log() { echo "[test] $*" >&2; }'
    echo '_die() { _log "FATAL $*"; return 1; }'
    /usr/bin/awk '
        /^_op_user\(\)/ { capture=1 }
        capture { print }
        capture && /^}$/ { capture=0 }
    ' "$COLIMA_LIB"
} > "$EXTRACT_OP"

# Test 7a — exported MG_INSTALL_OPERATOR_USER takes precedence.
out="$(MG_INSTALL_OPERATOR_USER=miningguardian \
        env -i HOME=/var/root PATH=/usr/bin:/bin USER=root \
        MG_INSTALL_OPERATOR_USER=miningguardian \
        bash -c "source '$EXTRACT_OP'; _op_user" 2>&1 || true)"
if [[ "$out" == "miningguardian" ]]; then
    ok "_op_user honors exported MG_INSTALL_OPERATOR_USER"
else
    fail "_op_user did not honor MG_INSTALL_OPERATOR_USER: got '${out}'"
fi

# Test 7b — when MG_INSTALL_OPERATOR_USER='root' (e.g. postinstall fell
# all the way through), the resolver MUST NOT just hand back 'root'.
# Stub /usr/bin/stat to a script that returns empty so the /dev/console
# probe yields no candidate; build a fake /Users tree that resembles
# the real Mini.
STUB_BIN="${TMP}/bin"
mkdir -p "$STUB_BIN"
cat > "${STUB_BIN}/stat" <<'STUB'
#!/usr/bin/env bash
if [[ "${1:-}" == "-f" && "${2:-}" == "%Su" ]]; then
    printf 'root'
    exit 0
fi
exit 1
STUB
chmod +x "${STUB_BIN}/stat"

FAKE_USERS="${TMP}/Users"
mkdir -p "${FAKE_USERS}/miningguardian/Desktop"
touch "${FAKE_USERS}/miningguardian/Desktop/MiningGuardian.conf"

# Build a path-shadowed resolver that points the /Users glob at the
# fake tree (same trick as test_postinstall_user_resolver.sh).
EXTRACT_FAKE="${TMP}/op_user_fake.sh"
{
    echo '#!/usr/bin/env bash'
    echo 'set -uo pipefail'
    echo '_log() { echo "[test] $*" >&2; }'
    echo '_die() { _log "FATAL $*"; return 1; }'
    echo "/usr/bin/stat() { '${STUB_BIN}/stat' \"\$@\"; }"
    /usr/bin/awk -v fake="${FAKE_USERS}" '
        /^_op_user\(\)/ { capture=1 }
        capture {
            sub(/\/Users\/\*/, fake "/*")
            print
        }
        capture && /^}$/ { capture=0 }
    ' "$COLIMA_LIB"
} > "$EXTRACT_FAKE"

# Test 7c — Installer.app env (MG_INSTALL_OPERATOR_USER unset, SUDO_USER
# unset, USER=root, /dev/console owner=root) — resolver MUST fall through
# to the Desktop scan and return 'miningguardian'.
out="$(env -i HOME=/var/root PATH=/usr/bin:/bin USER=root \
        bash -c "source '$EXTRACT_FAKE'; _op_user" 2>&1 || true)"
if [[ "$out" == "miningguardian" ]]; then
    ok "_op_user falls through to Desktop scan under Installer.app env (USER=root, console=root)"
elif [[ "$out" == "root" ]]; then
    fail "_op_user returned 'root' under Installer.app env — would still hit /Users/root (the B-12 symptom)"
else
    fail "_op_user returned unexpected value under Installer.app env: '${out}'"
fi

# Test 7d — when nothing resolves (no console user, no Desktop conf
# anywhere), the resolver MUST return non-zero rather than print 'root'.
EXTRACT_EMPTY="${TMP}/op_user_empty.sh"
EMPTY_USERS="${TMP}/EmptyUsers"
mkdir -p "$EMPTY_USERS"
{
    echo '#!/usr/bin/env bash'
    echo 'set -uo pipefail'
    echo '_log() { echo "[test] $*" >&2; }'
    echo '_die() { _log "FATAL $*"; return 1; }'
    echo "/usr/bin/stat() { '${STUB_BIN}/stat' \"\$@\"; }"
    /usr/bin/awk -v fake="${EMPTY_USERS}" '
        /^_op_user\(\)/ { capture=1 }
        capture {
            sub(/\/Users\/\*/, fake "/*")
            print
        }
        capture && /^}$/ { capture=0 }
    ' "$COLIMA_LIB"
} > "$EXTRACT_EMPTY"

# Use a wrapper that captures both stdout and exit code separately.
rc=0
out="$(env -i HOME=/var/root PATH=/usr/bin:/bin USER=root \
        bash -c "source '$EXTRACT_EMPTY'; _op_user" 2>/dev/null)" || rc=$?
if (( rc != 0 )); then
    ok "_op_user returns non-zero when no operator account resolves (rc=${rc})"
else
    fail "_op_user returned exit 0 with no resolvable operator — would let install continue as root"
fi
if [[ "$out" == "root" ]]; then
    fail "_op_user printed 'root' as last-ditch fallback (must be empty/fail)"
else
    ok "_op_user does not print 'root' as last-ditch fallback (got: '${out}')"
fi

# ---------------------------------------------------------------------
section "8. install_colima_runtime + provision_postgres + load_postgres_image use _op_user"
# ---------------------------------------------------------------------
# Light-touch pattern check: every place that previously took a username
# under sudo / chown should now derive it via _op_user. Count call sites.
op_user_calls="$(/usr/bin/grep -cE '_op_user' "$COLIMA_LIB" || true)"
if [[ "${op_user_calls:-0}" -ge 3 ]]; then
    ok "install_colima.sh has ${op_user_calls} _op_user call sites (≥3 expected: install_colima_runtime, load_postgres_image, provision_postgres)"
else
    fail "install_colima.sh only has ${op_user_calls} _op_user call site(s)"
fi

op_user_calls_ollama="$(/usr/bin/grep -cE '_op_user' "$OLLAMA_LIB" || true)"
if [[ "${op_user_calls_ollama:-0}" -ge 1 ]]; then
    ok "install_ollama.sh has ${op_user_calls_ollama} _op_user call site(s) (≥1 expected: pull_llm_model)"
else
    fail "install_ollama.sh has no _op_user call site"
fi

# ---------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------
echo
echo "Passed: $pass_count"
echo "Failed: $fail_count"
if (( fail_count > 0 )); then
    exit 1
fi
exit 0
