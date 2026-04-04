#!/usr/bin/env bash
#
# graph.sh - Graph utilities for pipeline execution
#
# Pure functions that operate on pipeline JSON via jq.
# No global state - all state passed as arguments.
#
# Functions:
#   topo_sort <pipeline_file>           - Topological sort (Kahn's algorithm)
#   detect_cycle <pipeline_file>        - Cycle detection (returns 0=clean, 1=cycle)
#   get_parallel_groups <pipeline_file> - Group nodes by execution depth
#   get_runnable_nodes <state_file>     - Nodes ready to dispatch
#   check_node_condition <state_file> <node_id> - Evaluate conditional execution
#   validate_pipeline <pipeline_file>   - Full validation (schema + graph)

# Topological sort using Kahn's algorithm in jq.
# Outputs node IDs in valid execution order (one per line).
# Exits 1 with error message on cycle detection.
topo_sort() {
  local pipeline_file=$1
  jq -r '
    .nodes as $nodes |
    # Build in-degree map: how many deps each node has
    ($nodes | map({key: .id, value: ((.depends // []) | length)}) | from_entries) as $in_deg |
    # Build reverse adjacency: for each dep, which nodes depend on it
    (reduce ($nodes[] | . as $n | (.depends // [])[] | {from: ., to: $n.id}) as $e
      ({}; .[$e.from] = ((.[$e.from] // []) + [$e.to]))) as $adj |
    # Kahn: process queue of zero-in-degree nodes
    {
      queue: [$nodes[] | select((.depends // []) | length == 0) | .id],
      in_deg: $in_deg,
      result: [],
      adj: $adj
    } |
    until(.queue | length == 0;
      .queue[0] as $current |
      .result += [$current] |
      .queue = .queue[1:] |
      reduce (.adj[$current] // [])[] as $neighbor (
        .;
        .in_deg[$neighbor] = (.in_deg[$neighbor] - 1) |
        if .in_deg[$neighbor] == 0 then .queue += [$neighbor] else . end
      )
    ) |
    if (.result | length) != ($nodes | length) then
      "CYCLE_DETECTED: \($nodes | length - (.result | length)) nodes in cycle" | halt_error(1)
    else
      .result[]
    end
  ' "$pipeline_file"
}

# Detect cycles in the dependency graph.
# Returns 0 if no cycle, 1 if cycle found.
# Outputs cycle path on stderr if found.
detect_cycle() {
  local pipeline_file=$1
  local result
  result=$(jq -r '
    .nodes as $nodes |
    ($nodes | map({key: .id, value: ((.depends // []) | length)}) | from_entries) as $in_deg |
    (reduce ($nodes[] | . as $n | (.depends // [])[] | {from: ., to: $n.id}) as $e
      ({}; .[$e.from] = ((.[$e.from] // []) + [$e.to]))) as $adj |
    {
      queue: [$nodes[] | select((.depends // []) | length == 0) | .id],
      in_deg: $in_deg,
      count: 0,
      adj: $adj
    } |
    until(.queue | length == 0;
      .queue[0] as $current |
      .count += 1 |
      .queue = .queue[1:] |
      reduce (.adj[$current] // [])[] as $neighbor (
        .;
        .in_deg[$neighbor] = (.in_deg[$neighbor] - 1) |
        if .in_deg[$neighbor] == 0 then .queue += [$neighbor] else . end
      )
    ) |
    if .count != ($nodes | length) then
      "cycle"
    else
      "clean"
    end
  ' "$pipeline_file" 2>/dev/null)

  if [[ "$result" == "cycle" ]]; then
    echo "Cycle detected in pipeline dependency graph" >&2
    return 1
  fi
  return 0
}

# Get parallel groups: nodes grouped by topological depth.
# Nodes at the same depth with no mutual dependencies can run in parallel.
# Outputs JSON array of arrays (each inner array is a parallel group).
get_parallel_groups() {
  local pipeline_file=$1
  jq '
    .nodes as $nodes |
    # Build dependency lookup: id -> depends[]
    ($nodes | map({key: .id, value: (.depends // [])}) | from_entries) as $deps |
    # Calculate depth iteratively: root=0, others=max(dep_depths)+1
    # Run N passes to propagate depths through the graph
    (reduce range(0; $nodes | length) as $_ (
      # Initialize: root nodes=0, others=-1
      ($nodes | map({key: .id, value: (if (.depends // []) | length == 0 then 0 else -1 end)}) | from_entries);
      # Each pass: try to assign depth to unresolved nodes
      . as $current |
      reduce ($nodes[].id) as $id ($current;
        if .[$id] >= 0 then . else
          # Check if all deps have assigned depths
          ($deps[$id] | map($current[.]) | if any(. == -1) then null else max end) as $max_dep |
          if $max_dep != null then .[$id] = ($max_dep + 1) else . end
        end
      )
    )) as $depths |
    # Group by depth, sorted by depth value
    [$depths | to_entries | group_by(.value) | sort_by(.[0].value)[] | map(.key)]
  ' "$pipeline_file"
}

# Get nodes ready to run: pending nodes with all dependencies completed.
# Takes a pipeline STATE file (not definition).
# Outputs space-separated node IDs.
get_runnable_nodes() {
  local state_file=$1
  jq -r '
    .nodes as $nodes |
    [
      $nodes | to_entries[] |
      select(.value.status == "pending") |
      select(
        if (.value.depends | length) == 0 then true
        else (.value.depends | all(. as $dep | $nodes[$dep].status == "completed"))
        end
      ) |
      .key
    ] | join(" ")
  ' "$state_file"
}

# Check if a node's conditions are met (on_success, on_failure).
# Returns 0 if node should run, 1 if it should be skipped.
check_node_condition() {
  local state_file=$1
  local node_id=$2

  local should_run
  should_run=$(jq -r --arg id "$node_id" '
    .nodes[$id] as $node |
    .nodes as $all_nodes |
    ($node.condition // {}) as $cond |
    if ($cond | length) == 0 then
      "run"
    else
      (
        if ($cond.on_success // []) | length > 0 then
          if ($cond.on_success | all(. as $n | $all_nodes[$n].status == "completed")) then true else false end
        else true end
      ) as $success_ok |
      (
        if ($cond.on_failure // []) | length > 0 then
          if ($cond.on_failure | any(. as $n | $all_nodes[$n].status == "failed")) then true else false end
        else true end
      ) as $failure_ok |
      if ($success_ok and $failure_ok) then "run" else "skip" end
    end
  ' "$state_file")

  [[ "$should_run" == "run" ]]
}

# Validate a pipeline definition file.
# Returns 0 if valid, 1 if invalid (errors on stderr).
validate_pipeline() {
  local pipeline_file=$1
  local errors=0

  # Check file exists and is valid JSON
  if [[ ! -f "$pipeline_file" ]]; then
    echo "Error: Pipeline file not found: $pipeline_file" >&2
    return 1
  fi

  if ! jq empty "$pipeline_file" 2>/dev/null; then
    echo "Error: Invalid JSON in $pipeline_file" >&2
    return 1
  fi

  # Check required top-level fields
  local missing
  missing=$(jq -r '
    [
      (if .pipeline then null else "pipeline" end),
      (if .version then null else "version" end),
      (if .nodes then null else "nodes" end)
    ] | map(select(. != null)) | join(", ")
  ' "$pipeline_file")

  if [[ -n "$missing" ]]; then
    echo "Error: Missing required fields: $missing" >&2
    errors=$((errors + 1))
  fi

  # Check nodes array is non-empty
  local node_count
  node_count=$(jq '.nodes | length' "$pipeline_file" 2>/dev/null || echo "0")
  if [[ "$node_count" -eq 0 ]]; then
    echo "Error: Pipeline must have at least one node" >&2
    errors=$((errors + 1))
  fi

  # Check node IDs are unique
  local dupes
  dupes=$(jq -r '
    [.nodes[].id] | group_by(.) | map(select(length > 1)) | map(.[0]) | join(", ")
  ' "$pipeline_file" 2>/dev/null)

  if [[ -n "$dupes" ]]; then
    echo "Error: Duplicate node IDs: $dupes" >&2
    errors=$((errors + 1))
  fi

  # Check depends references exist
  local bad_refs
  bad_refs=$(jq -r '
    [.nodes[].id] as $ids |
    [.nodes[] | (.depends // [])[] | select(. as $d | $ids | index($d) | not)] |
    unique | join(", ")
  ' "$pipeline_file" 2>/dev/null)

  if [[ -n "$bad_refs" ]]; then
    echo "Error: Unknown dependency references: $bad_refs" >&2
    errors=$((errors + 1))
  fi

  # Check node types are valid
  local bad_types
  bad_types=$(jq -r '
    [.nodes[] | select(.type | IN("task", "plan", "gate", "shell") | not) | .id + ":" + .type] | join(", ")
  ' "$pipeline_file" 2>/dev/null)

  if [[ -n "$bad_types" ]]; then
    echo "Error: Invalid node types: $bad_types" >&2
    errors=$((errors + 1))
  fi

  # Check backend values are valid
  local bad_backends
  bad_backends=$(jq -r '
    [.nodes[] | select(.backend != null) | select(.backend | IN("claude-code", "cursor", "shell", "manual") | not) | .id + ":" + .backend] | join(", ")
  ' "$pipeline_file" 2>/dev/null)

  if [[ -n "$bad_backends" ]]; then
    echo "Error: Invalid backend values: $bad_backends" >&2
    errors=$((errors + 1))
  fi

  # Check type-specific required fields
  local missing_cmd
  missing_cmd=$(jq -r '
    [.nodes[] | select(.type == "task" or .type == "shell") | select(.command == null or .command == "") | .id] | join(", ")
  ' "$pipeline_file" 2>/dev/null)

  if [[ -n "$missing_cmd" ]]; then
    echo "Error: Nodes missing required 'command' field: $missing_cmd" >&2
    errors=$((errors + 1))
  fi

  local missing_plan
  missing_plan=$(jq -r '
    [.nodes[] | select(.type == "plan") | select(.plan_path == null or .plan_path == "") | .id] | join(", ")
  ' "$pipeline_file" 2>/dev/null)

  if [[ -n "$missing_plan" ]]; then
    echo "Error: Plan nodes missing required 'plan_path' field: $missing_plan" >&2
    errors=$((errors + 1))
  fi

  # Check for cycles
  if ! detect_cycle "$pipeline_file"; then
    errors=$((errors + 1))
  fi

  if [[ "$errors" -gt 0 ]]; then
    return 1
  fi

  return 0
}
