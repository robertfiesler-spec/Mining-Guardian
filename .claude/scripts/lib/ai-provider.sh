#!/usr/bin/env bash

# Shared provider abstraction for AI runtime commands.
#
# Supported modes:
# - auto: prefer `claude` when available, fallback to `codex`
# - claude: force Claude command family
# - codex: force Codex command family
#
# Providers are intentionally configured via env vars for portability:
# - AI_PROVIDER: auto|claude|codex
# - AI_PROVIDER_BIN: override binary for auto-resolved provider
# - AI_PROVIDER_PRINT_ARGS: args for synchronous prompt execution
# - AI_PROVIDER_RUN_ARGS: default args for asynchronous agent execution
# - AI_PROVIDER_RUN_PREFIX: optional prefix command for async execution
#   (example: `happy` when running through the Happy CLI)

# NOTE: No `set` flags here — this file is sourced by callers (loop.sh,
# pipeline.sh, multitask.sh) that manage their own shell options.  Adding
# `set -uo pipefail` would silently tighten the caller's environment and
# break commands that rely on unset-variable defaults or piped globs.

AI_PROVIDER_BIN="${AI_PROVIDER_BIN:-}"
AI_PROVIDER_PRINT_ARGS="${AI_PROVIDER_PRINT_ARGS:-}"
AI_PROVIDER_RUN_ARGS="${AI_PROVIDER_RUN_ARGS:-}"
AI_PROVIDER_RUN_PREFIX="${AI_PROVIDER_RUN_PREFIX:-}"
AI_PROVIDER="${AI_PROVIDER:-auto}"

# Internal reusable command array.
AI_PROVIDER_COMMAND=( )

ai_provider_resolve() {
  if [[ -n "$AI_PROVIDER_BIN" ]]; then
    if ! command -v "$AI_PROVIDER_BIN" >/dev/null 2>&1; then
      echo "AI_PROVIDER_BIN '$AI_PROVIDER_BIN' is not available" >&2
      return 1
    fi
    return 0
  fi

  case "$AI_PROVIDER" in
    codex)
      if command -v codex >/dev/null 2>&1; then
        AI_PROVIDER_BIN="codex"
        return 0
      fi
      echo "Requested AI_PROVIDER=codex but codex is not installed" >&2
      return 1
      ;;
    claude)
      if command -v claude >/dev/null 2>&1; then
        AI_PROVIDER_BIN="claude"
        return 0
      fi
      echo "Requested AI_PROVIDER=claude but claude is not installed" >&2
      return 1
      ;;
    auto|*)
      if command -v claude >/dev/null 2>&1; then
        AI_PROVIDER_BIN="claude"
        return 0
      fi
      if command -v codex >/dev/null 2>&1; then
        AI_PROVIDER_BIN="codex"
        return 0
      fi
      echo "No supported AI provider available. Install codex or claude." >&2
      return 1
      ;;
  esac
}

ai_provider_apply_default_args() {
  if [[ -z "$AI_PROVIDER_BIN" ]]; then
    return 1
  fi

  if [[ -z "$AI_PROVIDER_PRINT_ARGS" ]]; then
    if [[ "$AI_PROVIDER_BIN" == "codex" ]]; then
      AI_PROVIDER_PRINT_ARGS="exec"
    else
      AI_PROVIDER_PRINT_ARGS="--print"
    fi
  fi

  if [[ -z "$AI_PROVIDER_RUN_ARGS" ]]; then
    if [[ "$AI_PROVIDER_BIN" == "codex" ]]; then
      AI_PROVIDER_RUN_ARGS="exec"
    else
      # --dangerously-skip-permissions: spawned instances run non-interactive
      # (-p mode) so permission prompts silently block all work. The parent
      # session already has user approval to run the loop.
      AI_PROVIDER_RUN_ARGS="--continue -p --dangerously-skip-permissions"
    fi
  fi
}

ai_provider_ensure() {
  if ! ai_provider_resolve; then
    return 1
  fi

  if ! ai_provider_apply_default_args; then
    return 1
  fi

  # Strip parent-session env vars so child Claude processes don't think
  # they're already inside an active session (which blocks nested spawning).
  unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT 2>/dev/null || true

  return 0
}

ai_provider_command() {
  local mode=$1
  local prompt=$2
  local run_prefix=$3
  local -a parsed_args=()

  AI_PROVIDER_COMMAND=()

  if [[ -n "$run_prefix" ]]; then
    read -r -a parsed_args <<< "$run_prefix"
    AI_PROVIDER_COMMAND+=("${parsed_args[@]}")
  fi

  AI_PROVIDER_COMMAND+=("$AI_PROVIDER_BIN")

  case "$mode" in
    print)
      parsed_args=()
      read -r -a parsed_args <<< "$AI_PROVIDER_PRINT_ARGS"
      ;;
    run)
      parsed_args=()
      read -r -a parsed_args <<< "$AI_PROVIDER_RUN_ARGS"
      ;;
    *)
      parsed_args=()
      ;;
  esac

  AI_PROVIDER_COMMAND+=("${parsed_args[@]}" "$prompt")
}

# Execute a synchronous prompt and return stdout.
ai_print_prompt() {
  local prompt="$1"

  ai_provider_ensure || return 1
  ai_provider_command print "$prompt" ""

  local output
  output="$(${AI_PROVIDER_COMMAND[@]} 2>&1)"
  local status=$?

  printf "%s" "$output"
  return $status
}

# Execute an async prompt and write to log.
# Optionally inject a run-time command prefix with args via $4.
ai_dispatch_prompt() {
  local prompt="$1"
  local log_file="$2"
  local work_dir="$3"
  local args="$4"
  local run_prefix="$5"

  ai_provider_ensure || return 1

  local prompt_args="${args:-$AI_PROVIDER_RUN_ARGS}"

  # Build full command with optional prefix.
  ai_provider_command run "$prompt" "$run_prefix"

  # Override args for this invocation if provided.
  if [[ -n "$prompt_args" ]]; then
    AI_PROVIDER_COMMAND=()

    if [[ -n "$run_prefix" ]]; then
      local -a prefix_parts=()
      read -r -a prefix_parts <<< "$run_prefix"
      AI_PROVIDER_COMMAND+=("${prefix_parts[@]}")
    fi

    AI_PROVIDER_COMMAND+=("$AI_PROVIDER_BIN")

    local -a run_parts=()
    read -r -a run_parts <<< "$prompt_args"
    AI_PROVIDER_COMMAND+=("${run_parts[@]}" "$prompt")
  fi

  local exit_file="$log_file.exit"

  (
    if [[ -n "$work_dir" ]]; then
      cd "$work_dir"
    fi

    set +e
    local _exit_code=1
    trap 'echo "${_exit_code}" > "${exit_file}"' EXIT

    "${AI_PROVIDER_COMMAND[@]}" >> "$log_file" 2>&1
    _exit_code=$?
  ) &

  echo $!
}

# Compatibility wrappers for common callsites.
ai_execute_prompt_file() {
  # shellcheck disable=SC2120
  local prompt="$1"
  ai_print_prompt "$prompt"
}

ai_print_available() {
  command -v "$AI_PROVIDER_BIN" >/dev/null 2>&1
}
