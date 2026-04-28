#!/bin/bash
# installer/macos-pkg/scripts/build_pkg.sh
#
# Build the Mining Guardian macOS .pkg (Q1 hybrid ~500 MB shape).
#
# This script implements the 9-step pipeline documented in
# installer/macos-pkg/README.md. It MUST be run on the operator's
# Mac (the build host that has the Apple Developer cert in its
# keychain + the .p8 private key on disk). It will refuse to run on
# anything else.
#
# Inputs (read at build time, NOT committed):
#   /Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt
#       Plain-text key=value file with these entries (one per line):
#         APPLE_TEAM_ID=ARJZ5FYU94                # public, also in repo
#         APPLE_NOTARIZATION_KEY_ID=FPZJ87B3QF    # public, also in repo
#         APPLE_NOTARIZATION_ISSUER_UUID=<uuid>   # PRIVATE
#         APPLE_NOTARIZATION_KEY_PATH=/path/to.p8 # PRIVATE
#         APPLE_DEV_ID_INSTALLER="Developer ID Installer: Robert Fiesler (ARJZ5FYU94)"
#       The script reads ONLY this one file. It refuses to read env vars
#       or prompt interactively, by design — single source of truth.
#
# Outputs (dropped on the operator's local disk, NOT committed):
#   build/MiningGuardian-<version>-<sha>.pkg
#   build/MiningGuardian-<version>-<sha>.pkg.sha256
#   build/MiningGuardian-<version>-<sha>.notarization-log.txt
#
# Per Q2 (locked decision), the resulting .pkg is uploaded to a private
# GitHub Release on robertfiesler-spec/Mining-Guardian, with a USB-stick
# offline fallback. This script does NOT do the upload — that's a
# separate `make release` target (out of scope for PR I-3).
#
# The 9 steps (mirror installer/macos-pkg/README.md):
#   1. Verify Apple Developer cert + notarization credentials reachable
#   2. Refuse to build with a dirty git tree
#   3. Stamp the build with current git SHA + version
#   4. Assemble the payload (app code + dependencies, vendored)
#   5. Sign the payload with Developer ID Installer cert
#   6. Submit to Apple notarization via notarytool
#   7. Staple the notarization ticket
#   8. Drop the final .pkg in build/ with a SHA-256 sidecar
#   9. Print the install command for the operator
#
# Exit codes:
#   40  — not running on macOS
#   41  — credentials file missing or malformed
#   42  — git tree dirty
#   43  — payload assembly failed
#   44  — productbuild / signing failed
#   45  — notarytool submission failed or timed out
#   46  — staple failed
#   47  — final integrity check failed

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
readonly PKG_DIR="${REPO_ROOT}/installer/macos-pkg"
readonly BUILD_DIR="${REPO_ROOT}/build"
readonly STAGE_DIR="${BUILD_DIR}/stage"
readonly PAYLOAD_DIR="${STAGE_DIR}/payload"
readonly SCRIPTS_DIR="${STAGE_DIR}/scripts"

readonly CREDS_FILE="/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt"

readonly PKG_IDENTIFIER="com.miningguardian.installer.core"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_log() { echo "[build_pkg] $*"; }
_die() { echo "[build_pkg] FATAL ($1) $2" >&2; exit "$1"; }

# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

step_1_verify_creds() {
    if [[ "$(uname -s)" != "Darwin" ]]; then
        _die 40 "build_pkg.sh runs on macOS only (uname -s = $(uname -s))"
    fi
    if [[ ! -r "$CREDS_FILE" ]]; then
        _die 41 "credentials file missing or unreadable: ${CREDS_FILE}"
    fi

    # Parse the file into the four required vars. Any missing line is fatal.
    local k v
    while IFS='=' read -r k v; do
        # strip trailing whitespace + surrounding quotes from value
        v="${v%\"}"; v="${v#\"}"; v="${v%[[:space:]]}"
        case "$k" in
            APPLE_TEAM_ID)                  APPLE_TEAM_ID="$v" ;;
            APPLE_NOTARIZATION_KEY_ID)      APPLE_NOTARIZATION_KEY_ID="$v" ;;
            APPLE_NOTARIZATION_ISSUER_UUID) APPLE_NOTARIZATION_ISSUER_UUID="$v" ;;
            APPLE_NOTARIZATION_KEY_PATH)    APPLE_NOTARIZATION_KEY_PATH="$v" ;;
            APPLE_DEV_ID_INSTALLER)         APPLE_DEV_ID_INSTALLER="$v" ;;
        esac
    done < <(grep -E '^[A-Z_]+=' "$CREDS_FILE")

    : "${APPLE_TEAM_ID:?missing APPLE_TEAM_ID in $CREDS_FILE}"
    : "${APPLE_NOTARIZATION_KEY_ID:?missing APPLE_NOTARIZATION_KEY_ID}"
    : "${APPLE_NOTARIZATION_ISSUER_UUID:?missing APPLE_NOTARIZATION_ISSUER_UUID}"
    : "${APPLE_NOTARIZATION_KEY_PATH:?missing APPLE_NOTARIZATION_KEY_PATH}"
    : "${APPLE_DEV_ID_INSTALLER:?missing APPLE_DEV_ID_INSTALLER}"

    if [[ ! -r "$APPLE_NOTARIZATION_KEY_PATH" ]]; then
        _die 41 ".p8 private key not readable: ${APPLE_NOTARIZATION_KEY_PATH}"
    fi

    # Verify the signing identity exists in the keychain.
    if ! /usr/bin/security find-identity -p basic -v \
            | grep -q "${APPLE_DEV_ID_INSTALLER}"; then
        _die 41 "Developer ID Installer not in keychain: ${APPLE_DEV_ID_INSTALLER}"
    fi

    _log "step 1 OK: credentials reachable, signing identity in keychain"
}

step_2_clean_tree() {
    cd "$REPO_ROOT"
    if ! /usr/bin/git diff --quiet --exit-code; then
        _die 42 "git tree dirty (unstaged changes); commit or stash first"
    fi
    if ! /usr/bin/git diff --cached --quiet --exit-code; then
        _die 42 "git tree dirty (staged but uncommitted); commit first"
    fi
    if [[ -n "$(/usr/bin/git ls-files --others --exclude-standard)" ]]; then
        _die 42 "git tree dirty (untracked files outside .gitignore); clean first"
    fi
    _log "step 2 OK: clean git tree"
}

step_3_stamp() {
    cd "$REPO_ROOT"
    BUILD_SHA="$(/usr/bin/git rev-parse --short=12 HEAD)"
    # Read version from pyproject.toml (single source of truth in this repo).
    # Falls back to 0.0.0 if pyproject.toml missing or unparseable.
    BUILD_VERSION="$(/usr/bin/python3 -c \
        "import re,sys;
try:
    m=re.search(r'^version\s*=\s*[\"\']([^\"\']+)', open('pyproject.toml').read(), re.M);
    sys.stdout.write(m.group(1) if m else '0.0.0')
except Exception:
    sys.stdout.write('0.0.0')")"
    BUILD_STAMP_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    rm -rf "$BUILD_DIR"
    install -d -m 0755 "$BUILD_DIR" "$STAGE_DIR" "$PAYLOAD_DIR" "$SCRIPTS_DIR"

    cat > "${PAYLOAD_DIR}/BUILD_STAMP.json" <<EOF
{
  "version":      "${BUILD_VERSION}",
  "git_sha":      "${BUILD_SHA}",
  "stamped_utc":  "${BUILD_STAMP_UTC}"
}
EOF
    _log "step 3 OK: stamped version=${BUILD_VERSION} sha=${BUILD_SHA}"
}

step_4_assemble_payload() {
    cd "$REPO_ROOT"

    # 4a. App code — a curated subset of the repo, NOT the whole tree.
    # Anything in this list is inside the .pkg.
    local app_root="${PAYLOAD_DIR}/MiningGuardian"
    install -d -m 0755 "$app_root"
    /usr/bin/rsync -a --delete \
        --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
        --exclude 'build' --exclude 'venv' --exclude '.venv' \
        --include 'pyproject.toml' \
        --include 'predictor.py' \
        --include 'requirements.txt' \
        --include 'core/***' \
        --include 'clients/***' \
        --include 'notifiers/***' \
        --include 'monitoring/***' \
        --include 'api/***' \
        --include 'ai/***' \
        --include 'intelligence/***' \
        --include 'mg_import_tool/***' \
        --include 'docs/***' \
        --include 'branding/***' \
        --include 'deploy/***' \
        --include 'migrations/***' \
        --exclude '*' \
        "${REPO_ROOT}/" "${app_root}/"

    # 4b. Migrations — surface them at the top of the payload so
    # postinstall.sh can find them at <payload>/migrations/.
    install -d -m 0755 "${PAYLOAD_DIR}/migrations"
    /usr/bin/rsync -a \
        "${REPO_ROOT}/mg_import_tool/sql/migrations/" \
        "${PAYLOAD_DIR}/migrations/"
    /usr/bin/rsync -a \
        "${REPO_ROOT}/migrations/003_c5_notify_triggers.sql" \
        "${PAYLOAD_DIR}/migrations/" 2>/dev/null || true

    # 4c. Vendored runtime: Colima, lima, qemu-img, Ollama.app,
    # postgres-16-bookworm.tar. These come from a vendor/ directory the
    # operator populates ONCE on the build host (out of scope for git).
    local vendor_dir="${HOME}/MiningGuardian-vendor"
    if [[ -d "$vendor_dir" ]]; then
        install -d -m 0755 "${PAYLOAD_DIR}/runtime"
        /usr/bin/rsync -a "${vendor_dir}/" "${PAYLOAD_DIR}/runtime/"
        _log "  vendored runtime from ${vendor_dir}"
    else
        _log "  WARN ${vendor_dir} missing — runtime/ left empty (postinstall will fail at install time, but pkg build proceeds for layout testing)"
    fi

    # 4d. Scripts — preinstall.sh, postinstall.sh, and the lib/ helpers
    # all go under STAGE/scripts/, which productbuild reads with
    # --scripts.
    /usr/bin/rsync -a \
        "${PKG_DIR}/scripts/" \
        "${SCRIPTS_DIR}/"

    # productbuild expects preinstall + postinstall to be at the top of
    # the scripts directory and named exactly so. Anything in lib/ is
    # also copied because the scripts source it relative to themselves.
    chmod +x "${SCRIPTS_DIR}/preinstall.sh" "${SCRIPTS_DIR}/postinstall.sh"
    chmod +x "${SCRIPTS_DIR}/lib/"*.sh

    _log "step 4 OK: payload assembled at ${PAYLOAD_DIR}"
}

step_5_pkgbuild_and_sign() {
    cd "$BUILD_DIR"

    # 5a. pkgbuild assembles the inner component pkg from the payload +
    # scripts. We DO NOT sign here — productbuild does the final sign.
    /usr/bin/pkgbuild \
        --root "$PAYLOAD_DIR" \
        --scripts "$SCRIPTS_DIR" \
        --identifier "$PKG_IDENTIFIER" \
        --version "$BUILD_VERSION" \
        --install-location "/" \
        "${BUILD_DIR}/core.pkg" \
        || _die 44 "pkgbuild failed"

    # 5b. productbuild wraps it with the Distribution.xml + branding.
    install -d -m 0755 "${BUILD_DIR}/resources"
    /usr/bin/rsync -a "${PKG_DIR}/resources/" "${BUILD_DIR}/resources/"

    local final_unsigned="${BUILD_DIR}/MiningGuardian-${BUILD_VERSION}-${BUILD_SHA}-unsigned.pkg"
    /usr/bin/productbuild \
        --distribution "${BUILD_DIR}/resources/Distribution.xml" \
        --resources    "${BUILD_DIR}/resources" \
        --package-path "$BUILD_DIR" \
        --version      "$BUILD_VERSION" \
        "$final_unsigned" \
        || _die 44 "productbuild failed"

    # 5c. Sign with the Developer ID Installer cert.
    FINAL_PKG="${BUILD_DIR}/MiningGuardian-${BUILD_VERSION}-${BUILD_SHA}.pkg"
    /usr/bin/productsign \
        --sign "$APPLE_DEV_ID_INSTALLER" \
        "$final_unsigned" \
        "$FINAL_PKG" \
        || _die 44 "productsign failed"

    rm -f "$final_unsigned"

    # 5d. Verify the signature locally before sending to Apple.
    if ! /usr/sbin/pkgutil --check-signature "$FINAL_PKG" \
            | grep -q "Developer ID Installer"; then
        _die 44 "pkgutil --check-signature did not find Developer ID Installer on ${FINAL_PKG}"
    fi
    _log "step 5 OK: signed pkg at ${FINAL_PKG}"
}

step_6_notarize() {
    local notlog="${BUILD_DIR}/MiningGuardian-${BUILD_VERSION}-${BUILD_SHA}.notarization-log.txt"

    /usr/bin/xcrun notarytool submit \
        "$FINAL_PKG" \
        --key       "$APPLE_NOTARIZATION_KEY_PATH" \
        --key-id    "$APPLE_NOTARIZATION_KEY_ID" \
        --issuer    "$APPLE_NOTARIZATION_ISSUER_UUID" \
        --team-id   "$APPLE_TEAM_ID" \
        --wait \
        --timeout   30m \
        2>&1 | tee "$notlog"

    if ! grep -q 'status: Accepted' "$notlog"; then
        _die 45 "notarization not accepted; see ${notlog}"
    fi
    _log "step 6 OK: notarization Accepted"
}

step_7_staple() {
    /usr/bin/xcrun stapler staple "$FINAL_PKG" \
        || _die 46 "stapler staple failed for ${FINAL_PKG}"
    /usr/bin/xcrun stapler validate "$FINAL_PKG" \
        || _die 46 "stapler validate failed for ${FINAL_PKG}"
    _log "step 7 OK: notarization ticket stapled"
}

step_8_sidecar() {
    /usr/bin/shasum -a 256 "$FINAL_PKG" > "${FINAL_PKG}.sha256"
    /usr/sbin/spctl -a -vv -t install "$FINAL_PKG" \
        2>&1 | tee -a "$BUILD_DIR/spctl.txt"
    if ! grep -q 'accepted' "$BUILD_DIR/spctl.txt"; then
        _die 47 "spctl did not accept the final pkg; see $BUILD_DIR/spctl.txt"
    fi
    _log "step 8 OK: SHA-256 sidecar + spctl acceptance recorded"
}

step_9_print() {
    cat <<EOF

================================================================================
 Mining Guardian .pkg build complete.

   Version:    ${BUILD_VERSION}
   Git SHA:    ${BUILD_SHA}
   Pkg:        ${FINAL_PKG}
   SHA-256:    ${FINAL_PKG}.sha256

 To install on a target Mac:
     sudo installer -pkg "${FINAL_PKG}" -target /

 Or double-click the .pkg in Finder. Installer.app will ask for the
 admin password and run preinstall + postinstall end-to-end.

 Per Q2: upload to the private GitHub Release on
   robertfiesler-spec/Mining-Guardian
 and copy to a USB stick as the offline fallback.
================================================================================
EOF
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    step_1_verify_creds
    step_2_clean_tree
    step_3_stamp
    step_4_assemble_payload
    step_5_pkgbuild_and_sign
    step_6_notarize
    step_7_staple
    step_8_sidecar
    step_9_print
}

main "$@"
