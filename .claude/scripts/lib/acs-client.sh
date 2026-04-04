#!/bin/bash
#
# acs-client.sh - ACS (Agent Cognition System) Shell Bridge
#
# Provides bash functions for querying and storing memories in ACS.
# Used by hooks, loop.sh, pipeline.sh, and multitask.sh.
#
# ACS is OPTIONAL. All functions degrade gracefully:
# - If ACS_URL is not set, functions return empty/false immediately
# - If ACS is unreachable, functions return empty/false
# - Availability is cached for 60 seconds to avoid hammering a dead server
#
# Usage:
#   source "$SCRIPT_DIR/lib/acs-client.sh"
#   if acs_is_available; then
#     CONTEXT=$(acs_query "TypeScript error handling patterns" 10 2000)
#     echo "$CONTEXT" | acs_extract_context
#   fi
#
# Environment Variables:
#   ACS_URL        - Base URL of ACS instance (e.g., http://localhost:3000)
#   ACS_TENANT_ID  - Tenant ID for multi-tenant isolation (default: "default")
#   ACS_TIMEOUT    - Request timeout in seconds (default: 5)
#   ACS_DEBUG      - Set to "true" for debug logging to stderr

# ============================================================================
# Configuration
# ============================================================================

ACS_URL="${ACS_URL:-}"
ACS_TENANT_ID="${ACS_TENANT_ID:-default}"
ACS_TIMEOUT="${ACS_TIMEOUT:-5}"
ACS_DEBUG="${ACS_DEBUG:-false}"

# Try reading from config.json if ACS_URL not set in environment
if [[ -z "$ACS_URL" ]]; then
  for _acs_config_path in ".claude/config.json" "$HOME/.claude/config.json"; do
    if [[ -f "$_acs_config_path" ]]; then
      _acs_config_url=$(jq -r '.acs.url // empty' "$_acs_config_path" 2>/dev/null) || true
      if [[ -n "$_acs_config_url" && "$_acs_config_url" != "null" ]]; then
        ACS_URL="$_acs_config_url"
        ACS_TENANT_ID=$(jq -r '.acs.tenantId // "default"' "$_acs_config_path" 2>/dev/null) || true
        _acs_debug "Loaded ACS_URL from $_acs_config_path: $ACS_URL"
        break
      fi
    fi
  done
fi

# Strip trailing slash from URL
ACS_URL="${ACS_URL%/}"

# ============================================================================
# Internal State
# ============================================================================

_ACS_AVAILABLE=""
_ACS_CHECKED_AT=0

# ============================================================================
# Debug Logging
# ============================================================================

# Log debug messages to stderr when ACS_DEBUG is true
_acs_debug() {
  if [[ "$ACS_DEBUG" == "true" ]]; then
    echo "[ACS] $*" >&2
  fi
}

# ============================================================================
# Availability Functions
# ============================================================================

# Check if ACS is configured (URL is set)
# Returns: 0 if configured, 1 if not
acs_is_configured() {
  [[ -n "$ACS_URL" ]]
}

# Check if ACS is available (health check with 60-second cache)
# Makes GET /api/health and checks for status "healthy" or "degraded"
# Returns: 0 if available, 1 if not
acs_is_available() {
  if ! acs_is_configured; then
    return 1
  fi

  local now
  now=$(date +%s)
  local elapsed=$((now - _ACS_CHECKED_AT))

  # Return cached result if within TTL
  if [[ -n "$_ACS_AVAILABLE" && $elapsed -lt 60 ]]; then
    [[ "$_ACS_AVAILABLE" == "true" ]]
    return $?
  fi

  _acs_debug "Checking ACS health at ${ACS_URL}/api/health"

  local response
  response=$(curl -s --max-time "$ACS_TIMEOUT" \
    -H "x-tenant-id: $ACS_TENANT_ID" \
    "${ACS_URL}/api/health" 2>/dev/null)

  local status
  status=$(echo "$response" | jq -r '.status // empty' 2>/dev/null)

  _ACS_CHECKED_AT=$now

  if [[ "$status" == "healthy" || "$status" == "degraded" ]]; then
    _ACS_AVAILABLE="true"
    _acs_debug "ACS is available (status: $status)"
    return 0
  else
    _ACS_AVAILABLE="false"
    _acs_debug "ACS is not available (status: ${status:-unreachable})"
    return 1
  fi
}

# Reset cached availability (forces re-check on next call)
acs_reset_cache() {
  _ACS_AVAILABLE=""
  _ACS_CHECKED_AT=0
}

# ============================================================================
# Query Functions
# ============================================================================

# Query ACS for context using hybrid retrieval (POST /api/retrieve)
#
# Usage: acs_query "query text" [max_results] [token_budget]
# Output: JSON response on stdout, or empty string on failure
# Returns: 0 on success, 1 on failure
acs_query() {
  local query="$1"
  local max_results="${2:-20}"
  local token_budget="${3:-3000}"

  if ! acs_is_available; then
    echo ""
    return 1
  fi

  _acs_debug "Querying: '$query' (max=$max_results, budget=$token_budget)"

  local body
  body=$(jq -n \
    --arg q "$query" \
    --argjson mr "$max_results" \
    --argjson tb "$token_budget" \
    '{
      query: $q,
      filters: {
        categories: ["insight", "fact", "preference"]
      },
      options: {
        maxResults: $mr,
        tokenBudget: $tb,
        outputFormat: "markdown",
        includeGraph: true
      }
    }')

  local response
  response=$(curl -s --max-time "$ACS_TIMEOUT" \
    -X POST \
    -H "Content-Type: application/json" \
    -H "x-tenant-id: $ACS_TENANT_ID" \
    -d "$body" \
    "${ACS_URL}/api/retrieve" 2>/dev/null)

  if [[ -n "$response" ]]; then
    _acs_debug "Query returned $(echo "$response" | jq -r '.memories | length // 0') memories"
    echo "$response"
    return 0
  else
    _acs_debug "Query failed or returned empty"
    echo ""
    return 1
  fi
}

# Store a learning in ACS (POST /api/memories)
#
# Usage: acs_store "content" [category] [source_command] [project_name]
# Output: JSON response on stdout, or empty string on failure
# Returns: 0 on success, 1 on failure
acs_store() {
  local content="$1"
  local category="${2:-insight}"
  local source_cmd="${3:-}"
  local project="${4:-}"

  if ! acs_is_available; then
    echo ""
    return 1
  fi

  _acs_debug "Storing learning (category=$category, source=$source_cmd)"

  local snippet
  snippet=$(echo "$content" | head -c 200)

  local body
  body=$(jq -n \
    --arg c "$content" \
    --arg s "$snippet" \
    --arg cat "$category" \
    --arg src "$source_cmd" \
    --arg prj "$project" \
    '{
      content: $c,
      contentSnippet: $s,
      category: $cat,
      tier: "WARM",
      confidenceScore: 1.0,
      metadata: {
        source: $src,
        project: $prj
      }
    }')

  local response
  response=$(curl -s --max-time "$ACS_TIMEOUT" \
    -X POST \
    -H "Content-Type: application/json" \
    -H "x-tenant-id: $ACS_TENANT_ID" \
    -d "$body" \
    "${ACS_URL}/api/memories" 2>/dev/null)

  if [[ -n "$response" ]]; then
    local mem_id
    mem_id=$(echo "$response" | jq -r '.id // empty' 2>/dev/null)
    _acs_debug "Stored memory: $mem_id"
    echo "$response"
    return 0
  else
    _acs_debug "Store failed"
    echo ""
    return 1
  fi
}

# Search memories in ACS (GET /api/memories)
#
# Usage: acs_search "query" [category] [page_size]
# Output: JSON response on stdout, or empty string on failure
# Returns: 0 on success, 1 on failure
acs_search() {
  local query="$1"
  local category="${2:-}"
  local page_size="${3:-20}"

  if ! acs_is_available; then
    echo ""
    return 1
  fi

  _acs_debug "Searching: '$query' (category=$category, pageSize=$page_size)"

  # URL-encode the query
  local encoded_query
  encoded_query=$(jq -rn --arg q "$query" '$q | @uri')

  local params="search=${encoded_query}&pageSize=${page_size}"
  if [[ -n "$category" ]]; then
    params="${params}&category=${category}"
  fi

  local response
  response=$(curl -s --max-time "$ACS_TIMEOUT" \
    -H "x-tenant-id: $ACS_TENANT_ID" \
    "${ACS_URL}/api/memories?${params}" 2>/dev/null)

  if [[ -n "$response" ]]; then
    _acs_debug "Search returned $(echo "$response" | jq -r '.total // 0') results"
    echo "$response"
    return 0
  else
    _acs_debug "Search failed"
    echo ""
    return 1
  fi
}

# Get project-specific context from ACS
#
# Usage: acs_get_project_context "project-name" ["focus area"]
# Output: JSON response on stdout, or empty string on failure
# Returns: 0 on success, 1 on failure
acs_get_project_context() {
  local project="$1"
  local focus="${2:-}"

  local query
  if [[ -n "$focus" ]]; then
    query="Project \"$project\": $focus"
  else
    query="Project context and learnings for \"$project\""
  fi

  acs_query "$query" 20 3000
}

# ============================================================================
# Output Helpers
# ============================================================================

# Extract just the context string from a query/retrieve response
# Pipe JSON response into this function
#
# Usage: acs_query "..." | acs_extract_context
# Output: Plain text context, or empty
acs_extract_context() {
  jq -r '.context // empty' 2>/dev/null
}

# Extract memory count from a query response
#
# Usage: acs_query "..." | acs_extract_memory_count
# Output: Number of memories, or "0"
acs_extract_memory_count() {
  jq -r '.memories | length // 0' 2>/dev/null
}

# Format a query result as a summary line for logging
#
# Usage: acs_query "..." | acs_format_summary
# Output: "ACS: 5 memories found (3 vector, 2 graph)"
acs_format_summary() {
  local json
  json=$(cat)
  local count vector graph
  count=$(echo "$json" | jq -r '.memories | length // 0' 2>/dev/null)
  vector=$(echo "$json" | jq -r '.metadata.vectorResults // 0' 2>/dev/null)
  graph=$(echo "$json" | jq -r '.metadata.graphResults // 0' 2>/dev/null)
  echo "ACS: ${count} memories found (${vector} vector, ${graph} graph)"
}

# ============================================================================
# Status Reporting
# ============================================================================

# Print ACS connection status for /kickoff and session initialization
#
# Usage: acs_print_status
# Output: Status message to stdout
acs_print_status() {
  if ! acs_is_configured; then
    echo "ACS: Not configured (set ACS_URL to enable cross-project memory)"
    return
  fi

  if acs_is_available; then
    local project_name
    project_name=$(basename "$(pwd)")
    local result
    result=$(acs_get_project_context "$project_name" 2>/dev/null)
    local mem_count
    mem_count=$(echo "$result" | jq -r '.metadata.memoriesScanned // 0' 2>/dev/null)
    echo "ACS: Connected (${mem_count} memories scanned for project '$project_name')"
  else
    echo "ACS: Configured but unreachable (${ACS_URL})"
  fi
}
