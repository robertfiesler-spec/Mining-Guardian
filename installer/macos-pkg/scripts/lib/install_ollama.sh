#!/bin/bash
# installer/macos-pkg/scripts/lib/install_ollama.sh
#
# Install Ollama on the host + pull the LLM model selected by
# detect_ram.sh (D-13: 16 GB → llama3.2:3b, 24 GB+ →
# qwen2.5:14b-instruct-q4_K_M).
#
# Ollama is the ONE first-run network step in the Q1 hybrid .pkg
# (see installer/macos-pkg/README.md). The Ollama installer .app
# itself is vendored inside the .pkg payload so no curl-pipe-bash;
# only the model bytes come over the wire.
#
# Loud failure on network unreachable, per the D-14 PR 3/5
# dual-contract precedent: this install MUST NOT silently degrade
# to "no LLM, scanner half-works". If the model can't be pulled,
# the install aborts cleanly so the operator can fix the network
# and re-run.
#
# This script is sourced by postinstall.sh, NOT executed standalone.
# It expects:
#   • Caller is already root.
#   • $MG_PKG_PAYLOAD points at the directory containing the vendored
#     Ollama.app installer payload.
#   • $MG_INSTALL_ENV has been written by detect_ram.sh; we re-source
#     it here for the LLM model name.
#   • $MG_INSTALL_LOG is open for append.
#
# Functions exported:
#   install_ollama_runtime  — copy Ollama.app + register launchd agent
#   pull_llm_model          — `ollama pull $MG_INSTALL_LLM_MODEL` with
#                              a hard timeout and retries.

set -euo pipefail

# ---------------------------------------------------------------------------
# Logging — re-uses the preinstall log file
# ---------------------------------------------------------------------------

_log() {
    local msg="[ollama] $*"
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $msg" | tee -a "${MG_INSTALL_LOG:-/dev/stderr}" >&2
}

_die() {
    _log "FATAL $*"
    return 1
}

# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

install_ollama_runtime() {
    local payload="${MG_PKG_PAYLOAD:?MG_PKG_PAYLOAD must be set}"
    local src="${payload}/runtime/ollama/Ollama.app"

    if [[ ! -d "$src" ]]; then
        _die "vendored Ollama.app not found at ${src}"
        return 1
    fi

    # Idempotent re-install: ditto -rsrc preserves resource forks and
    # signatures correctly, unlike cp -R.
    /usr/bin/ditto "$src" "/Applications/Ollama.app"
    _log "INFO Ollama.app installed to /Applications"

    # The vendored Ollama.app expects to register its own LaunchAgent
    # the first time the user launches it. We don't auto-launch in
    # postinstall — the user does that on first login. Postinstall
    # only needs the `ollama` CLI to do `pull`, which is at
    # /Applications/Ollama.app/Contents/Resources/ollama.
    local cli="/Applications/Ollama.app/Contents/Resources/ollama"
    if [[ ! -x "$cli" ]]; then
        # Newer Ollama versions ship the CLI at a different path; fall
        # back to a search.
        cli="$(/usr/bin/find /Applications/Ollama.app -type f -name ollama -perm -u+x 2>/dev/null | head -n1)"
        if [[ -z "$cli" ]]; then
            _die "could not locate ollama CLI inside Ollama.app"
            return 1
        fi
    fi

    install -d -m 0755 /usr/local/bin
    /bin/ln -sf "$cli" /usr/local/bin/ollama
    _log "INFO symlinked ollama CLI into /usr/local/bin"
}

_check_network() {
    # Vision Anchor 7 is "no cloud-only DEPENDENCIES at runtime", which
    # explicitly DOES allow the one-time first-run model pull. But we
    # still want to fail loud if the user is offline at install time
    # rather than after the user clicks the .pkg and waits 5 minutes.
    if ! /usr/bin/curl --max-time 5 --silent --output /dev/null \
            --write-out '%{http_code}\n' https://ollama.com/ \
            | grep -qE '^[23][0-9][0-9]$'; then
        _die "ollama.com is not reachable; cannot pull LLM model. \
Connect this Mac to the network and re-run the installer."
        return 1
    fi
    _log "INFO network reachable; ollama.com responded"
}

pull_llm_model() {
    if [[ ! -r "${MG_INSTALL_ENV:-/tmp/mg_install_env}" ]]; then
        _die "MG_INSTALL_ENV is missing; detect_ram.sh did not run?"
        return 1
    fi
    # shellcheck disable=SC1090
    source "${MG_INSTALL_ENV}"

    if [[ -z "${MG_INSTALL_LLM_MODEL:-}" ]]; then
        _die "MG_INSTALL_LLM_MODEL is empty in MG_INSTALL_ENV"
        return 1
    fi

    _check_network

    _log "INFO pulling ollama model: ${MG_INSTALL_LLM_MODEL}"

    # 3 retries with exponential backoff. ollama pull is itself
    # resumable, so retrying is safe.
    local tries=0 max_tries=3 delay=5
    while (( tries < max_tries )); do
        if sudo -u "${SUDO_USER:-${USER}}" \
                /usr/local/bin/ollama pull "$MG_INSTALL_LLM_MODEL" \
                2>&1 | tee -a "${MG_INSTALL_LOG}"; then
            _log "INFO ollama pull succeeded on try $(( tries + 1 ))"
            return 0
        fi
        tries=$(( tries + 1 ))
        if (( tries >= max_tries )); then
            break
        fi
        _log "WARN ollama pull failed; retry ${tries}/${max_tries} after ${delay}s"
        sleep "$delay"
        delay=$(( delay * 2 ))
    done

    _die "ollama pull failed ${max_tries} times for model ${MG_INSTALL_LLM_MODEL}"
    return 1
}
