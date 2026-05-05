#!/bin/bash
# installer/macos-pkg/scripts/lib/install_colima.sh
#
# Stand up Colima as the local container runtime + load the bundled
# Postgres 16-bookworm image (vendored inside the .pkg payload — no
# network call needed for this step). Mining Guardian's database lives
# inside this Colima-managed Postgres container.
#
# Q1 (hybrid .pkg) calls for Colima + the Postgres image to be
# **shipped inside** the .pkg so a customer can stand up the database
# offline. The actual `ollama pull <model>` is the one network step
# at first-run (see install_ollama.sh).
#
# This script is sourced by postinstall.sh, NOT executed standalone.
# It expects:
#   • Caller is already root.
#   • $MG_PKG_PAYLOAD points at the directory in which the bundled
#     binaries (colima, lima) and the docker images live. We use
#     Apple's Virtualization.framework (--vm-type vz) — no QEMU needed.
#   • $MG_INSTALL_ROOT = /Library/Application Support/MiningGuardian.
#   • $MG_INSTALL_LOG is open for append.
#
# Functions exported:
#   install_colima_runtime   — copy colima/lima binaries, init+start
#   load_postgres_image      — `docker load` the bundled image tarball
#   provision_postgres       — create persistent volume + start container
#                              + run migrations 000/002/003 + wait for
#                              "ready" before returning
#
# Vision Anchor 7 (local-only) — no curl, no brew install. All bytes
# are vendored.

set -euo pipefail

# ---------------------------------------------------------------------------
# Logging — re-uses the preinstall log file
# ---------------------------------------------------------------------------

_log() {
    local msg="[colima] $*"
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $msg" | tee -a "${MG_INSTALL_LOG:-/dev/stderr}" >&2
}

_die() {
    _log "FATAL $*"
    return 1
}

# ---------------------------------------------------------------------------
# Operator-user resolution (P-018, 2026-05-05)
# ---------------------------------------------------------------------------
#
# Postinstall.sh resolves the operator account once (via three bounded
# probes — see postinstall.sh::_resolve_install_user) and exports the
# value as MG_INSTALL_OPERATOR_USER before sourcing this helper. Use that
# value in every `chown` / `sudo -u` site so we never accidentally fall
# back to the legacy `${SUDO_USER:-${USER}}` pattern, which evaluates to
# `root` under Installer.app (USER=root, SUDO_USER unset) and would (a)
# point colima at /Users/root (does not exist) and (b) own colima/docker
# state as root rather than the operator.
#
# `_op_user` mirrors postinstall's resolver as a fallback so dev / smoke-
# test invocations that source this lib outside a real .pkg install still
# get a usable, non-root account. Order:
#
#   1. ${MG_INSTALL_OPERATOR_USER} if set, non-empty, and not "root".
#   2. ${SUDO_USER} if set, non-empty, and not "root" (operator-side
#      `sudo bash install_colima.sh` for testing).
#   3. /dev/console owner via stat -f '%Su' (the GUI logged-in user).
#   4. /Users/*/Desktop/MiningGuardian.conf scan (last-ditch — finds the
#      operator by where they put the conf).
#   5. Empty + `_die` — refuse to silently pick `root` when a real user
#      account exists somewhere.
#
# Returns the chosen account on stdout; non-zero exit on no usable user.
_op_user() {
    local u="${MG_INSTALL_OPERATOR_USER:-}"
    if [[ -n "$u" && "$u" != "root" ]]; then
        printf '%s' "$u"
        return 0
    fi
    if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
        printf '%s' "${SUDO_USER}"
        return 0
    fi
    if [[ -e /dev/console ]]; then
        u="$(/usr/bin/stat -f '%Su' /dev/console 2>/dev/null || true)"
        if [[ -n "$u" && "$u" != "root" ]]; then
            printf '%s' "$u"
            return 0
        fi
    fi
    local d
    for d in /Users/*; do
        [[ -e "${d}/Desktop/MiningGuardian.conf" ]] || continue
        printf '%s' "$(basename "$d")"
        return 0
    done
    _die "could not resolve a non-root operator account; refusing to run colima as root"
    return 1
}

_op_home() {
    local user
    user="$(_op_user)" || return 1
    local home
    home="$(/usr/bin/dscl . -read "/Users/${user}" NFSHomeDirectory 2>/dev/null \
              | /usr/bin/awk '/^NFSHomeDirectory:/ { print $2 }')"
    if [[ -z "$home" ]]; then
        home="/Users/${user}"
    fi
    if [[ ! -d "$home" ]]; then
        _die "operator home directory not found for ${user}: ${home}"
        return 1
    fi
    printf '%s' "$home"
}

# ---------------------------------------------------------------------------
# PATH propagation under `sudo -u` (P-019, 2026-05-05)
# ---------------------------------------------------------------------------
#
# `sudo -u <op>` on macOS clears the inherited PATH and substitutes the
# `secure_path` from /etc/sudoers (typically `/usr/bin:/bin:/usr/sbin:/sbin`
# — note the absence of /usr/local/bin). That is fine for invoking colima
# itself by absolute path, but `colima start` shells out to look up its
# helpers via `os/exec.LookPath("limactl")`, which obeys the child PATH.
#
# Without explicit PATH propagation, the post-`install_colima_runtime`
# `colima start` invocation crashes with
#     lima compatibility error: error checking Lima version:
#     exec: "limactl": executable file not found in $PATH
# even though we just installed limactl to /usr/local/bin two lines above
# — observed live on the customer Mac mini against
# `MiningGuardian-1.0.3-32ec2dcad973.pkg` (postinstall round 3, 2026-05-05).
#
# `_op_path` returns the PATH every `sudo -u "$op_user" …` invocation in
# this file MUST pass through `env PATH=…` so colima/docker can find
# their helpers (limactl, lima, lima-driver-krunkit). Order matters:
# /usr/local/bin first so our vendored binaries shadow any older copies
# that might have ended up in /opt/homebrew or /usr/bin.
#
# Same value used by every site below — defined once so a future
# redirection of /usr/local/bin → /opt/mg/bin is a one-liner.
_op_path() {
    printf '%s' "/usr/local/bin:/usr/local/sbin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
}

# Verify limactl is present at the expected install location and is
# executable. Refuse to proceed otherwise — colima will produce a
# misleading "$PATH" error if limactl is missing entirely, but we want
# the postinstall log to say which file is missing (P-019).
_verify_limactl() {
    local limactl_path="$1"
    if [[ ! -x "$limactl_path" ]]; then
        _die "limactl not found at ${limactl_path}; vendored runtime layout is wrong (expected limactl alongside colima)"
        return 1
    fi
    _log "INFO limactl present at ${limactl_path}"
    return 0
}

# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

install_colima_runtime() {
    local payload="${MG_PKG_PAYLOAD:?MG_PKG_PAYLOAD must be set}"
    local target_bin="/usr/local/bin"

    # Vendored binaries live under <payload>/runtime/colima/.
    # Confirm they are present before doing anything destructive.
    local src="${payload}/runtime/colima"
    if [[ ! -d "$src" ]]; then
        _die "vendored colima runtime not found at ${src}"
        return 1
    fi

    install -d -m 0755 "$target_bin"
    install -m 0755 "${src}/colima"  "${target_bin}/colima"

    # P-020 (2026-05-05). Locate limactl in the vendored payload. Lima
    # 1.x ships it directly under `${src}/limactl`; Lima 2.x ships it
    # under `${src}/bin/limactl`. The earlier hard-coded `${src}/limactl`
    # would `install` exit non-zero (set -e) on Lima 2.x layouts and
    # leave the operator with no clear log line about why. Walk the two
    # known locations explicitly, and refuse to proceed (with the path
    # we searched logged) if neither is present. Build-time
    # step_4b_codesign_inner_binaries also asserts at least one
    # `limactl` exists anywhere under runtime/, so a vendor-dir layout
    # that hides limactl elsewhere would already fail the build.
    local limactl_src=""
    if [[ -f "${src}/limactl" ]]; then
        limactl_src="${src}/limactl"
    elif [[ -f "${src}/bin/limactl" ]]; then
        limactl_src="${src}/bin/limactl"
    fi
    if [[ -z "$limactl_src" ]]; then
        _die "vendored limactl not found at ${src}/limactl or ${src}/bin/limactl (P-020)"
        return 1
    fi
    install -m 0755 "$limactl_src" "${target_bin}/limactl"
    _log "INFO copied limactl from ${limactl_src#${payload}/} to ${target_bin}/limactl"

    # Docker CLI — client only. Daemon runs inside the Colima VM.
    # Vendored at <payload>/runtime/docker/docker (alongside colima/).
    local docker_src="${payload}/runtime/docker/docker"
    if [[ -f "$docker_src" ]]; then
        install -m 0755 "$docker_src" "${target_bin}/docker"
        _log "INFO copied docker CLI to ${target_bin}/docker"
    else
        _die "vendored docker CLI not found at ${docker_src}"
        return 1
    fi

    # Lima 2.x ships its helpers (lima-driver-krunkit, limactl-mcp) in
    # libexec/. Mirror the vendored layout into /usr/local/libexec so
    # limactl can find them at runtime.
    if [[ -d "${src}/libexec" ]]; then
        install -d -m 0755 /usr/local/libexec
        cp -R "${src}/libexec/lima" /usr/local/libexec/lima
    fi
    if [[ -d "${src}/share" ]]; then
        install -d -m 0755 /usr/local/share
        cp -R "${src}/share/"* /usr/local/share/ 2>/dev/null || true
    fi
    if [[ -d "${src}/bin" ]]; then
        # Lima wrapper scripts (docker.lima, kubectl.lima, etc.)
        for w in "${src}/bin"/*.lima; do
            [[ -f "$w" ]] && install -m 0755 "$w" "${target_bin}/$(basename "$w")"
        done
        # The actual lima binary lives in bin/ on Lima 2.x
        if [[ -f "${src}/bin/lima" ]]; then
            install -m 0755 "${src}/bin/lima" "${target_bin}/lima"
        fi
    fi

    _log "INFO copied colima + lima (VZ-only, no QEMU) to ${target_bin}"

    # Initialise the colima VM in the operator's home. We pin a small VM
    # (4 CPU, 8 GB) — the heavier work is the LLM, which runs on the host
    # not the VM.
    #
    # P-018 — resolve the operator via _op_user (which prefers
    # MG_INSTALL_OPERATOR_USER, exported by postinstall.sh::main()
    # before this helper is sourced). The legacy
    # `${SUDO_USER:-${USER}}` pattern resolved to `root` under
    # Installer.app (USER=root, SUDO_USER unset) and would have run
    # `sudo -u root colima start` while pointing at /Users/root — both
    # wrong. _op_user refuses to return `root`, so a missing operator
    # raises `_die` cleanly here.
    local op_user op_home
    op_user="$(_op_user)" || return 1
    op_home="$(_op_home)" || return 1
    _log "INFO colima will run as ${op_user} (home=${op_home})"

    # P-019 — verify limactl is at the location we just installed it
    # before we hand control to colima. `colima start` resolves limactl
    # through `$PATH`, and `sudo -u` strips PATH on macOS — see _op_path
    # header. A missing limactl would otherwise surface as the misleading
    # `executable file not found in $PATH` error from colima.
    _verify_limactl "${target_bin}/limactl" || return 1

    # Apple Silicon: use --vm-type vz (Apple's Virtualization.framework).
    # Faster than QEMU, native to M-series, and means we don't need to
    # bundle qemu-system-aarch64 in the .pkg payload (saves ~50 MB).
    #
    # P-019 — explicit PATH on the `sudo -u` line via `env PATH=…` so
    # colima's child-process lookup of `limactl` succeeds. Without it,
    # the operator inherits sudoers' secure_path (no /usr/local/bin) and
    # colima fails before any VM bytes are touched. HOME is set so
    # colima's per-user state lands under the operator's home, not /var/empty.
    sudo -u "${op_user}" \
        /usr/bin/env PATH="$(_op_path)" HOME="${op_home}" \
        "${target_bin}/colima" start --vm-type vz \
        --runtime docker --memory 8 --cpu 4 --disk 60 \
        2>&1 | tee -a "${MG_INSTALL_LOG}" || {
            _die "colima start failed; see install log"
            return 1
        }
    _log "INFO colima started (vz, 4 cpu, 8 GB, 60 GB disk)"
}

load_postgres_image() {
    local payload="${MG_PKG_PAYLOAD:?MG_PKG_PAYLOAD must be set}"
    local tarball="${payload}/runtime/images/postgres-16-bookworm.tar"

    if [[ ! -f "$tarball" ]]; then
        _die "vendored postgres image not found at ${tarball}"
        return 1
    fi

    # docker load is idempotent — it will refuse-with-success if the
    # image already exists at this digest, which is what we want for
    # re-installs.
    #
    # P-018 — `sudo -u <op>` so docker.sock ownership matches the
    # colima-launching user (lib/install_colima.sh runs `colima start`
    # as that same user above). Legacy `${SUDO_USER:-${USER}}` would
    # become `root` under Installer.app and `sudo -u root` cannot read
    # the operator's docker context.
    local op_user op_home
    op_user="$(_op_user)" || return 1
    op_home="$(_op_home)" || return 1
    # P-019 — same PATH propagation rule as install_colima_runtime.
    # `docker` is a shim that resolves `colima` / `limactl` for context
    # discovery; without /usr/local/bin on PATH the docker CLI cannot
    # locate its sibling binaries even though we just installed them.
    sudo -u "${op_user}" \
        /usr/bin/env PATH="$(_op_path)" HOME="${op_home}" \
        docker load -i "$tarball" \
        2>&1 | tee -a "${MG_INSTALL_LOG}" || {
            _die "docker load of postgres image failed"
            return 1
        }
    _log "INFO loaded postgres:16-bookworm into colima"
}

provision_postgres() {
    local install_root="${MG_INSTALL_ROOT:?MG_INSTALL_ROOT must be set}"
    local pgdata_dir="${install_root}/postgres-data"
    local container_name="mining-guardian-db"

    # P-018 — resolve once, use everywhere. The legacy
    # `${SUDO_USER:-${USER}}` pattern picked `root` under Installer.app
    # and chowned pgdata to root, then ran every docker call as root —
    # which fails because `colima start` was launched as the operator
    # and the docker socket lives in the operator's home.
    local op_user op_home
    op_user="$(_op_user)" || return 1
    op_home="$(_op_home)" || return 1
    # P-019 — every `sudo -u` site below uses `env PATH=…` so docker can
    # resolve its colima/limactl helpers under sudoers' stripped PATH.
    local op_path
    op_path="$(_op_path)"

    install -d -m 0700 "$pgdata_dir"
    chown "${op_user}:staff" "$pgdata_dir"
    _log "INFO created persistent postgres volume at ${pgdata_dir} (owner=${op_user})"

    # Pull MG_DB_PASSWORD from the .env that postinstall.sh dropped
    # before calling us. NEVER hard-code a default here.
    if [[ -z "${MG_DB_PASSWORD:-}" ]]; then
        _die "MG_DB_PASSWORD missing from environment; postinstall did not source .env"
        return 1
    fi

    # Start (or re-start, idempotent) the container. We deliberately do
    # NOT publish 5432 to 0.0.0.0 — only to 127.0.0.1 — because the
    # Mini stays on the miner LAN and there's no reason to expose
    # Postgres to other hosts on that network.
    sudo -u "${op_user}" \
        /usr/bin/env PATH="$op_path" HOME="${op_home}" \
        docker rm -f "$container_name" 2>/dev/null || true
    sudo -u "${op_user}" \
        /usr/bin/env PATH="$op_path" HOME="${op_home}" \
        docker run -d \
        --name "$container_name" \
        --restart unless-stopped \
        -p 127.0.0.1:5432:5432 \
        -e POSTGRES_DB=mining_guardian \
        -e POSTGRES_USER=mg \
        -e POSTGRES_PASSWORD="$MG_DB_PASSWORD" \
        -v "${pgdata_dir}:/var/lib/postgresql/data" \
        postgres:16-bookworm \
        2>&1 | tee -a "${MG_INSTALL_LOG}" || {
            _die "docker run for postgres failed"
            return 1
        }

    # Wait for `pg_isready` for up to 60 s.
    local i=0
    while (( i < 60 )); do
        if sudo -u "${op_user}" \
                /usr/bin/env PATH="$op_path" HOME="${op_home}" \
                docker exec "$container_name" \
                pg_isready -U mg -d mining_guardian >/dev/null 2>&1; then
            _log "INFO postgres ready after ${i}s"
            return 0
        fi
        sleep 1
        i=$(( i + 1 ))
    done

    _die "postgres did not become ready within 60s; see ${MG_INSTALL_LOG}"
    return 1
}
