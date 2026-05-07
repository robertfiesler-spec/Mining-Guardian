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
#         operator-only per D-20 and must never ship to customers; AND
#         step 4i P-026 violation: installer-owned Python 3.12 runtime
#         missing/broken/wrong-version under
#         ${HOME}/MiningGuardian-vendor/python-runtime/)
#   44  — productbuild / signing failed; or step 4g catalog-seed
#         payload assertion failed (D-18 Gap 2)
#   45  — notarytool submission failed or timed out
#   46  — staple failed
#   47  — final integrity check failed
#   49  — wheel re-signing failed (P-011, step 4c). Mach-O binaries inside
#         vendored Python wheels could not be signed with Developer ID
#         Application + hardened runtime + secure timestamp, OR the
#         RECORD manifest rewrite produced a wheel that fails its own
#         post-rewrite verify (would brick `pip install` on the customer
#         Mac if shipped). See installer/macos-pkg/scripts/lib/resign_wheel.py.

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
    # D-18 P-025 (2026-05-05) — `scripts/***` added.
    # 6 of the 11 scheduled-job plists invoke entrypoints under
    # `scripts/` (cleanup_ams_logs.py, db_maintenance.sh,
    # direct_collect_logs.py, daily_log_failure_report.py,
    # morning_briefing.py, daily_operator_review.py). Without scripts/
    # in the payload, scheduled_job_launcher.sh exits 1 on first fire
    # with `entrypoint not found: ${INSTALL_ROOT}/scripts/...`, leaving
    # the plist installed but every scheduled run failing silently.
    # The benchmark plist's `tests/run_benchmark.py` entrypoint is a
    # known pre-existing latent bug (see plist comment + docs/LATENT_BUGS.md);
    # `tests/` is not added here because the only scheduled .py inside
    # it is the missing one. P-025 scope stops at the audit's P0 list.
    #
    # P-024 (2026-05-07) — narrowed `scripts/***` to a per-file allowlist.
    # The previous broad include was shipping operator-only / dead-code
    # scripts (backup_db.sh, backup_mining_guardian.sh, start_guardian.sh,
    # setup.sh, etc.) inside the customer payload. Those reference Bobby's
    # Mac (BigBobby username, /Volumes/Big-Bobby-T9, 100.103.185.53
    # tailscale IP) and the retired Hostinger VPS (187.124.247.182), and
    # never run on the customer Mac Mini — the Mini has no plist or
    # launcher pointing at them. The allowlist below is exactly the set
    # of `scripts/*` paths reachable from a launchd plist
    # `ProgramArguments` entry or a launcher script under
    # `installer/macos-pkg/resources/launchd/launchers/`.
    # `scripts/__init__.py` ships so `scripts/` remains a valid Python
    # package dir if a future entrypoint imports siblings.
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
        --include '/branding/***' \
        --include 'deploy/***' \
        --include 'migrations/***' \
        --include 'scripts/' \
        --include 'scripts/__init__.py' \
        --include 'scripts/cleanup_ams_logs.py' \
        --include 'scripts/db_maintenance.sh' \
        --include 'scripts/direct_collect_logs.py' \
        --include 'scripts/daily_log_failure_report.py' \
        --include 'scripts/morning_briefing.py' \
        --include 'scripts/daily_operator_review.py' \
        --exclude 'scripts/*' \
        --include 'config/***' \
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

    # D-18 P-025 (2026-05-05): scripts/ is required for 6 of the 11
    # scheduled-job plists. A missing scripts/ in the payload would
    # leave the plists installed but every scheduled run failing with
    # exit 1 the first time it fires. Belt-and-suspenders here so a
    # future include-list edit cannot silently drop scripts/.
    # P-024 (2026-05-07) — the include list is now a per-file allowlist
    # (see comment block above the rsync). The directory must still exist
    # and the 6 scheduled scripts must still be present.
    if [[ ! -d "${PAYLOAD_DIR}/scripts" ]]; then
        _die 43 "step 4b: <payload>/scripts/ missing after 4a rsync — the per-file allowlist must keep 'scripts/' as a directory include (D-18 P-025 / P-024)"
    fi
    local mg_scheduled_scripts=(
        "scripts/cleanup_ams_logs.py"
        "scripts/db_maintenance.sh"
        "scripts/direct_collect_logs.py"
        "scripts/daily_log_failure_report.py"
        "scripts/morning_briefing.py"
        "scripts/daily_operator_review.py"
    )
    local sched_script
    for sched_script in "${mg_scheduled_scripts[@]}"; do
        if [[ ! -r "${PAYLOAD_DIR}/${sched_script}" ]]; then
            _die 43 "step 4b: scheduled-job entrypoint missing in payload: ${sched_script} (D-18 P-025)"
        fi
    done

    # 4c. Vendored runtime: Colima, lima, qemu-img, Ollama.app,
    # postgres-16-bookworm.tar. These come from a vendor/ directory the
    # operator populates ONCE on the build host (out of scope for git).
    #
    # P-026 (2026-05-05) — `python-runtime/` is also excluded from this
    # bulk rsync. Step 4i below stages the installer-owned Python 3.12
    # interpreter from `${HOME}/MiningGuardian-vendor/python-runtime/`
    # into `<payload>/runtime/python/` with its own assertions (so a
    # missing/broken Python runtime is a hard build error, not a silent
    # WARN-and-proceed). Splitting it out also keeps the runtime/
    # codesign step (4b) straightforward — it walks runtime/ recursively
    # and signs every Mach-O regardless of which subdir put it there.
    local vendor_dir="${HOME}/MiningGuardian-vendor"
    if [[ -d "$vendor_dir" ]]; then
        install -d -m 0755 "${PAYLOAD_DIR}/runtime"
        # Exclude python-wheels/ from the runtime/ rsync — wheels are
        # surfaced at <payload>/python-wheels/ (step 4e) so postinstall
        # step_create_venv (D-18 Gap 5) does not need to know about the
        # vendor-dir layout.
        # Exclude python-runtime/ from the runtime/ rsync — the Python
        # interpreter is staged by step 4i with its own validation
        # (P-026). The Python runtime still LANDS under runtime/ in the
        # payload (at <payload>/runtime/python/), it's just placed there
        # by step 4i instead of this bulk rsync.
        /usr/bin/rsync -a \
            --exclude 'python-wheels/' \
            --exclude 'python-runtime/' \
            "${vendor_dir}/" "${PAYLOAD_DIR}/runtime/"
        _log "  vendored runtime from ${vendor_dir} (python-wheels/ split out — see step 4e; python-runtime/ split out — see step 4i, P-026)"
    else
        _log "  WARN ${vendor_dir} missing — runtime/ left empty (postinstall will fail at install time, but pkg build proceeds for layout testing)"
    fi

    # 4i. Installer-owned Python 3.12 runtime — P-026 (2026-05-05).
    #
    # Before P-026 the .pkg's postinstall.sh::step_create_venv reached
    # for `/opt/homebrew/opt/python@3.12/bin/python3.12` on the customer
    # Mac mini. That made Homebrew + python@3.12 a hidden customer
    # prerequisite, which violated the "no nontechnical-user prereqs"
    # bar (CLAUDE.md "Working Principles", D-23 customer-onboarding
    # gaps). Round 9 of the Mac mini install (2026-05-05) hit it live:
    # FATAL (38) python3.12 not found on this Mac.
    #
    # Operator decision (Rob, 2026-05-05): "yes include it in the
    # installer and whatever else might pop up as the install keeps
    # going". The .pkg now vendors its own Python 3.12 interpreter.
    #
    # Vendor layout (operator-side, ${HOME}/MiningGuardian-vendor/):
    #   python-runtime/
    #     bin/python3.12               (executable, --version → "Python 3.12.x")
    #     bin/python3   -> python3.12  (symlink, optional)
    #     bin/python    -> python3.12  (symlink, optional)
    #     lib/python3.12/...           (full stdlib + ensurepip)
    #     include/python3.12/...       (headers — needed by some C-extension
    #                                   wheels at install time, even though
    #                                   we use --only-binary=:all: pip should
    #                                   never compile, but psycopg2-binary
    #                                   etc. occasionally inspect headers)
    # OR (alternate framework-shaped layout, also accepted):
    #   python-runtime/
    #     Python.framework/Versions/3.12/bin/python3.12
    #     Python.framework/Versions/3.12/lib/python3.12/...
    #
    # Recommended source: python-build-standalone (astral-sh) — these
    # are the same tarballs Astral / uv / Rye / hatch / mise use. They
    # are fully relocatable, self-contained, signable, and ship a working
    # ensurepip + venv module. Choose the install_only_stripped variant
    # for `aarch64-apple-darwin` Python 3.12.x. Extract under
    # `${HOME}/MiningGuardian-vendor/python-runtime/` so the relative
    # path of the python3.12 binary lands at one of the two layouts above.
    #
    # The exact `pip download` command for the wheelhouse (step 4e) MUST
    # be re-run with this packaged interpreter once it's in place, so
    # the vendored wheel ABI matches the runtime's CPython version.
    # docs/RUNBOOK_PKG_REBUILD.md "Block Pre-B — populate the Python
    # runtime" has the full operator commands.
    #
    # Build-time hard fail rules:
    #   1. Vendor dir must exist.
    #   2. python3.12 binary must be present at one of the two layouts.
    #   3. Binary must be Mach-O (codesign at step 4b will reject
    #      anything else anyway — fail fast here with a clearer error).
    #   4. Binary must run and report Python 3.12.x. We test this BEFORE
    #      payload-staging because a wrong-version interpreter would
    #      brick the venv create at install time, after the operator has
    #      already burned a 5-minute notarization round-trip.
    #
    # Output: <payload>/runtime/python/ — flat or framework, preserved.
    # Step 4b will codesign every Mach-O under runtime/ (the .so / .dylib
    # files inside the Python tree included), so notarization-readiness
    # is automatic — no new codesign branch needed in step 4b.
    local pyrt_src="${HOME}/MiningGuardian-vendor/python-runtime"
    if [[ ! -d "$pyrt_src" ]]; then
        _die 43 "step 4i: installer-owned Python runtime missing: ${pyrt_src} — postinstall step_create_venv (P-026) would fail at install time. Populate it with python-build-standalone per docs/RUNBOOK_PKG_REBUILD.md 'Block Pre-B' before re-running build_pkg.sh."
    fi

    # Resolve the python3.12 inside the vendor dir. Two accepted layouts.
    local pyrt_bin=""
    local pyrt_layout=""
    if [[ -x "${pyrt_src}/bin/python3.12" ]]; then
        pyrt_bin="${pyrt_src}/bin/python3.12"
        pyrt_layout="flat"
    elif [[ -x "${pyrt_src}/Python.framework/Versions/3.12/bin/python3.12" ]]; then
        pyrt_bin="${pyrt_src}/Python.framework/Versions/3.12/bin/python3.12"
        pyrt_layout="framework"
    else
        _die 43 "step 4i: no python3.12 binary found in ${pyrt_src} (looked for bin/python3.12 and Python.framework/Versions/3.12/bin/python3.12); see docs/RUNBOOK_PKG_REBUILD.md 'Block Pre-B' (P-026)"
    fi

    # The interpreter must be a Mach-O. (`file -b` reports
    # "Mach-O 64-bit executable arm64" or universal. Anything else —
    # ELF from an accidentally-Linux tarball, a wrapper script — is
    # rejected here.)
    local pyrt_filetype
    pyrt_filetype="$(/usr/bin/file -b "$pyrt_bin" 2>/dev/null || true)"
    if [[ "$pyrt_filetype" != *"Mach-O"* ]]; then
        _die 43 "step 4i: ${pyrt_bin} is not a Mach-O binary (got '${pyrt_filetype}') — wrong tarball flavor? Use python-build-standalone for aarch64-apple-darwin (P-026)"
    fi

    # The interpreter must run and report 3.12.x. We accept any patch
    # level so future python-build-standalone refreshes do not require
    # a build_pkg.sh edit.
    local pyrt_ver
    if ! pyrt_ver="$("$pyrt_bin" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"; then
        _die 43 "step 4i: ${pyrt_bin} could not report a Python version — interpreter is broken (P-026)"
    fi
    if [[ "$pyrt_ver" != "3.12" ]]; then
        _die 43 "step 4i: ${pyrt_bin} reported Python ${pyrt_ver}, expected 3.12 (vendored wheels are cp312 only — P-026)"
    fi

    # The interpreter MUST also have the `venv` module — postinstall
    # uses `python -m venv`. python-build-standalone install_only/
    # install_only_stripped variants ship venv; the build-only variant
    # does not. Catch that here, not at install time.
    if ! "$pyrt_bin" -c 'import venv' >/dev/null 2>&1; then
        _die 43 "step 4i: ${pyrt_bin} cannot import the 'venv' module — wrong python-build-standalone variant? (use install_only or install_only_stripped, not build) (P-026)"
    fi

    # Stage into the payload at <payload>/runtime/python/. Preserve the
    # vendor dir layout exactly so symlinks (e.g. python3 → python3.12)
    # and the framework Versions/Current pointer stay intact.
    install -d -m 0755 "${PAYLOAD_DIR}/runtime/python"
    /usr/bin/rsync -a "${pyrt_src}/" "${PAYLOAD_DIR}/runtime/python/"

    # Verify the staged interpreter runs (catches the rsync silently
    # turning a symlink into a broken file or dropping the executable
    # bit; refuses to ship a .pkg whose runtime/python/ would crash on
    # the customer Mac).
    local staged_bin
    if [[ "$pyrt_layout" == "flat" ]]; then
        staged_bin="${PAYLOAD_DIR}/runtime/python/bin/python3.12"
    else
        staged_bin="${PAYLOAD_DIR}/runtime/python/Python.framework/Versions/3.12/bin/python3.12"
    fi
    if [[ ! -x "$staged_bin" ]]; then
        _die 43 "step 4i: staged Python interpreter not executable at ${staged_bin} (rsync issue?) (P-026)"
    fi
    if ! "$staged_bin" -c 'import sys, venv; sys.exit(0 if sys.version_info[:2]==(3,12) else 1)' >/dev/null 2>&1; then
        _die 43 "step 4i: staged Python interpreter at ${staged_bin} failed post-rsync sanity check (P-026)"
    fi

    _log "step 4i OK: installer-owned Python runtime staged from ${pyrt_src} (${pyrt_layout} layout, version 3.12, venv module present) — P-026"

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
    # P-010 (2026-05-04): missing wheelhouse must abort the build, not WARN.
    # The pre-P-010 path emitted a WARN and proceeded; the resulting .pkg
    # signed and notarized cleanly but its postinstall step_create_venv
    # would exit 38 at install time on the customer Mac because
    # <payload>/python-wheels/ was absent. That burns an Apple notarization
    # round-trip on a dead .pkg. Treat a missing wheelhouse the same way
    # we already treat an empty wheelhouse: fail step 4e with exit 43
    # before signing.
    #
    # Operator populates the wheelhouse ONCE per build host using:
    #   mkdir -p ${HOME}/MiningGuardian-vendor/python-wheels
    #   /opt/homebrew/opt/python@3.12/bin/python3.12 -m pip download \
    #       --only-binary=:all: --platform macosx_11_0_arm64 \
    #       --python-version 3.12 --implementation cp --abi cp312 \
    #       -d ${HOME}/MiningGuardian-vendor/python-wheels \
    #       -r installer/macos-pkg/payload-requirements.txt
    # See docs/RUNBOOK_PKG_REBUILD.md "Block Pre-A — populate the
    # wheelhouse" for the full step-by-step.
    local wheels_src="${HOME}/MiningGuardian-vendor/python-wheels"
    if [[ ! -d "$wheels_src" ]]; then
        _die 43 "step 4e: vendor wheelhouse missing: ${wheels_src} — postinstall step_create_venv (D-18 Gap 5) would fail at install time. Populate it with the pip download command in docs/RUNBOOK_PKG_REBUILD.md before re-running build_pkg.sh."
    fi
    install -d -m 0755 "${PAYLOAD_DIR}/python-wheels"
    /usr/bin/rsync -a "${wheels_src}/" "${PAYLOAD_DIR}/python-wheels/"
    local wheel_count
    wheel_count="$(/usr/bin/find "${PAYLOAD_DIR}/python-wheels" -maxdepth 1 -type f -name '*.whl' | /usr/bin/wc -l | /usr/bin/tr -d ' ')"
    _log "  vendored ${wheel_count} python wheel(s) from ${wheels_src}"
    if (( wheel_count < 1 )); then
        _die 43 "step 4e: ${wheels_src} contained no .whl files — postinstall step_create_venv would fail at install time"
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

    # 4d. Scripts — preinstall, postinstall, and the lib/ helpers all go
    # under STAGE/scripts/, which pkgbuild reads with --scripts.
    #
    # P-013 (2026-05-04). macOS PackageKit honors EXACTLY two top-level
    # script names in a component pkg's scripts archive: `preinstall` and
    # `postinstall`, with NO extension. Anything else (preinstall.sh,
    # postinstall.sh, my-preinstall, etc.) is silently ignored — Installer.app
    # lays down the payload, writes the BOM/receipt, reports success, and
    # the scripts never fire. That is exactly the failure mode v1.0.3 hit
    # on Rob's Mac mini install of build a35728d (2026-05-04): payload
    # extracted, receipt registered, but `/var/log/mining-guardian/install-postinstall.log`,
    # `/etc/mining-guardian/install-receipt.json`, `.env`, `venv`, and
    # every other postinstall artifact were absent because the scripts
    # were named preinstall.sh/postinstall.sh in the .pkg's Scripts
    # archive. See `man pkgbuild`:
    #     "If this directory contains scripts named preinstall and/or
    #      postinstall, these will be run as the top-level scripts of
    #      the package."
    # The repo-side filenames keep the .sh extension so editors highlight
    # them, shellcheck recognizes them, and `bash -n` works in CI; the
    # rename happens here at staging time, just before pkgbuild snapshots.
    #
    # Strategy:
    #   1. rsync the package-script content under installer/macos-pkg/scripts/
    #      (lib/ + preinstall.sh + postinstall.sh) into ${SCRIPTS_DIR} so the
    #      lib/ helpers travel alongside the scripts that source them via
    #      SCRIPT_DIR/lib/... build_pkg.sh itself lives in the same source
    #      directory but is NOT a package script — it is the build-host
    #      entry point. Excluding it here is mandatory: pkgbuild ignores
    #      the package-script archive entirely if it sees any top-level
    #      *.sh next to preinstall/postinstall (P-013), and the leftover
    #      build_pkg.sh would also leak the build-host source path into
    #      the customer .pkg. P-014 (2026-05-04) — see REPAIR_LOG.md.
    #   2. Move the .sh files in place to extensionless names. We keep
    #      both files under the same SCRIPTS_DIR (no copies) so there's
    #      exactly one preinstall and one postinstall in the archive.
    #   3. Re-assert executable bits on the renamed entry points and on
    #      every shell helper under lib/.
    /usr/bin/rsync -a \
        --exclude 'build_pkg.sh' \
        "${PKG_DIR}/scripts/" \
        "${SCRIPTS_DIR}/"

    if [[ ! -r "${SCRIPTS_DIR}/preinstall.sh" ]]; then
        _die 43 "step 4d: preinstall.sh missing in staged scripts dir: ${SCRIPTS_DIR}/preinstall.sh"
    fi
    if [[ ! -r "${SCRIPTS_DIR}/postinstall.sh" ]]; then
        _die 43 "step 4d: postinstall.sh missing in staged scripts dir: ${SCRIPTS_DIR}/postinstall.sh"
    fi
    /bin/mv -f "${SCRIPTS_DIR}/preinstall.sh"  "${SCRIPTS_DIR}/preinstall"
    /bin/mv -f "${SCRIPTS_DIR}/postinstall.sh" "${SCRIPTS_DIR}/postinstall"
    chmod 0755 "${SCRIPTS_DIR}/preinstall" "${SCRIPTS_DIR}/postinstall"
    chmod +x "${SCRIPTS_DIR}/lib/"*.sh

    # P-013 belt-and-suspenders: refuse to proceed unless the staged
    # scripts directory has the two extensionless entry points executable
    # and zero leftover *.sh entries at its top level (those would mean
    # the rename failed silently, e.g. file system case-insensitivity or
    # a future refactor that copied instead of moved).
    if [[ ! -x "${SCRIPTS_DIR}/preinstall" ]]; then
        _die 43 "step 4d: ${SCRIPTS_DIR}/preinstall not present or not executable after rename (P-013)"
    fi
    if [[ ! -x "${SCRIPTS_DIR}/postinstall" ]]; then
        _die 43 "step 4d: ${SCRIPTS_DIR}/postinstall not present or not executable after rename (P-013)"
    fi
    local stray_sh
    stray_sh="$(/usr/bin/find "${SCRIPTS_DIR}" -maxdepth 1 -type f -name '*.sh' 2>/dev/null)"
    if [[ -n "$stray_sh" ]]; then
        _log "step 4d FAIL: leftover top-level *.sh in scripts staging dir:"
        echo "$stray_sh" >&2
        _die 43 "step 4d: top-level *.sh files in ${SCRIPTS_DIR} after rename — pkgbuild --scripts would ignore preinstall/postinstall (P-013)"
    fi
    _log "step 4d OK: scripts staged as preinstall/postinstall (extensionless, executable) — P-013"

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

    # 4j. Uninstaller script assertion (D-18 Copy bug 3 / P-008,
    # v1.0.3). postinstall.sh::step_install_uninstall_script copies
    # ${PKG_DIR}/resources/uninstall.sh into ${MG_INSTALL_ROOT}/bin/
    # uninstall.sh and is the action that fulfills the
    # `sudo /Library/Application Support/MiningGuardian/bin/uninstall.sh`
    # path referenced from conclusion.html. A missing source file would
    # surface as exit 37 at install time on the customer Mac, after
    # notarization has already burned a round-trip; assert here in the
    # source tree so the build hard-fails earlier with exit 48.
    local uninstall_src="${PKG_DIR}/resources/uninstall.sh"
    if [[ ! -r "$uninstall_src" ]]; then
        _die 48 "step 4j: uninstall.sh missing in source tree: ${uninstall_src} (D-18 Copy bug 3 / P-008)"
    fi
    if [[ ! -x "$uninstall_src" ]]; then
        _die 48 "step 4j: uninstall.sh not executable: ${uninstall_src} (chmod +x committed source)"
    fi
    _log "step 4j OK: uninstall.sh staged from ${uninstall_src} (D-18 Copy bug 3)"

    # 4k. Installer-owned resources staging (D-18 P-025, 2026-05-05).
    #
    # postinstall.sh used to read launchd plists, launcher wrappers, the
    # scheduled-job plists, and uninstall.sh from `${SCRIPT_DIR}/../resources/...`.
    # That path resolves inside Installer.app's private scripts sandbox
    # at install time (`/tmp/PKInstallSandbox.<rand>/Scripts/...`), where
    # only preinstall + postinstall + lib/ exist — productbuild
    # --resources content is metadata-only and never lands on disk
    # alongside the scripts. Result: every install attempted to read
    # plists out of a directory the .pkg never created, which would have
    # surfaced as exit 37 / exit 40 the moment the path resolution was
    # exercised on a real Mini.
    #
    # Fix: copy the same `installer/macos-pkg/resources/launchd/` tree
    # plus `installer/macos-pkg/resources/uninstall.sh` into the payload
    # at `<payload>/installer-resources/`. At install time the payload is
    # laid down at `${MG_INSTALL_ROOT}/installer-resources/`, which
    # postinstall.sh now resolves through MG_PKG_PAYLOAD via the new
    # INSTALLER_RESOURCES_SRC constant (see postinstall.sh, just below
    # the MG_PKG_PAYLOAD assignment).
    #
    # The legacy `${PKG_DIR}/resources/` tree continues to feed
    # productbuild --resources for Distribution.xml, branding, welcome /
    # conclusion HTML, license text, etc. — that content remains
    # metadata-only and is unchanged. Only the install-time path
    # consumers move into the payload.
    local installer_resources_dst="${PAYLOAD_DIR}/installer-resources"
    install -d -m 0755 "$installer_resources_dst" "${installer_resources_dst}/launchd"
    /usr/bin/rsync -a \
        --exclude 'README.md' \
        "${PKG_DIR}/resources/launchd/" \
        "${installer_resources_dst}/launchd/"
    install -m 0755 "$uninstall_src" "${installer_resources_dst}/uninstall.sh"
    # Re-assert exec bits on launcher wrappers — rsync should preserve
    # them from the source tree, but a future operator-side checkout
    # without --keep-exec or a Windows-style filesystem could drop them.
    /bin/chmod +x "${installer_resources_dst}/launchd/launchers/"*.sh
    # Belt-and-suspenders: every label this build claims to ship must
    # exist in the staged payload tree. Drift here would silently let a
    # postinstall path resolution fall through to its dev-fallback at
    # install time (which would be `${SCRIPT_DIR}/../resources` — the
    # exact bug P-025 fixes), so we hard-fail the build instead.
    local stage_label
    for stage_label in "${scheduled_labels[@]}"; do
        if [[ ! -r "${installer_resources_dst}/launchd/scheduled/${stage_label}.plist" ]]; then
            _die 47 "step 4k: scheduled plist missing in staged installer-resources: ${stage_label}.plist (D-18 P-025)"
        fi
    done
    if [[ ! -x "${installer_resources_dst}/uninstall.sh" ]]; then
        _die 48 "step 4k: staged installer-resources/uninstall.sh not executable (D-18 P-025)"
    fi
    _log "step 4k OK: installer-resources staged at ${installer_resources_dst} (D-18 P-025)"

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
    # P-021 (2026-05-05). Lima/Colima's VZ driver requires the
    # `com.apple.security.virtualization` entitlement on the process
    # that creates the VZVirtualMachine. Upstream Lima's Makefile signs
    # both `_output/bin/limactl` and `_output/libexec/lima/lima-driver-vz`
    # with `codesign -f -v --entitlements vz.entitlements -s -`. When
    # we re-sign every Mach-O with Developer ID Application + hardened
    # runtime + secure timestamp here, codesign REPLACES the upstream
    # signature wholesale — including any embedded entitlements. Without
    # passing `--entitlements` ourselves, every VZ-needing binary loses
    # the virtualization entitlement, and `colima start --vm-type vz`
    # on Apple Silicon fails inside Lima's VZ driver subprocess with:
    #     Error Domain=VZErrorDomain Code=2
    #     "Invalid virtual machine configuration. The process doesn't
    #      have the "com.apple.security.virtualization" entitlement."
    # Observed live on the customer Mac mini against
    # `MiningGuardian-1.0.3-47efd658f16a.pkg` (postinstall round 4,
    # 2026-05-05): `colima start` succeeded through Lima version
    # handshake, downloaded + converted the disk image, then VZ rejected
    # the configuration. ha.stderr.log captured the exact entitlement
    # rejection.
    # Fix: pass our `vz.entitlements` plist to the Pass 2 codesign call
    # for every loose Mach-O whose basename matches the upstream-signed
    # set (limactl, lima-driver-vz, lima). Other binaries (colima,
    # docker, qemu-img if present) re-sign without entitlements as
    # before — they don't host VZ sessions and don't need the
    # entitlement.
    #
    # We also drop runtime/colima/share/lima/lima-guestagent.Darwin-aarch64.gz —
    # that's the Linux guest agent for QEMU mode. We're VZ-only on Apple
    # Silicon (PR #47), so the guest agent is dead weight AND notarization
    # rejects it because the .gz wrapper contains an unsigned Linux binary
    # that codesign cannot fix.
    #
    # P-026 (2026-05-05). The `find ... -type f -print0` Pass-2 walk
    # below picks up every Mach-O under the installer-owned Python
    # interpreter staged at `<payload>/runtime/python/` by step 4i. The
    # python3.12 binary, every `.so` extension under `lib/python3.12/`,
    # and any `.dylib` shipped with the framework all get re-signed with
    # Developer ID Application + hardened runtime + secure timestamp
    # without any new code path here — they live under runtime/, the
    # walk catches them, the same per-Mach-O codesign call applies. The
    # `Python.framework` (alternate layout) is caught by Pass 1 instead,
    # which already handles every `.framework` bundle as a unit.
    local runtime_dir="${PAYLOAD_DIR}/runtime"
    if [[ ! -d "$runtime_dir" ]]; then
        _log "step 4b SKIP: no runtime/ in payload (vendor dir was missing)"
        return 0
    fi

    # P-021. Locate the entitlements plist that pairs with the codesign
    # call below. Co-located with the helper libs at
    # installer/macos-pkg/scripts/lib/vz.entitlements (same directory
    # as resign_wheel.py / install_colima.sh — it ships with the build
    # script, NOT the customer payload).
    local vz_entitlements="${PKG_DIR}/scripts/lib/vz.entitlements"
    if [[ ! -r "$vz_entitlements" ]]; then
        _die 44 "step 4b: VZ entitlements plist missing at ${vz_entitlements} (P-021)"
    fi

    # P-021. Set of basenames that need the VZ entitlement passed to
    # codesign. Mirrors upstream lima-vm/lima Makefile, which signs
    # `_output/bin/limactl` and `_output/libexec/lima/lima-driver-vz`
    # with the same plist. We add `lima` (the client) defensively —
    # Lima 2.x exec's lima-driver-vz from limactl, but a future driver-
    # less mode where `lima` itself talks to VZ would already be
    # covered. Keep this list small and explicit; over-broad
    # entitlement application is itself a notarization risk.
    local vz_binary_names=(
        "limactl"
        "lima-driver-vz"
        "lima"
    )

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
    # .app or .framework bundle (Pass 1 already handled those). For
    # VZ-needing binaries we additionally pass --entitlements (P-021).
    local count_bundles=0 count_loose=0 count_vz=0 failed=0 path file_out base

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

        # P-021. Decide whether this binary needs the VZ entitlement.
        # Match by basename only — the vendor layout shifts between
        # Lima 1.x (limactl in colima/) and Lima 2.x (limactl in
        # colima/bin/, lima-driver-vz in colima/libexec/lima/), and
        # we want the rule to bind to the binary identity, not its
        # source path.
        base="$(basename "$path")"
        local needs_vz=0 vz_name
        for vz_name in "${vz_binary_names[@]}"; do
            if [[ "$base" == "$vz_name" ]]; then
                needs_vz=1
                break
            fi
        done

        if (( needs_vz == 1 )); then
            if /usr/bin/codesign \
                    --force \
                    --sign "$APPLE_DEV_ID_APPLICATION" \
                    --options runtime \
                    --timestamp \
                    --entitlements "$vz_entitlements" \
                    "$path" >/dev/null 2>&1; then
                count_loose=$((count_loose + 1))
                count_vz=$((count_vz + 1))
                _log "  signed with VZ entitlements: ${path#${PAYLOAD_DIR}/}"
            else
                failed=$((failed + 1))
                _log "  WARN codesign+entitlements failed for ${path#${PAYLOAD_DIR}/}"
            fi
        else
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

    # P-021 verify-after-sign — every VZ-needing binary present in the
    # payload must now carry com.apple.security.virtualization. The
    # build hard-fails here rather than burning a notarization round-
    # trip on a .pkg whose VZ binaries are missing the entitlement
    # (which would not be caught by Apple notary — the entitlement is
    # legal to omit; the failure surfaces only at install-time `colima
    # start`). We use `codesign -d --entitlements - <bin>` and grep the
    # output for the entitlement key. limactl is mandatory; the others
    # are optional (Lima 2.x ships lima-driver-vz, Lima 1.x does not).
    local vz_check_path vz_check_base
    while IFS= read -r -d '' vz_check_path; do
        vz_check_base="$(basename "$vz_check_path")"
        local match=0 vz_name
        for vz_name in "${vz_binary_names[@]}"; do
            if [[ "$vz_check_base" == "$vz_name" ]]; then
                match=1
                break
            fi
        done
        if (( match == 0 )); then
            continue
        fi
        case "$vz_check_path" in
            */*.app/*|*/*.framework/*) continue ;;
        esac
        if [[ "$(/usr/bin/file -b "$vz_check_path" 2>/dev/null || true)" != *"Mach-O"* ]]; then
            continue
        fi
        if ! /usr/bin/codesign -d --entitlements - "$vz_check_path" 2>/dev/null \
                | /usr/bin/grep -q 'com.apple.security.virtualization'; then
            _die 44 "step 4b: VZ entitlement missing after codesign on ${vz_check_path#${PAYLOAD_DIR}/} (P-021)"
        fi
    done < <(/usr/bin/find "$runtime_dir" -type f -print0)

    # P-021 mandatory-presence check. limactl MUST be present in the
    # payload — without it the install_colima.sh helper exits 1 at
    # install time anyway, but we want the build to fail fast (and
    # before notarization burns the cert + Apple round-trip). The
    # other VZ binaries are version-dependent and may legitimately be
    # absent.
    if [[ -z "$(/usr/bin/find "$runtime_dir" -type f -name 'limactl' -print -quit 2>/dev/null)" ]]; then
        _die 44 "step 4b: limactl not found anywhere under ${runtime_dir} — vendor layout is wrong (P-020)"
    fi

    _log "step 4b OK: re-sealed ${count_bundles} bundle(s), codesigned ${count_loose} loose Mach-O (${count_vz} with VZ entitlements — P-021)"
}

step_4c_resign_inner_wheels() {
    # P-011 (2026-05-04). Apple notarization rejects vendored Python wheels
    # whose embedded Mach-O binaries (.so / .dylib) are not signed with our
    # Developer ID Application + hardened runtime + secure timestamp.
    #
    # Apple notary submission 750c089f-f0a1-4d40-bf15-e8c295828027
    # (v1.0.3 first build, sha 295aec38f2ee, 2026-05-04) returned `Invalid`
    # listing rejections inside aiohttp, bcrypt (universal2), matplotlib,
    # and other wheels — all upstream-signed by their package maintainers
    # but not with our identity. The detailed log surfaced lines like:
    #   "not signed with valid Developer ID certificate ... no secure timestamp"
    # against paths of the form
    #   Payload/.../python-wheels/<wheel>.whl/<inner>/<file>.so
    #
    # The fix walks every *.whl in <payload>/python-wheels/, extracts it,
    # codesigns each inner Mach-O with --options runtime --timestamp, and
    # rewrites the wheel's *.dist-info/RECORD manifest so pip still accepts
    # the modified wheel as a valid install source. The Python helper
    # (`installer/macos-pkg/scripts/lib/resign_wheel.py`) implements all of
    # that with a post-rewrite verify pass that fails fast if RECORD and
    # the actual zip contents have drifted (would brick the customer's
    # `pip install --no-index` step at install time).
    #
    # We DO NOT touch wheels that contain no Mach-O — those are pure-Python
    # and pip accepts them unmodified. Most of the 108 wheels in the v1.0.3
    # closure fall in this category; only the C-extension wheels (aiohttp,
    # bcrypt, matplotlib, numpy, pandas, psycopg2-binary, pillow, frozenlist,
    # multidict, yarl, charset-normalizer, propcache, regex, ruamel.yaml.clib,
    # cryptography, lxml, pyzmq, etc.) need signing.
    #
    # Why this runs at step 4c, not 4b: 4b signs the loose vendored runtime
    # binaries (Colima, lima, qemu-img). Those live at <payload>/runtime/
    # and were never inside an archive; they sign in place. Wheel internals
    # need extract + sign + RECORD rewrite + repack, which is a different
    # shape and gets its own step. The wheels MUST be re-signed before
    # pkgbuild snapshots the payload at step 5.
    local wheels_dir="${PAYLOAD_DIR}/python-wheels"
    if [[ ! -d "$wheels_dir" ]]; then
        # Should never happen — step 4e exits 43 if the wheelhouse is missing.
        # Belt-and-suspenders: do not silently skip.
        _die 49 "step 4c: ${wheels_dir} missing — step 4e should have caught this"
    fi

    local wheel_total
    wheel_total="$(/usr/bin/find "$wheels_dir" -maxdepth 1 -type f -name '*.whl' | /usr/bin/wc -l | /usr/bin/tr -d ' ')"
    if (( wheel_total < 1 )); then
        _die 49 "step 4c: ${wheels_dir} contains no .whl (step 4e should have caught this)"
    fi

    local resigner="${PKG_DIR}/scripts/lib/resign_wheel.py"
    if [[ ! -r "$resigner" ]]; then
        _die 49 "step 4c: resign_wheel.py missing at ${resigner}"
    fi

    _log "step 4c: re-signing inner Mach-O across ${wheel_total} vendored wheel(s) in ${wheels_dir}"

    # /usr/bin/python3 ships on macOS as the Apple-stub Python; it's
    # sufficient for the helper's stdlib-only needs (zipfile, hashlib,
    # subprocess). We do NOT use the Homebrew /opt/homebrew/opt/python@3.12
    # interpreter here — keeping the build-time helper on the OS Python
    # avoids a second dependency on a specific Homebrew install path.
    if ! /usr/bin/python3 "$resigner" \
            --identity "$APPLE_DEV_ID_APPLICATION" \
            "$wheels_dir"; then
        _die 49 "step 4c: resign_wheel.py failed (see [resign_wheel] log lines above for the failing wheel)"
    fi

    # Post-flight: every wheel must still open as a valid zip and contain
    # exactly one *.dist-info/RECORD. The helper already runs an internal
    # verify, but we double-check here so a future refactor can't
    # accidentally bypass it.
    local whl
    while IFS= read -r -d '' whl; do
        if ! /usr/bin/python3 -c "
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'r') as zf:
    names = zf.namelist()
    rec = [n for n in names if n.endswith('.dist-info/RECORD')]
    if len(rec) != 1:
        sys.exit(f'expected one RECORD, got {len(rec)} in {sys.argv[1]}')
" "$whl" >/dev/null 2>&1; then
            _die 49 "step 4c: post-resign verify failed for ${whl#${PAYLOAD_DIR}/}"
        fi
    done < <(/usr/bin/find "$wheels_dir" -maxdepth 1 -type f -name '*.whl' -print0)

    _log "step 4c OK: ${wheel_total} wheel(s) re-signed and RECORD-verified (P-011)"
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
    local detail_log="${BUILD_DIR}/MiningGuardian-${BUILD_VERSION}-${BUILD_SHA}.notarization-detail.json"

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
        # P-011 follow-up (low-risk auto-fetch). When notary returns Invalid,
        # the only way to know which Mach-O failed is `xcrun notarytool log
        # <submission-id>`. Auto-fetch it here so the operator gets the
        # detailed JSON in the same build/ directory as the summary log.
        # Failure of the auto-fetch itself MUST NOT mask the original
        # _die 45 — we always exit non-zero below.
        local sub_id
        sub_id="$(/usr/bin/awk '/^[[:space:]]*id:[[:space:]]/{print $2; exit}' "$notlog" | /usr/bin/tr -d '\r')"
        if [[ -n "$sub_id" ]]; then
            _log "step 6: notarization not Accepted; fetching detailed log for submission ${sub_id}"
            /usr/bin/xcrun notarytool log \
                "$sub_id" \
                --key       "$APPLE_NOTARIZATION_KEY_PATH" \
                --key-id    "$APPLE_NOTARIZATION_KEY_ID" \
                --issuer    "$APPLE_NOTARIZATION_ISSUER_UUID" \
                --team-id   "$APPLE_TEAM_ID" \
                "$detail_log" 2>&1 || true
            if [[ -s "$detail_log" ]]; then
                _log "step 6: detailed notarization log written to ${detail_log}"
            fi
        else
            _log "step 6: could not parse submission id from ${notlog}; skip detail fetch"
        fi
        _die 45 "notarization not accepted; see ${notlog} and ${detail_log}"
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
    step_4c_resign_inner_wheels
    step_5_pkgbuild_and_sign
    step_6_notarize
    step_7_staple
    step_8_sidecar
    step_9_print
}

main "$@"
