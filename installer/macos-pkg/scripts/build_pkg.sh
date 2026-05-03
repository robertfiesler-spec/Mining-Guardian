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
#         APPLE_DEV_ID_APPLICATION="Developer ID Application: Robert Fiesler (ARJZ5FYU94)"
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
#   43  — payload assembly failed (includes step 4h D-20 violation:
#         customer payload contains mg_import* path — importer is
#         operator-only per D-20 and must never ship to customers)
#   44  — productbuild / signing failed; or step 4g catalog-seed
#         payload assertion failed (D-18 Gap 2)
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
            APPLE_DEV_ID_APPLICATION)       APPLE_DEV_ID_APPLICATION="$v" ;;
        esac
    done < <(grep -E '^[A-Z_]+=' "$CREDS_FILE")

    : "${APPLE_TEAM_ID:?missing APPLE_TEAM_ID in $CREDS_FILE}"
    : "${APPLE_NOTARIZATION_KEY_ID:?missing APPLE_NOTARIZATION_KEY_ID}"
    : "${APPLE_NOTARIZATION_ISSUER_UUID:?missing APPLE_NOTARIZATION_ISSUER_UUID}"
    : "${APPLE_NOTARIZATION_KEY_PATH:?missing APPLE_NOTARIZATION_KEY_PATH}"
    : "${APPLE_DEV_ID_INSTALLER:?missing APPLE_DEV_ID_INSTALLER}"
    : "${APPLE_DEV_ID_APPLICATION:?missing APPLE_DEV_ID_APPLICATION in $CREDS_FILE}"

    if [[ ! -r "$APPLE_NOTARIZATION_KEY_PATH" ]]; then
        _die 41 ".p8 private key not readable: ${APPLE_NOTARIZATION_KEY_PATH}"
    fi

    # Verify both signing identities exist in the keychain.
    # - Installer cert signs the outer .pkg (productsign)
    # - Application cert signs every Mach-O binary in runtime/ (codesign)
    local identities
    identities="$(/usr/bin/security find-identity -p basic -v)"
    if ! echo "$identities" | grep -q "${APPLE_DEV_ID_INSTALLER}"; then
        _die 41 "Developer ID Installer not in keychain: ${APPLE_DEV_ID_INSTALLER}"
    fi
    if ! echo "$identities" | grep -q "${APPLE_DEV_ID_APPLICATION}"; then
        _die 41 "Developer ID Application not in keychain: ${APPLE_DEV_ID_APPLICATION}"
    fi

    _log "step 1 OK: credentials reachable, both signing identities in keychain"
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
    # Payload is rooted directly at PAYLOAD_DIR so it lays down at the
    # install-location without an extra MiningGuardian/ wrapper directory.
    # Combined with --install-location "/Library/Application Support/MiningGuardian"
    # in step 5, the result is a flat install at that path.
    #
    # Tahoe SSV (B-13 fix, v1.0.1): we MUST install onto the data volume,
    # not the system root. /Library/Application Support is writable on the
    # data volume and explicitly Apple-blessed for system-wide application
    # state — see Apple HIG "File System Programming Guide". The earlier
    # v1.0.0 layout (--install-location "/" + payload/MiningGuardian/...)
    # tried to write /MiningGuardian/ at the system-volume root, which
    # Tahoe's signed-system-volume protection rejects with the
    # "package is incompatible with this version of macOS" dialog
    # (logged in docs/INSTALLER_UX_BACKLOG_2026-05-01.md as B-13).
    local app_root="${PAYLOAD_DIR}"
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
        --include 'console/***' \
        --include 'intelligence-catalog/***' \
        --include 'docs/***' \
        --include 'branding/***' \
        --include 'deploy/***' \
        --include 'migrations/***' \
        --exclude '*' \
        "${REPO_ROOT}/" "${app_root}/"

    # 4b. Migrations — already laid down at <payload>/migrations/ by the
    # 4a rsync above (`--include 'migrations/***'` from REPO_ROOT/migrations).
    # Per D-20 (locked 2026-05-03) and the v1.0.3 importer-payload
    # reconciliation (P-004, PR mg/v103-d20-importer-payload-reconciliation,
    # 2026-05-04), the canonical `migrations/` directory is the SOLE source
    # of payload migrations. The previous overlay from
    # `mg_import_tool/sql/migrations/` was a live D-20 violation — the
    # importer is operator-only forever and does not ship to customers.
    #
    # The runtime-relevant importer migrations (field-log bootstrap +
    # layer-2 resolver) were relocated to `migrations/006_field_log_bootstrap.sql`
    # and `migrations/007_layer2_resolver.sql` in the same PR; they ride
    # in via the 4a `migrations/***` rsync. The operator-side originals at
    # `mg_import_tool/sql/migrations/000_bootstrap_field_log_tables.sql`
    # and `mg_import_tool/sql/migrations/002_layer2_and_learning_foundation.sql`
    # are intentionally retained as the importer's own source of truth on
    # the operator workstation (D-20 footnote 1) but are NOT copied into
    # the customer payload.
    #
    # Belt-and-suspenders: step 4h below asserts that the assembled payload
    # contains zero `mg_import*` files or directories and aborts the build
    # with exit 43 if any are found.
    if [[ ! -d "${PAYLOAD_DIR}/migrations" ]]; then
        _die 43 "step 4b: <payload>/migrations/ missing after 4a rsync — `--include 'migrations/***'` must be present in the include list above"
    fi

    # 4c. Vendored runtime: Colima, lima, qemu-img, Ollama.app,
    # postgres-16-bookworm.tar. These come from a vendor/ directory the
    # operator populates ONCE on the build host (out of scope for git).
    local vendor_dir="${HOME}/MiningGuardian-vendor"
    if [[ -d "$vendor_dir" ]]; then
        install -d -m 0755 "${PAYLOAD_DIR}/runtime"
        # Exclude python-wheels/ from the runtime/ rsync — wheels are
        # surfaced at <payload>/python-wheels/ (step 4e) so postinstall
        # step_create_venv (D-18 Gap 5) does not need to know about the
        # vendor-dir layout.
        /usr/bin/rsync -a --exclude 'python-wheels/' \
            "${vendor_dir}/" "${PAYLOAD_DIR}/runtime/"
        _log "  vendored runtime from ${vendor_dir} (python-wheels/ split out — see step 4e)"
    else
        _log "  WARN ${vendor_dir} missing — runtime/ left empty (postinstall will fail at install time, but pkg build proceeds for layout testing)"
    fi

    # 4e. Vendored Python wheels — D-18 Gap 5. Postinstall's
    # step_create_venv pip-installs offline from <payload>/python-wheels/
    # against <payload>/requirements.txt. No network for pip.
    #
    # Operator is expected to populate the vendor dir BEFORE running
    # build_pkg.sh:
    #   mkdir -p ${HOME}/MiningGuardian-vendor/python-wheels
    #   /opt/homebrew/opt/python@3.12/bin/python3.12 -m pip download \
    #       --only-binary=:all: --platform macosx_11_0_arm64 \
    #       --python-version 3.12 \
    #       -d ${HOME}/MiningGuardian-vendor/python-wheels \
    #       -r installer/macos-pkg/payload-requirements.txt
    # See docs/RUNBOOK_PKG_REBUILD.md (updated in this PR) for the
    # full step-by-step.
    local wheels_src="${HOME}/MiningGuardian-vendor/python-wheels"
    if [[ -d "$wheels_src" ]]; then
        install -d -m 0755 "${PAYLOAD_DIR}/python-wheels"
        /usr/bin/rsync -a "${wheels_src}/" "${PAYLOAD_DIR}/python-wheels/"
        local wheel_count
        wheel_count="$(/usr/bin/find "${PAYLOAD_DIR}/python-wheels" -maxdepth 1 -type f -name '*.whl' | /usr/bin/wc -l | /usr/bin/tr -d ' ')"
        _log "  vendored ${wheel_count} python wheel(s) from ${wheels_src}"
        if (( wheel_count < 1 )); then
            _die 43 "step 4e: ${wheels_src} contained no .whl files — postinstall step_create_venv would fail at install time"
        fi
    else
        _log "  WARN ${wheels_src} missing — postinstall step_create_venv (D-18 Gap 5) will fail at install time"
    fi

    # 4f. requirements.txt — single source of truth for the install-time
    # pip install. Lives at installer/macos-pkg/payload-requirements.txt
    # (committed to git; deliberately separate from any future repo-root
    # requirements.txt so the .pkg pin set is reviewed independently).
    local payload_req_src="${PKG_DIR}/payload-requirements.txt"
    if [[ ! -r "$payload_req_src" ]]; then
        _die 43 "step 4f: payload requirements pin file missing: ${payload_req_src}"
    fi
    install -m 0644 "$payload_req_src" "${PAYLOAD_DIR}/requirements.txt"
    _log "  staged requirements.txt from ${payload_req_src}"

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

    # 4g. Catalog seed assertion (D-18 Gap 2). postinstall.sh
    # step_provision_catalog_db_and_seed expects deploy_schema.sql and
    # seed_miner_models.sql under <payload>/intelligence-catalog/seed-data/.
    # Those land via the 4a rsync `--include 'intelligence-catalog/***'`
    # but a typo or future include-list edit could silently drop them and
    # the failure would not surface until install time on a customer Mac.
    # Belt-and-suspenders: assert here, fail the build with exit 44 if
    # missing.
    local catalog_seed_dir="${PAYLOAD_DIR}/intelligence-catalog/seed-data"
    local schema_file="${catalog_seed_dir}/deploy_schema.sql"
    local seed_file="${catalog_seed_dir}/seed_miner_models.sql"
    if [[ ! -r "$schema_file" ]]; then
        _die 44 "step 4g: catalog deploy_schema.sql missing in payload at ${schema_file} (D-18 Gap 2)"
    fi
    if [[ ! -r "$seed_file" ]]; then
        _die 44 "step 4g: catalog seed_miner_models.sql missing in payload at ${seed_file} (D-18 Gap 2)"
    fi
    # Sanity-check the seed has the expected row count (320 INSERT rows
    # at v1.0.3; the count will grow as miners are added — operator
    # quote 2026-04-30: "the list grows as miners get added so it needs
    # to reflect that... it is not a static number"). Use >= as the
    # assertion to make this future-proof.
    local seed_inserts
    seed_inserts="$(/usr/bin/grep -cE '^INSERT INTO hardware\.miner_models' "$seed_file" || true)"
    if (( seed_inserts < 320 )); then
        _die 44 "step 4g: seed_miner_models.sql has ${seed_inserts} INSERT rows, expected ≥ 320 (D-18 verification gate)"
    fi
    _log "step 4g OK: catalog seed staged (${seed_inserts} INSERT rows in seed_miner_models.sql)"

    # 4h. D-20 importer-payload regression assertion (P-004 PR
    # mg/v103-d20-importer-payload-reconciliation, 2026-05-04).
    #
    # D-20 (locked 2026-05-03): the hardware-catalog importer
    # (`mg_import_tool/`) stays on the operator's workstation forever and
    # is NOT shipped to customers. v1.0.2's build_pkg.sh had `mg_import_tool/***`
    # in the 4a rsync include list and rsync'd `mg_import_tool/sql/migrations/`
    # over `<payload>/migrations/`; both were removed in this PR. This
    # assertion is belt-and-suspenders: even if a future include-list edit
    # silently re-adds the path, the build hard-fails before we burn an
    # Apple notarization round-trip on a payload that violates D-20.
    #
    # Scope: the entire PAYLOAD_DIR tree, including any staging copies the
    # 4c (vendored runtime) or 4e (vendored python wheels) rsync may have
    # populated. The operator-side `MiningGuardian-vendor/` directory should
    # NEVER contain `mg_import*` — but if it does (operator mistake), this
    # check catches it and aborts with exit 43.
    local mg_import_hits
    # `find ... -print` writes one absolute path per match; we count lines.
    # `wc -l` is safe with no trailing newline because empty input returns 0.
    mg_import_hits="$(/usr/bin/find "$PAYLOAD_DIR" -name 'mg_import*' -print 2>/dev/null | /usr/bin/wc -l | /usr/bin/tr -d ' ')"
    if (( mg_import_hits > 0 )); then
        _log "step 4h FAIL: payload contains ${mg_import_hits} mg_import* path(s):"
        /usr/bin/find "$PAYLOAD_DIR" -name 'mg_import*' -print | /usr/bin/sed "s#${PAYLOAD_DIR}#<payload>#" >&2
        _die 43 "step 4h: D-20 violation — customer payload must contain no mg_import* files or directories (the importer is operator-only forever)"
    fi
    _log "step 4h OK: D-20 assertion passed (zero mg_import* paths in payload)"

    # 4i. Scheduled-jobs plist assertion (D-18 Gap 4 / P-007). postinstall.sh
    # step_install_scheduled_plists_and_bootstrap reads the 11 scheduled
    # plists from the same productbuild --resources directory the services
    # use. A typo or missing plist file at this point would not surface
    # until install time on a customer Mac (where the scheduled bootstrap
    # would fail with exit code 40), so we assert here and abort the build
    # with exit 47 if any of the 11 scheduled plists are missing from the
    # source tree.
    #
    # Source location: ${PKG_DIR}/resources/launchd/scheduled/
    #   (mirrors installer/macos-pkg/resources/launchd/scheduled/)
    #
    # Why we assert in the source tree rather than in PAYLOAD_DIR: the
    # scheduled plists are productbuild --resources content (see step 5b
    # below — `rsync ${PKG_DIR}/resources/ ${BUILD_DIR}/resources/`), not
    # payload content. A future build_pkg.sh refactor that moved this
    # rsync would still benefit from the source-tree assertion landing
    # here (where step 4 already lives).
    local scheduled_dir="${PKG_DIR}/resources/launchd/scheduled"
    local scheduled_labels=(
        "com.miningguardian.scheduled.weekly-training"
        "com.miningguardian.scheduled.refinement-chain"
        "com.miningguardian.scheduled.db-maintenance"
        "com.miningguardian.scheduled.knowledge-backup"
        "com.miningguardian.scheduled.morning-briefing"
        "com.miningguardian.scheduled.operator-review"
        "com.miningguardian.scheduled.ams-cleanup"
        "com.miningguardian.scheduled.log-collection"
        "com.miningguardian.scheduled.daily-deep-dive"
        "com.miningguardian.scheduled.log-failure-report"
        "com.miningguardian.scheduled.benchmark"
    )
    if [[ ! -d "$scheduled_dir" ]]; then
        _die 47 "step 4i: scheduled-plists directory missing: ${scheduled_dir} (D-18 Gap 4)"
    fi
    local sl
    for sl in "${scheduled_labels[@]}"; do
        if [[ ! -r "${scheduled_dir}/${sl}.plist" ]]; then
            _die 47 "step 4i: scheduled plist missing: ${scheduled_dir}/${sl}.plist (D-18 Gap 4)"
        fi
    done
    local scheduled_launcher="${PKG_DIR}/resources/launchd/launchers/scheduled_job_launcher.sh"
    if [[ ! -r "$scheduled_launcher" ]]; then
        _die 47 "step 4i: scheduled-job launcher missing: ${scheduled_launcher} (D-18 Gap 4)"
    fi
    _log "step 4i OK: ${#scheduled_labels[@]} scheduled-job plists + scheduled_job_launcher.sh staged (D-18 Gap 4)"

    _log "step 4 OK: payload assembled at ${PAYLOAD_DIR}"
}

step_4b_codesign_inner_binaries() {
    # Notarization (step 6) rejects any third-party Mach-O inside the
    # payload that isn't:
    #   * signed with a Developer ID Application cert
    #   * stamped with a secure timestamp
    #   * built with hardened runtime enabled
    #
    # Vendored binaries (Colima, lima, docker) ship unsigned, so we
    # codesign each one in place here, BEFORE pkgbuild snapshots the
    # payload.
    #
    # We also drop runtime/colima/share/lima/lima-guestagent.Darwin-aarch64.gz —
    # that's the Linux guest agent for QEMU mode. We're VZ-only on Apple
    # Silicon (PR #47), so the guest agent is dead weight AND notarization
    # rejects it because the .gz wrapper contains an unsigned Linux binary
    # that codesign cannot fix.
    local runtime_dir="${PAYLOAD_DIR}/runtime"
    if [[ ! -d "$runtime_dir" ]]; then
        _log "step 4b SKIP: no runtime/ in payload (vendor dir was missing)"
        return 0
    fi

    # Drop the Linux guest agent — VZ doesn't use it.
    local guestagent_gz="${runtime_dir}/colima/share/lima/lima-guestagent.Darwin-aarch64.gz"
    if [[ -f "$guestagent_gz" ]]; then
        rm -f "$guestagent_gz"
        _log "  removed lima-guestagent.Darwin-aarch64.gz (VZ-only build, Linux guest agent unused)"
    fi

    # Two-pass codesign:
    #
    # Pass 1: re-sign every .app and .framework bundle as a UNIT with
    # --deep. App/framework bundles are pre-sealed by their vendor
    # (Ollama, etc.) and ship with internal _CodeSignature manifests.
    # If we walk inside one and re-sign individual Mach-O files, we
    # break that seal and the bundle becomes invalid — which is exactly
    # what happened to Ollama.app in submission 63236a3b on 2026-04-28.
    # The correct approach is to re-sign the bundle from the outside in
    # using --deep + --options runtime + --timestamp, which re-seals
    # every level (helpers, frameworks, dylibs, the main executable).
    #
    # Pass 2: codesign every loose Mach-O file that is NOT inside a
    # .app or .framework bundle (Pass 1 already handled those).
    local count_bundles=0 count_loose=0 failed=0 path file_out

    # Pass 1 — .app and .framework bundles. -prune so find doesn't
    # descend into them after we list them.
    while IFS= read -r -d '' path; do
        if /usr/bin/codesign \
                --force \
                --deep \
                --sign "$APPLE_DEV_ID_APPLICATION" \
                --options runtime \
                --timestamp \
                "$path" >/dev/null 2>&1; then
            count_bundles=$((count_bundles + 1))
            _log "  re-sealed bundle: ${path#${PAYLOAD_DIR}/}"
        else
            failed=$((failed + 1))
            _log "  WARN codesign --deep failed for bundle ${path#${PAYLOAD_DIR}/}"
        fi
    done < <(/usr/bin/find "$runtime_dir" \
        \( -name '*.app' -o -name '*.framework' \) -prune -print0)

    # Pass 2 — loose Mach-O files outside any .app/.framework bundle.
    # `file` reports Mach-O binaries with strings like:
    #   "Mach-O 64-bit executable arm64"
    #   "Mach-O 64-bit dynamically linked shared library arm64"
    #   "Mach-O universal binary with 2 architectures"
    while IFS= read -r -d '' path; do
        # Skip anything inside a .app or .framework — Pass 1 owns those.
        case "$path" in
            */*.app/*|*/*.framework/*) continue ;;
        esac
        file_out="$(/usr/bin/file -b "$path" 2>/dev/null || true)"
        if [[ "$file_out" != *"Mach-O"* ]]; then
            continue
        fi
        if /usr/bin/codesign \
                --force \
                --sign "$APPLE_DEV_ID_APPLICATION" \
                --options runtime \
                --timestamp \
                "$path" >/dev/null 2>&1; then
            count_loose=$((count_loose + 1))
        else
            failed=$((failed + 1))
            _log "  WARN codesign failed for ${path#${PAYLOAD_DIR}/}"
        fi
    done < <(/usr/bin/find "$runtime_dir" -type f -print0)

    if (( failed > 0 )); then
        _die 44 "step 4b: codesign failed on ${failed} item(s) (see WARNs above)"
    fi

    # Verify every bundle's seal is intact — catches the failure mode
    # that bit us in submission 63236a3b: a binary whose hash no longer
    # matches the bundle's CodeResources manifest. Apple's notary
    # service runs the same check.
    while IFS= read -r -d '' path; do
        if ! /usr/bin/codesign --verify --deep --strict "$path" >/dev/null 2>&1; then
            _die 44 "step 4b: bundle failed --verify --deep --strict: ${path#${PAYLOAD_DIR}/}"
        fi
    done < <(/usr/bin/find "$runtime_dir" \
        \( -name '*.app' -o -name '*.framework' \) -prune -print0)

    _log "step 4b OK: re-sealed ${count_bundles} bundle(s), codesigned ${count_loose} loose Mach-O"
}

step_5_pkgbuild_and_sign() {
    cd "$BUILD_DIR"

    # 5a. pkgbuild assembles the inner component pkg from the payload +
    # scripts. We DO NOT sign here — productbuild does the final sign.
    # B-13 fix (v1.0.1): install to /Library/Application Support/MiningGuardian.
    # The previous v1.0.0 used --install-location "/" with payload structured
    # as payload/MiningGuardian/, which Tahoe's signed-system-volume (SSV)
    # rejects: "This package is incompatible with this version of macOS."
    # See INSTALLER_UX_BACKLOG_2026-05-01.md row B-13 for the forensic
    # capture and the SSV write-restriction explanation.
    /usr/bin/pkgbuild \
        --root "$PAYLOAD_DIR" \
        --scripts "$SCRIPTS_DIR" \
        --identifier "$PKG_IDENTIFIER" \
        --version "$BUILD_VERSION" \
        --install-location "/Library/Application Support/MiningGuardian" \
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
    step_4b_codesign_inner_binaries
    step_5_pkgbuild_and_sign
    step_6_notarize
    step_7_staple
    step_8_sidecar
    step_9_print
}

main "$@"
