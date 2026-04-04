#!/usr/bin/env bash
#
# multitask.sh - Parallel worktree orchestration for concurrent Claude instances
#
# Creates git worktrees and spawns independent Claude instances to develop
# multiple features simultaneously.
#
# Usage: ./scripts/multitask.sh [OPTIONS]
#
# Options:
#   --plans=list           Comma-separated plan files (e.g., auth.json,api.json)
#   --branches=list        Comma-separated branch names (auto-creates)
#   --auto                 Auto-detect all plans in docs/plans/
#   --happy                Use Happy CLI for instance management (optional)
#   --tui                  Launch TUI dashboard (default)
#   --no-tui               Disable TUI, use log output
#   --max=N                Max iterations per instance (default: 50)
#   --cleanup              Clean up existing worktrees first
#   --cleanup-all          Remove all multitask worktrees and exit
#   --stop                 Stop all running multitask instances
#   --web-viewer            Launch web viewer dashboard (http://localhost:8000)
#   --auto-respawn         Auto-respawn crashed instances during monitoring
#   --max-respawn=N        Max respawn attempts per instance (default: 3)
#   --recover              Auto-recover: reattach to running, respawn crashed
#   --recover-monitor      Reattach to running instances only (no respawn)
#   --force-new            Stop existing session and start fresh (no prompt)
#
# Examples:
#   ./scripts/multitask.sh --plans=docs/plans/auth.json,docs/plans/api.json
#   ./scripts/multitask.sh --auto --tui
#   ./scripts/multitask.sh --auto --happy  # Use Happy CLI
#   ./scripts/multitask.sh --auto --web-viewer  # With web dashboard
#   ./scripts/multitask.sh --auto --auto-respawn  # Auto-recover crashes
#   ./scripts/multitask.sh --branches=feat/a,feat/b --max=100
#   ./scripts/multitask.sh --cleanup-all
#   ./scripts/multitask.sh --stop
#   ./scripts/multitask.sh --recover       # Auto-recover crashed session
#   ./scripts/multitask.sh --force-new     # Force fresh start
#
# Environment Variables:
#   MAX_INSTANCES                Max parallel instances (default: 5)
#   MULTITASK_WORKTREE_PREFIX    Prefix for worktree dirs (default: wt-)
#   MULTITASK_MAX_ITERATIONS     Default max iterations (default: 50)
#   HEALTH_CHECK_INTERVAL        Seconds between health checks (default: 10)

set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source ACS client (optional - degrades gracefully)
ACS_ENABLED=false
if [[ -f "$SCRIPT_DIR/lib/acs-client.sh" ]]; then
  source "$SCRIPT_DIR/lib/acs-client.sh"
  if acs_is_configured; then
    ACS_ENABLED=true
  fi
fi

# Source AI provider abstraction.
source "$SCRIPT_DIR/lib/ai-provider.sh"

# Configuration
MAX_INSTANCES="${MAX_INSTANCES:-5}"
WORKTREE_PREFIX="${MULTITASK_WORKTREE_PREFIX:-wt-}"
DEFAULT_MAX_ITERATIONS="${MULTITASK_MAX_ITERATIONS:-50}"
STATE_DIR="$(pwd)/.claude/state"
SESSION_FILE="$STATE_DIR/multitask-session.json"
LOG_FILE="$STATE_DIR/multitask.log"
PLAN_DIR="docs/plans"

# Runtime state
PLANS=()
BRANCHES=()
AUTO_MODE=false
USE_HAPPY_CLI=false
TUI_ENABLED=true
WEB_VIEWER_ENABLED=false
WEB_VIEWER_PID=""
MAX_ITERATIONS="$DEFAULT_MAX_ITERATIONS"
CLEANUP_FIRST=false
INSTANCE_PIDS=()

# Recovery state
STALE_SESSION_STATE=""  # "running", "mixed", "stopped", or ""
RUNNING_INSTANCES=()
DEAD_INSTANCES=()
RECOVERY_MODE=""        # "", "full", "monitor-only"
FORCE_NEW_SESSION=false

# Lightweight task input state
TASK_DESCRIPTIONS=()
FROM_FILE=""
GENERATED_PLANS=()

# Health monitoring state
AUTO_RESPAWN=false
MAX_RESPAWN_ATTEMPTS=3
HEALTH_CHECK_INTERVAL="${HEALTH_CHECK_INTERVAL:-10}"

# Shared logging (LOG_FILE set above enables tee)
source "$SCRIPT_DIR/lib/logging.sh"

# =============================================================================
# Session Recovery Functions
# =============================================================================

# Detect if a stale session exists
# Returns 0 if session file exists with instances, 1 otherwise
# Sets STALE_SESSION_STATE to "running", "mixed", "stopped", or ""
detect_stale_session() {
  STALE_SESSION_STATE=""

  # Check if session file exists
  if [[ ! -f "$SESSION_FILE" ]]; then
    return 1
  fi

  # Check if file is valid JSON
  if ! jq empty "$SESSION_FILE" 2>/dev/null; then
    log_warn "Session file exists but is invalid JSON, treating as no session"
    return 1
  fi

  # Check if there are any instances
  local instance_count
  instance_count=$(jq -r '.instances | length' "$SESSION_FILE" 2>/dev/null || echo "0")

  if [[ "$instance_count" -eq 0 ]]; then
    return 1
  fi

  # Session file exists with instances - stale session detected
  log_info "Detected existing session with $instance_count instance(s)"
  return 0
}

# Check if a PID is a valid AI multitask instance.
# Returns 0 if PID exists and process command matches known providers.
# This prevents false positives from recycled PIDs
is_valid_multitask_pid() {
  local pid=$1

  # Check if PID exists
  if ! ps -p "$pid" > /dev/null 2>&1; then
    return 1
  fi

  # Get the process command line
  # On macOS, use ps with -o command
  # On Linux, use /proc/$pid/cmdline
  local cmd
  if [[ -f "/proc/$pid/cmdline" ]]; then
    cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || echo "")
  else
    cmd=$(ps -p "$pid" -o command= 2>/dev/null || echo "")
  fi

  if ! ai_provider_ensure; then
    if [[ "$cmd" == *"claude"* || "$cmd" == *"codex"* ]]; then
      return 0
    fi
    return 1
  fi

  # Check if command contains provider binary used for this session.
  if [[ "$cmd" == *"$AI_PROVIDER_BIN"* || "$cmd" == *"claude"* || "$cmd" == *"codex"* ]]; then
    return 0
  fi

  return 1
}

start_ai_loop_instance() {
  local worktree=$1
  local log_file=$2
  local acs_env=$3

  local run_prefix=""
  if [[ "$USE_HAPPY_CLI" == true ]]; then
    run_prefix="happy"
  fi

  # Create a temp file for the subshell to discover its exit file path.
  # We write the path after spawning (once we know $!).
  local _exit_path_file
  _exit_path_file=$(mktemp "${STATE_DIR}/.exit-path.XXXXXX")

  (
    cd "$worktree"

    [[ -n "$acs_env" ]] && export ACS_CONTEXT="$acs_env"
    local _exit_code=1

    # Wait briefly for parent to write the exit file path (uses $! PID).
    # Bash 3.2 lacks $BASHPID, so the parent tells us our exit file.
    sleep 1
    local _exit_file=""
    if [[ -f "$_exit_path_file" ]]; then
      _exit_file=$(cat "$_exit_path_file")
      rm -f "$_exit_path_file"
    fi
    trap '[[ -n "$_exit_file" ]] && echo "$_exit_code" > "$_exit_file"' EXIT

    ai_provider_ensure || { _exit_code=1; exit 1; }

    ai_provider_command run "/ai-loop --max $MAX_ITERATIONS" "$run_prefix"
    set +e
    "${AI_PROVIDER_COMMAND[@]}" >> "$log_file" 2>&1
    _exit_code=$?
  ) </dev/null >/dev/null 2>/dev/null &

  local _pid=$!
  # Tell the subshell where to write its exit code.
  echo "$STATE_DIR/.exit-${_pid}" > "$_exit_path_file"
  echo "$_pid"
}

# Read the exit code for a finished process
# Returns the exit code via stdout, or empty string if not available
# Cleans up the exit code file after reading
read_exit_code() {
  local pid=$1
  local exit_file="$STATE_DIR/.exit-${pid}"

  if [[ -f "$exit_file" ]]; then
    local code
    code=$(cat "$exit_file" 2>/dev/null || echo "")
    rm -f "$exit_file"
    echo "$code"
  else
    echo ""
  fi
}

# Calculate runtime in seconds from an ISO 8601 start timestamp
calculate_runtime() {
  local started=$1
  local now
  now=$(date +%s)

  # Parse ISO timestamp to epoch seconds
  local start_epoch
  if [[ "$OSTYPE" == "darwin"* ]]; then
    start_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$started" +%s 2>/dev/null || echo "0")
  else
    start_epoch=$(date -d "$started" +%s 2>/dev/null || echo "0")
  fi

  if [[ "$start_epoch" -eq 0 ]]; then
    echo "0"
    return
  fi

  echo $(( now - start_epoch ))
}

# Format seconds into human-readable duration (e.g., "14m 7s")
format_duration() {
  local total_seconds=$1
  local hours=$((total_seconds / 3600))
  local minutes=$(( (total_seconds % 3600) / 60 ))
  local seconds=$((total_seconds % 60))

  if [[ $hours -gt 0 ]]; then
    echo "${hours}h ${minutes}m ${seconds}s"
  elif [[ $minutes -gt 0 ]]; then
    echo "${minutes}m ${seconds}s"
  else
    echo "${seconds}s"
  fi
}

# Validate all instance PIDs and determine session state
# Updates session file with crashed status for dead PIDs
# Sets STALE_SESSION_STATE to "running", "mixed", or "stopped"
# Populates RUNNING_INSTANCES and DEAD_INSTANCES arrays
# NOTE: DEAD_INSTANCES must only include recoverable failures (crashed).
#       Do NOT include intentionally inactive instances (stopped/completed),
#       otherwise recovery will incorrectly respawn them.
validate_instance_pids() {
  RUNNING_INSTANCES=()
  DEAD_INSTANCES=()

  # Get all instances from session file
  local instances
  instances=$(jq -c '.instances[]' "$SESSION_FILE" 2>/dev/null || echo "")

  if [[ -z "$instances" ]]; then
    STALE_SESSION_STATE="stopped"
    return
  fi

  # Check each instance PID
  while IFS= read -r instance; do
    local pid branch status instance_num
    pid=$(echo "$instance" | jq -r '.pid // ""')
    branch=$(echo "$instance" | jq -r '.branch // ""')
    status=$(echo "$instance" | jq -r '.status // "unknown"')
    instance_num=$(echo "$instance" | jq -r '.instance_num // 0')

    # Intentionally inactive instances are NOT recoverable and must not be
    # treated as "dead" for recovery purposes.
    if [[ "$status" == "stopped" || "$status" == "completed" ]]; then
      continue
    fi

    # Validate the PID
    if [[ -n "$pid" ]] && is_valid_multitask_pid "$pid"; then
      RUNNING_INSTANCES+=("$instance_num")
    else
      DEAD_INSTANCES+=("$instance_num")

      # Update session file to mark as crashed
      jq --argjson num "$instance_num" \
        '.instances |= map(if .instance_num == $num then .status = "crashed" else . end)' \
        "$SESSION_FILE" > "${SESSION_FILE}.tmp" && mv "${SESSION_FILE}.tmp" "$SESSION_FILE"
    fi
  done <<< "$instances"

  # Determine overall state
  local running_count=${#RUNNING_INSTANCES[@]}
  local dead_count=${#DEAD_INSTANCES[@]}

  if [[ $running_count -gt 0 && $dead_count -eq 0 ]]; then
    STALE_SESSION_STATE="running"
  elif [[ $running_count -eq 0 && $dead_count -gt 0 ]]; then
    STALE_SESSION_STATE="stopped"
  elif [[ $running_count -gt 0 && $dead_count -gt 0 ]]; then
    STALE_SESSION_STATE="mixed"
  else
    STALE_SESSION_STATE="stopped"
  fi

  log_info "Session state: $STALE_SESSION_STATE (running: $running_count, crashed: $dead_count)"
}

# Display formatted instance summary table
show_instance_summary() {
  echo ""
  echo "╭─────────────────────────────────────────────────────────────────╮"
  echo "│ Existing Session Detected                                      │"
  echo "╰─────────────────────────────────────────────────────────────────╯"
  echo ""

  # Get session info
  local session_id started
  session_id=$(jq -r '.session_id // "unknown"' "$SESSION_FILE")
  started=$(jq -r '.started // "unknown"' "$SESSION_FILE")

  echo -e "  ${CYAN}Session:${NC} $session_id"
  echo -e "  ${CYAN}Started:${NC} $started"
  echo -e "  ${CYAN}State:${NC}   $STALE_SESSION_STATE"
  echo ""
  echo "  Instances:"

  # List each instance
  local instances
  instances=$(jq -c '.instances[]' "$SESSION_FILE" 2>/dev/null || echo "")

  while IFS= read -r instance; do
    local pid branch status instance_num worktree
    pid=$(echo "$instance" | jq -r '.pid // "N/A"')
    branch=$(echo "$instance" | jq -r '.branch // "unknown"')
    status=$(echo "$instance" | jq -r '.status // "unknown"')
    instance_num=$(echo "$instance" | jq -r '.instance_num // 0')
    worktree=$(echo "$instance" | jq -r '.worktree // ""')

    # Color based on status
    local color status_icon
    case "$status" in
      running)
        color="$GREEN"
        status_icon="●"
        ;;
      crashed)
        color="$RED"
        status_icon="✗"
        ;;
      stopped|completed)
        color="$YELLOW"
        status_icon="○"
        ;;
      *)
        color="$NC"
        status_icon="?"
        ;;
    esac

    echo -e "    ${color}${status_icon}${NC} #$instance_num: $branch ${color}[$status]${NC} (PID: $pid)"
  done <<< "$instances"

  echo ""
}

# Prompt user for session recovery action
# Returns: 0 = start fresh, 1 = resume/recover, 2 = cleanup, 3 = quit
prompt_session_recovery() {
  local running_count=${#RUNNING_INSTANCES[@]}
  local dead_count=${#DEAD_INSTANCES[@]}

  echo "  Options:"

  case "$STALE_SESSION_STATE" in
    running)
      echo -e "    ${GREEN}[r]${NC} Resume    - Reattach to running instances (monitor only)"
      echo -e "    ${YELLOW}[s]${NC} Stop      - Stop all instances and start fresh"
      echo -e "    ${RED}[q]${NC} Quit      - Exit without changes"
      echo ""
      echo -n "  Choice [r/s/q]: "
      read -r choice
      case "$choice" in
        r|R) return 1 ;;  # Resume
        s|S) return 0 ;;  # Stop and start fresh
        q|Q) return 3 ;;  # Quit
        *)
          log_warn "Invalid choice, defaulting to quit"
          return 3
          ;;
      esac
      ;;

    mixed)
      echo -e "    ${GREEN}[r]${NC} Resume    - Reattach to $running_count running, restart $dead_count crashed"
      echo -e "    ${YELLOW}[s]${NC} Stop      - Stop all and start fresh"
      echo -e "    ${RED}[c]${NC} Cleanup   - Stop all and remove worktrees"
      echo -e "    ${RED}[q]${NC} Quit      - Exit without changes"
      echo ""
      echo -n "  Choice [r/s/c/q]: "
      read -r choice
      case "$choice" in
        r|R) return 1 ;;  # Resume/recover
        s|S) return 0 ;;  # Stop and start fresh
        c|C) return 2 ;;  # Cleanup
        q|Q) return 3 ;;  # Quit
        *)
          log_warn "Invalid choice, defaulting to quit"
          return 3
          ;;
      esac
      ;;

    stopped)
      echo -e "    ${GREEN}[r]${NC} Restart   - Respawn instances using existing worktrees"
      echo -e "    ${YELLOW}[n]${NC} New       - Create fresh worktrees"
      echo -e "    ${RED}[c]${NC} Cleanup   - Remove everything and exit"
      echo -e "    ${RED}[q]${NC} Quit      - Exit without changes"
      echo ""
      echo -n "  Choice [r/n/c/q]: "
      read -r choice
      case "$choice" in
        r|R) return 1 ;;  # Restart/respawn
        n|N) return 0 ;;  # New (start fresh)
        c|C) return 2 ;;  # Cleanup
        q|Q) return 3 ;;  # Quit
        *)
          log_warn "Invalid choice, defaulting to quit"
          return 3
          ;;
      esac
      ;;

    *)
      log_warn "Unknown session state: $STALE_SESSION_STATE"
      return 0
      ;;
  esac
}

# Archive session file to sessions directory with timestamp
cleanup_session_file() {
  if [[ ! -f "$SESSION_FILE" ]]; then
    return
  fi

  local archive_dir="$STATE_DIR/sessions"
  mkdir -p "$archive_dir"

  local timestamp
  timestamp=$(date +%Y%m%d-%H%M%S)
  local archive_name="multitask-session-${timestamp}.json"

  mv "$SESSION_FILE" "$archive_dir/$archive_name"
  log_info "Session archived to: $archive_dir/$archive_name"
}

# Respawn a crashed instance in its existing worktree
# Updates session file with new PID and status
respawn_instance() {
  local instance_num=$1
  local worktree branch plan instance_log

  # Get instance info from session
  worktree=$(jq -r --argjson num "$instance_num" '.instances[] | select(.instance_num == $num) | .worktree' "$SESSION_FILE")
  branch=$(jq -r --argjson num "$instance_num" '.instances[] | select(.instance_num == $num) | .branch' "$SESSION_FILE")
  plan=$(jq -r --argjson num "$instance_num" '.instances[] | select(.instance_num == $num) | .plan' "$SESSION_FILE")
  instance_log=$(jq -r --argjson num "$instance_num" '.instances[] | select(.instance_num == $num) | (.log_file // empty)' "$SESSION_FILE")

  if [[ -z "$worktree" || ! -d "$worktree" ]]; then
    log_error "Worktree not found for instance #$instance_num: $worktree"
    return 1
  fi

  # Validate / repair log file path.
  #
  # Bug prevented: if .log_file is missing/null, `jq -r` would yield the literal
  # string "null", causing writes to a file named "null" in the current dir.
  if [[ -z "$instance_log" || "$instance_log" == "null" ]]; then
    instance_log="$STATE_DIR/multitask-instance-${instance_num}.log"
    log_warn "Instance #$instance_num missing log_file in session; defaulting to: $instance_log"

    mkdir -p "$(dirname "$instance_log")"

    # Persist back to session so future recovery uses the same path.
    jq --argjson num "$instance_num" --arg log_file "$instance_log" \
      '.instances |= map(if .instance_num == $num then .log_file = $log_file else . end)' \
      "$SESSION_FILE" > "${SESSION_FILE}.tmp" && mv "${SESSION_FILE}.tmp" "$SESSION_FILE"
  else
    mkdir -p "$(dirname "$instance_log")"
  fi

  log_info "Respawning instance #$instance_num in $worktree"

  # Append to existing log file
  echo "" >> "$instance_log"
  echo "=== Respawned: $(date) ===" >> "$instance_log"

  # Spawn AI instance in background with exit code capture
  local new_pid
  new_pid=$(start_ai_loop_instance "$worktree" "$instance_log" "$acs_env" || true)
  if [[ -z "$new_pid" ]]; then
    log_error "Failed to spawn AI instance for instance #$instance_num"
    return 1
  fi

  echo "" >> "$instance_log"
  echo "Exit file: $STATE_DIR/.exit-${new_pid}" >> "$instance_log"

  INSTANCE_PIDS+=("$new_pid")

  # Update session file with new PID and status
  jq --argjson num "$instance_num" --argjson pid "$new_pid" \
    '.instances |= map(if .instance_num == $num then .pid = $pid | .status = "running" else . end)' \
    "$SESSION_FILE" > "${SESSION_FILE}.tmp" && mv "${SESSION_FILE}.tmp" "$SESSION_FILE"

  log_success "Instance #$instance_num respawned (PID: $new_pid)"
  return 0
}

# Recover a session - reattach to running instances and optionally respawn crashed ones
# Mode: "full" = reattach + respawn, "monitor-only" = reattach only
recover_session() {
  local mode="${1:-full}"

  log_section "Recovering Session"

  # Collect PIDs of running instances for monitoring
  for instance_num in "${RUNNING_INSTANCES[@]}"; do
    local pid
    pid=$(jq -r --argjson num "$instance_num" '.instances[] | select(.instance_num == $num) | .pid' "$SESSION_FILE")
    if [[ -n "$pid" ]]; then
      INSTANCE_PIDS+=("$pid")
      log_info "Reattaching to instance #$instance_num (PID: $pid)"
    fi
  done

  # Respawn crashed instances if in full recovery mode
  if [[ "$mode" == "full" ]]; then
    for instance_num in "${DEAD_INSTANCES[@]}"; do
      # Only respawn instances marked as crashed. This prevents restarting
      # successfully completed work (or intentionally stopped instances) if they
      # ever end up in the list due to a bad session file or older versions.
      local status
      status=$(jq -r --argjson num "$instance_num" '.instances[] | select(.instance_num == $num) | (.status // "unknown")' "$SESSION_FILE" 2>/dev/null || echo "unknown")
      if [[ "$status" != "crashed" ]]; then
        log_info "Skipping instance #$instance_num - status is '$status' (not recoverable)"
        continue
      fi

      # Check if this instance has a valid worktree
      local worktree
      worktree=$(jq -r --argjson num "$instance_num" '.instances[] | select(.instance_num == $num) | .worktree' "$SESSION_FILE")

      if [[ -n "$worktree" && -d "$worktree" ]]; then
        respawn_instance "$instance_num"
      else
        log_warn "Skipping instance #$instance_num - worktree not found: $worktree"
      fi
    done
  else
    log_info "Monitor-only mode - not respawning crashed instances"
  fi

  log_success "Session recovered - ${#INSTANCE_PIDS[@]} active instance(s)"
}

# Launch web viewer dashboard server
launch_web_viewer() {
  if [[ "$WEB_VIEWER_ENABLED" != true ]]; then
    return
  fi

  local web_viewer_dir="$SCRIPT_DIR/web-viewer"

  # Check if web-viewer directory exists
  if [[ ! -d "$web_viewer_dir" ]]; then
    log_warn "Web viewer not found at: $web_viewer_dir"
    log_info "Skipping web viewer launch"
    return
  fi

  # Check for node_modules
  if [[ ! -d "$web_viewer_dir/node_modules" ]]; then
    log_info "Installing web viewer dependencies..."
    (cd "$web_viewer_dir" && npm install > /dev/null 2>&1)
  fi

  # Build if needed
  if [[ ! -d "$web_viewer_dir/dist" ]] || [[ "$web_viewer_dir/src" -nt "$web_viewer_dir/dist" ]]; then
    log_info "Building web viewer..."
    (cd "$web_viewer_dir" && npm run build > /dev/null 2>&1)
  fi

  local base_dir
  base_dir=$(git rev-parse --show-toplevel)

  log_info "Starting web viewer dashboard..."

  # Launch web viewer in background with correct env vars
  (
    cd "$web_viewer_dir"
    WEB_VIEWER_BASE_DIR="$base_dir" npm start > "$STATE_DIR/web-viewer.log" 2>&1
  ) &
  WEB_VIEWER_PID=$!

  # Brief pause to let the server bind
  sleep 1

  # Verify it started
  if ps -p "$WEB_VIEWER_PID" > /dev/null 2>&1; then
    log_success "Web viewer running at http://localhost:8000 (PID: $WEB_VIEWER_PID)"

    # Store PID in session file
    if [[ -f "$SESSION_FILE" ]]; then
      jq --argjson pid "$WEB_VIEWER_PID" '.web_viewer_pid = $pid' "$SESSION_FILE" > "${SESSION_FILE}.tmp" \
        && mv "${SESSION_FILE}.tmp" "$SESSION_FILE"
    fi
  else
    log_warn "Web viewer failed to start - check $STATE_DIR/web-viewer.log"
    WEB_VIEWER_PID=""
  fi
}

# Stop web viewer server
stop_web_viewer() {
  # Try PID from variable first, then session file
  local pid="${WEB_VIEWER_PID}"

  if [[ -z "$pid" && -f "$SESSION_FILE" ]]; then
    pid=$(jq -r '.web_viewer_pid // ""' "$SESSION_FILE" 2>/dev/null || echo "")
  fi

  if [[ -n "$pid" ]] && ps -p "$pid" > /dev/null 2>&1; then
    log_info "Stopping web viewer (PID: $pid)"
    kill -TERM "$pid" 2>/dev/null || true
  fi

  WEB_VIEWER_PID=""
}

# Launch monitoring - abstracts TUI vs non-TUI modes
# Works for both new and recovered sessions
launch_monitoring() {
  if [[ ${#INSTANCE_PIDS[@]} -eq 0 ]]; then
    log_warn "No instances to monitor"
    return
  fi

  if [[ "$TUI_ENABLED" == true ]]; then
    launch_tui

    # Wait for TUI to exit
    local tui_pid
    tui_pid=$(jq -r '.tui_pid // ""' "$SESSION_FILE" 2>/dev/null || echo "")
    if [[ -n "$tui_pid" ]]; then
      wait "$tui_pid" 2>/dev/null || true
    fi
  else
    monitor_instances
  fi
}

# Parse arguments
parse_args() {
  while [[ $# -gt 0 ]]; do
    case $1 in
      --plans=*)
        IFS=',' read -ra PLANS <<< "${1#*=}"
        shift
        ;;
      --branches=*)
        IFS=',' read -ra BRANCHES <<< "${1#*=}"
        shift
        ;;
      --auto)
        AUTO_MODE=true
        shift
        ;;
      --happy)
        USE_HAPPY_CLI=true
        shift
        ;;
      --tui)
        TUI_ENABLED=true
        shift
        ;;
      --no-tui)
        TUI_ENABLED=false
        shift
        ;;
      --web-viewer)
        WEB_VIEWER_ENABLED=true
        shift
        ;;
      --max=*)
        MAX_ITERATIONS="${1#*=}"
        shift
        ;;
      --cleanup)
        CLEANUP_FIRST=true
        shift
        ;;
      --cleanup-all)
        cleanup_all_worktrees
        exit 0
        ;;
      --stop)
        stop_all_instances
        exit 0
        ;;
      --auto-respawn)
        AUTO_RESPAWN=true
        shift
        ;;
      --max-respawn=*)
        MAX_RESPAWN_ATTEMPTS="${1#*=}"
        shift
        ;;
      --recover)
        RECOVERY_MODE="full"
        shift
        ;;
      --recover-monitor)
        RECOVERY_MODE="monitor-only"
        shift
        ;;
      --force-new)
        FORCE_NEW_SESSION=true
        shift
        ;;
      --tasks)
        shift
        while [[ $# -gt 0 && ! "$1" == --* ]]; do
          TASK_DESCRIPTIONS+=("$1")
          shift
        done
        if [[ ${#TASK_DESCRIPTIONS[@]} -eq 0 ]]; then
          log_error "No task descriptions provided after --tasks"
          exit 1
        fi
        ;;
      --from=*)
        FROM_FILE="${1#*=}"
        shift
        ;;
      --from)
        FROM_FILE="$2"
        shift 2
        ;;
      *)
        log_error "Unknown option: $1"
        exit 1
        ;;
    esac
  done
}

# Validate prerequisites
validate_prerequisites() {
  log_section "Validating Prerequisites"

  # Check if we're in a git repo
  if ! git rev-parse --git-dir > /dev/null 2>&1; then
    log_error "Not in a git repository"
    exit 1
  fi

  # Check for clean working tree
  if [[ -n $(git status --porcelain) ]]; then
    log_error "Working tree has uncommitted changes"
    log_info "Please commit or stash changes before running multitask"
    exit 1
  fi

  # Check for supported AI provider.
  if ! ai_provider_ensure; then
    log_error "No supported AI provider found (codex or claude)"
    log_info "Set AI_PROVIDER (auto|claude|codex) or install one"
    exit 1
  fi

  if [[ "$USE_HAPPY_CLI" == true ]] && [[ "$AI_PROVIDER_BIN" != "claude" ]]; then
    log_error "Happy CLI is only supported with Claude provider"
    log_info "Set AI_PROVIDER=claude or run without --happy"
    exit 1
  fi

  # Check for happy CLI if --happy flag is used
  if [[ "$USE_HAPPY_CLI" == true ]]; then
    if ! command -v happy &> /dev/null; then
      log_error "happy CLI not found (required when using --happy flag)"
      log_info "Install from: https://github.com/happycode-dev/happy"
      exit 1
    fi
    log_info "Using Happy CLI for instance management"
  fi

  # Check for jq
  if ! command -v jq &> /dev/null; then
    log_error "jq not found - required for JSON parsing"
    log_info "Install with: brew install jq (macOS) or apt install jq (Linux)"
    exit 1
  fi

  # Create state directory
  mkdir -p "$STATE_DIR"

  log_success "Prerequisites validated"
}

# Discover plans
discover_plans() {
  log_section "Discovering Plans"

  if [[ "$AUTO_MODE" == true ]]; then
    log_info "Auto-discovering plans in $PLAN_DIR/"

    if [[ ! -d "$PLAN_DIR" ]]; then
      log_error "Plan directory not found: $PLAN_DIR"
      exit 1
    fi

    PLANS=($(find "$PLAN_DIR" -maxdepth 1 -name "*.json" -type f))

    if [[ ${#PLANS[@]} -eq 0 ]]; then
      log_error "No plans found in $PLAN_DIR/"
      log_info "Create plans with /create-plan first"
      exit 1
    fi

    log_success "Found ${#PLANS[@]} plans"
  fi

  # Validate plan files exist
  for plan in "${PLANS[@]}"; do
    if [[ ! -f "$plan" ]]; then
      log_error "Plan file not found: $plan"
      exit 1
    fi

    # Validate JSON
    if ! jq empty "$plan" 2>/dev/null; then
      log_error "Invalid JSON in plan: $plan"
      exit 1
    fi

    # Extract branch name from plan
    local branch=$(jq -r '.branch // ""' "$plan")
    if [[ -z "$branch" && ${#BRANCHES[@]} -eq 0 ]]; then
      log_error "Plan missing 'branch' field: $plan"
      log_info "Either specify --branches or ensure plans have 'branch' field"
      exit 1
    fi

    if [[ -n "$branch" ]]; then
      BRANCHES+=("$branch")
    fi

    log_info "  ✓ $plan → branch: $branch"
  done

  # Check that we have at least one plan
  if [[ ${#PLANS[@]} -eq 0 ]]; then
    log_error "No plans specified"
    log_info "Use one of: --plans, --auto, --tasks, or --from"
    exit 1
  fi

  # Validate we don't exceed max instances
  if [[ ${#PLANS[@]} -gt $MAX_INSTANCES ]]; then
    log_error "Too many instances requested: ${#PLANS[@]} (max: $MAX_INSTANCES)"
    log_info "Set MAX_INSTANCES environment variable to increase limit"
    exit 1
  fi

  log_success "Ready with ${#PLANS[@]} plan(s)"
}

# Get repo name
get_repo_name() {
  basename "$(git rev-parse --show-toplevel)"
}

# Get worktree path for branch
get_worktree_path() {
  local branch=$1
  local repo_name=$(get_repo_name)
  local branch_suffix=$(echo "$branch" | sed 's/\//-/g')
  echo "../${repo_name}-${WORKTREE_PREFIX}${branch_suffix}"
}

# ==========================================================================
# Lightweight Task Conversion
# Convert --tasks and --from inputs to JSON PRD files in docs/plans/
# ==========================================================================

# Convert a task title to a valid kebab-case string for branch/file names
title_to_kebab() {
  local title="$1"
  echo "$title" \
    | tr '[:upper:]' '[:lower:]' \
    | sed 's/[^a-z0-9 ]//g' \
    | sed 's/  */ /g' \
    | sed 's/^ //' \
    | sed 's/ $//' \
    | sed 's/ /-/g' \
    | cut -c1-50
}

# Append numeric suffix if branch already exists in the repo
ensure_unique_branch() {
  local base_branch="$1"
  local branch="$base_branch"
  local suffix=2

  while git show-ref --verify --quiet "refs/heads/$branch" 2>/dev/null; do
    log_warn "Branch '$branch' already exists, using suffix"
    branch="${base_branch}-${suffix}"
    ((suffix++))
  done

  echo "$branch"
}

# Generate a minimal valid JSON PRD from a task description
generate_plan_json() {
  local title="$1"
  local branch="$2"
  local task_type="${3:-Setup}"
  local timestamp
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  local feature_name
  feature_name=$(title_to_kebab "$title")

  # Use jq to produce valid JSON with proper escaping
  jq -n \
    --arg feature "$feature_name" \
    --arg branch "$branch" \
    --arg created "$timestamp" \
    --arg title "$title" \
    --arg type "$task_type" \
    '{
      feature: $feature,
      branch: $branch,
      status: "in_progress",
      created: $created,
      source: "lightweight-task",
      stories: [{
        id: "US-1",
        title: $title,
        type: $type,
        priority: 1,
        passes: false
      }]
    }'
}

# Emit a single task as a JSON plan file (shared by inline and file parsers)
_emit_task() {
  local title="$1"
  local branch="$2"
  local task_type="${3:-Setup}"

  local feature_name
  feature_name=$(title_to_kebab "$title")

  if [[ -z "$branch" ]]; then
    branch="feature/$feature_name"
  fi
  branch=$(ensure_unique_branch "$branch")

  local plan_file="$PLAN_DIR/${feature_name}.json"

  # Avoid overwriting existing plan files
  if [[ -f "$plan_file" ]]; then
    local counter=2
    while [[ -f "$PLAN_DIR/${feature_name}-${counter}.json" ]]; do
      ((counter++))
    done
    plan_file="$PLAN_DIR/${feature_name}-${counter}.json"
  fi

  local json
  json=$(generate_plan_json "$title" "$branch" "$task_type")
  echo "$json" > "$plan_file"

  PLANS+=("$plan_file")
  GENERATED_PLANS+=("$plan_file")

  log_info "  Created: $plan_file (branch: $branch)"
}

# Convert --tasks inline descriptions to JSON plan files
convert_inline_tasks() {
  if [[ ${#TASK_DESCRIPTIONS[@]} -eq 0 ]]; then
    return
  fi

  log_section "Converting Inline Tasks to Plans"

  mkdir -p "$PLAN_DIR"

  for desc in "${TASK_DESCRIPTIONS[@]}"; do
    if [[ ${#desc} -lt 10 ]]; then
      log_warn "Task description too short (min 10 chars), skipping: '$desc'"
      continue
    fi

    _emit_task "$desc" "" "Setup"
  done

  if [[ ${#GENERATED_PLANS[@]} -gt 0 ]]; then
    log_success "Generated ${#GENERATED_PLANS[@]} plan(s) from inline tasks"
  fi
}

# Parse a plain text file (one task per line, # comments, blank lines skipped)
convert_text_file() {
  local file="$1"
  log_info "Parsing text task file: $file"

  while IFS= read -r line || [[ -n "$line" ]]; do
    # Trim whitespace
    line=$(echo "$line" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
    [[ -z "$line" ]] && continue
    [[ "$line" == \#* ]] && continue

    TASK_DESCRIPTIONS+=("$line")
  done < "$file"

  convert_inline_tasks
}

# Parse a simple YAML task file with bash (no yq dependency required)
# Supports: tasks: list with title, branch, type fields
convert_yaml_file() {
  local file="$1"
  log_info "Parsing YAML task file: $file"

  # Use yq if available for robust parsing
  if command -v yq &> /dev/null; then
    _convert_yaml_with_yq "$file"
    return
  fi

  log_info "yq not found, using basic YAML parser (simple task format only)"

  mkdir -p "$PLAN_DIR"

  local current_title=""
  local current_branch=""
  local current_type="Setup"

  while IFS= read -r line || [[ -n "$line" ]]; do
    local trimmed
    trimmed=$(echo "$line" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')

    [[ -z "$trimmed" ]] && continue
    [[ "$trimmed" == \#* ]] && continue
    [[ "$trimmed" == "tasks:" ]] && continue

    # New task item starts with "- "
    if [[ "$trimmed" =~ ^-[[:space:]] ]]; then
      # Flush previous task
      if [[ -n "$current_title" ]]; then
        _emit_task "$current_title" "$current_branch" "$current_type"
      fi

      current_branch=""
      current_type="Setup"

      # Extract title from "- title: X" or bare "- X"
      if [[ "$trimmed" =~ ^-[[:space:]]+title:[[:space:]]*(.*) ]]; then
        current_title="${BASH_REMATCH[1]}"
      else
        current_title="${trimmed#- }"
      fi
    elif [[ "$trimmed" =~ ^branch:[[:space:]]*(.*) ]]; then
      current_branch="${BASH_REMATCH[1]}"
    elif [[ "$trimmed" =~ ^type:[[:space:]]*(.*) ]]; then
      current_type="${BASH_REMATCH[1]}"
    fi
  done < "$file"

  # Flush last task
  if [[ -n "$current_title" ]]; then
    _emit_task "$current_title" "$current_branch" "$current_type"
  fi

  if [[ ${#GENERATED_PLANS[@]} -gt 0 ]]; then
    log_success "Generated ${#GENERATED_PLANS[@]} plan(s) from YAML file"
  fi
}

# YAML parsing with yq (preferred when available)
_convert_yaml_with_yq() {
  local file="$1"
  mkdir -p "$PLAN_DIR"

  local count
  count=$(yq '.tasks | length' "$file")

  for ((i=0; i<count; i++)); do
    local title branch task_type
    title=$(yq -r ".tasks[$i].title" "$file")
    branch=$(yq -r ".tasks[$i].branch // \"\"" "$file")
    task_type=$(yq -r ".tasks[$i].type // \"Setup\"" "$file")

    _emit_task "$title" "$branch" "$task_type"
  done

  if [[ ${#GENERATED_PLANS[@]} -gt 0 ]]; then
    log_success "Generated ${#GENERATED_PLANS[@]} plan(s) from YAML file (yq)"
  fi
}

# Dispatch --from file by extension
convert_from_file() {
  if [[ -z "$FROM_FILE" ]]; then
    return
  fi

  log_section "Converting Task File to Plans"

  if [[ ! -f "$FROM_FILE" ]]; then
    log_error "Task file not found: $FROM_FILE"
    exit 1
  fi

  local extension="${FROM_FILE##*.}"

  case "$extension" in
    json)
      # Existing JSON plan - add directly
      log_info "Detected JSON plan file: $FROM_FILE"
      PLANS+=("$FROM_FILE")
      ;;
    yaml|yml)
      convert_yaml_file "$FROM_FILE"
      ;;
    *)
      convert_text_file "$FROM_FILE"
      ;;
  esac
}

# Cleanup all multitask worktrees
cleanup_all_worktrees() {
  log_section "Cleaning Up All Worktrees"

  local repo_name=$(get_repo_name)
  local parent_dir=$(dirname "$(git rev-parse --show-toplevel)")

  # Find all worktree directories
  local worktrees=($(find "$parent_dir" -maxdepth 1 -type d -name "${repo_name}-${WORKTREE_PREFIX}*" 2>/dev/null || true))

  if [[ ${#worktrees[@]} -eq 0 ]]; then
    log_info "No worktrees found to clean up"
    return
  fi

  log_info "Found ${#worktrees[@]} worktrees to remove"

  for wt in "${worktrees[@]}"; do
    local wt_name=$(basename "$wt")
    log_info "Removing worktree: $wt_name"

    # Remove from git worktree list
    git worktree remove "$wt" --force 2>/dev/null || true

    # Remove directory if still exists
    if [[ -d "$wt" ]]; then
      rm -rf "$wt"
    fi

    log_success "  ✓ Removed $wt_name"
  done

  # Clean up session file
  if [[ -f "$SESSION_FILE" ]]; then
    rm "$SESSION_FILE"
    log_info "Removed session file"
  fi

  log_success "Cleanup complete"
}

# Stop all running instances
stop_all_instances() {
  log_section "Stopping All Instances"

  if [[ ! -f "$SESSION_FILE" ]]; then
    log_info "No active session found"
    return
  fi

  # Read PIDs from session file
  local pids=($(jq -r '.instances[].pid // empty' "$SESSION_FILE" 2>/dev/null || true))

  if [[ ${#pids[@]} -eq 0 ]]; then
    log_info "No running instances found"
    return
  fi

  log_info "Stopping ${#pids[@]} instances..."

  for pid in "${pids[@]}"; do
    if ps -p "$pid" > /dev/null 2>&1; then
      log_info "Sending SIGTERM to PID $pid"
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done

  # Wait for graceful shutdown
  sleep 3

  # Force kill if still running
  for pid in "${pids[@]}"; do
    if ps -p "$pid" > /dev/null 2>&1; then
      log_warn "Force killing PID $pid"
      kill -KILL "$pid" 2>/dev/null || true
    fi
  done

  # Stop web viewer if running
  stop_web_viewer

  log_success "All instances stopped"

  # Update session file
  jq '.instances[].status = "stopped"' "$SESSION_FILE" > "${SESSION_FILE}.tmp" && mv "${SESSION_FILE}.tmp" "$SESSION_FILE"
}

# Create worktree for branch
create_worktree() {
  local branch=$1
  local plan=$2
  local worktree_path=$(get_worktree_path "$branch")

  log_info "Creating worktree for $branch → $worktree_path"

  # Check if worktree already exists
  if [[ -d "$worktree_path" ]]; then
    if [[ "$CLEANUP_FIRST" == true ]]; then
      log_warn "Worktree exists, removing: $worktree_path"
      git worktree remove "$worktree_path" --force 2>/dev/null || true
      rm -rf "$worktree_path"
    else
      log_error "Worktree already exists: $worktree_path"
      log_info "Use --cleanup flag to remove existing worktrees first"
      exit 1
    fi
  fi

  # Check if branch exists
  if git show-ref --verify --quiet "refs/heads/$branch"; then
    log_info "Branch exists, checking out: $branch"
    git worktree add "$worktree_path" "$branch"
  else
    log_info "Creating new branch: $branch"
    git worktree add "$worktree_path" -b "$branch"
  fi

  # Symlink environment files if they exist
  local repo_root
  repo_root=$(git rev-parse --show-toplevel)
  if [[ -f "$repo_root/.env" ]]; then
    log_info "Symlinking .env to worktree"
    ln -sf "$repo_root/.env" "$worktree_path/.env"
  fi

  if [[ -f "$repo_root/.env.local" ]]; then
    log_info "Symlinking .env.local to worktree"
    ln -sf "$repo_root/.env.local" "$worktree_path/.env.local"
  fi

  # Copy plan file to worktree
  local plan_name=$(basename "$plan")
  log_info "Copying plan: $plan_name"
  mkdir -p "$worktree_path/$PLAN_DIR"
  cp "$plan" "$worktree_path/$PLAN_DIR/$plan_name"

  # Install dependencies in worktree
  log_info "Installing dependencies in worktree..."
  (
    cd "$worktree_path"

    if [[ -f "package-lock.json" ]]; then
      npm install > /dev/null 2>&1
    elif [[ -f "pnpm-lock.yaml" ]]; then
      pnpm install > /dev/null 2>&1
    elif [[ -f "yarn.lock" ]]; then
      yarn install > /dev/null 2>&1
    elif [[ -f "package.json" ]]; then
      npm install > /dev/null 2>&1
    fi
  )

  log_success "Worktree created: $worktree_path"
}

# Spawn AI instance in worktree
spawn_instance() {
  local branch=$1
  local plan=$2
  local instance_num=$3
  local worktree_path=$(get_worktree_path "$branch")
  local instance_log="$STATE_DIR/multitask-instance-${instance_num}.log"

  log_info "Spawning AI instance #$instance_num for $branch" >&2

  # Create instance log file
  echo "=== Multitask Instance #$instance_num: $branch ===" > "$instance_log"
  echo "Started: $(date)" >> "$instance_log"
  echo "Worktree: $worktree_path" >> "$instance_log"
  echo "Plan: $plan" >> "$instance_log"
  echo "Using Happy CLI: $USE_HAPPY_CLI" >> "$instance_log"
  echo "" >> "$instance_log"

  # Query ACS for cross-project context (non-blocking, optional)
  local acs_env=""
  if [[ "$ACS_ENABLED" == "true" ]] && acs_is_available; then
    local project_name
    project_name=$(basename "$(git rev-parse --show-toplevel)")
    local acs_result
    acs_result=$(acs_query "cross-project patterns for: $branch" 5 1500 2>/dev/null) || true
    local acs_context
    acs_context=$(echo "$acs_result" | acs_extract_context 2>/dev/null) || true
    if [[ -n "$acs_context" ]]; then
      acs_env="$acs_context"
      echo "ACS: Injecting cross-project context" >> "$instance_log"
    fi
  fi

  # Spawn AI instance in background with exit code capture
  # NOTE: Subshell redirects (</dev/null >/dev/null 2>/dev/null) are critical.
  # Without them, $(spawn_instance ...) blocks because the background subshell
  # inherits the pipe fd from command substitution, preventing EOF.
  local pid
  pid=$(start_ai_loop_instance "$worktree_path" "$instance_log" "$acs_env" || true)
  if [[ -z "$pid" ]]; then
    log_error "Failed to spawn AI instance for instance #$instance_num"
    return 1
  fi

  echo "" >> "$instance_log"
  echo "Exit file: $STATE_DIR/.exit-${pid}" >> "$instance_log"
  INSTANCE_PIDS+=("$pid")

  log_success "Instance #$instance_num spawned (PID: $pid)" >&2

  # Return instance metadata as JSON
  cat <<EOF
{
  "instance_num": $instance_num,
  "worktree": "$worktree_path",
  "branch": "$branch",
  "plan": "$plan",
  "pid": $pid,
  "status": "running",
  "started": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "log_file": "$instance_log",
  "exit_code": null,
  "exited_at": null,
  "last_heartbeat": null,
  "runtime_seconds": 0,
  "crash_count": 0,
  "crash_log": []
}
EOF
}

# Initialize session file
init_session() {
  log_section "Initializing Session"

  local session_id="multitask-$(date +%Y-%m-%d-%H%M%S)"

  cat > "$SESSION_FILE" <<EOF
{
  "session_id": "$session_id",
  "started": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "tui_enabled": $TUI_ENABLED,
  "use_happy_cli": $USE_HAPPY_CLI,
  "max_iterations": $MAX_ITERATIONS,
  "instances": []
}
EOF

  log_success "Session initialized: $session_id"
}

# Update session file with instance
add_instance_to_session() {
  local instance_json=$1

  # Append instance to session file
  jq --argjson instance "$instance_json" '.instances += [$instance]' "$SESSION_FILE" > "${SESSION_FILE}.tmp"
  mv "${SESSION_FILE}.tmp" "$SESSION_FILE"
}

# Launch TUI monitor
launch_tui() {
  log_section "Launching TUI Monitor"

  if [[ ! -f "$SCRIPT_DIR/multitask-tui-wrapper.sh" ]]; then
    log_warn "TUI wrapper not found, falling back to log monitoring"
    TUI_ENABLED=false
    return
  fi

  log_info "Starting TUI dashboard..."

  # Launch TUI in background
  "$SCRIPT_DIR/multitask-tui-wrapper.sh" &
  local tui_pid=$!

  log_success "TUI launched (PID: $tui_pid)"

  # Store TUI PID in session
  jq --arg pid "$tui_pid" '.tui_pid = $pid' "$SESSION_FILE" > "${SESSION_FILE}.tmp"
  mv "${SESSION_FILE}.tmp" "$SESSION_FILE"
}

# Update health fields for a running instance in the session file
update_instance_health() {
  local instance_num=$1
  local heartbeat_ts=$2
  local runtime_secs=$3

  jq --argjson num "$instance_num" \
    --arg hb "$heartbeat_ts" \
    --argjson rt "$runtime_secs" \
    '.instances |= map(if .instance_num == $num then .last_heartbeat = $hb | .runtime_seconds = $rt else . end)' \
    "$SESSION_FILE" > "${SESSION_FILE}.tmp" && mv "${SESSION_FILE}.tmp" "$SESSION_FILE"
}

# Record exit data for a finished instance
# Updates status, exit_code, exited_at, runtime_seconds
# If exit code is non-zero, increments crash_count and appends to crash_log
record_instance_exit() {
  local instance_num=$1
  local exit_code=$2
  local pid=$3

  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Determine status: exit 0 = completed, anything else = crashed
  local new_status="completed"
  if [[ "$exit_code" -ne 0 ]]; then
    new_status="crashed"
  fi

  # Get the started timestamp and compute runtime
  local started
  started=$(jq -r --argjson num "$instance_num" \
    '.instances[] | select(.instance_num == $num) | .started // ""' "$SESSION_FILE")
  local runtime_secs=0
  if [[ -n "$started" ]]; then
    runtime_secs=$(calculate_runtime "$started")
  fi

  local branch
  branch=$(jq -r --argjson num "$instance_num" \
    '.instances[] | select(.instance_num == $num) | .branch // ""' "$SESSION_FILE")

  if [[ "$new_status" == "crashed" ]]; then
    # Build crash event message
    local duration_str
    duration_str=$(format_duration "$runtime_secs")
    local crash_msg="Instance #${instance_num} (${branch}) crashed after ${duration_str} with exit code ${exit_code}"

    log_error "$crash_msg"

    # Update session: status, exit_code, exited_at, runtime, crash_count++, append crash_log
    jq --argjson num "$instance_num" \
      --arg status "$new_status" \
      --argjson code "$exit_code" \
      --arg exited "$now" \
      --argjson rt "$runtime_secs" \
      --argjson pid "$pid" \
      --arg msg "$crash_msg" \
      --arg ts "$now" \
      '.instances |= map(
        if .instance_num == $num then
          .status = $status |
          .exit_code = $code |
          .exited_at = $exited |
          .runtime_seconds = $rt |
          .last_heartbeat = $exited |
          .crash_count = ((.crash_count // 0) + 1) |
          .crash_log = ((.crash_log // []) + [{
            timestamp: $ts,
            exit_code: $code,
            pid: $pid,
            runtime_seconds: $rt,
            message: $msg
          }])
        else . end)' \
      "$SESSION_FILE" > "${SESSION_FILE}.tmp" && mv "${SESSION_FILE}.tmp" "$SESSION_FILE"
  else
    # Clean exit: update status, exit_code, exited_at, runtime
    log_success "Instance #${instance_num} (${branch}) completed after $(format_duration "$runtime_secs")"

    jq --argjson num "$instance_num" \
      --arg status "$new_status" \
      --argjson code "$exit_code" \
      --arg exited "$now" \
      --argjson rt "$runtime_secs" \
      '.instances |= map(
        if .instance_num == $num then
          .status = $status |
          .exit_code = $code |
          .exited_at = $exited |
          .runtime_seconds = $rt |
          .last_heartbeat = $exited
        else . end)' \
      "$SESSION_FILE" > "${SESSION_FILE}.tmp" && mv "${SESSION_FILE}.tmp" "$SESSION_FILE"
  fi
}

# Monitor instances with health checks
monitor_instances() {
  log_section "Monitoring Instances"

  log_info "Monitoring ${#INSTANCE_PIDS[@]} instances (health check every ${HEALTH_CHECK_INTERVAL}s)..."
  log_info "Press Ctrl+C to stop all instances"
  log_info ""
  log_info "Instance logs:"

  for i in "${!INSTANCE_PIDS[@]}"; do
    local num=$((i + 1))
    log_info "  Instance #$num: tail -f $STATE_DIR/multitask-instance-${num}.log"
  done

  log_info ""
  log_info "Aggregate log: tail -f $LOG_FILE"
  log_info ""

  # Build parallel arrays for PID-to-instance mapping (bash 3.2 compatible).
  # _mt_pids[i] and _mt_nums[i] map PIDs to instance numbers.
  # _mt_exited[i] tracks whether we've already processed a PID exit.
  local _mt_pids=()
  local _mt_nums=()
  local _mt_exited=()

  for i in "${!INSTANCE_PIDS[@]}"; do
    _mt_pids+=("${INSTANCE_PIDS[$i]}")
    _mt_nums+=($((i + 1)))
    _mt_exited+=(0)
  done

  # Helper: find instance_num for a PID
  _mt_lookup_num() {
    local _pid=$1
    for _j in "${!_mt_pids[@]}"; do
      if [[ "${_mt_pids[$_j]}" == "$_pid" ]]; then
        echo "${_mt_nums[$_j]}"
        return
      fi
    done
    echo ""
  }

  # Helper: check if a PID has been marked exited
  _mt_is_exited() {
    local _pid=$1
    for _j in "${!_mt_pids[@]}"; do
      if [[ "${_mt_pids[$_j]}" == "$_pid" ]]; then
        echo "${_mt_exited[$_j]}"
        return
      fi
    done
    echo "0"
  }

  # Helper: mark a PID as exited
  _mt_mark_exited() {
    local _pid=$1
    for _j in "${!_mt_pids[@]}"; do
      if [[ "${_mt_pids[$_j]}" == "$_pid" ]]; then
        _mt_exited[$_j]=1
        return
      fi
    done
  }

  # Helper: add a new PID to tracking (for respawns)
  _mt_add_pid() {
    local _pid=$1
    local _num=$2
    _mt_pids+=("$_pid")
    _mt_nums+=("$_num")
    _mt_exited+=(0)
  }

  # Health check loop
  local all_complete=false

  while [[ "$all_complete" == false ]]; do
    all_complete=true
    local running_count=0
    local completed_count=0
    local crashed_count=0
    local heartbeat_ts
    heartbeat_ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    for pid in "${_mt_pids[@]}"; do
      # Skip PIDs we've already processed
      if [[ "$(_mt_is_exited "$pid")" == "1" ]]; then
        continue
      fi

      local instance_num
      instance_num=$(_mt_lookup_num "$pid")

      if ps -p "$pid" > /dev/null 2>&1; then
        # Process is alive - update heartbeat and runtime
        all_complete=false
        running_count=$((running_count + 1))

        local started
        started=$(jq -r --argjson num "$instance_num" \
          '.instances[] | select(.instance_num == $num) | .started // ""' "$SESSION_FILE" 2>/dev/null || echo "")
        local runtime_secs=0
        if [[ -n "$started" ]]; then
          runtime_secs=$(calculate_runtime "$started")
        fi

        update_instance_health "$instance_num" "$heartbeat_ts" "$runtime_secs"
      else
        # Process is dead - read exit code and record
        _mt_mark_exited "$pid"

        local exit_code
        exit_code=$(read_exit_code "$pid")

        if [[ -z "$exit_code" ]]; then
          # No exit code file - process may have been killed externally
          exit_code="-1"
        fi

        record_instance_exit "$instance_num" "$exit_code" "$pid"

        if [[ "$exit_code" -eq 0 ]]; then
          completed_count=$((completed_count + 1))
        else
          crashed_count=$((crashed_count + 1))

          # Auto-respawn if enabled
          if [[ "$AUTO_RESPAWN" == true ]]; then
            local current_crash_count
            current_crash_count=$(jq -r --argjson num "$instance_num" \
              '.instances[] | select(.instance_num == $num) | .crash_count // 0' "$SESSION_FILE")

            if [[ "$current_crash_count" -lt "$MAX_RESPAWN_ATTEMPTS" ]]; then
              log_info "Auto-respawning instance #${instance_num} (attempt ${current_crash_count}/${MAX_RESPAWN_ATTEMPTS})..."
              if respawn_instance "$instance_num"; then
                # Get the new PID and add it to tracking
                local new_pid="${INSTANCE_PIDS[${#INSTANCE_PIDS[@]}-1]}"
                _mt_add_pid "$new_pid" "$instance_num"
                all_complete=false
              else
                log_error "Failed to respawn instance #${instance_num}"
              fi
            else
              log_warn "Instance #${instance_num} exceeded max respawn attempts (${MAX_RESPAWN_ATTEMPTS}), not respawning"
            fi
          fi
        fi
      fi
    done

    # Also check any newly-spawned PIDs from respawn
    for _k in "${!_mt_pids[@]}"; do
      if [[ "${_mt_exited[$_k]}" == "0" ]] && ps -p "${_mt_pids[$_k]}" > /dev/null 2>&1; then
        all_complete=false
        break
      fi
    done

    if [[ "$all_complete" == false ]]; then
      log_info "Health: ${running_count} running, ${completed_count} completed, ${crashed_count} crashed"
      sleep "$HEALTH_CHECK_INTERVAL"
    fi
  done

  log_success "All instances completed"
}

# Show completion summary
show_summary() {
  log_section "Completion Summary"

  # Read session file with health data
  local instances
  instances=$(jq -r '.instances[] | "\(.instance_num)|\(.branch)|\(.status)|\(.runtime_seconds // 0)|\(.crash_count // 0)|\(.exit_code // "")"' "$SESSION_FILE")

  echo ""
  echo "╭─────────────────────────────────────────────────────────────────╮"
  echo "│ Multitask Session Complete                                     │"
  echo "╰─────────────────────────────────────────────────────────────────╯"
  echo ""

  local total_runtime=0
  local total_crashes=0

  while IFS='|' read -r num branch status runtime crashes exit_code; do
    local symbol="✓"
    local color="$GREEN"

    if [[ "$status" != "completed" ]]; then
      symbol="✗"
      color="$RED"
    fi

    local duration_str
    duration_str=$(format_duration "${runtime:-0}")
    total_runtime=$((total_runtime + ${runtime:-0}))
    total_crashes=$((total_crashes + ${crashes:-0}))

    local crash_info=""
    if [[ "${crashes:-0}" -gt 0 ]]; then
      crash_info=" [${crashes} crash(es)]"
    fi

    local exit_info=""
    if [[ -n "$exit_code" && "$exit_code" != "null" ]]; then
      exit_info=" exit:${exit_code}"
    fi

    echo -e "${color}${symbol}${NC} Instance #$num: $branch ($status, ${duration_str}${exit_info}${crash_info})"
  done <<< "$instances"

  echo ""
  echo -e "${CYAN}Total runtime:${NC} $(format_duration $total_runtime)"
  if [[ $total_crashes -gt 0 ]]; then
    echo -e "${YELLOW}Total crashes:${NC} $total_crashes"
  fi

  echo ""
  log_info "Review instance logs in: $STATE_DIR/"
  log_info ""
  log_info "Next steps:"
  log_info "  1. Review changes in each worktree"
  log_info "  2. Merge completed branches: git merge <branch>"
  log_info "  3. Clean up worktrees: $0 --cleanup-all"
  log_info "  4. Create PR: /create-pr"
}

# Cleanup handler
cleanup() {
  log_info ""
  log_warn "Received interrupt signal, cleaning up..."

  # Stop web viewer
  stop_web_viewer

  # Stop all instances
  stop_all_instances

  # Kill TUI if running
  if [[ -f "$SESSION_FILE" ]]; then
    local tui_pid=$(jq -r '.tui_pid // ""' "$SESSION_FILE")
    if [[ -n "$tui_pid" ]] && ps -p "$tui_pid" > /dev/null 2>&1; then
      kill "$tui_pid" 2>/dev/null || true
    fi
  fi

  log_info "Cleanup complete"
  exit 130
}

# Main execution
main() {
  # Set up signal handlers
  trap cleanup SIGINT SIGTERM

  # Initialize log file (append, don't overwrite - may be recovering)
  mkdir -p "$STATE_DIR"
  echo "=== Multitask Session Started: $(date) ===" >> "$LOG_FILE"

  log_section "Multitask - Parallel Worktree Orchestration"

  # Parse arguments (--stop and --cleanup-all exit here)
  parse_args "$@"

  # ==========================================================================
  # Session Recovery Detection
  # Check for existing session BEFORE validate_prerequisites and discover_plans
  # ==========================================================================
  if [[ "$FORCE_NEW_SESSION" != true ]] && detect_stale_session; then
    # Validate PIDs and determine state
    validate_instance_pids

    # Handle explicit recovery flags (non-interactive)
    if [[ -n "$RECOVERY_MODE" ]]; then
      show_instance_summary
      recover_session "$RECOVERY_MODE"
      launch_web_viewer
      launch_monitoring
      show_summary
      return
    fi

    # Interactive recovery prompt
    show_instance_summary
    local recovery_choice
    prompt_session_recovery
    recovery_choice=$?

    case $recovery_choice in
      0)  # Start fresh
        log_info "Stopping existing instances and starting fresh..."
        stop_all_instances
        cleanup_session_file
        ;;
      1)  # Resume/recover
        if [[ "$STALE_SESSION_STATE" == "running" ]]; then
          recover_session "monitor-only"
        else
          recover_session "full"
        fi
        launch_web_viewer
        launch_monitoring
        show_summary
        return
        ;;
      2)  # Cleanup
        log_info "Cleaning up..."
        stop_all_instances
        cleanup_all_worktrees
        cleanup_session_file
        log_success "Cleanup complete"
        return
        ;;
      3)  # Quit
        log_info "Exiting without changes"
        return
        ;;
    esac
  elif [[ "$FORCE_NEW_SESSION" == true ]] && detect_stale_session; then
    log_info "Force-new flag set, stopping existing instances..."
    stop_all_instances
    cleanup_session_file
  fi

  # ==========================================================================
  # Normal startup flow (no stale session or user chose to start fresh)
  # ==========================================================================

  # Validate prerequisites
  validate_prerequisites

  # Convert lightweight task formats to JSON PRDs (if applicable)
  convert_from_file
  convert_inline_tasks

  # Discover plans
  discover_plans

  # Initialize session
  init_session

  # Create worktrees and spawn instances
  log_section "Creating Worktrees and Spawning Instances"

  for i in "${!PLANS[@]}"; do
    local plan="${PLANS[$i]}"
    local branch="${BRANCHES[$i]}"
    local instance_num=$((i + 1))

    log_info "Instance #$instance_num: $branch"

    # Create worktree
    create_worktree "$branch" "$plan"

    # Spawn AI instance
    local instance_json=$(spawn_instance "$branch" "$plan" "$instance_num")

    # Extract PID from JSON and track in parent (command substitution runs in
    # a subshell, so INSTANCE_PIDS changes inside spawn_instance are lost).
    local _pid
    _pid=$(echo "$instance_json" | jq -r '.pid // empty')
    if [[ -n "$_pid" ]]; then
      INSTANCE_PIDS+=("$_pid")
    fi

    # Add to session
    add_instance_to_session "$instance_json"

    echo ""
  done

  log_success "${#PLANS[@]} instances spawned"

  # Launch web viewer if enabled
  launch_web_viewer

  # Launch monitoring
  launch_monitoring

  # Show summary
  show_summary
}

# Run main
main "$@"
