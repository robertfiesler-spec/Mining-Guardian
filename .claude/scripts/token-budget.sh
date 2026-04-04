#!/usr/bin/env bash
# Token Budget Tracker for AI Dev Toolkit
#
# Measures token cost of every toolkit component and checks
# against configurable budget thresholds in config.json.
#
# Usage:
#   ./scripts/token-budget.sh [OPTIONS]
#
# Options:
#   --check          Check budgets, exit non-zero if over (default)
#   --report         Print full human-readable report
#   --json           Output machine-readable JSON
#   --save-baseline  Save current measurements as baseline
#   --compare        Compare against saved baseline
#   --quiet          Only output errors and warnings
#   --verbose        Show per-file token counts
#   --config PATH    Path to config.json (default: auto-detect)
#   --component TYPE Only check specific type (commands|agents|skills|rules)
#
# Exit codes:
#   0 - All within budget
#   1 - Over budget (failAtPercent exceeded)
#   2 - Configuration error

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Defaults ───────────────────────────────────────────────

MODE="check"
QUIET=false
VERBOSE=false
CONFIG_PATH=""
COMPONENT_FILTER=""
BASELINE_FILE=""

# Default thresholds (overridden by config.json)
THRESHOLD_CLAUDE_MD=8000
THRESHOLD_COMMAND=8000
THRESHOLD_AGENT=4000
THRESHOLD_SKILL=4000
THRESHOLD_RULE=3000
THRESHOLD_HOOK_CONFIG=2000
THRESHOLD_TOTAL_ALWAYS_LOADED=35000
THRESHOLD_TOTAL_COMMANDS=100000
THRESHOLD_TOTAL_AGENTS=15000
THRESHOLD_TOTAL_SKILLS=20000
THRESHOLD_TOTAL_RULES=6000
WARN_AT_PERCENT=80
FAIL_AT_PERCENT=100

# Accumulators (parallel arrays for bash 3.2 compat)
FILE_NAMES=()
FILE_TOKENS=()
FILE_CATEGORIES=()
FILE_STATUSES=()

TOTAL_ALWAYS_LOADED=0
TOTAL_COMMANDS=0
TOTAL_AGENTS=0
TOTAL_SKILLS=0
TOTAL_RULES=0

FAIL_COUNT=0
WARN_COUNT=0

# ─── Utility Functions ──────────────────────────────────────

source "$SCRIPT_DIR/lib/logging.sh"

# ─── Core Functions ─────────────────────────────────────────

estimate_tokens() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "0"
    return
  fi
  local chars
  chars=$(wc -c < "$file" | tr -d ' ')
  echo $(( chars / 4 ))
}

detect_toolkit_root() {
  # Source repo: config.json at repo root (SCRIPT_DIR is scripts/)
  if [[ -f "$SCRIPT_DIR/../config.json" ]]; then
    echo "$SCRIPT_DIR/.."
    return
  fi
  # Installed (local): .claude/config.json
  if [[ -f ".claude/config.json" ]]; then
    echo ".claude"
    return
  fi
  # Installed (global): ~/.claude/config.json
  if [[ -f "$HOME/.claude/config.json" ]]; then
    echo "$HOME/.claude"
    return
  fi
  echo ""
}

load_config() {
  local config_file="$1"

  if [[ ! -f "$config_file" ]]; then
    log_warn "Config not found at $config_file; using defaults"
    return
  fi

  if ! command -v jq &>/dev/null; then
    log_warn "jq not found; using default thresholds"
    return
  fi

  # Check if tokenBudget section exists
  local has_section
  has_section=$(jq -r 'has("tokenBudget")' "$config_file" 2>/dev/null || echo "false")
  if [[ "$has_section" != "true" ]]; then
    log_warn "No tokenBudget section in config; using defaults"
    return
  fi

  # Check enabled flag
  local enabled
  enabled=$(jq -r '.tokenBudget.enabled // true' "$config_file")
  if [[ "$enabled" == "false" ]]; then
    log_info "Token budget checking disabled in config"
    exit 0
  fi

  # Load thresholds with defaults
  THRESHOLD_CLAUDE_MD=$(jq -r '.tokenBudget.thresholds.claudeMd // 8000' "$config_file")
  THRESHOLD_COMMAND=$(jq -r '.tokenBudget.thresholds.command // 8000' "$config_file")
  THRESHOLD_AGENT=$(jq -r '.tokenBudget.thresholds.agent // 4000' "$config_file")
  THRESHOLD_SKILL=$(jq -r '.tokenBudget.thresholds.skill // 4000' "$config_file")
  THRESHOLD_RULE=$(jq -r '.tokenBudget.thresholds.rule // 3000' "$config_file")
  THRESHOLD_HOOK_CONFIG=$(jq -r '.tokenBudget.thresholds.hookConfig // 2000' "$config_file")
  THRESHOLD_TOTAL_ALWAYS_LOADED=$(jq -r '.tokenBudget.thresholds.totalAlwaysLoaded // 35000' "$config_file")
  THRESHOLD_TOTAL_COMMANDS=$(jq -r '.tokenBudget.thresholds.totalCommands // 100000' "$config_file")
  THRESHOLD_TOTAL_AGENTS=$(jq -r '.tokenBudget.thresholds.totalAgents // 15000' "$config_file")
  THRESHOLD_TOTAL_SKILLS=$(jq -r '.tokenBudget.thresholds.totalSkills // 20000' "$config_file")
  THRESHOLD_TOTAL_RULES=$(jq -r '.tokenBudget.thresholds.totalRules // 6000' "$config_file")
  WARN_AT_PERCENT=$(jq -r '.tokenBudget.warnAtPercent // 80' "$config_file")
  FAIL_AT_PERCENT=$(jq -r '.tokenBudget.failAtPercent // 100' "$config_file")
  BASELINE_FILE=$(jq -r '.tokenBudget.baselineFile // ".claude/state/token-baseline.json"' "$config_file")
}

check_threshold() {
  local tokens="$1"
  local threshold="$2"

  local fail_at=$(( threshold * FAIL_AT_PERCENT / 100 ))
  local warn_at=$(( threshold * WARN_AT_PERCENT / 100 ))

  if (( tokens >= fail_at )); then
    echo "FAIL"
  elif (( tokens >= warn_at )); then
    echo "WARN"
  else
    echo "OK"
  fi
}

format_number() {
  local num="$1"
  # Add commas to numbers for readability
  if command -v printf &>/dev/null; then
    printf "%'d" "$num" 2>/dev/null || echo "$num"
  else
    echo "$num"
  fi
}

format_percent() {
  local tokens="$1"
  local threshold="$2"
  if (( threshold == 0 )); then
    echo "N/A"
    return
  fi
  echo $(( tokens * 100 / threshold ))
}

# ─── Scanning Functions ─────────────────────────────────────

record_file() {
  local name="$1"
  local tokens="$2"
  local category="$3"
  local threshold="$4"

  local status
  status=$(check_threshold "$tokens" "$threshold")

  FILE_NAMES+=("$name")
  FILE_TOKENS+=("$tokens")
  FILE_CATEGORIES+=("$category")
  FILE_STATUSES+=("$status")

  if [[ "$status" == "FAIL" ]]; then
    FAIL_COUNT=$(( FAIL_COUNT + 1 ))
  elif [[ "$status" == "WARN" ]]; then
    WARN_COUNT=$(( WARN_COUNT + 1 ))
  fi
}

scan_claude_md() {
  local root="$1"

  # Source repo has CLAUDE.md at root
  if [[ -f "$root/CLAUDE.md" ]]; then
    local tokens
    tokens=$(estimate_tokens "$root/CLAUDE.md")
    record_file "CLAUDE.md" "$tokens" "always-loaded" "$THRESHOLD_CLAUDE_MD"
    TOTAL_ALWAYS_LOADED=$(( TOTAL_ALWAYS_LOADED + tokens ))
  fi
}

scan_commands() {
  local root="$1"
  local dir="$root/commands"

  if [[ ! -d "$dir" ]]; then
    return
  fi

  for file in "$dir"/*.md; do
    [[ -f "$file" ]] || continue
    local name
    name=$(basename "$file")
    local tokens
    tokens=$(estimate_tokens "$file")
    record_file "commands/$name" "$tokens" "command" "$THRESHOLD_COMMAND"
    TOTAL_COMMANDS=$(( TOTAL_COMMANDS + tokens ))
  done
}

scan_agents() {
  local root="$1"
  local dir="$root/agents"

  if [[ ! -d "$dir" ]]; then
    return
  fi

  for file in "$dir"/*.md; do
    [[ -f "$file" ]] || continue
    local name
    name=$(basename "$file")
    local tokens
    tokens=$(estimate_tokens "$file")
    record_file "agents/$name" "$tokens" "agent" "$THRESHOLD_AGENT"
    TOTAL_AGENTS=$(( TOTAL_AGENTS + tokens ))
  done
}

scan_skills() {
  local root="$1"
  local dir="$root/skills"

  if [[ ! -d "$dir" ]]; then
    return
  fi

  for skill_dir in "$dir"/*/; do
    [[ -d "$skill_dir" ]] || continue
    local skill_file="$skill_dir/SKILL.md"
    if [[ -f "$skill_file" ]]; then
      local skill_name
      skill_name=$(basename "$skill_dir")
      local tokens
      tokens=$(estimate_tokens "$skill_file")
      record_file "skills/$skill_name/SKILL.md" "$tokens" "skill" "$THRESHOLD_SKILL"
      TOTAL_SKILLS=$(( TOTAL_SKILLS + tokens ))
    fi
  done
}

scan_rules() {
  local root="$1"
  local dir="$root/rules"

  if [[ ! -d "$dir" ]]; then
    return
  fi

  # Root-level rules
  for file in "$dir"/*.md; do
    [[ -f "$file" ]] || continue
    local name
    name=$(basename "$file")
    local tokens
    tokens=$(estimate_tokens "$file")
    record_file "rules/$name" "$tokens" "rule" "$THRESHOLD_RULE"
    TOTAL_RULES=$(( TOTAL_RULES + tokens ))
    TOTAL_ALWAYS_LOADED=$(( TOTAL_ALWAYS_LOADED + tokens ))
  done

  # Design-system sub-directory
  if [[ -d "$dir/design-system" ]]; then
    for file in "$dir/design-system"/*.md; do
      [[ -f "$file" ]] || continue
      local name
      name=$(basename "$file")
      local tokens
      tokens=$(estimate_tokens "$file")
      record_file "rules/design-system/$name" "$tokens" "rule" "$THRESHOLD_RULE"
      TOTAL_RULES=$(( TOTAL_RULES + tokens ))
      TOTAL_ALWAYS_LOADED=$(( TOTAL_ALWAYS_LOADED + tokens ))
    done
  fi
}

scan_hooks() {
  local root="$1"
  local dir="$root/hooks"

  if [[ ! -d "$dir" ]]; then
    return
  fi

  for file in "$dir"/*.json; do
    [[ -f "$file" ]] || continue
    local name
    name=$(basename "$file")
    local tokens
    tokens=$(estimate_tokens "$file")
    record_file "hooks/$name" "$tokens" "hook-config" "$THRESHOLD_HOOK_CONFIG"
    TOTAL_ALWAYS_LOADED=$(( TOTAL_ALWAYS_LOADED + tokens ))
  done
}

scan_all() {
  local root="$1"

  if [[ -n "$COMPONENT_FILTER" ]]; then
    case "$COMPONENT_FILTER" in
      commands) scan_commands "$root" ;;
      agents)   scan_agents "$root" ;;
      skills)   scan_skills "$root" ;;
      rules)    scan_rules "$root" ;;
      *)        log_error "Unknown component type: $COMPONENT_FILTER"; exit 2 ;;
    esac
  else
    scan_claude_md "$root"
    scan_commands "$root"
    scan_agents "$root"
    scan_skills "$root"
    scan_rules "$root"
    scan_hooks "$root"
  fi
}

# ─── Aggregate Threshold Checks ────────────────────────────

check_aggregates() {
  if [[ -z "$COMPONENT_FILTER" ]]; then
    local status

    status=$(check_threshold "$TOTAL_ALWAYS_LOADED" "$THRESHOLD_TOTAL_ALWAYS_LOADED")
    record_file "TOTAL: always-loaded" "$TOTAL_ALWAYS_LOADED" "aggregate" "$THRESHOLD_TOTAL_ALWAYS_LOADED"

    status=$(check_threshold "$TOTAL_COMMANDS" "$THRESHOLD_TOTAL_COMMANDS")
    record_file "TOTAL: commands" "$TOTAL_COMMANDS" "aggregate" "$THRESHOLD_TOTAL_COMMANDS"

    status=$(check_threshold "$TOTAL_AGENTS" "$THRESHOLD_TOTAL_AGENTS")
    record_file "TOTAL: agents" "$TOTAL_AGENTS" "aggregate" "$THRESHOLD_TOTAL_AGENTS"

    status=$(check_threshold "$TOTAL_SKILLS" "$THRESHOLD_TOTAL_SKILLS")
    record_file "TOTAL: skills" "$TOTAL_SKILLS" "aggregate" "$THRESHOLD_TOTAL_SKILLS"

    status=$(check_threshold "$TOTAL_RULES" "$THRESHOLD_TOTAL_RULES")
    record_file "TOTAL: rules" "$TOTAL_RULES" "aggregate" "$THRESHOLD_TOTAL_RULES"
  fi
}

# ─── Output Functions ───────────────────────────────────────

print_report_line() {
  local name="$1"
  local tokens="$2"
  local threshold="$3"
  local status="$4"

  local pct
  pct=$(format_percent "$tokens" "$threshold")

  local status_color=""
  local reset=""
  if [[ -t 1 ]]; then
    case "$status" in
      FAIL) status_color="\033[31m"; reset="\033[0m" ;;
      WARN) status_color="\033[33m"; reset="\033[0m" ;;
      OK)   status_color="\033[32m"; reset="\033[0m" ;;
    esac
  fi

  printf "  %-38s %6d tk   [%3d%% of %6d]  ${status_color}%s${reset}\n" \
    "$name" "$tokens" "$pct" "$threshold" "$status"
}

print_report() {
  local root="$1"
  local version=""

  if command -v jq &>/dev/null && [[ -f "$root/config.json" ]]; then
    version=$(jq -r '.version // "unknown"' "$root/config.json")
  fi

  local date_str
  date_str=$(date +"%Y-%m-%d")

  echo "======================================"
  echo "  Token Budget Report"
  echo "  Toolkit v${version} | ${date_str}"
  echo "======================================"
  echo ""

  # Always-loaded section
  local section="always-loaded"
  local has_items=false
  for i in "${!FILE_NAMES[@]}"; do
    if [[ "${FILE_CATEGORIES[$i]}" == "$section" ]]; then
      if [[ "$has_items" == false ]]; then
        echo "--- Always-Loaded ---"
        has_items=true
      fi
      print_report_line "${FILE_NAMES[$i]}" "${FILE_TOKENS[$i]}" "$THRESHOLD_CLAUDE_MD" "${FILE_STATUSES[$i]}"
    fi
  done

  # Rules (part of always-loaded too)
  has_items=false
  for i in "${!FILE_NAMES[@]}"; do
    if [[ "${FILE_CATEGORIES[$i]}" == "rule" ]]; then
      if [[ "$has_items" == false ]]; then
        echo ""
        echo "--- Rules ---"
        has_items=true
      fi
      if [[ "$VERBOSE" == true ]] || [[ "${FILE_STATUSES[$i]}" != "OK" ]]; then
        print_report_line "${FILE_NAMES[$i]}" "${FILE_TOKENS[$i]}" "$THRESHOLD_RULE" "${FILE_STATUSES[$i]}"
      fi
    fi
  done
  if [[ "$has_items" == true ]] && [[ "$VERBOSE" == false ]]; then
    local ok_count=0
    for i in "${!FILE_NAMES[@]}"; do
      if [[ "${FILE_CATEGORIES[$i]}" == "rule" ]] && [[ "${FILE_STATUSES[$i]}" == "OK" ]]; then
        ok_count=$(( ok_count + 1 ))
      fi
    done
    if (( ok_count > 0 )); then
      echo "  ... ($ok_count more files OK)"
    fi
  fi

  # Hook configs
  has_items=false
  for i in "${!FILE_NAMES[@]}"; do
    if [[ "${FILE_CATEGORIES[$i]}" == "hook-config" ]]; then
      if [[ "$has_items" == false ]]; then
        echo ""
        echo "--- Hook Configs ---"
        has_items=true
      fi
      print_report_line "${FILE_NAMES[$i]}" "${FILE_TOKENS[$i]}" "$THRESHOLD_HOOK_CONFIG" "${FILE_STATUSES[$i]}"
    fi
  done

  # Commands
  has_items=false
  local cmd_count=0
  for i in "${!FILE_NAMES[@]}"; do
    if [[ "${FILE_CATEGORIES[$i]}" == "command" ]]; then
      cmd_count=$(( cmd_count + 1 ))
    fi
  done
  # Sort commands by token count (show top 5 + any warnings/failures)
  for i in "${!FILE_NAMES[@]}"; do
    if [[ "${FILE_CATEGORIES[$i]}" == "command" ]]; then
      if [[ "$has_items" == false ]]; then
        echo ""
        echo "--- Commands ($cmd_count files) ---"
        has_items=true
      fi
      if [[ "$VERBOSE" == true ]] || [[ "${FILE_STATUSES[$i]}" != "OK" ]]; then
        print_report_line "${FILE_NAMES[$i]}" "${FILE_TOKENS[$i]}" "$THRESHOLD_COMMAND" "${FILE_STATUSES[$i]}"
      fi
    fi
  done
  if [[ "$has_items" == true ]] && [[ "$VERBOSE" == false ]]; then
    local ok_count=0
    for i in "${!FILE_NAMES[@]}"; do
      if [[ "${FILE_CATEGORIES[$i]}" == "command" ]] && [[ "${FILE_STATUSES[$i]}" == "OK" ]]; then
        ok_count=$(( ok_count + 1 ))
      fi
    done
    if (( ok_count > 0 )); then
      echo "  ... ($ok_count more files OK)"
    fi
  fi

  # Agents
  has_items=false
  local agent_count=0
  for i in "${!FILE_NAMES[@]}"; do
    if [[ "${FILE_CATEGORIES[$i]}" == "agent" ]]; then
      agent_count=$(( agent_count + 1 ))
    fi
  done
  for i in "${!FILE_NAMES[@]}"; do
    if [[ "${FILE_CATEGORIES[$i]}" == "agent" ]]; then
      if [[ "$has_items" == false ]]; then
        echo ""
        echo "--- Agents ($agent_count files) ---"
        has_items=true
      fi
      if [[ "$VERBOSE" == true ]] || [[ "${FILE_STATUSES[$i]}" != "OK" ]]; then
        print_report_line "${FILE_NAMES[$i]}" "${FILE_TOKENS[$i]}" "$THRESHOLD_AGENT" "${FILE_STATUSES[$i]}"
      fi
    fi
  done
  if [[ "$has_items" == true ]] && [[ "$VERBOSE" == false ]]; then
    local ok_count=0
    for i in "${!FILE_NAMES[@]}"; do
      if [[ "${FILE_CATEGORIES[$i]}" == "agent" ]] && [[ "${FILE_STATUSES[$i]}" == "OK" ]]; then
        ok_count=$(( ok_count + 1 ))
      fi
    done
    if (( ok_count > 0 )); then
      echo "  ... ($ok_count more files OK)"
    fi
  fi

  # Skills
  has_items=false
  local skill_count=0
  for i in "${!FILE_NAMES[@]}"; do
    if [[ "${FILE_CATEGORIES[$i]}" == "skill" ]]; then
      skill_count=$(( skill_count + 1 ))
    fi
  done
  for i in "${!FILE_NAMES[@]}"; do
    if [[ "${FILE_CATEGORIES[$i]}" == "skill" ]]; then
      if [[ "$has_items" == false ]]; then
        echo ""
        echo "--- Skills ($skill_count files) ---"
        has_items=true
      fi
      if [[ "$VERBOSE" == true ]] || [[ "${FILE_STATUSES[$i]}" != "OK" ]]; then
        print_report_line "${FILE_NAMES[$i]}" "${FILE_TOKENS[$i]}" "$THRESHOLD_SKILL" "${FILE_STATUSES[$i]}"
      fi
    fi
  done
  if [[ "$has_items" == true ]] && [[ "$VERBOSE" == false ]]; then
    local ok_count=0
    for i in "${!FILE_NAMES[@]}"; do
      if [[ "${FILE_CATEGORIES[$i]}" == "skill" ]] && [[ "${FILE_STATUSES[$i]}" == "OK" ]]; then
        ok_count=$(( ok_count + 1 ))
      fi
    done
    if (( ok_count > 0 )); then
      echo "  ... ($ok_count more files OK)"
    fi
  fi

  # Aggregates
  echo ""
  echo "--- Aggregates ---"
  for i in "${!FILE_NAMES[@]}"; do
    if [[ "${FILE_CATEGORIES[$i]}" == "aggregate" ]]; then
      local threshold=0
      case "${FILE_NAMES[$i]}" in
        "TOTAL: always-loaded") threshold=$THRESHOLD_TOTAL_ALWAYS_LOADED ;;
        "TOTAL: commands")      threshold=$THRESHOLD_TOTAL_COMMANDS ;;
        "TOTAL: agents")        threshold=$THRESHOLD_TOTAL_AGENTS ;;
        "TOTAL: skills")        threshold=$THRESHOLD_TOTAL_SKILLS ;;
        "TOTAL: rules")         threshold=$THRESHOLD_TOTAL_RULES ;;
      esac
      print_report_line "${FILE_NAMES[$i]}" "${FILE_TOKENS[$i]}" "$threshold" "${FILE_STATUSES[$i]}"
    fi
  done

  # Summary
  echo ""
  echo "======================================"
  if (( FAIL_COUNT > 0 )); then
    echo "  RESULT: $FAIL_COUNT FAIL, $WARN_COUNT WARN"
  elif (( WARN_COUNT > 0 )); then
    echo "  RESULT: 0 FAIL, $WARN_COUNT WARN"
  else
    echo "  RESULT: All within budget"
  fi
  echo "======================================"

  # List failures and warnings
  if (( FAIL_COUNT > 0 || WARN_COUNT > 0 )); then
    echo ""
    for i in "${!FILE_NAMES[@]}"; do
      if [[ "${FILE_STATUSES[$i]}" == "FAIL" ]]; then
        local threshold=0
        case "${FILE_CATEGORIES[$i]}" in
          always-loaded) threshold=$THRESHOLD_CLAUDE_MD ;;
          command)       threshold=$THRESHOLD_COMMAND ;;
          agent)         threshold=$THRESHOLD_AGENT ;;
          skill)         threshold=$THRESHOLD_SKILL ;;
          rule)          threshold=$THRESHOLD_RULE ;;
          hook-config)   threshold=$THRESHOLD_HOOK_CONFIG ;;
          aggregate)
            case "${FILE_NAMES[$i]}" in
              "TOTAL: always-loaded") threshold=$THRESHOLD_TOTAL_ALWAYS_LOADED ;;
              "TOTAL: commands")      threshold=$THRESHOLD_TOTAL_COMMANDS ;;
              "TOTAL: agents")        threshold=$THRESHOLD_TOTAL_AGENTS ;;
              "TOTAL: skills")        threshold=$THRESHOLD_TOTAL_SKILLS ;;
              "TOTAL: rules")         threshold=$THRESHOLD_TOTAL_RULES ;;
            esac
            ;;
        esac
        echo "FAIL: ${FILE_NAMES[$i]} exceeds ${threshold} token budget (${FILE_TOKENS[$i]})"
      fi
    done
    for i in "${!FILE_NAMES[@]}"; do
      if [[ "${FILE_STATUSES[$i]}" == "WARN" ]]; then
        local threshold=0
        case "${FILE_CATEGORIES[$i]}" in
          always-loaded) threshold=$THRESHOLD_CLAUDE_MD ;;
          command)       threshold=$THRESHOLD_COMMAND ;;
          agent)         threshold=$THRESHOLD_AGENT ;;
          skill)         threshold=$THRESHOLD_SKILL ;;
          rule)          threshold=$THRESHOLD_RULE ;;
          hook-config)   threshold=$THRESHOLD_HOOK_CONFIG ;;
          aggregate)
            case "${FILE_NAMES[$i]}" in
              "TOTAL: always-loaded") threshold=$THRESHOLD_TOTAL_ALWAYS_LOADED ;;
              "TOTAL: commands")      threshold=$THRESHOLD_TOTAL_COMMANDS ;;
              "TOTAL: agents")        threshold=$THRESHOLD_TOTAL_AGENTS ;;
              "TOTAL: skills")        threshold=$THRESHOLD_TOTAL_SKILLS ;;
              "TOTAL: rules")         threshold=$THRESHOLD_TOTAL_RULES ;;
            esac
            ;;
        esac
        local pct
        pct=$(format_percent "${FILE_TOKENS[$i]}" "$threshold")
        echo "WARN: ${FILE_NAMES[$i]} at ${pct}% of ${threshold} token budget"
      fi
    done
  fi
}

print_check() {
  # Quiet mode: only failures and warnings
  for i in "${!FILE_NAMES[@]}"; do
    if [[ "${FILE_STATUSES[$i]}" == "FAIL" ]]; then
      echo "FAIL: ${FILE_NAMES[$i]} (${FILE_TOKENS[$i]} tokens)"
    fi
  done
  if [[ "$QUIET" == false ]]; then
    for i in "${!FILE_NAMES[@]}"; do
      if [[ "${FILE_STATUSES[$i]}" == "WARN" ]]; then
        echo "WARN: ${FILE_NAMES[$i]} (${FILE_TOKENS[$i]} tokens)"
      fi
    done
  fi
}

print_json() {
  if ! command -v jq &>/dev/null; then
    # Manual JSON without jq
    echo "{"
    echo "  \"files\": ["
    local first=true
    for i in "${!FILE_NAMES[@]}"; do
      if [[ "${FILE_CATEGORIES[$i]}" != "aggregate" ]]; then
        if [[ "$first" == true ]]; then
          first=false
        else
          echo ","
        fi
        printf '    {"name": "%s", "tokens": %d, "category": "%s", "status": "%s"}' \
          "${FILE_NAMES[$i]}" "${FILE_TOKENS[$i]}" "${FILE_CATEGORIES[$i]}" "${FILE_STATUSES[$i]}"
      fi
    done
    echo ""
    echo "  ],"
    echo "  \"aggregates\": {"
    echo "    \"alwaysLoaded\": $TOTAL_ALWAYS_LOADED,"
    echo "    \"commands\": $TOTAL_COMMANDS,"
    echo "    \"agents\": $TOTAL_AGENTS,"
    echo "    \"skills\": $TOTAL_SKILLS,"
    echo "    \"rules\": $TOTAL_RULES"
    echo "  },"
    echo "  \"result\": {"
    echo "    \"failures\": $FAIL_COUNT,"
    echo "    \"warnings\": $WARN_COUNT"
    echo "  }"
    echo "}"
  else
    # Build JSON with jq
    local json="{\"files\":["
    local first=true
    for i in "${!FILE_NAMES[@]}"; do
      if [[ "${FILE_CATEGORIES[$i]}" != "aggregate" ]]; then
        if [[ "$first" == true ]]; then
          first=false
        else
          json+=","
        fi
        json+="{\"name\":\"${FILE_NAMES[$i]}\",\"tokens\":${FILE_TOKENS[$i]},\"category\":\"${FILE_CATEGORIES[$i]}\",\"status\":\"${FILE_STATUSES[$i]}\"}"
      fi
    done
    json+="],\"aggregates\":{\"alwaysLoaded\":$TOTAL_ALWAYS_LOADED,\"commands\":$TOTAL_COMMANDS,\"agents\":$TOTAL_AGENTS,\"skills\":$TOTAL_SKILLS,\"rules\":$TOTAL_RULES},\"result\":{\"failures\":$FAIL_COUNT,\"warnings\":$WARN_COUNT}}"
    echo "$json" | jq .
  fi
}

# ─── Baseline Functions ─────────────────────────────────────

save_baseline() {
  local root="$1"
  local baseline="$BASELINE_FILE"

  if [[ -z "$baseline" ]]; then
    baseline=".claude/state/token-baseline.json"
  fi

  # Resolve relative to root if needed
  if [[ "$baseline" != /* ]]; then
    baseline="$root/$baseline"
  fi

  mkdir -p "$(dirname "$baseline")"

  local version=""
  if command -v jq &>/dev/null && [[ -f "$root/config.json" ]]; then
    version=$(jq -r '.version // "unknown"' "$root/config.json")
  fi

  local timestamp
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Build baseline JSON
  {
    echo "{"
    echo "  \"timestamp\": \"$timestamp\","
    echo "  \"version\": \"$version\","
    echo "  \"components\": {"
    local first=true
    for i in "${!FILE_NAMES[@]}"; do
      if [[ "${FILE_CATEGORIES[$i]}" != "aggregate" ]]; then
        if [[ "$first" == true ]]; then
          first=false
        else
          echo ","
        fi
        printf '    "%s": %d' "${FILE_NAMES[$i]}" "${FILE_TOKENS[$i]}"
      fi
    done
    echo ""
    echo "  },"
    echo "  \"aggregates\": {"
    echo "    \"alwaysLoaded\": $TOTAL_ALWAYS_LOADED,"
    echo "    \"commands\": $TOTAL_COMMANDS,"
    echo "    \"agents\": $TOTAL_AGENTS,"
    echo "    \"skills\": $TOTAL_SKILLS,"
    echo "    \"rules\": $TOTAL_RULES"
    echo "  }"
    echo "}"
  } > "$baseline"

  echo "Baseline saved to $baseline"
  echo "  Timestamp: $timestamp"
  echo "  Version: $version"
  echo "  Components: ${#FILE_NAMES[@]} files measured"
}

compare_baseline() {
  local root="$1"
  local baseline="$BASELINE_FILE"

  if [[ -z "$baseline" ]]; then
    baseline=".claude/state/token-baseline.json"
  fi

  if [[ "$baseline" != /* ]]; then
    baseline="$root/$baseline"
  fi

  if [[ ! -f "$baseline" ]]; then
    log_error "No baseline found at $baseline"
    echo "Run --save-baseline first to create one."
    exit 2
  fi

  if ! command -v jq &>/dev/null; then
    log_error "jq is required for baseline comparison"
    exit 2
  fi

  local bl_timestamp bl_version
  bl_timestamp=$(jq -r '.timestamp' "$baseline")
  bl_version=$(jq -r '.version' "$baseline")

  local version=""
  if [[ -f "$root/config.json" ]]; then
    version=$(jq -r '.version // "unknown"' "$root/config.json")
  fi

  echo "--- Baseline Comparison ---"
  echo "Baseline: $bl_timestamp (v$bl_version)"
  echo "Current:  $(date -u +"%Y-%m-%dT%H:%M:%SZ") (v$version)"
  echo ""

  local net_change=0
  local has_changes=false

  echo "Changed:"
  for i in "${!FILE_NAMES[@]}"; do
    if [[ "${FILE_CATEGORIES[$i]}" == "aggregate" ]]; then
      continue
    fi

    local name="${FILE_NAMES[$i]}"
    local current="${FILE_TOKENS[$i]}"
    local prev
    prev=$(jq -r ".components[\"$name\"] // \"new\"" "$baseline")

    if [[ "$prev" == "new" ]] || [[ "$prev" == "null" ]]; then
      echo "  $name  (new)  $current  (+$current)"
      net_change=$(( net_change + current ))
      has_changes=true
    elif (( current != prev )); then
      local delta=$(( current - prev ))
      local sign="+"
      if (( delta < 0 )); then
        sign=""
      fi
      local pct_change=""
      if (( prev > 0 )); then
        pct_change=" (${sign}$(( delta * 100 / prev ))%)"
      fi
      echo "  $name  $prev -> $current  (${sign}${delta}${pct_change})"
      net_change=$(( net_change + delta ))
      has_changes=true
    fi
  done

  # Check for removed files
  local bl_keys
  bl_keys=$(jq -r '.components | keys[]' "$baseline")
  while IFS= read -r key; do
    local found=false
    for i in "${!FILE_NAMES[@]}"; do
      if [[ "${FILE_NAMES[$i]}" == "$key" ]]; then
        found=true
        break
      fi
    done
    if [[ "$found" == false ]]; then
      local prev
      prev=$(jq -r ".components[\"$key\"]" "$baseline")
      echo "  $key  (removed)  -$prev"
      net_change=$(( net_change - prev ))
      has_changes=true
    fi
  done <<< "$bl_keys"

  if [[ "$has_changes" == false ]]; then
    echo "  (no changes)"
  fi

  # Aggregate comparison
  echo ""
  echo "Aggregates:"
  for agg in alwaysLoaded commands agents skills rules; do
    local bl_val
    bl_val=$(jq -r ".aggregates.$agg // 0" "$baseline")
    local current=0
    case "$agg" in
      alwaysLoaded) current=$TOTAL_ALWAYS_LOADED ;;
      commands)     current=$TOTAL_COMMANDS ;;
      agents)       current=$TOTAL_AGENTS ;;
      skills)       current=$TOTAL_SKILLS ;;
      rules)        current=$TOTAL_RULES ;;
    esac
    local delta=$(( current - bl_val ))
    local sign="+"
    if (( delta < 0 )); then sign=""; fi
    local pct=""
    if (( bl_val > 0 )); then
      pct=" (${sign}$(( delta * 100 / bl_val ))%)"
    fi
    printf "  %-20s %6d -> %6d  (%s%d%s)\n" "$agg" "$bl_val" "$current" "$sign" "$delta" "$pct"
  done

  echo ""
  local sign="+"
  if (( net_change < 0 )); then sign=""; fi
  echo "Net change: ${sign}${net_change} tokens"
}

# ─── Argument Parsing ───────────────────────────────────────

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --check)
        MODE="check"
        shift
        ;;
      --report)
        MODE="report"
        shift
        ;;
      --json)
        MODE="json"
        shift
        ;;
      --save-baseline)
        MODE="save-baseline"
        shift
        ;;
      --compare)
        MODE="compare"
        shift
        ;;
      --quiet)
        QUIET=true
        shift
        ;;
      --verbose)
        VERBOSE=true
        shift
        ;;
      --config)
        CONFIG_PATH="$2"
        shift 2
        ;;
      --component)
        COMPONENT_FILTER="$2"
        shift 2
        ;;
      --help|-h)
        head -26 "${BASH_SOURCE[0]}" | tail -22
        exit 0
        ;;
      *)
        log_error "Unknown option: $1"
        exit 2
        ;;
    esac
  done
}

# ─── Main ───────────────────────────────────────────────────

main() {
  parse_args "$@"

  local root
  root=$(detect_toolkit_root)

  if [[ -z "$root" ]]; then
    log_error "Cannot find toolkit root (no config.json found)"
    exit 2
  fi

  local config="$root/config.json"
  if [[ -n "$CONFIG_PATH" ]]; then
    config="$CONFIG_PATH"
  fi

  load_config "$config"

  scan_all "$root"
  check_aggregates

  case "$MODE" in
    report)
      print_report "$root"
      ;;
    json)
      print_json
      ;;
    check)
      print_check
      ;;
    save-baseline)
      save_baseline "$root"
      ;;
    compare)
      compare_baseline "$root"
      ;;
  esac

  if (( FAIL_COUNT > 0 )); then
    exit 1
  fi
  exit 0
}

# Allow sourcing for testing
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
