#!/bin/bash
#
# session-manager.sh - Session state management helpers
#
# Provides functions for creating, updating, and reading session state
# for autonomous and attended execution modes.

# State directory - single source of truth for all runtime state
STATE_DIR=".claude/state"

# Legacy session file locations (for backwards compatibility)
SESSION_FILE="$STATE_DIR/session.json"
SESSION_ARCHIVE_DIR="$STATE_DIR/sessions"
PROGRESS_FILE="$STATE_DIR/progress.txt"
PAUSE_FILE="$STATE_DIR/.pause"
QUIT_FILE="$STATE_DIR/.quit"
STOP_FILE="$STATE_DIR/.stop-loop"

# Plan-scoped state directories
PLANS_STATE_DIR="$STATE_DIR/plans"
FILE_CLAIMS_FILE="$STATE_DIR/file-claims.json"

# =============================================================================
# Plan-Scoped Session Functions (Multi-Agent Coordination)
# =============================================================================

# Get state directory for a specific plan
# Usage: get_plan_state_dir <plan_name>
get_plan_state_dir() {
  local plan_name=$1
  echo "$PLANS_STATE_DIR/$plan_name"
}

# Get session file path for a specific plan
# Usage: get_plan_session_file <plan_name>
get_plan_session_file() {
  local plan_name=$1
  echo "$(get_plan_state_dir "$plan_name")/session.json"
}

# Detect active plan from context
# Priority: 1. CLAUDE_PLAN env var, 2. Git branch, 3. Most recent plan file
# Usage: detect_active_plan
detect_active_plan() {
  # 1. Check environment variable (explicit override)
  if [[ -n "${CLAUDE_PLAN:-}" ]]; then
    echo "$CLAUDE_PLAN"
    return 0
  fi

  # 2. Try to match git branch to a plan file
  local branch=$(git branch --show-current 2>/dev/null)
  if [[ -n "$branch" ]]; then
    # Extract plan name from branch (e.g., "feature/my-feature" -> "my-feature")
    local plan_name="${branch#feature/}"
    plan_name="${plan_name#fix/}"
    plan_name="${plan_name#refactor/}"

    # Check if matching plan file exists
    if [[ -f "docs/plans/${plan_name}.json" ]]; then
      echo "$plan_name"
      return 0
    fi
    if [[ -f "docs/plans/${plan_name}.md" ]]; then
      echo "$plan_name"
      return 0
    fi
  fi

  # 3. Find most recently modified plan file (guard against missing directory)
  if [[ ! -d "docs/plans" ]]; then
    return 1
  fi

  local recent_plan=$(ls -t docs/plans/*.json 2>/dev/null | head -1)
  if [[ -n "$recent_plan" ]]; then
    basename "$recent_plan" .json
    return 0
  fi

  # Fallback to markdown plans
  recent_plan=$(ls -t docs/plans/*.md 2>/dev/null | head -1)
  if [[ -n "$recent_plan" ]]; then
    basename "$recent_plan" .md
    return 0
  fi

  # No plan found
  return 1
}

# List all plans with active sessions
# Usage: list_active_plans
list_active_plans() {
  local plans=()

  # Check plan-scoped sessions
  if [[ -d "$PLANS_STATE_DIR" ]]; then
    for session in "$PLANS_STATE_DIR"/*/session.json; do
      if [[ -f "$session" ]]; then
        local status=$(jq -r '.status // "unknown"' "$session" 2>/dev/null)
        if [[ "$status" == "running" || "$status" == "paused" ]]; then
          local plan_name=$(jq -r '.plan.name // empty' "$session" 2>/dev/null)
          if [[ -n "$plan_name" ]]; then
            plans+=("$plan_name")
          fi
        fi
      fi
    done
  fi

  # Also check legacy global session for backwards compatibility
  if [[ -f "$SESSION_FILE" ]]; then
    local status=$(jq -r '.status // "unknown"' "$SESSION_FILE" 2>/dev/null)
    if [[ "$status" == "running" || "$status" == "paused" ]]; then
      local plan_name=$(jq -r '.plan.name // empty' "$SESSION_FILE" 2>/dev/null)
      if [[ -n "$plan_name" ]]; then
        # Only add if not already in list
        local found=0
        for p in "${plans[@]}"; do
          if [[ "$p" == "$plan_name" ]]; then
            found=1
            break
          fi
        done
        if [[ $found -eq 0 ]]; then
          plans+=("$plan_name (legacy)")
        fi
      fi
    fi
  fi

  printf '%s\n' "${plans[@]}"
}

# Get the session file path to use (plan-scoped or legacy)
# If CLAUDE_PLAN is set, uses plan-scoped; otherwise falls back to legacy
# Usage: get_active_session_file
get_active_session_file() {
  local plan_name="${CLAUDE_PLAN:-}"

  if [[ -n "$plan_name" ]]; then
    get_plan_session_file "$plan_name"
  else
    echo "$SESSION_FILE"
  fi
}

# Check if a specific plan has an active session
# Usage: has_plan_session <plan_name>
has_plan_session() {
  local plan_name=$1
  local session_file=$(get_plan_session_file "$plan_name")
  [[ -f "$session_file" ]]
}

# Get session field from a specific plan's session
# Usage: get_plan_session_field <plan_name> <field_path>
get_plan_session_field() {
  local plan_name=$1
  local field_path=$2
  local session_file=$(get_plan_session_file "$plan_name")

  if [[ ! -f "$session_file" ]]; then
    echo ""
    return 1
  fi

  jq -r "$field_path // empty" "$session_file"
}

# Initialize a plan-scoped session
# Usage: init_plan_session <plan_path> <mode>
init_plan_session() {
  local plan_path=$1
  local mode=${2:-"autonomous"}
  local plan_name=$(basename "$plan_path" .json)
  local plan_state_dir=$(get_plan_state_dir "$plan_name")
  local session_file=$(get_plan_session_file "$plan_name")
  local branch=$(git branch --show-current)
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Create plan-scoped state directory
  mkdir -p "$plan_state_dir"

  # Get total stories from plan
  local total_stories=$(jq '.stories | length' "$plan_path" 2>/dev/null || echo "0")

  # Create initial session state with v2.0 format (includes agent tracking)
  cat > "$session_file" << EOF
{
  "version": "2.0",
  "plan_id": "$plan_name",
  "created_at": "$timestamp",
  "updated_at": "$timestamp",
  "status": "running",
  "plan": {
    "path": "$plan_path",
    "name": "$plan_name",
    "branch": "$branch"
  },
  "progress": {
    "total_stories": $total_stories,
    "completed": 0,
    "current_story": null,
    "current_iteration": 0
  },
  "agents": [],
  "file_claims": [],
  "git": {
    "branch": "$branch",
    "head_commit": "$(git rev-parse --short HEAD 2>/dev/null || echo 'none')",
    "modified_files": []
  },
  "execution": {
    "mode": "$mode",
    "pid": $$,
    "start_time": "$timestamp"
  },
  "activity_log": []
}
EOF

  # Export plan name for child processes
  export CLAUDE_PLAN="$plan_name"

  echo "$session_file"
}

# Update a plan-scoped session
# Usage: update_plan_session <plan_name> <field_path> <value>
update_plan_session() {
  local plan_name=$1
  local field_path=$2
  local value=$3
  local session_file=$(get_plan_session_file "$plan_name")
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  if [[ ! -f "$session_file" ]]; then
    echo "Error: Session file not found for plan: $plan_name" >&2
    return 1
  fi

  # Update the field and timestamp atomically
  jq --arg ts "$timestamp" --arg val "$value" \
    "$field_path = \$val | .updated_at = \$ts" \
    "$session_file" > "$session_file.tmp" && \
    mv "$session_file.tmp" "$session_file"
}

# Register an agent with a plan session
# Usage: register_agent_with_plan <plan_name> <agent_id> <role>
register_agent_with_plan() {
  local plan_name=$1
  local agent_id=$2
  local role=${3:-"worker"}
  local session_file=$(get_plan_session_file "$plan_name")
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  if [[ ! -f "$session_file" ]]; then
    echo "Error: Session file not found for plan: $plan_name" >&2
    return 1
  fi

  jq --arg id "$agent_id" --arg ts "$timestamp" --arg role "$role" \
    '.agents += [{id: $id, joined_at: $ts, role: $role}] | .updated_at = $ts' \
    "$session_file" > "$session_file.tmp" && \
    mv "$session_file.tmp" "$session_file"
}

# Deregister an agent from a plan session
# Usage: deregister_agent_from_plan <plan_name> <agent_id>
deregister_agent_from_plan() {
  local plan_name=$1
  local agent_id=$2
  local session_file=$(get_plan_session_file "$plan_name")
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  if [[ ! -f "$session_file" ]]; then
    return 0  # No session, nothing to do
  fi

  jq --arg id "$agent_id" --arg ts "$timestamp" \
    '.agents = [.agents[] | if .id == $id then . + {departed_at: $ts} else . end] | .updated_at = $ts' \
    "$session_file" > "$session_file.tmp" && \
    mv "$session_file.tmp" "$session_file"
}

# Migrate global session.json to plan-scoped session
# Called when transitioning from legacy single-session to multi-agent mode
# Usage: migrate_to_plan_scoped
migrate_to_plan_scoped() {
  # Only migrate if old global session.json exists with a plan reference
  if [[ ! -f "$SESSION_FILE" ]]; then
    return 0
  fi

  local plan_name=$(jq -r '.plan.name // empty' "$SESSION_FILE" 2>/dev/null)
  if [[ -z "$plan_name" ]]; then
    echo "Warning: Global session has no plan name, cannot migrate" >&2
    return 1
  fi

  # Check if plan-scoped session already exists
  local plan_dir=$(get_plan_state_dir "$plan_name")
  local plan_session=$(get_plan_session_file "$plan_name")

  if [[ -f "$plan_session" ]]; then
    echo "Plan-scoped session already exists for: $plan_name" >&2
    echo "Archiving global session instead" >&2
    archive_session "migrated-$(date +%Y%m%d-%H%M%S)"
    rm -f "$SESSION_FILE"
    return 0
  fi

  # Create plan directory and move session
  mkdir -p "$plan_dir"

  # Update version and add new fields before moving
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  jq --arg ts "$timestamp" \
    '.version = "2.0" | .plan_id = .plan.name | .agents = [] | .file_claims = [] | .updated_at = $ts' \
    "$SESSION_FILE" > "$plan_session"

  # Archive the original global session
  archive_session "pre-migration-$plan_name"
  rm -f "$SESSION_FILE"

  echo "Migrated global session to plan-scoped: $plan_name" >&2
  echo "$plan_session"
}

# =============================================================================
# Worktree Detection and Multitask Session Functions
# =============================================================================

# Multitask session file name
MULTITASK_SESSION_FILE="multitask-session.json"

# Check if running in a git worktree
# Returns 0 (true) if in worktree, 1 (false) if in main repo
# Usage: is_worktree
is_worktree() {
  local worktree_root=$(git rev-parse --show-toplevel 2>/dev/null)
  local main_repo=$(git worktree list 2>/dev/null | head -1 | awk '{print $1}')

  if [[ -z "$worktree_root" || -z "$main_repo" ]]; then
    return 1  # Not in a git repo or worktree detection failed
  fi

  [[ "$worktree_root" != "$main_repo" ]]
}

# Get the main repository root path
# Works whether running in main repo or a worktree
# Usage: get_main_repo_root
get_main_repo_root() {
  git worktree list 2>/dev/null | head -1 | awk '{print $1}'
}

# Get the multitask session file path (always in main repo)
# Usage: get_multitask_session_file
get_multitask_session_file() {
  local main_repo=$(get_main_repo_root)
  if [[ -n "$main_repo" ]]; then
    echo "$main_repo/$STATE_DIR/$MULTITASK_SESSION_FILE"
  else
    echo "$STATE_DIR/$MULTITASK_SESSION_FILE"
  fi
}

# Register this instance with the multitask session
# Appends to existing instances array instead of overwriting
# Usage: register_multitask_instance <plan_name> <branch> <worktree_path>
register_multitask_instance() {
  local plan_name=$1
  local branch=$2
  local worktree_path=${3:-$(git rev-parse --show-toplevel 2>/dev/null)}
  local session_file=$(get_multitask_session_file)
  local main_repo=$(get_main_repo_root)
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  local pid=$$

  # Ensure state directory exists in main repo
  mkdir -p "$main_repo/$STATE_DIR"

  # Create session file if it doesn't exist
  if [[ ! -f "$session_file" ]]; then
    cat > "$session_file" << EOF
{
  "session_id": "multitask-$(date +%Y-%m-%d-%H%M%S)",
  "started": "$timestamp",
  "instances": []
}
EOF
  fi

  # Check if this instance (by PID or worktree) already exists
  local existing=$(jq --arg wt "$worktree_path" '.instances[] | select(.worktree == $wt)' "$session_file" 2>/dev/null)

  if [[ -n "$existing" ]]; then
    # Update existing instance
    jq --arg wt "$worktree_path" \
       --arg ts "$timestamp" \
       --arg pid "$pid" \
       --arg status "running" \
       '(.instances[] | select(.worktree == $wt)) |= . + {pid: ($pid | tonumber), status: $status, updated: $ts}' \
       "$session_file" > "${session_file}.tmp" && mv "${session_file}.tmp" "$session_file"
  else
    # Append new instance
    local instance_num=$(jq '.instances | length + 1' "$session_file")
    local instance_json=$(cat <<EOF
{
  "instance_num": $instance_num,
  "worktree": "$worktree_path",
  "branch": "$branch",
  "plan": "$plan_name",
  "pid": $pid,
  "status": "running",
  "started": "$timestamp",
  "updated": "$timestamp"
}
EOF
)
    jq --argjson instance "$instance_json" '.instances += [$instance]' \
       "$session_file" > "${session_file}.tmp" && mv "${session_file}.tmp" "$session_file"
  fi

  echo "Registered instance with multitask session (PID: $pid)" >&2
}

# Update this instance's status in the multitask session
# Usage: update_multitask_instance_status <status>
# status: "running" | "completed" | "stopped" | "crashed"
update_multitask_instance_status() {
  local status=$1
  local session_file=$(get_multitask_session_file)
  local worktree_path=$(git rev-parse --show-toplevel 2>/dev/null)
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  local pid=$$

  if [[ ! -f "$session_file" ]]; then
    return 0  # No session file, nothing to update
  fi

  # Update by worktree path (more reliable than PID which may have changed)
  jq --arg wt "$worktree_path" \
     --arg ts "$timestamp" \
     --arg status "$status" \
     --arg pid "$pid" \
     '(.instances[] | select(.worktree == $wt)) |= . + {status: $status, updated: $ts, pid: ($pid | tonumber)}' \
     "$session_file" > "${session_file}.tmp" && mv "${session_file}.tmp" "$session_file"
}

# Get current worktree's instance info from multitask session
# Usage: get_multitask_instance_info
get_multitask_instance_info() {
  local session_file=$(get_multitask_session_file)
  local worktree_path=$(git rev-parse --show-toplevel 2>/dev/null)

  if [[ ! -f "$session_file" ]]; then
    echo "{}"
    return 1
  fi

  jq --arg wt "$worktree_path" '.instances[] | select(.worktree == $wt)' "$session_file" 2>/dev/null || echo "{}"
}

# =============================================================================
# Legacy Functions (Backwards Compatibility)
# =============================================================================

# Migrate legacy .ai/ state to .claude/state/
# Called automatically when this script is sourced
migrate_legacy_state() {
  # Only migrate if .ai exists and .claude/state doesn't
  if [[ -d ".ai" && ! -d "$STATE_DIR" ]]; then
    mkdir -p "$STATE_DIR"

    # Migrate files if they exist
    [[ -f ".ai/session.json" ]] && mv ".ai/session.json" "$STATE_DIR/"
    [[ -d ".ai/sessions" ]] && mv ".ai/sessions" "$STATE_DIR/"
    [[ -f ".ai/progress.txt" ]] && mv ".ai/progress.txt" "$STATE_DIR/"
    [[ -f ".ai/.pause" ]] && mv ".ai/.pause" "$STATE_DIR/"
    [[ -f ".ai/.quit" ]] && mv ".ai/.quit" "$STATE_DIR/"
    [[ -f ".ai/.stop-loop" ]] && mv ".ai/.stop-loop" "$STATE_DIR/"

    # Try to remove empty .ai directory
    rmdir ".ai" 2>/dev/null || true

    echo "Migrated runtime state from .ai/ to $STATE_DIR/"
  fi
}

# Run migration on source
migrate_legacy_state

# Initialize session state
# Usage: init_session <plan_path> <mode>
#   plan_path: Path to the PRD JSON file
#   mode: "autonomous" or "attended"
init_session() {
  local plan_path=$1
  local mode=${2:-"autonomous"}
  local plan_name=$(basename "$plan_path" .json)
  local branch=$(git branch --show-current)
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Create state directory if needed
  mkdir -p "$STATE_DIR"

  # Get total stories from plan
  local total_stories=$(jq '.stories | length' "$plan_path" 2>/dev/null || echo "0")

  # Create initial session state
  cat > "$SESSION_FILE" << EOF
{
  "version": "1.0",
  "created_at": "$timestamp",
  "updated_at": "$timestamp",
  "status": "running",
  "plan": {
    "path": "$plan_path",
    "name": "$plan_name",
    "branch": "$branch"
  },
  "progress": {
    "total_stories": $total_stories,
    "completed": 0,
    "current_story": null,
    "current_iteration": 0
  },
  "git": {
    "branch": "$branch",
    "head_commit": "$(git rev-parse --short HEAD 2>/dev/null || echo 'none')",
    "modified_files": []
  },
  "execution": {
    "mode": "$mode",
    "pid": $$,
    "start_time": "$timestamp"
  },
  "activity_log": []
}
EOF
}

# Update session state
# Usage: update_session <field_path> <value>
#   field_path: jq-style path (e.g., ".progress.completed")
#   value: New value
# Note: Automatically uses plan-scoped session if CLAUDE_PLAN is set
update_session() {
  local field_path=$1
  local value=$2
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  local session_file=$(get_active_session_file)

  if [[ ! -f "$session_file" ]]; then
    echo "Error: Session file not found at $session_file" >&2
    return 1
  fi

  # Update the field and timestamp atomically
  jq --arg ts "$timestamp" --arg val "$value" \
    "$field_path = \$val | .updated_at = \$ts" \
    "$session_file" > "$session_file.tmp" && \
    mv "$session_file.tmp" "$session_file"
}

# Update session with JSON object
# Usage: update_session_json <field_path> <json_string>
# Note: Automatically uses plan-scoped session if CLAUDE_PLAN is set
update_session_json() {
  local field_path=$1
  local json_value=$2
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  local session_file=$(get_active_session_file)

  if [[ ! -f "$session_file" ]]; then
    echo "Error: Session file not found at $session_file" >&2
    return 1
  fi

  # Update with JSON value
  jq --arg ts "$timestamp" --argjson val "$json_value" \
    "$field_path = \$val | .updated_at = \$ts" \
    "$session_file" > "$session_file.tmp" && \
    mv "$session_file.tmp" "$session_file"
}

# Add activity log entry
# Usage: add_activity <type> <story_id> <message>
#   type: "story_started" | "story_completed" | "error" | "pause" | "resume"
# Note: Automatically uses plan-scoped session if CLAUDE_PLAN is set
add_activity() {
  local type=$1
  local story=$2
  local message=$3
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  local session_file=$(get_active_session_file)

  if [[ ! -f "$session_file" ]]; then
    echo "Error: Session file not found at $session_file" >&2
    return 1
  fi

  local activity=$(jq -n \
    --arg ts "$timestamp" \
    --arg t "$type" \
    --arg s "$story" \
    --arg m "$message" \
    '{timestamp: $ts, type: $t, story: $s, message: $m}')

  jq --argjson entry "$activity" --arg ts "$timestamp" \
    '.activity_log += [$entry] | .updated_at = $ts' \
    "$session_file" > "$session_file.tmp" && \
    mv "$session_file.tmp" "$session_file"
}

# Update progress
# Usage: update_progress <completed> <current_story> <iteration>
# Note: Automatically uses plan-scoped session if CLAUDE_PLAN is set
update_progress() {
  local completed=$1
  local current_story=$2
  local iteration=$3
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  local session_file=$(get_active_session_file)

  if [[ ! -f "$session_file" ]]; then
    echo "Error: Session file not found at $session_file" >&2
    return 1
  fi

  jq --arg ts "$timestamp" \
     --arg completed "$completed" \
     --arg story "$current_story" \
     --arg iter "$iteration" \
    '.progress.completed = ($completed | tonumber) |
     .progress.current_story = $story |
     .progress.current_iteration = ($iter | tonumber) |
     .updated_at = $ts' \
    "$session_file" > "$session_file.tmp" && \
    mv "$session_file.tmp" "$session_file"
}

# Update git status in session
# Note: Automatically uses plan-scoped session if CLAUDE_PLAN is set
update_git_status() {
  local branch=$(git branch --show-current)
  local head=$(git rev-parse --short HEAD 2>/dev/null || echo 'none')
  local modified=$(git status --short | awk '{print $2}' | jq -R . | jq -s .)
  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  local session_file=$(get_active_session_file)

  if [[ ! -f "$session_file" ]]; then
    echo "Error: Session file not found at $session_file" >&2
    return 1
  fi

  jq --arg ts "$timestamp" \
     --arg branch "$branch" \
     --arg head "$head" \
     --argjson modified "$modified" \
    '.git.branch = $branch |
     .git.head_commit = $head |
     .git.modified_files = $modified |
     .updated_at = $ts' \
    "$session_file" > "$session_file.tmp" && \
    mv "$session_file.tmp" "$session_file"
}

# Mark session as complete
# Also releases file claims for the plan (multi-agent coordination)
complete_session() {
  # Get plan name before updating status
  local plan_name=$(get_session_field ".plan.name")

  update_session ".status" "complete"
  add_activity "complete" "" "All stories completed"

  # Release file claims for this plan (if file-claims.sh is available)
  if [[ -n "$plan_name" ]]; then
    local claims_lib="$SCRIPT_DIR/../hooks/lib/file-claims.sh"
    if [[ -f "$claims_lib" ]]; then
      source "$claims_lib"
      release_plan_claims "$plan_name"
      echo "Released file claims for plan: $plan_name" >&2
    fi
  fi
}

# Mark plan-scoped session as complete
# Usage: complete_plan_session <plan_name>
complete_plan_session() {
  local plan_name=$1
  local session_file=$(get_plan_session_file "$plan_name")

  if [[ ! -f "$session_file" ]]; then
    echo "Error: Session file not found for plan: $plan_name" >&2
    return 1
  fi

  local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Update session status
  jq --arg ts "$timestamp" \
    '.status = "complete" | .updated_at = $ts' \
    "$session_file" > "$session_file.tmp" && \
    mv "$session_file.tmp" "$session_file"

  # Release file claims for this plan
  local claims_lib="$SCRIPT_DIR/../hooks/lib/file-claims.sh"
  if [[ -f "$claims_lib" ]]; then
    source "$claims_lib"
    release_plan_claims "$plan_name"
    echo "Released file claims for plan: $plan_name" >&2
  fi
}

# Mark session as crashed
crash_session() {
  update_session ".status" "crashed"
  add_activity "error" "" "Session interrupted"
}

# Archive current session
# Usage: archive_session [name]
# Note: Automatically uses plan-scoped session if CLAUDE_PLAN is set
archive_session() {
  local name=${1:-$(date +"%Y%m%d-%H%M%S")}
  local session_file=$(get_active_session_file)

  if [[ ! -f "$session_file" ]]; then
    echo "Error: No session to archive" >&2
    return 1
  fi

  mkdir -p "$SESSION_ARCHIVE_DIR"
  cp "$session_file" "$SESSION_ARCHIVE_DIR/session-$name.json"
  echo "$SESSION_ARCHIVE_DIR/session-$name.json"
}

# Check if session exists
# Note: Automatically uses plan-scoped session if CLAUDE_PLAN is set
has_active_session() {
  local session_file=$(get_active_session_file)
  [[ -f "$session_file" ]]
}

# Get session field value
# Usage: get_session_field <field_path>
# Note: Automatically uses plan-scoped session if CLAUDE_PLAN is set
get_session_field() {
  local field_path=$1
  local session_file=$(get_active_session_file)

  if [[ ! -f "$session_file" ]]; then
    echo ""
    return 1
  fi

  jq -r "$field_path // empty" "$session_file"
}

# Check if session was interrupted (status != complete/running)
# Note: Automatically uses plan-scoped session if CLAUDE_PLAN is set
is_session_interrupted() {
  local session_file=$(get_active_session_file)

  if [[ ! -f "$session_file" ]]; then
    return 1
  fi

  local status=$(get_session_field ".status")
  [[ "$status" != "running" && "$status" != "complete" ]]
}

# Pause session
pause_session() {
  touch "$PAUSE_FILE"
  update_session ".status" "paused"
  add_activity "pause" "" "Session paused by user"
}

# Resume session
resume_session() {
  rm -f "$PAUSE_FILE"
  update_session ".status" "running"
  add_activity "resume" "" "Session resumed"
}

# Check if session is paused
is_paused() {
  [[ -f "$PAUSE_FILE" ]]
}

# Display session summary
# Note: Automatically uses plan-scoped session if CLAUDE_PLAN is set
show_session_summary() {
  local session_file=$(get_active_session_file)

  if [[ ! -f "$session_file" ]]; then
    echo "No active session"
    return 1
  fi

  echo "=== Session Summary ==="
  echo "Status: $(get_session_field '.status')"
  echo "Plan: $(get_session_field '.plan.name')"
  echo "Branch: $(get_session_field '.plan.branch')"
  echo "Progress: $(get_session_field '.progress.completed')/$(get_session_field '.progress.total_stories')"
  echo "Current Story: $(get_session_field '.progress.current_story')"
  echo "Iteration: $(get_session_field '.progress.current_iteration')"
  echo "Started: $(get_session_field '.execution.start_time')"
  echo "Updated: $(get_session_field '.updated_at')"
}
