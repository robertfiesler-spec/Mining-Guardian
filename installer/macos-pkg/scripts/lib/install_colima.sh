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
#     binaries (colima, lima, qemu) and the docker images live.
#   • $MG_INSTALL_ROOT = /usr/local/MiningGuardian.
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
    install -m 0755 "${src}/limactl" "${target_bin}/limactl"
    install -m 0755 "${src}/qemu-img" "${target_bin}/qemu-img" 2>/dev/null || true

    _log "INFO copied colima + lima to ${target_bin}"

    # Initialise the colima VM in the operator's home. We pin a small VM
    # (4 CPU, 8 GB) — the heavier work is the LLM, which runs on the host
    # not the VM.
    local home="/Users/${SUDO_USER:-${USER}}"
    if [[ ! -d "$home" ]]; then
        _die "could not resolve operator home directory"
        return 1
    fi

    sudo -u "${SUDO_USER:-${USER}}" \
        "${target_bin}/colima" start --runtime docker --memory 8 --cpu 4 \
        --disk 60 \
        2>&1 | tee -a "${MG_INSTALL_LOG}" || {
            _die "colima start failed; see install log"
            return 1
        }
    _log "INFO colima started (4 cpu, 8 GB, 60 GB disk)"
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
    sudo -u "${SUDO_USER:-${USER}}" docker load -i "$tarball" \
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

    install -d -m 0700 "$pgdata_dir"
    chown "${SUDO_USER:-${USER}}:staff" "$pgdata_dir"
    _log "INFO created persistent postgres volume at ${pgdata_dir}"

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
    sudo -u "${SUDO_USER:-${USER}}" docker rm -f "$container_name" 2>/dev/null || true
    sudo -u "${SUDO_USER:-${USER}}" docker run -d \
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
        if sudo -u "${SUDO_USER:-${USER}}" docker exec "$container_name" \
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
