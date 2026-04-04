#!/usr/bin/env bash
#
# pipeline.sh - Graph-based pipeline orchestration
#
# Executes a pipeline definition (JSON) as a DAG of tasks,
# with parallel dispatch, checkpointing, and resumability.
#
# Usage: ./scripts/pipeline.sh [OPTIONS] <pipeline.json>
#
# Options:
#   --resume <id>          Resume a paused/failed pipeline
#   --dry-run              Validate and show execution order, don't execute
#   --events               Write NDJSON event stream
#   --web-viewer           Update state for web viewer integration
#   --max-parallel=N       Max concurrent nodes (default: 5)
#   --timeout=N            Global timeout in seconds (0 = no timeout)
#   --list                 List all pipeline state files
#   --status <id>          Show status of a specific pipeline
#   --cancel <id>          Cancel a running pipeline
#
# Examples:
#   ./scripts/pipeline.sh docs/plans/deploy.pipeline.json
#   ./scripts/pipeline.sh --resume deploy-feature
#   ./scripts/pipeline.sh --dry-run docs/plans/ci.pipeline.json
#   ./scripts/pipeline.sh --events --web-viewer docs/plans/release.pipeline.json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/graph.sh"

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

# ===== Configuration =====

STATE_DIR=".claude/state"
MAX_PARALLEL="${MAX_PARALLEL:-5}"
EVENTS_ENABLED=false
WEB_VIEWER_ENABLED=false
DRY_RUN=false
GLOBAL_TIMEOUT=0
RESUME_ID=""
PIPELINE_FILE=""

# Shared logging with pipeline prefix
LOG_PREFIX="[pipeline]"
source "$SCRIPT_DIR/lib/logging.sh"

# ===== State Management Functions =====

# Initialize pipeline state file from a pipeline definition.
# Creates .claude/state/pipeline-{id}.json with all nodes in pending state.
init_pipeline_state() {
  local pipeline_file=$1
  local pipeline_id
  pipeline_id=$(jq -r '.pipeline' "$pipeline_file")

  local state_file="$STATE_DIR/pipeline-${pipeline_id}.json"
  mkdir -p "$STATE_DIR"

  # Compute topo order and parallel groups
  local topo_order parallel_groups
  topo_order=$(topo_sort "$pipeline_file" | jq -R . | jq -s .)
  parallel_groups=$(get_parallel_groups "$pipeline_file")

  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Build the state file from the definition
  jq --argjson order "$topo_order" \
     --argjson groups "$parallel_groups" \
     --arg now "$now" \
     --arg def_path "$pipeline_file" '
    {
      version: "1.0",
      pipeline_id: .pipeline,
      definition_path: $def_path,
      status: "pending",
      created_at: $now,
      updated_at: $now,
      started_at: null,
      completed_at: null,
      execution_order: $order,
      parallel_groups: $groups,
      env: (.env // {}),
      nodes: (
        .nodes | map({
          key: .id,
          value: {
            id: .id,
            type: .type,
            name: (.name // .id),
            status: "pending",
            backend: (.backend // "shell"),
            command: (.command // null),
            depends: (.depends // []),
            condition: (.condition // {}),
            timeout: (.timeout // 0),
            retry: (.retry // {max_attempts: 1, delay_seconds: 5}),
            env: (.env // {}),
            plan_path: (.plan_path // null),
            prompt: (.prompt // null),
            started_at: null,
            completed_at: null,
            exit_code: null,
            pid: null,
            attempt: 0,
            log_file: null,
            runtime_seconds: 0,
            error: null
          }
        }) | from_entries
      ),
      checkpoint: {
        saved_at: $now,
        completed_nodes: [],
        failed_nodes: [],
        skipped_nodes: []
      }
    }
  ' "$pipeline_file" > "${state_file}.tmp" && mv "${state_file}.tmp" "$state_file"

  echo "$state_file"
}

# Update pipeline-level status.
update_pipeline_status() {
  local state_file=$1
  local new_status=$2
  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  jq --arg status "$new_status" --arg now "$now" '
    .status = $status |
    .updated_at = $now |
    if $status == "running" and .started_at == null then .started_at = $now else . end |
    if ($status == "completed" or $status == "failed") then .completed_at = $now else . end
  ' "$state_file" > "${state_file}.tmp" && mv "${state_file}.tmp" "$state_file"
}

# Update a node's status with timestamp.
update_node_status() {
  local state_file=$1
  local node_id=$2
  local new_status=$3
  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  jq --arg id "$node_id" --arg status "$new_status" --arg now "$now" '
    .nodes[$id].status = $status |
    .updated_at = $now
  ' "$state_file" > "${state_file}.tmp" && mv "${state_file}.tmp" "$state_file"
}

# Mark a node as queued (optionally with attempt number for retries).
mark_node_queued() {
  local state_file=$1
  local node_id=$2
  local attempt=${3:-1}
  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  jq --arg id "$node_id" --arg now "$now" --argjson attempt "$attempt" '
    .nodes[$id].status = "queued" |
    .nodes[$id].attempt = $attempt |
    .updated_at = $now
  ' "$state_file" > "${state_file}.tmp" && mv "${state_file}.tmp" "$state_file"
}

# Mark a node as running with PID and log file.
mark_node_running() {
  local state_file=$1
  local node_id=$2
  local pid=$3
  local log_file=$4
  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  jq --arg id "$node_id" --arg now "$now" \
     --argjson pid "$pid" --arg log "$log_file" '
    .nodes[$id].status = "running" |
    .nodes[$id].started_at = $now |
    .nodes[$id].pid = $pid |
    .nodes[$id].log_file = $log |
    .updated_at = $now
  ' "$state_file" > "${state_file}.tmp" && mv "${state_file}.tmp" "$state_file"
}

# Mark a node as completed.
mark_node_completed() {
  local state_file=$1
  local node_id=$2
  local exit_code=$3
  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  jq --arg id "$node_id" --arg now "$now" --argjson ec "$exit_code" '
    .nodes[$id].status = "completed" |
    .nodes[$id].completed_at = $now |
    .nodes[$id].exit_code = $ec |
    .nodes[$id].pid = null |
    .updated_at = $now
  ' "$state_file" > "${state_file}.tmp" && mv "${state_file}.tmp" "$state_file"
}

# Mark a node as failed.
mark_node_failed() {
  local state_file=$1
  local node_id=$2
  local exit_code=$3
  local error_msg=${4:-""}
  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  jq --arg id "$node_id" --arg now "$now" \
     --argjson ec "$exit_code" --arg err "$error_msg" '
    .nodes[$id].status = "failed" |
    .nodes[$id].completed_at = $now |
    .nodes[$id].exit_code = $ec |
    .nodes[$id].error = (if $err == "" then null else $err end) |
    .nodes[$id].pid = null |
    .updated_at = $now
  ' "$state_file" > "${state_file}.tmp" && mv "${state_file}.tmp" "$state_file"
}

# Mark a node as skipped (condition not met).
mark_node_skipped() {
  local state_file=$1
  local node_id=$2
  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  jq --arg id "$node_id" --arg now "$now" '
    .nodes[$id].status = "skipped" |
    .nodes[$id].completed_at = $now |
    .updated_at = $now
  ' "$state_file" > "${state_file}.tmp" && mv "${state_file}.tmp" "$state_file"
}

# Update a node's runtime_seconds (called during monitoring).
update_node_runtime() {
  local state_file=$1
  local node_id=$2
  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  jq --arg id "$node_id" --arg now "$now" '
    .nodes[$id] as $node |
    if $node.started_at then
      (($now | fromdateiso8601) - ($node.started_at | fromdateiso8601)) as $runtime |
      .nodes[$id].runtime_seconds = $runtime |
      .updated_at = $now
    else . end
  ' "$state_file" > "${state_file}.tmp" && mv "${state_file}.tmp" "$state_file"
}

# Save checkpoint (record terminal node states).
save_checkpoint() {
  local state_file=$1
  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  jq --arg now "$now" '
    .checkpoint = {
      saved_at: $now,
      completed_nodes: [.nodes | to_entries[] | select(.value.status == "completed") | .key],
      failed_nodes: [.nodes | to_entries[] | select(.value.status == "failed") | .key],
      skipped_nodes: [.nodes | to_entries[] | select(.value.status == "skipped") | .key]
    } |
    .updated_at = $now
  ' "$state_file" > "${state_file}.tmp" && mv "${state_file}.tmp" "$state_file"
}

# Check if pipeline is complete (all nodes in terminal state).
is_pipeline_complete() {
  local state_file=$1
  local non_terminal
  non_terminal=$(jq '[.nodes | to_entries[] | select(.value.status | IN("pending","queued","running"))] | length' "$state_file")
  [[ "$non_terminal" -eq 0 ]]
}

# ===== NDJSON Event Stream =====

# Emit an event to the NDJSON stream.
emit_event() {
  [[ "$EVENTS_ENABLED" != "true" ]] && return 0

  local state_file=$1
  local event_type=$2
  local node_id=${3:-}
  local data_json=${4:-"{}"}
  local pipeline_id
  pipeline_id=$(jq -r '.pipeline_id' "$state_file")
  local events_file="${state_file%.json}.events.ndjson"
  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  local event_json
  if [[ -n "$node_id" ]]; then
    event_json=$(jq -nc \
      --arg ts "$now" \
      --arg pid "$pipeline_id" \
      --arg evt "$event_type" \
      --arg nid "$node_id" \
      --argjson data "$data_json" \
      '{timestamp:$ts, pipeline_id:$pid, event:$evt, node_id:$nid, data:$data}')
  else
    event_json=$(jq -nc \
      --arg ts "$now" \
      --arg pid "$pipeline_id" \
      --arg evt "$event_type" \
      --argjson data "$data_json" \
      '{timestamp:$ts, pipeline_id:$pid, event:$evt, data:$data}')
  fi

  echo "$event_json" >> "$events_file"
}

# ===== Backend Dispatch =====

# Query ACS for context relevant to a pipeline node.
# Sets ACS_NODE_CONTEXT variable with formatted context string.
query_acs_for_node() {
  local node_id=$1
  local node_name=$2
  local command=$3

  ACS_NODE_CONTEXT=""
  if [[ "$ACS_ENABLED" != "true" ]] || ! acs_is_available; then
    return 0
  fi

  local query_text="${node_name}: ${command}"
  local acs_result
  acs_result=$(acs_query "$query_text" 5 1500 2>/dev/null) || true
  local context
  context=$(echo "$acs_result" | acs_extract_context 2>/dev/null) || true

  if [[ -n "$context" ]]; then
    ACS_NODE_CONTEXT="$context"
  fi
}

# Execute a node using its configured backend.
# Returns the PID of the spawned process.
execute_node() {
  local state_file=$1
  local node_id=$2

  local backend command log_file pipeline_id node_name
  backend=$(jq -r --arg id "$node_id" '.nodes[$id].backend' "$state_file")
  command=$(jq -r --arg id "$node_id" '.nodes[$id].command // ""' "$state_file")
  node_name=$(jq -r --arg id "$node_id" '.nodes[$id].name // $id' "$state_file")
  pipeline_id=$(jq -r '.pipeline_id' "$state_file")
  log_file="$STATE_DIR/pipeline-${pipeline_id}-node-${node_id}.log"

  # Query ACS for relevant context (non-blocking, optional)
  query_acs_for_node "$node_id" "$node_name" "$command"

  # Merge pipeline env + node env
  local env_json
  env_json=$(jq --arg id "$node_id" '
    (.env // {}) * (.nodes[$id].env // {})
  ' "$state_file")

  # Inject ACS context as environment variable if available
  if [[ -n "${ACS_NODE_CONTEXT:-}" ]]; then
    env_json=$(echo "$env_json" | jq --arg ctx "$ACS_NODE_CONTEXT" '. + {ACS_CONTEXT: $ctx}')
  fi

  local pid
  case "$backend" in
    shell)
      pid=$(dispatch_shell "$command" "$log_file" "$env_json")
      ;;
    claude-code)
    # Prepend ACS context to AI prompts for cross-project awareness
      local cc_command="$command"
      if [[ -n "${ACS_NODE_CONTEXT:-}" ]]; then
        cc_command="[Cross-project context from ACS:]
${ACS_NODE_CONTEXT}

[Task:]
${command}"
      fi
      pid=$(dispatch_claude_code "$cc_command" "$log_file" "$env_json")
      ;;
    manual)
      pid=$(dispatch_manual "$node_id" "$log_file" "$state_file")
      ;;
    *)
      log_error "Unknown backend: $backend for node $node_id"
      return 1
      ;;
  esac

  echo "$pid"
}

# Shell backend: direct bash execution.
dispatch_shell() {
  local command=$1
  local log_file=$2
  local env_json=$3

  (
    _log_file="$log_file"
    trap 'echo "$_exit_code" > "${_log_file}.exit"' EXIT
    _exit_code=1

    # Export environment variables
    while IFS='=' read -r key value; do
      [[ -n "$key" ]] && export "$key=$value"
    done < <(echo "$env_json" | jq -r 'to_entries[] | "\(.key)=\(.value)"' 2>/dev/null)

    set +e
    eval "$command" >> "$log_file" 2>&1
    _exit_code=$?
  ) &

  echo $!
}

# AI backend: spawn configured AI instance.
dispatch_claude_code() {
  local command=$1
  local log_file=$2
  local env_json=$3

  ai_provider_ensure || return 1

  (
    _log_file="$log_file"
    trap 'echo "$_exit_code" > "${_log_file}.exit"' EXIT
    _exit_code=1

    while IFS='=' read -r key value; do
      [[ -n "$key" ]] && export "$key=$value"
    done < <(echo "$env_json" | jq -r 'to_entries[] | "\(.key)=\(.value)"' 2>/dev/null)

    set +e
    ai_provider_command run "$command" "$AI_PROVIDER_RUN_PREFIX"
    "${AI_PROVIDER_COMMAND[@]}" >> "$log_file" 2>&1
    _exit_code=$?
  ) &

  echo $!
}

# Manual backend: wait for approval via file signal.
dispatch_manual() {
  local node_id=$1
  local log_file=$2
  local state_file=$3
  local approval_file="$STATE_DIR/.gate-${node_id}"
  local prompt_text
  prompt_text=$(jq -r --arg id "$node_id" '.nodes[$id].prompt // "Approve this gate?"' "$state_file")

  echo "=== GATE: $node_id ===" > "$log_file"
  echo "Prompt: $prompt_text" >> "$log_file"
  echo "Waiting for approval..." >> "$log_file"
  echo "" >> "$log_file"
  echo "To approve: echo 'approved' > $approval_file" >> "$log_file"
  echo "To reject:  echo 'rejected' > $approval_file" >> "$log_file"

  (
    while true; do
      if [[ -f "$approval_file" ]]; then
        local decision
        decision=$(cat "$approval_file")
        rm -f "$approval_file"
        if [[ "$decision" == "approved" ]]; then
          echo "Gate approved at $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "$log_file"
          echo "0" > "${log_file}.exit"
          exit 0
        else
          echo "Gate rejected at $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "$log_file"
          echo "1" > "${log_file}.exit"
          exit 1
        fi
      fi
      sleep 2
    done
  ) &

  echo $!
}

# ===== Running Node Monitoring =====

# Check running nodes for completion.
# Reads exit codes, updates state, handles retries.
check_running_nodes() {
  local state_file=$1

  local running_nodes
  running_nodes=$(jq -r '.nodes | to_entries[] | select(.value.status == "running") | .key' "$state_file")

  for node_id in $running_nodes; do
    local pid log_file
    pid=$(jq -r --arg id "$node_id" '.nodes[$id].pid' "$state_file")
    log_file=$(jq -r --arg id "$node_id" '.nodes[$id].log_file' "$state_file")

    if ! ps -p "$pid" > /dev/null 2>&1; then
      # Process exited
      local exit_code="-1"
      if [[ -f "${log_file}.exit" ]]; then
        exit_code=$(cat "${log_file}.exit")
        rm -f "${log_file}.exit"
      fi

      if [[ "$exit_code" -eq 0 ]]; then
        mark_node_completed "$state_file" "$node_id" "$exit_code"
        emit_event "$state_file" "node_completed" "$node_id" \
          "$(jq -nc --argjson ec "$exit_code" '{exit_code:$ec}')"
        log_success "Node $node_id completed"
      else
        # Check retry
        local attempt max_attempts
        attempt=$(jq -r --arg id "$node_id" '.nodes[$id].attempt' "$state_file")
        max_attempts=$(jq -r --arg id "$node_id" '.nodes[$id].retry.max_attempts // 1' "$state_file")

        if (( attempt < max_attempts )); then
          local next_attempt=$((attempt + 1))
          log_warn "Node $node_id failed (attempt $attempt/$max_attempts), retrying..."
          mark_node_queued "$state_file" "$node_id" "$next_attempt"
          emit_event "$state_file" "node_retrying" "$node_id" \
            "$(jq -nc --argjson a "$next_attempt" '{attempt:$a}')"
        else
          mark_node_failed "$state_file" "$node_id" "$exit_code" "Exit code: $exit_code"
          emit_event "$state_file" "node_failed" "$node_id" \
            "$(jq -nc --argjson ec "$exit_code" '{exit_code:$ec}')"
          log_error "Node $node_id failed (exit code: $exit_code)"
        fi
      fi

      save_checkpoint "$state_file"
    else
      # Process still running - update runtime
      update_node_runtime "$state_file" "$node_id"
    fi
  done
}

# ===== Dispatch Node =====

# Dispatch a single node: mark queued → running, spawn backend.
dispatch_node() {
  local state_file=$1
  local node_id=$2

  mark_node_queued "$state_file" "$node_id" 1
  emit_event "$state_file" "node_queued" "$node_id"

  local pid log_file pipeline_id
  pipeline_id=$(jq -r '.pipeline_id' "$state_file")
  log_file="$STATE_DIR/pipeline-${pipeline_id}-node-${node_id}.log"

  pid=$(execute_node "$state_file" "$node_id")
  mark_node_running "$state_file" "$node_id" "$pid" "$log_file"
  emit_event "$state_file" "node_started" "$node_id" \
    "$(jq -nc --argjson p "$pid" '{pid:$p}')"

  log_info "Dispatched node ${CYAN}$node_id${NC} (PID: $pid)"
}

# ===== Main Execution Loop =====

# Run the pipeline to completion.
run_pipeline() {
  local state_file=$1

  local node_count
  node_count=$(jq '.nodes | length' "$state_file")
  emit_event "$state_file" "pipeline_started" "" \
    "$(jq -nc --argjson n "$node_count" '{node_count:$n}')"

  update_pipeline_status "$state_file" "running"
  log_info "Pipeline started ($node_count nodes)"

  while true; do
    # Check for stop signal
    if [[ -f "$STATE_DIR/.stop-pipeline" ]]; then
      rm -f "$STATE_DIR/.stop-pipeline"
      update_pipeline_status "$state_file" "paused"
      emit_event "$state_file" "pipeline_paused"
      log_warn "Pipeline paused by stop signal"
      save_checkpoint "$state_file"
      return 0
    fi

    # Check running nodes for completion
    check_running_nodes "$state_file"

    # Get currently running count
    local running_count
    running_count=$(jq '[.nodes | to_entries[] | select(.value.status == "running")] | length' "$state_file")

    # Get runnable nodes (pending with all deps satisfied)
    local runnable
    runnable=$(get_runnable_nodes "$state_file")

    # Dispatch runnable nodes up to MAX_PARALLEL
    local dispatched=0
    for node_id in $runnable; do
      if (( running_count + dispatched >= MAX_PARALLEL )); then
        break
      fi

      # Check conditions (on_success, on_failure)
      if ! check_node_condition "$state_file" "$node_id"; then
        mark_node_skipped "$state_file" "$node_id"
        emit_event "$state_file" "node_skipped" "$node_id"
        log_info "Node $node_id skipped (condition not met)"
        continue
      fi

      dispatch_node "$state_file" "$node_id"
      dispatched=$((dispatched + 1))
    done

    # Check if pipeline is complete
    if is_pipeline_complete "$state_file"; then
      local fail_count
      fail_count=$(jq '[.nodes | to_entries[] | select(.value.status == "failed")] | length' "$state_file")

      if [[ "$fail_count" -gt 0 ]]; then
        update_pipeline_status "$state_file" "failed"
        emit_event "$state_file" "pipeline_failed" "" \
          "$(jq -nc --argjson f "$fail_count" '{failed_count:$f}')"
        log_error "Pipeline failed ($fail_count node(s) failed)"
      else
        update_pipeline_status "$state_file" "completed"
        emit_event "$state_file" "pipeline_completed"
        log_success "Pipeline completed successfully!"
      fi
      save_checkpoint "$state_file"
      return 0
    fi

    # Deadlock detection: nothing runnable and nothing running
    if [[ -z "$runnable" && "$running_count" -eq 0 ]]; then
      log_error "Pipeline deadlocked: no runnable or running nodes"
      update_pipeline_status "$state_file" "failed"
      emit_event "$state_file" "pipeline_failed" "" '{"reason":"deadlock"}'
      save_checkpoint "$state_file"
      return 1
    fi

    # Poll interval
    sleep 2
  done
}

# ===== Resume =====

# Restore pipeline from checkpoint for resume.
restore_from_checkpoint() {
  local state_file=$1

  # Reset any "running" nodes to "queued" (process died mid-execution)
  local running_nodes
  running_nodes=$(jq -r '.nodes | to_entries[] | select(.value.status == "running") | .key' "$state_file")

  for node_id in $running_nodes; do
    log_warn "Resetting crashed node $node_id to queued"
    update_node_status "$state_file" "$node_id" "pending"
  done

  # Reset any "queued" nodes back to "pending"
  local queued_nodes
  queued_nodes=$(jq -r '.nodes | to_entries[] | select(.value.status == "queued") | .key' "$state_file")

  for node_id in $queued_nodes; do
    update_node_status "$state_file" "$node_id" "pending"
  done

  emit_event "$state_file" "pipeline_resumed"
  log_info "Pipeline restored from checkpoint"
}

# ===== CLI Commands =====

# List all pipeline state files.
cmd_list() {
  local state_files
  state_files=$(find "$STATE_DIR" -name "pipeline-*.json" -not -name "*.events.*" 2>/dev/null | sort)

  if [[ -z "$state_files" ]]; then
    echo "No pipeline runs found."
    return 0
  fi

  printf "%-25s %-12s %-10s %-20s\n" "PIPELINE" "STATUS" "NODES" "UPDATED"
  printf "%-25s %-12s %-10s %-20s\n" "--------" "------" "-----" "-------"

  while IFS= read -r f; do
    local id status node_count updated
    id=$(jq -r '.pipeline_id' "$f")
    status=$(jq -r '.status' "$f")
    node_count=$(jq '.nodes | length' "$f")
    updated=$(jq -r '.updated_at' "$f")
    local completed_count
    completed_count=$(jq '[.nodes | to_entries[] | select(.value.status == "completed")] | length' "$f")
    printf "%-25s %-12s %s/%-7s %-20s\n" "$id" "$status" "$completed_count" "$node_count" "$updated"
  done <<< "$state_files"
}

# Show status of a specific pipeline.
cmd_status() {
  local pipeline_id=$1
  local state_file="$STATE_DIR/pipeline-${pipeline_id}.json"

  if [[ ! -f "$state_file" ]]; then
    log_error "Pipeline not found: $pipeline_id"
    return 1
  fi

  echo ""
  echo -e "${CYAN}Pipeline: $pipeline_id${NC}"
  echo -e "Status:   $(jq -r '.status' "$state_file")"
  echo -e "Created:  $(jq -r '.created_at' "$state_file")"
  echo -e "Updated:  $(jq -r '.updated_at' "$state_file")"
  echo ""

  printf "  %-20s %-12s %-8s %-10s %-8s\n" "NODE" "STATUS" "BACKEND" "EXIT" "RUNTIME"
  printf "  %-20s %-12s %-8s %-10s %-8s\n" "----" "------" "-------" "----" "-------"

  jq -r '
    .execution_order[] as $id |
    .nodes[$id] |
    "  \(.id | .[0:20] | . + (" " * (20 - length)))  \(.status | .[0:12] | . + (" " * (12 - length)))  \(.backend | .[0:8] | . + (" " * (8 - length)))  \(.exit_code // "-" | tostring | .[0:10] | . + (" " * (10 - length)))  \(.runtime_seconds)s"
  ' "$state_file"

  echo ""
}

# Cancel a running pipeline.
cmd_cancel() {
  local pipeline_id=$1
  local stop_file="$STATE_DIR/.stop-pipeline"
  echo "cancel" > "$stop_file"
  log_info "Stop signal sent to pipeline $pipeline_id"
}

# Dry run: validate and show execution plan.
cmd_dry_run() {
  local pipeline_file=$1

  echo ""
  log_info "Validating pipeline..."
  if ! validate_pipeline "$pipeline_file"; then
    log_error "Validation failed"
    return 1
  fi
  log_success "Pipeline is valid"

  echo ""
  echo -e "${CYAN}Execution Order:${NC}"
  local i=1
  while IFS= read -r node_id; do
    local node_type backend command
    node_type=$(jq -r --arg id "$node_id" '.nodes[] | select(.id == $id) | .type' "$pipeline_file")
    backend=$(jq -r --arg id "$node_id" '.nodes[] | select(.id == $id) | .backend // "shell"' "$pipeline_file")
    command=$(jq -r --arg id "$node_id" '.nodes[] | select(.id == $id) | .command // .plan_path // "(gate)"' "$pipeline_file")
    printf "  %2d. %-15s [%s/%s] %s\n" "$i" "$node_id" "$node_type" "$backend" "$command"
    i=$((i + 1))
  done < <(topo_sort "$pipeline_file")

  echo ""
  echo -e "${CYAN}Parallel Groups:${NC}"
  get_parallel_groups "$pipeline_file" | jq -r 'to_entries[] | "  Level \(.key): \(.value | join(", "))"'

  echo ""
  log_success "Dry run complete. Use without --dry-run to execute."
}

# ===== Argument Parsing =====

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --resume)
        RESUME_ID="$2"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --events)
        EVENTS_ENABLED=true
        shift
        ;;
      --web-viewer)
        WEB_VIEWER_ENABLED=true
        shift
        ;;
      --max-parallel=*)
        MAX_PARALLEL="${1#*=}"
        shift
        ;;
      --max-parallel)
        MAX_PARALLEL="$2"
        shift 2
        ;;
      --timeout=*)
        GLOBAL_TIMEOUT="${1#*=}"
        shift
        ;;
      --timeout)
        GLOBAL_TIMEOUT="$2"
        shift 2
        ;;
      --list)
        cmd_list
        exit 0
        ;;
      --status)
        cmd_status "$2"
        exit 0
        ;;
      --cancel)
        cmd_cancel "$2"
        exit 0
        ;;
      --help|-h)
        head -27 "$0" | tail -25
        exit 0
        ;;
      -*)
        log_error "Unknown option: $1"
        exit 1
        ;;
      *)
        PIPELINE_FILE="$1"
        shift
        ;;
    esac
  done
}

# ===== Signal Handling =====

cleanup() {
  log_warn "Received interrupt signal"
  if [[ -n "${CURRENT_STATE_FILE:-}" ]]; then
    # Kill all running node processes
    local running_pids
    running_pids=$(jq -r '.nodes | to_entries[] | select(.value.status == "running") | .value.pid | select(. != null)' "$CURRENT_STATE_FILE" 2>/dev/null)
    for pid in $running_pids; do
      kill "$pid" 2>/dev/null || true
    done
    # Wait briefly then force kill
    sleep 1
    for pid in $running_pids; do
      kill -9 "$pid" 2>/dev/null || true
    done

    update_pipeline_status "$CURRENT_STATE_FILE" "paused"
    save_checkpoint "$CURRENT_STATE_FILE"
    log_info "Pipeline paused. Resume with: pipeline.sh --resume $(jq -r '.pipeline_id' "$CURRENT_STATE_FILE")"
  fi
  exit 130
}

trap cleanup SIGINT SIGTERM

# ===== Main =====

main() {
  parse_args "$@"

  mkdir -p "$STATE_DIR"

  # Resume mode
  if [[ -n "$RESUME_ID" ]]; then
    local state_file="$STATE_DIR/pipeline-${RESUME_ID}.json"
    if [[ ! -f "$state_file" ]]; then
      log_error "Pipeline state not found: $RESUME_ID"
      exit 1
    fi
    local current_status
    current_status=$(jq -r '.status' "$state_file")
    if [[ "$current_status" != "failed" && "$current_status" != "paused" ]]; then
      log_error "Cannot resume pipeline with status: $current_status (must be failed or paused)"
      exit 1
    fi

    CURRENT_STATE_FILE="$state_file"
    restore_from_checkpoint "$state_file"
    run_pipeline "$state_file"
    exit $?
  fi

  # Dry run mode
  if [[ "$DRY_RUN" == "true" ]]; then
    if [[ -z "$PIPELINE_FILE" ]]; then
      log_error "Pipeline file required for dry run"
      exit 1
    fi
    cmd_dry_run "$PIPELINE_FILE"
    exit $?
  fi

  # Normal execution
  if [[ -z "$PIPELINE_FILE" ]]; then
    log_error "Pipeline file required. Usage: pipeline.sh [OPTIONS] <pipeline.json>"
    exit 1
  fi

  if [[ ! -f "$PIPELINE_FILE" ]]; then
    log_error "Pipeline file not found: $PIPELINE_FILE"
    exit 1
  fi

  log_info "Validating pipeline..."
  if ! validate_pipeline "$PIPELINE_FILE"; then
    log_error "Pipeline validation failed"
    exit 1
  fi
  log_success "Pipeline valid"

  local state_file
  state_file=$(init_pipeline_state "$PIPELINE_FILE")
  CURRENT_STATE_FILE="$state_file"

  log_info "State file: $state_file"
  log_info "Max parallel: $MAX_PARALLEL"
  echo ""

  run_pipeline "$state_file"
}

main "$@"
