#!/bin/bash
# installer/macos-pkg/scripts/preinstall.sh
#
# macOS .pkg preinstall script — RUNS AS root via Installer.app.
#
# Job: validate the host BEFORE any payload is laid down on disk. If any
# refuse-to-install gate fails, exit non-zero so Installer.app aborts the
# install cleanly and shows the error to the operator.
#
# Implements the following locked decisions from docs/DECISIONS.md:
#
#   • Q1 (Hybrid ~500 MB .pkg)        — single-shot install, no terminal wizard
#   • D-13 (RAM-detected Ollama)      — delegated to lib/detect_ram.sh
#   • Cutover scope γ                 — Mini replaces VPS + ROBS-PC, so we
#                                        gate on Apple Silicon + macOS 13+
#   • Vision Anchor 6 (BTC SHA-256)   — no altcoin paths, ever
#   • Vision Anchor 7 (local-only)    — no cloud-only deps. Network IS
#                                        required at first-run for the
#                                        Ollama model pull (postinstall.sh),
#                                        but THIS script makes no calls.
#
# Refuse-to-install gates (in evaluation order):
#   1. Running as root
#   2. macOS 13.0 (Ventura) or later
#   3. Apple Silicon (arm64)         — Mini is M-series; refuse Intel
#   4. RAM ≥ 16 GB                   — D-13 floor
#   5. Free disk on / ≥ 20 GB        — payload + Postgres data + LLM model
#   6. /Applications writable        — sanity check
#   7. No conflicting prior install  — refuse if a non-pkg-managed
#                                       Mining-Guardian instance is detected
#
# All log lines go to /var/log/mining-guardian/install-preinstall.log AND
# stderr (Installer.app surfaces stderr in the install-failed dialog).
#
# Exit codes:
#   0   — all gates passed; ok to lay down payload
#   10  — not root
#   11  — macOS too old
#   12  — Intel Mac (or unsupported arch)
#   13  — insufficient RAM
#   14  — insufficient disk
#   15  — /Applications not writable
#   16  — conflicting prior install detected
#   20  — detect_ram.sh failed to write env file (fatal — postinstall
#         depends on it)

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

readonly MIN_MACOS_MAJOR=13
readonly MIN_RAM_GB=16
readonly MIN_FREE_DISK_GB=20
readonly EXPECTED_ARCH="arm64"

# Exported so detect_ram.sh + postinstall.sh agree on paths.
export MG_INSTALL_LOG="/var/log/mining-guardian/install-preinstall.log"
export MG_INSTALL_ENV="/tmp/mg_install_env"

# Resolve the directory this script is in so we can find lib/detect_ram.sh
# regardless of where Installer.app spawns us from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DETECT_RAM_LIB="${SCRIPT_DIR}/lib/detect_ram.sh"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_setup_log() {
    # /var/log is always writable as root on macOS.
    local log_dir
    log_dir="$(dirname "$MG_INSTALL_LOG")"
    mkdir -p "$log_dir"
    chown root:wheel "$log_dir"
    chmod 0750 "$log_dir"
    : > "$MG_INSTALL_LOG"
    chmod 0640 "$MG_INSTALL_LOG"
}

log() {
    local msg="$1"
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [preinstall] $msg" | tee -a "$MG_INSTALL_LOG" >&2
}

fail() {
    local code="$1"; shift
    log "FATAL ($code) $*"
    log "Aborting install. See $MG_INSTALL_LOG for full context."
    exit "$code"
}

# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

gate_root() {
    # Installer.app runs preinstall as root; if EUID != 0 we are running
    # outside Installer.app (someone double-clicked a script directly?)
    # and should refuse.
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        fail 10 "preinstall.sh must run as root (EUID=$(id -u))"
    fi
    log "OK gate_root: running as root"
}

gate_macos_version() {
    local product_version major
    if ! product_version=$(/usr/bin/sw_vers -productVersion 2>/dev/null); then
        fail 11 "could not read sw_vers -productVersion"
    fi
    major="${product_version%%.*}"
    if ! [[ "$major" =~ ^[0-9]+$ ]]; then
        fail 11 "could not parse macOS major version from '$product_version'"
    fi
    if [[ "$major" -lt "$MIN_MACOS_MAJOR" ]]; then
        fail 11 "macOS $product_version is too old; require ${MIN_MACOS_MAJOR}.0+"
    fi
    log "OK gate_macos_version: ${product_version} >= ${MIN_MACOS_MAJOR}.0"
}

gate_apple_silicon() {
    # P-015 — `uname -m` reports the architecture of the CURRENT PROCESS, not
    # the hardware. On Apple Silicon, if Installer.app spawns the preinstall
    # under a Rosetta-translated /bin/bash (common when the operator's
    # Terminal.app has "Open using Rosetta" checked, or when `installer` is
    # invoked via `arch -x86_64 sudo installer ...`), `uname -m` returns
    # `x86_64` even though the Mac is M-series. v1.0.3 build 2b48f98 hit this
    # exact false negative on Bobby's Mac mini 2026-05-04, with the
    # preinstall log showing "FATAL (12) ... detected 'x86_64'" on what is
    # documented as an M-series box.
    #
    # The kernel-authoritative hardware indicator is `sysctl hw.optional.arm64`,
    # which is set by the kernel based on the SoC and does NOT change under
    # Rosetta translation:
    #   * `=1` on Apple Silicon hardware (M1/M2/M3/M4/...), regardless of
    #     whether the calling process is Rosetta-translated.
    #   * `=0` (or sysctl key not present, returning non-zero exit) on Intel
    #     Macs.
    #
    # `sysctl.proc_translated` is the per-process Rosetta indicator
    # (=1 iff the current process is running under Rosetta 2; =0 native;
    # missing on Intel). We log it for diagnostics but do NOT gate on it —
    # a Rosetta-translated preinstall on Apple Silicon hardware should still
    # succeed; the postinstall and the daemon will run native arm64 once
    # the LaunchDaemons fire.
    #
    # Intel-only support is explicitly out of scope per CLAUDE.md / D-18 /
    # Vision Anchor 2 (Mini IS the product, M-series only). This gate must
    # still hard-refuse Intel — only the false-negative on Apple Silicon is
    # being fixed here.

    local hw_arm64 sysctl_rc translated translated_rc uname_arch
    # Capture sysctl exit code separately from value. `set -e` is in effect
    # so we wrap the assignment in an explicit if so a non-zero rc (missing
    # key on Intel, sysctl binary missing) does NOT abort the script.
    if hw_arm64="$(/usr/sbin/sysctl -n hw.optional.arm64 2>/dev/null)"; then
        sysctl_rc=0
    else
        sysctl_rc=$?
        hw_arm64=""
    fi
    if translated="$(/usr/sbin/sysctl -n sysctl.proc_translated 2>/dev/null)"; then
        translated_rc=0
    else
        translated_rc=$?
        translated=""
    fi
    uname_arch="$(/usr/bin/uname -m 2>/dev/null || echo unknown)"

    log "gate_apple_silicon probes: hw.optional.arm64='${hw_arm64}' (rc=${sysctl_rc}) sysctl.proc_translated='${translated}' (rc=${translated_rc}) uname -m='${uname_arch}'"

    # Authoritative path: hw.optional.arm64 readable AND equals 1 → Apple
    # Silicon hardware, accept regardless of process arch.
    if [[ "$hw_arm64" == "1" ]]; then
        if [[ "$translated" == "1" ]]; then
            log "WARN gate_apple_silicon: preinstall is running under Rosetta 2 translation (sysctl.proc_translated=1); hardware is Apple Silicon so install will proceed, but the operator should re-run with a native /bin/bash (Terminal.app → Get Info → uncheck 'Open using Rosetta', or invoke 'arch -arm64 sudo installer ...') if they hit any other arch-sensitive failure"
        fi
        log "OK gate_apple_silicon: hw.optional.arm64=1 (Apple Silicon hardware confirmed; uname -m='${uname_arch}')"
        return 0
    fi

    # hw.optional.arm64 readable AND equals 0 → Intel hardware. Refuse.
    if [[ "$hw_arm64" == "0" ]]; then
        fail 12 "this build supports Apple Silicon only; sysctl hw.optional.arm64=0 (Intel hardware)"
    fi

    # sysctl unreadable / missing key (rc != 0 or empty value): we cannot
    # trust uname -m alone (it lies under Rosetta). The defensive choice is
    # to fall back to uname -m only when uname AGREES with arm64 — that's
    # the only path where both signals point at Apple Silicon. If uname
    # says x86_64 here, we have NO authoritative arm64 evidence and must
    # refuse rather than accept a likely-Intel Mac.
    if [[ "$uname_arch" == "$EXPECTED_ARCH" ]]; then
        log "WARN gate_apple_silicon: sysctl hw.optional.arm64 unreadable (rc=${sysctl_rc}, value='${hw_arm64}'); falling back to uname -m='${uname_arch}' which agrees with Apple Silicon"
        return 0
    fi

    fail 12 "this build supports Apple Silicon (${EXPECTED_ARCH}) only; sysctl hw.optional.arm64='${hw_arm64}' (rc=${sysctl_rc}), uname -m='${uname_arch}'"
}

gate_ram() {
    # We delegate the actual sysctl read + tier selection to
    # lib/detect_ram.sh, which writes MG_INSTALL_ENV. Here we just
    # parse the result and assert the floor.
    if [[ ! -x "$DETECT_RAM_LIB" ]]; then
        # Fall back to bash-executing it if not marked +x (the .pkg build
        # SHOULD chmod +x at productbuild time, but defensively handle
        # the case where it didn't).
        if [[ ! -r "$DETECT_RAM_LIB" ]]; then
            fail 13 "RAM detection helper missing: $DETECT_RAM_LIB"
        fi
    fi

    if ! /bin/bash "$DETECT_RAM_LIB"; then
        fail 20 "detect_ram.sh failed; postinstall would have no LLM model"
    fi

    if [[ ! -r "$MG_INSTALL_ENV" ]]; then
        fail 20 "$MG_INSTALL_ENV was not produced by detect_ram.sh"
    fi

    # shellcheck disable=SC1090
    source "$MG_INSTALL_ENV"

    if [[ -z "${MG_INSTALL_RAM_TIER:-}" ]]; then
        fail 20 "MG_INSTALL_RAM_TIER is empty after sourcing $MG_INSTALL_ENV"
    fi

    if [[ "$MG_INSTALL_RAM_TIER" -lt "$MIN_RAM_GB" ]]; then
        fail 13 "detected ${MG_INSTALL_RAM_TIER} GB RAM; require ${MIN_RAM_GB} GB+"
    fi

    log "OK gate_ram: ${MG_INSTALL_RAM_TIER} GB >= ${MIN_RAM_GB} GB; model=${MG_INSTALL_LLM_MODEL:-?}"
}

gate_free_disk() {
    # df -k / returns 1K-blocks; column 4 is "Available". Convert to GB.
    local avail_kb avail_gb
    if ! avail_kb=$(/bin/df -k / | awk 'NR==2 {print $4}'); then
        fail 14 "could not read free disk on /"
    fi
    if ! [[ "$avail_kb" =~ ^[0-9]+$ ]]; then
        fail 14 "df returned non-numeric available KB: '$avail_kb'"
    fi
    avail_gb=$(( avail_kb / 1024 / 1024 ))
    if [[ "$avail_gb" -lt "$MIN_FREE_DISK_GB" ]]; then
        fail 14 "only ${avail_gb} GB free on /; require ${MIN_FREE_DISK_GB} GB+"
    fi
    log "OK gate_free_disk: ${avail_gb} GB free >= ${MIN_FREE_DISK_GB} GB"
}

gate_applications_writable() {
    if [[ ! -d /Applications ]]; then
        fail 15 "/Applications does not exist"
    fi
    if [[ ! -w /Applications ]]; then
        fail 15 "/Applications is not writable by root (filesystem read-only?)"
    fi
    log "OK gate_applications_writable"
}

gate_no_conflict() {
    # Refuse if a previously-installed Mining-Guardian shell is sitting
    # at /Applications/Mining\ Guardian.app AND was not laid down by a
    # .pkg (i.e. no /var/db/receipts entry). That's the case where a dev
    # built from source on this Mac and the operator forgot.
    local app="/Applications/Mining Guardian.app"
    if [[ -d "$app" ]]; then
        if /usr/sbin/pkgutil --pkg-info-plist com.miningguardian.installer >/dev/null 2>&1; then
            log "OK gate_no_conflict: prior pkg-managed install found, will be upgraded"
            return 0
        fi
        fail 16 "found '$app' but no pkg receipt — refuse to clobber a hand-built copy"
    fi
    log "OK gate_no_conflict: clean host"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    _setup_log
    log "Mining Guardian preinstall starting (pid=$$)"
    log "Installer payload: ${PWD}"
    log "Target volume: ${3:-/}"

    gate_root
    gate_macos_version
    gate_apple_silicon
    gate_ram
    gate_free_disk
    gate_applications_writable
    gate_no_conflict

    log "All preinstall gates passed; handing off to Installer.app payload phase"
    return 0
}

main "$@"
