#!/bin/bash
#
# loop.sh - Ralph-style autonomous agent loop
#
# Spawns fresh Claude instances repeatedly until all Plan stories
# are complete or max iterations reached.
#
# Tasks Integration:
#   Each iteration instructs Claude to use the Tasks API for state tracking.
#   This provides visual progress via /tasks command and enables cross-session
#   state persistence. Uses TaskCreate/TaskUpdate/TaskList/TaskGet tools.
#
# Usage: ./scripts/loop.sh [OPTIONS] [max_iterations]
#
# Options:
#   --tui              Launch live TUI dashboard
#   --max N            Set max iterations (default: 20)
#   [N]                Legacy: Set max iterations as positional arg
#
# Examples:
#   ./scripts/loop.sh --tui              # Run with TUI dashboard
#   ./scripts/loop.sh --max 10           # Run max 10 iterations
#   ./scripts/loop.sh --tui --max 15    # Combine options
#   ./scripts/loop.sh 20                 # Legacy syntax
#
# Prerequisites:
#   - AI provider (auto-detects codex or claude)
#   - jq installed for JSON parsing
#   - Active prd.json in docs/plans/
#   - Node.js installed (if using --tui)

set -e

# Script directory for sourcing helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prerequisite checks
check_prerequisites() {
  local missing=()

  if ! command -v jq &>/dev/null; then
    missing+=("jq")
  fi

  if ! command -v git &>/dev/null; then
    missing+=("git")
  fi

  if [[ ${#missing[@]} -gt 0 ]]; then
    echo -e "\033[0;31m[ERROR]\033[0m Missing required dependencies: ${missing[*]}"
    echo ""
    echo "Install with:"
    for dep in "${missing[@]}"; do
      case "$dep" in
        jq)  echo "  brew install jq        # macOS"
             echo "  sudo apt install jq    # Ubuntu/Debian" ;;
        git) echo "  brew install git       # macOS"
             echo "  sudo apt install git   # Ubuntu/Debian" ;;
      esac
    done
    exit 1
  fi
}

check_prerequisites

# Source session manager library
source "$SCRIPT_DIR/lib/session-manager.sh"

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
MAX_ITERATIONS=20
PLAN_DIR="docs/plans"
# PROGRESS_FILE, STOP_FILE, PAUSE_FILE, QUIT_FILE are provided by session-manager.sh
TUI_ENABLED=false
TUI_PID=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --tui)
      TUI_ENABLED=true
      shift
      ;;
    --max)
      MAX_ITERATIONS="$2"
      shift 2
      ;;
    *)
      # Legacy: first positional arg is max iterations
      if [[ "$1" =~ ^[0-9]+$ ]]; then
        MAX_ITERATIONS="$1"
      fi
      shift
      ;;
  esac
done

# Shared logging
source "$SCRIPT_DIR/lib/logging.sh"

# Find active prd.json
find_prd() {
  # Ensure plan directory exists
  mkdir -p "$PLAN_DIR" 2>/dev/null || true

  # Find most recently modified .json in plan directory
  local prd=$(ls -t "$PLAN_DIR"/*.json 2>/dev/null | head -1)

  # Plan Recovery: if no JSON found, check .claude/plans/ for embedded plans
  if [[ -z "$prd" ]]; then
    log_info "No plan JSON in $PLAN_DIR — checking .claude/plans/ for recoverable plans..."
    local recovered=""
    for candidate in .claude/plans/*.md "$HOME/.claude/plans/"*.md; do
      [[ -f "$candidate" ]] || continue
      if grep -q "PLAN_JSON" "$candidate" 2>/dev/null; then
        recovered="$candidate"
        break
      fi
    done

    if [[ -n "$recovered" ]]; then
      log_info "Found recoverable plan: $recovered"
      # Extract feature name from PLAN_META block
      local feature_name
      feature_name=$(sed -n '/<!-- PLAN_META/,/PLAN_META -->/{ /^feature:/s/feature: *//p }' "$recovered" 2>/dev/null) || true
      if [[ -z "$feature_name" ]]; then
        feature_name="recovered-plan"
      fi

      # Extract JSON from PLAN_JSON block
      local json_content
      json_content=$(sed -n '/<!-- PLAN_JSON/,/PLAN_JSON -->/{//d; /^```json$/d; /^```$/d; p}' "$recovered" 2>/dev/null) || true

      if [[ -n "$json_content" ]]; then
        echo "$json_content" > "$PLAN_DIR/${feature_name}.json"
        log_info "Recovered plan JSON → $PLAN_DIR/${feature_name}.json"

        # Also extract markdown (strip PLAN_JSON and PLAN_META blocks)
        sed '/<!-- PLAN_JSON/,/PLAN_JSON -->/d; /<!-- PLAN_META/,/PLAN_META -->/d' "$recovered" > "$PLAN_DIR/${feature_name}.md" 2>/dev/null || true

        prd="$PLAN_DIR/${feature_name}.json"
      fi
    fi
  fi

  if [[ -z "$prd" ]]; then
    log_error "No plan JSON found in $PLAN_DIR"
    log_info "Run '/create-plan' to create a plan first"
    exit 1
  fi
  echo "$prd"
}

# Check if all stories pass
all_complete() {
  local prd=$1
  local incomplete=$(jq '[.stories[] | select(.passes == false)] | length' "$prd")
  [[ "$incomplete" -eq 0 ]]
}

# Archive completed plan to docs/plans/archive/ so it won't be picked up by future loops
archive_completed_plan() {
  local prd=$1
  local archive_dir="$PLAN_DIR/archive"
  mkdir -p "$archive_dir"
  local plan_basename=$(basename "$prd")
  local archive_path="$archive_dir/$plan_basename"
  if mv "$prd" "$archive_path" 2>/dev/null; then
    log_success "Plan archived: $archive_path"
  else
    log_warn "Could not archive plan file (may have already been moved)"
  fi
}

# Get next incomplete story
next_story() {
  local prd=$1
  jq -r '[.stories[] | select(.passes == false)] | sort_by(.priority) | .[0] | "\(.id): \(.title) [\(.type)]"' "$prd"
}

# Get story type by ID
get_story_type() {
  local prd=$1
  local story_id=$2
  jq -r --arg id "$story_id" '.stories[] | select(.id == $id) | .type // "Core"' "$prd"
}

# Count stories
count_stories() {
  local prd=$1
  local total=$(jq '.stories | length' "$prd")
  local complete=$(jq '[.stories[] | select(.passes == true)] | length' "$prd")
  echo "$complete/$total"
}

# Run visual verification for UI stories
run_visual_verification() {
  local story_type=$1

  # Only run for UI stories
  if [[ "$story_type" != "UI" ]]; then
    return 0
  fi

  log_info "UI story detected - running visual verification..."

  # Check if browser-verify.sh exists
  local browser_verify=""
  if [[ -f "$SCRIPT_DIR/browser-verify.sh" ]]; then
    browser_verify="$SCRIPT_DIR/browser-verify.sh"
  elif [[ -f ".claude/scripts/browser-verify.sh" ]]; then
    browser_verify=".claude/scripts/browser-verify.sh"
  fi

  if [[ -z "$browser_verify" ]]; then
    log_warn "browser-verify.sh not found - skipping visual verification"
    return 0
  fi

  # Detect dev server URL from environment or use default
  local dev_url="${DEV_SERVER_URL:-http://localhost:3000}"

  # Run visual verification (soft failure - don't block loop)
  if "$browser_verify" --compare "$dev_url" 2>/dev/null; then
    log_success "Visual verification passed"
  else
    log_warn "Visual verification failed or unavailable (non-blocking)"
  fi

  return 0
}

# Initialize progress file if needed
init_progress() {
  if [[ ! -f "$PROGRESS_FILE" ]]; then
    mkdir -p "$(dirname "$PROGRESS_FILE")"
    cat > "$PROGRESS_FILE" << 'EOF'
# Progress Log

Append-only log of learnings and progress across iterations.

## Codebase Patterns

<!-- Consolidated patterns discovered during implementation -->

---

## Iteration Log

EOF
    log_info "Created $PROGRESS_FILE"
  fi
}

# Append iteration start to progress
log_iteration_start() {
  local iteration=$1
  local story=$2
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

  cat >> "$PROGRESS_FILE" << EOF

### Iteration $iteration ($timestamp)

**Story**: $story
**Status**: In Progress

EOF
}

# Check TUI prerequisites
check_tui_prerequisites() {
  local errors=()

  # Check Node.js
  if ! command -v node &> /dev/null; then
    errors+=("Node.js is not installed (required for TUI)")
  fi

  # Check TUI directory exists
  if [[ ! -d "$SCRIPT_DIR/tui" ]]; then
    errors+=("TUI directory not found at $SCRIPT_DIR/tui")
  fi

  # Return errors if any
  if [[ ${#errors[@]} -gt 0 ]]; then
    for err in "${errors[@]}"; do
      log_warn "$err"
    done
    return 1
  fi

  return 0
}

# Start TUI in background
start_tui() {
  if [[ "$TUI_ENABLED" != "true" ]]; then
    return 0
  fi

  log_info "Starting TUI dashboard..."

  # Check prerequisites first
  if ! check_tui_prerequisites; then
    log_warn "TUI prerequisites not met, falling back to traditional mode"
    log_info "The loop will continue without the dashboard"
    log_info "Monitor progress with: tail -f $PROGRESS_FILE"
    TUI_ENABLED=false
    return 0
  fi

  # Create a temporary file for TUI startup errors
  local tui_error_log=$(mktemp)

  # Start TUI, capturing errors to temp file
  "$SCRIPT_DIR/tui-wrapper.sh" 2>"$tui_error_log" &
  TUI_PID=$!

  # Give TUI a moment to start
  sleep 2

  # Check if TUI is still running
  if ! kill -0 "$TUI_PID" 2>/dev/null; then
    log_warn "TUI failed to start, falling back to traditional mode"

    # Show any error output from TUI
    if [[ -s "$tui_error_log" ]]; then
      log_warn "TUI error: $(head -3 "$tui_error_log")"
    fi

    log_info "The loop will continue running without the dashboard"
    log_info "Monitor progress with: tail -f $PROGRESS_FILE"
    TUI_ENABLED=false
    TUI_PID=""
  else
    log_success "TUI running (PID: $TUI_PID)"
  fi

  # Clean up temp file
  rm -f "$tui_error_log"
}

# Stop TUI
stop_tui() {
  if [[ -n "$TUI_PID" ]] && kill -0 "$TUI_PID" 2>/dev/null; then
    log_info "Stopping TUI..."
    kill "$TUI_PID" 2>/dev/null || true
    wait "$TUI_PID" 2>/dev/null || true
  fi
}

# Graceful shutdown handler
shutdown_handler() {
  echo ""
  log_warn "Received interrupt signal (Ctrl+C)"
  log_info "Saving session state..."

  # Stop TUI first
  stop_tui

  # Update multitask instance status if running in worktree
  if is_worktree; then
    update_multitask_instance_status "stopped"
    log_info "Updated multitask instance status to 'stopped'"
  fi

  # Mark session as crashed (interrupted)
  # Use plan-scoped session if CLAUDE_PLAN is set
  local plan_name="${CLAUDE_PLAN:-}"
  if [[ -n "$plan_name" ]]; then
    update_plan_session "$plan_name" ".status" "crashed"
    local session_file=$(get_plan_session_file "$plan_name")
    log_success "Session state saved to $session_file"
  else
    crash_session
    log_success "Session state saved to $SESSION_FILE"
  fi
  log_info "To resume: run './scripts/loop.sh' again"
  exit 130
}

# Check for interrupted session and prompt to resume
# Uses plan-scoped sessions if CLAUDE_PLAN is set
check_for_resume() {
  local plan_name="${CLAUDE_PLAN:-}"
  local session_file

  if [[ -n "$plan_name" ]]; then
    # Check plan-scoped session
    session_file=$(get_plan_session_file "$plan_name")
    if [[ ! -f "$session_file" ]]; then
      return 0  # No session for this plan
    fi
    local status=$(jq -r '.status // "unknown"' "$session_file")
  else
    # Legacy: check global session
    if ! has_active_session; then
      return 0
    fi
    session_file="$SESSION_FILE"
    local status=$(get_session_field ".status")
  fi

  # Only prompt for crashed or paused sessions
  if [[ "$status" != "crashed" && "$status" != "paused" ]]; then
    return 0
  fi

  # Display session summary
  echo ""
  log_warn "Found interrupted session from previous run"
  echo ""
  if [[ -n "$plan_name" ]]; then
    echo "=== Session Summary (Plan: $plan_name) ==="
    echo "Status: $(jq -r '.status' "$session_file")"
    echo "Progress: $(jq -r '.progress.completed' "$session_file")/$(jq -r '.progress.total_stories' "$session_file")"
    echo "Current Story: $(jq -r '.progress.current_story' "$session_file")"
    echo "Iteration: $(jq -r '.progress.current_iteration' "$session_file")"
  else
    show_session_summary
  fi
  echo ""

  # Prompt user
  read -p "Resume this session? [Y/n] " -n 1 -r
  echo ""

  if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
    log_info "Resuming session..."
    if [[ -n "$plan_name" ]]; then
      update_plan_session "$plan_name" ".status" "running"
    else
      resume_session
    fi
    return 1  # Signal to skip init_session
  else
    log_info "Starting new session (old session will be archived)"
    if [[ -n "$plan_name" ]]; then
      # Archive plan-scoped session
      local archive_dir="$(get_plan_state_dir "$plan_name")/archive"
      mkdir -p "$archive_dir"
      cp "$session_file" "$archive_dir/session-interrupted-$(date +%Y%m%d-%H%M%S).json"
      rm -f "$session_file"
      log_info "Archived plan session"
    else
      local old_plan_name=$(get_session_field ".plan.name")
      local archive_path
      archive_path=$(archive_session "${old_plan_name}-interrupted")
      log_info "Archived to: ${archive_path}"
    fi
    return 0  # Signal to proceed with init_session
  fi
}

# Main loop
main() {
  # Set up signal trap for graceful shutdown
  trap shutdown_handler SIGINT SIGTERM
  log_info "Starting autonomous loop (max $MAX_ITERATIONS iterations)"

  # Find plan
  local prd=$(find_prd)
  local plan_name=$(basename "$prd" .json)
  log_info "Using plan: $prd"

  # Export CLAUDE_PLAN for plan-scoped session management
  # This enables multi-agent coordination with isolated sessions per plan
  export CLAUDE_PLAN="$plan_name"
  log_info "Plan context: $plan_name (CLAUDE_PLAN exported)"

  # If running in a worktree (e.g., spawned by /multitask), register with
  # the main repo's multitask-session.json instead of overwriting it
  if is_worktree; then
    local branch=$(git branch --show-current)
    local worktree_path=$(git rev-parse --show-toplevel)
    log_info "Running in worktree: $worktree_path"
    register_multitask_instance "$plan_name" "$branch" "$worktree_path"
  fi

  # Initialize progress
  init_progress

  # Check for interrupted session and prompt to resume
  local should_init_session=true
  if check_for_resume; then
    # User declined resume or no interrupted session
    should_init_session=true
  else
    # User accepted resume
    should_init_session=false
  fi

  # Initialize plan-scoped session state if needed (not resuming)
  local session_file
  if [[ "$should_init_session" == "true" ]]; then
    log_info "Initializing plan-scoped session..."
    session_file=$(init_plan_session "$prd" "autonomous")
    log_info "Session initialized: $session_file"
  else
    session_file=$(get_plan_session_file "$plan_name")
  fi

  # Start TUI if enabled
  start_tui

  # Clean up any previous stop file
  rm -f "$STOP_FILE"

  # CRITICAL: Ensure tasks exist for the plan before starting loop
  # This fixes the issue where /create-plan didn't create tasks
  log_info "Syncing plan to Tasks API..."
  local sync_prompt="Sync the plan file to Claude Code Tasks.

**Plan file**: $prd

1. Read the plan JSON file
2. Use TaskList to check if tasks exist for this plan
3. If NO tasks exist (or fewer tasks than stories), CREATE them using TaskCreate:
   - For each story where passes: false
   - Subject: '\${story.id}: \${story.title}'
   - Description: Story acceptance criteria
   - ActiveForm: 'Implementing \${story.title}'
   - Metadata: { planPath: '$prd', itemId: story.id, storyType: story.type }
4. For stories already marked passes: true, ensure their task is marked 'completed'
5. Report how many tasks were created, synced, or already existed

This is REQUIRED before the loop can track progress via /tasks."

  local task_sync_output
  if task_sync_output=$(ai_print_prompt "$sync_prompt" 2>&1); then
    log_success "Tasks synced"
  else
    log_warn "Task sync failed - tasks may not appear in /tasks but loop will continue"
    log_info "  (Plan JSON file remains the source of truth for progress)"

    # Write structured diagnostic for task sync failure
    local diag_file="$STATE_DIR/loop-diagnostics.jsonl"
    local diag_ts
    diag_ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local sync_error
    sync_error=$(echo "$task_sync_output" | tail -5 | tr '\n' ' ' | cut -c1-300 | sed 's/"/\\"/g')
    printf '{"event":"task_sync_failed","plan":"%s","error":"%s","timestamp":"%s"}\n' \
      "$plan_name" "$sync_error" "$diag_ts" >> "$diag_file"
  fi

  # Check if already complete
  if all_complete "$prd"; then
    log_success "All stories already complete!"
    complete_session
    # Update multitask instance status if in worktree
    is_worktree && update_multitask_instance_status "completed"
    archive_completed_plan "$prd"
    stop_tui
    exit 0
  fi

  # Determine starting iteration
  local iteration=1
  if [[ "$should_init_session" == "false" ]]; then
    # Resuming: continue from last iteration
    local saved_iteration=$(get_session_field ".progress.current_iteration")
    if [[ -n "$saved_iteration" && "$saved_iteration" -gt 0 ]]; then
      iteration=$((saved_iteration + 1))
      log_info "Resuming from iteration $iteration"
    fi
  fi

  while [[ $iteration -le $MAX_ITERATIONS ]]; do
    # Check for stop signal
    if [[ -f "$STOP_FILE" ]]; then
      log_warn "Stop signal detected. Exiting gracefully."
      rm -f "$STOP_FILE"
      # Update multitask instance status if in worktree
      is_worktree && update_multitask_instance_status "stopped"
      stop_tui
      exit 0
    fi

    # Check for quit signal (from TUI)
    if [[ -f "$QUIT_FILE" ]]; then
      log_warn "Quit requested from TUI. Exiting gracefully..."
      rm -f "$QUIT_FILE"
      update_session ".status" "complete"
      add_activity "complete" "" "Loop quit by user"
      # Update multitask instance status if in worktree
      is_worktree && update_multitask_instance_status "stopped"
      stop_tui

      echo ""
      log_info "Next steps:"
      echo "  1. Review progress in $PROGRESS_FILE"
      echo "  2. Run /iterate to continue, or"
      echo "  3. Run /pre-pr-check if ready for PR"
      exit 0
    fi

    # Check for pause signal (from TUI)
    if [[ -f "$PAUSE_FILE" ]]; then
      log_warn "Pause requested - finishing current story, then waiting..."
      update_session ".status" "paused"
      add_activity "pause" "" "Loop paused by user"

      # Wait for resume signal
      while [[ -f "$PAUSE_FILE" ]]; do
        sleep 2
        # Check if quit was requested during pause
        if [[ -f "$QUIT_FILE" ]]; then
          log_warn "Quit requested while paused. Exiting..."
          rm -f "$QUIT_FILE" "$PAUSE_FILE"
          update_session ".status" "complete"
          stop_tui
          exit 0
        fi
      done

      log_info "Resume signal received. Continuing..."
      update_session ".status" "running"
      add_activity "resume" "" "Loop resumed by user"
    fi

    # Check completion
    if all_complete "$prd"; then
      local final_progress=$(count_stories "$prd")
      local plan_name=$(basename "$prd" .json)
      log_success "All stories complete!"

      # Update session to complete
      complete_session
      # Update multitask instance status if in worktree
      is_worktree && update_multitask_instance_status "completed"

      # Archive completed plan so future loops don't pick it up
      archive_completed_plan "$prd"

      # Send notifications
      "$SCRIPT_DIR/notify.sh" "loop_complete" "Loop Complete" "All stories complete!" \
        --progress "$final_progress" --plan "$plan_name"

      echo ""
      log_info "Next steps:"
      echo "  1. Run /pre-pr-check"
      echo "  2. Run /create-pr"
      stop_tui
      exit 0
    fi

    # Get next story
    local story=$(next_story "$prd")
    local story_id=$(echo "$story" | cut -d: -f1)
    local story_type=$(get_story_type "$prd" "$story_id")
    local progress=$(count_stories "$prd")
    local completed=$(echo "$progress" | cut -d/ -f1)

    local total=$(echo "$progress" | cut -d/ -f2)
    local pct=0
    if [[ "$total" -gt 0 ]]; then
      pct=$(( completed * 100 / total ))
    fi

    echo ""
    log_info "═══════════════════════════════════════════════════"
    log_info "Iteration $iteration/$MAX_ITERATIONS"
    log_info "Progress: $progress stories complete ($pct%)"
    log_info "Next: $story"
    log_info "═══════════════════════════════════════════════════"
    echo ""

    # Log to progress file
    log_iteration_start "$iteration" "$story"

    # Update session: story started
    update_progress "$completed" "$story_id" "$iteration"
    add_activity "story_started" "$story_id" "Starting implementation"

    # Run Claude with the loop-iteration prompt
    # Enhanced prompt includes Tasks API integration for persistent state tracking:
    # 1. Read prd.json and find next story
    # 2. TaskUpdate - mark story as in_progress
    # 3. Implement it
    # 4. Verify
    # 5. Commit
    # 6. Update prd.json
    # 7. TaskUpdate - mark story as completed
    # 8. Append learnings to progress.txt
    # 9. Output <promise>COMPLETE</promise> if all done

    # Query ACS for relevant context (optional, non-blocking)
    local acs_context=""
    if [[ "$ACS_ENABLED" == "true" ]] && acs_is_available; then
      local acs_result
      acs_result=$(acs_query "patterns and learnings for: $story" 10 2000 2>/dev/null) || true
      acs_context=$(echo "$acs_result" | acs_extract_context 2>/dev/null) || true
      if [[ -n "$acs_context" ]]; then
        _acs_debug "Injecting ACS context for story: $story_id"
      fi
    fi

    # Extract reuse/constraints context for this story from prd.json
    local reuse_section=""
    local story_reuse=""
    local story_constraints=""
    story_reuse=$(jq -r --arg id "$story_id" '
      .stories[] | select(.id == $id) |
      if .reuse and (.reuse | length > 0) then
        "**Reuse (MANDATORY — read these files before implementing):**\n" +
        (.reuse | map("- `" + .path + "` — " + .what + " (" + .how + ")") | join("\n"))
      else "" end
    ' "$prd" 2>/dev/null) || true
    story_constraints=$(jq -r --arg id "$story_id" '
      .stories[] | select(.id == $id) |
      if .constraints and (.constraints | length > 0) then
        "**Constraints (DO NOT violate):**\n" +
        (.constraints | map("- " + .) | join("\n"))
      else "" end
    ' "$prd" 2>/dev/null) || true

    if [[ -n "$story_reuse" || -n "$story_constraints" ]]; then
      reuse_section="

${story_reuse}
${story_constraints}
"
    else
      reuse_section="

**Reuse-first**: Before creating new components, hooks, or utilities, search for existing similar code in the codebase. Extend or adapt existing implementations rather than building from scratch."
    fi

    local output
    local acs_section=""
    if [[ -n "$acs_context" ]]; then
      acs_section="

**ACS Context (cross-project learnings):**
$acs_context
"
    fi
    local prompt="Execute one iteration of the autonomous loop.

**Story**: $story${acs_section}${reuse_section}

1. Read the prd.json at $prd
2. Find the next incomplete story (passes: false)
3. **Sync Task for this story**:
   - Use TaskList to find the task for this story (by itemId in metadata or subject prefix)
   - If task NOT found: Create it with TaskCreate first
   - Use TaskUpdate to set status to 'in_progress'
4. Implement the story following best practices
5. Verify with lint/typecheck/test
6. Commit changes (the loop runner will detect the commit and mark the story complete in prd.json automatically)
7. **Update Tasks via TaskUpdate**: Mark the completed story as 'completed'
8. Append learnings to $PROGRESS_FILE

If ALL stories are now complete, output <promise>COMPLETE</promise> at the end.

**Important**: Always ensure a Task exists before starting work. If TaskList doesn't find a matching task, use TaskCreate to create it. This enables progress tracking via /tasks."

    # Capture git HEAD before iteration so we can detect new commits
    local head_before
    head_before=$(git rev-parse HEAD 2>/dev/null || echo "")

    local iter_log="$STATE_DIR/loop-iteration-${iteration}.log"
    local iter_pid
    iter_pid=$(ai_dispatch_prompt "$prompt" "$iter_log" "" "" "")
    wait "$iter_pid" 2>/dev/null || true
    output=$(cat "$iter_log" 2>/dev/null) || true

    # Run visual verification for UI stories
    run_visual_verification "$story_type"

    # Detect if the spawned instance committed changes (new HEAD != old HEAD)
    local head_after
    head_after=$(git rev-parse HEAD 2>/dev/null || echo "")
    local has_new_commit=false
    if [[ -n "$head_before" && -n "$head_after" && "$head_before" != "$head_after" ]]; then
      has_new_commit=true
    fi

    # If a new commit was made but the plan file wasn't updated, mark the story
    # complete from loop.sh directly. This is the safety net — spawned instances
    # often fail to update the JSON because they run in print mode with limited
    # tool access.
    local plan_already_updated=false
    local current_passes
    current_passes=$(jq -r --arg id "$story_id" '.stories[] | select(.id == $id) | .passes' "$prd" 2>/dev/null)
    if [[ "$current_passes" == "true" ]]; then
      plan_already_updated=true
    fi

    if [[ "$has_new_commit" == true && "$plan_already_updated" == false ]]; then
      local commit_hash
      commit_hash=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
      local completed_at
      completed_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
      log_info "New commit detected ($commit_hash) — marking $story_id complete in plan"
      jq --arg id "$story_id" --arg commit "$commit_hash" --arg ts "$completed_at" \
        '.stories |= map(if .id == $id then .passes = true | .commit = $commit | .completed_at = $ts else . end)' \
        "$prd" > "${prd}.tmp" && mv "${prd}.tmp" "$prd"
    fi

    # Write structured diagnostic for this iteration
    local diag_file="$STATE_DIR/loop-diagnostics.jsonl"
    local iter_exit_code
    iter_exit_code=$(cat "$iter_log.exit" 2>/dev/null || echo "-1")
    local iter_duration_s=""
    local output_tail=""
    output_tail=$(tail -3 "$iter_log" 2>/dev/null | tr '\n' ' ' | cut -c1-200)
    local diag_ts
    diag_ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    printf '{"iteration":%d,"story_id":"%s","head_before":"%s","head_after":"%s","commit_detected":%s,"plan_updated":%s,"exit_code":%s,"output_tail":"%s","timestamp":"%s"}\n' \
      "$iteration" "$story_id" "$head_before" "$head_after" \
      "$has_new_commit" "$plan_already_updated" "$iter_exit_code" \
      "$(echo "$output_tail" | sed 's/"/\\"/g')" "$diag_ts" \
      >> "$diag_file"

    # Update session after iteration
    local new_progress=$(count_stories "$prd")
    local new_completed=$(echo "$new_progress" | cut -d/ -f1)
    update_progress "$new_completed" "$story_id" "$iteration"
    update_git_status

    # Sync task status if story was completed in this iteration
    if [[ "$new_completed" -gt "$completed" ]]; then
      add_activity "story_completed" "$story_id" "Implementation complete"
      log_success "✓ Story $story_id completed ($new_progress)"

      # Post-iteration task sync: ensure Tasks API reflects completion
      local task_sync_log="$STATE_DIR/loop-task-sync-${iteration}.log"
      local task_sync_prompt="Sync task completion for story $story_id.

1. Use TaskList to find the task for story '$story_id' (check metadata.itemId or subject prefix)
2. If found, use TaskUpdate to set status to 'completed'
3. If NOT found, create it with TaskCreate (subject: '$story_id: completed', status: completed)

This is a quick sync operation - no code changes needed."
      local task_pid
      task_pid=$(ai_dispatch_prompt "$task_sync_prompt" "$task_sync_log" "" "" "")
      wait "$task_pid" 2>/dev/null || true
      log_info "  Tasks API synced for $story_id"
    else
      add_activity "iteration_complete" "$story_id" "Iteration finished (story may still be in progress)"
      log_warn "Story $story_id not yet complete after iteration $iteration"
    fi

    # Check for completion signal — verify against actual plan before trusting it
    if echo "$output" | grep -q "<promise>COMPLETE</promise>"; then
      local final_progress=$(count_stories "$prd")
      local final_completed=$(echo "$final_progress" | cut -d/ -f1)
      local final_total=$(echo "$final_progress" | cut -d/ -f2)
      local plan_name=$(basename "$prd" .json)

      if [[ "$final_completed" -lt "$final_total" ]]; then
        log_warn "Completion signal received but only $final_progress stories done — ignoring false signal"
      else
        log_success "Completion signal received!"

      # Update session to complete
      complete_session
      # Update multitask instance status if in worktree
      is_worktree && update_multitask_instance_status "completed"

      # Archive completed plan so future loops don't pick it up
      archive_completed_plan "$prd"

      # Send notifications
      "$SCRIPT_DIR/notify.sh" "loop_complete" "Loop Complete" "All stories complete!" \
        --progress "$final_progress" --plan "$plan_name"

      echo ""
      log_info "Next steps:"
      echo "  1. Run /pre-pr-check"
      echo "  2. Run /create-pr"
      stop_tui
      exit 0
      fi
    fi

    # Brief pause between iterations
    sleep 2

    ((iteration++))
  done

  local final_progress=$(count_stories "$prd")
  local plan_name=$(basename "$prd" .json)
  log_warn "Reached maximum iterations ($MAX_ITERATIONS)"

  # Update multitask instance status if in worktree
  is_worktree && update_multitask_instance_status "stopped"

  # Send notifications
  "$SCRIPT_DIR/notify.sh" "loop_max_iterations" "Loop Stopped" "Reached max iterations ($MAX_ITERATIONS)" \
    --progress "$final_progress" --plan "$plan_name"

  log_info "Check $PROGRESS_FILE for status"
  log_info "Run './scripts/loop.sh' to continue"
  stop_tui
  exit 1
}

# Run main
main "$@"
