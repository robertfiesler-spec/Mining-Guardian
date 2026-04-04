#!/bin/bash
# design-lint.sh — Deterministic design-system linter
#
# Enforces design token usage by scanning for violations in UI files.
# Runs the same checks locally and in CI for consistent enforcement.
#
# Usage:
#   ./design-lint.sh [options] [files...]
#
# Options:
#   --staged       Only check git staged files
#   --strict       Exit 1 on any violation (for CI gates)
#   --json         Output as JSON
#   --scope <dir>  Limit to a directory (default: app/ components/ src/)
#   --quiet        Only show violation count
#
# Checks:
#   1. Spacing: ban raw numeric utilities, require semantic tokens
#   2. Color: ban raw hex/rgb/hsl and arbitrary color utilities
#   3. Typography: ban arbitrary font sizes, require scale tokens
#   4. Accessibility: ban outline-none without focus-visible replacement
#   5. Exception audit: report ds-exception markers

set -euo pipefail

# --- Configuration ---
VIOLATION_COUNT=0
EXCEPTION_COUNT=0
STRICT=false
JSON_OUTPUT=false
QUIET=false
STAGED=false
SCOPE=""
FILES=()

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
DIM='\033[0;90m'
NC='\033[0m'
BOLD='\033[1m'

# Violation storage for JSON output
declare -a VIOLATIONS_JSON=()
declare -A REPORTED_EXCEPTIONS=()

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --staged)   STAGED=true; shift ;;
    --strict)   STRICT=true; shift ;;
    --json)     JSON_OUTPUT=true; shift ;;
    --quiet)    QUIET=true; shift ;;
    --scope)
      if [[ $# -lt 2 || -z "${2:-}" || "${2:-}" == -* ]]; then
        echo "Error: --scope requires a directory path." >&2
        echo "Usage: $0 --scope <dir>" >&2
        exit 1
      fi
      SCOPE="$2"
      shift 2
      ;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *)          FILES+=("$1"); shift ;;
  esac
done

# --- File Discovery ---
get_files() {
  if [[ ${#FILES[@]} -gt 0 ]]; then
    # Explicit files provided
    for f in "${FILES[@]}"; do
      if [[ -f "$f" && "$f" =~ \.(tsx|jsx|css|html)$ ]]; then
        echo "$f"
      elif [[ -d "$f" ]]; then
        find "$f" -type f \( -name "*.tsx" -o -name "*.jsx" -o -name "*.css" -o -name "*.html" \) \
          -not -path "*/node_modules/*" -not -path "*/.next/*" -not -path "*/dist/*"
      fi
    done
  elif [[ "$STAGED" == true ]]; then
    # Staged files only
    git diff --cached --name-only --diff-filter=ACMR 2>/dev/null \
      | grep -E '\.(tsx|jsx|css|html)$' || true
  elif [[ -n "$SCOPE" ]]; then
    # Scoped directory
    if [[ -d "$SCOPE" ]]; then
      find "$SCOPE" -type f \( -name "*.tsx" -o -name "*.jsx" -o -name "*.css" -o -name "*.html" \) \
        -not -path "*/node_modules/*" -not -path "*/.next/*" -not -path "*/dist/*" 2>/dev/null
    fi
  else
    # Default: common UI directories
    for dir in app components src; do
      if [[ -d "$dir" ]]; then
        find "$dir" -type f \( -name "*.tsx" -o -name "*.jsx" -o -name "*.css" -o -name "*.html" \) \
          -not -path "*/node_modules/*" -not -path "*/.next/*" -not -path "*/dist/*"
      fi
    done
  fi
}

# --- Helpers ---
report_violation() {
  local file="$1"
  local line_num="$2"
  local category="$3"
  local rule="$4"
  local code="$5"
  local fix="$6"

  VIOLATION_COUNT=$((VIOLATION_COUNT + 1))

  if [[ "$JSON_OUTPUT" == true ]]; then
    VIOLATIONS_JSON+=("$(jq -cn \
      --arg file "$file" \
      --argjson line "$line_num" \
      --arg category "$category" \
      --arg rule "$rule" \
      --arg code "$code" \
      --arg fix "$fix" \
      '{file:$file,line:$line,category:$category,rule:$rule,code:$code,fix:$fix}')")
    return
  fi

  if [[ "$QUIET" == true ]]; then
    return
  fi

  echo -e "  ${RED}[${category}]${NC} ${file}:${line_num}"
  echo -e "    ${DIM}${code}${NC}"
  echo -e "    ${CYAN}→ ${fix}${NC}"
  echo ""
}

report_exception() {
  local file="$1"
  local line_num="$2"
  local reason="$3"
  local exception_key="${file}:${line_num}"

  if [[ -n "${REPORTED_EXCEPTIONS[$exception_key]+x}" ]]; then
    return
  fi
  REPORTED_EXCEPTIONS[$exception_key]=1

  EXCEPTION_COUNT=$((EXCEPTION_COUNT + 1))

  if [[ "$JSON_OUTPUT" != true && "$QUIET" != true ]]; then
    echo -e "  ${YELLOW}[EXCEPTION]${NC} ${file}:${line_num}"
    echo -e "    ${DIM}${reason}${NC}"
    echo ""
  fi
}

# Read file content from index when linting staged changes.
read_file_content() {
  local file="$1"
  if [[ "$STAGED" == true ]]; then
    git show ":$file" 2>/dev/null || true
    return
  fi

  cat "$file"
}

# Read one line from the relevant content source.
read_file_line() {
  local file="$1"
  local line_num="$2"
  if [[ "$STAGED" == true ]]; then
    (git show ":$file" 2>/dev/null || true) | sed -n "${line_num}p"
    return
  fi

  sed -n "${line_num}p" "$file" 2>/dev/null
}

# Check if a line has a ds-exception marker on the preceding line
has_exception() {
  local file="$1"
  local line_num="$2"
  local prev_line=""

  if [[ "$line_num" -le 1 ]]; then
    return 1
  fi

  if [[ $# -ge 3 ]]; then
    prev_line="$3"
  else
    prev_line=$(read_file_line "$file" "$((line_num - 1))")
  fi

  if echo "$prev_line" | grep -q 'ds-exception:'; then
    local reason
    reason=$(echo "$prev_line" | sed -n 's/.*ds-exception:[[:space:]]*\(.*\)[[:space:]]*\*\/.*/\1/p')
    report_exception "$file" "$((line_num - 1))" "${reason:-no reason given}"
    return 0
  fi
  return 1
}

# Remove comment segments while preserving non-comment code.
# Prints "<in_block_comment>\t<sanitized_line>".
strip_comment_segments() {
  local line="$1"
  local in_block_comment="$2"
  local remaining="$line"
  local sanitized=""

  if [[ "$in_block_comment" == true ]]; then
    if [[ "$remaining" == *"*/"* ]]; then
      remaining="${remaining#*\*/}"
      in_block_comment=false
    else
      printf '%s\t%s\n' "true" ""
      return
    fi
  fi

  while [[ "$remaining" == *"/*"* ]]; do
    sanitized+="${remaining%%/\**}"
    local after_comment_start="${remaining#*/\*}"

    if [[ "$after_comment_start" == *"*/"* ]]; then
      remaining="${after_comment_start#*\*/}"
      continue
    fi

    in_block_comment=true
    remaining=""
    break
  done

  sanitized+="$remaining"

  # Remove trailing // comment, but only when not inside a quoted string.
  local without_line_comment=""
  local in_single_quote=false
  local in_double_quote=false
  local in_template_string=false
  local escaped=false
  local index=0
  local line_length=${#sanitized}

  while (( index < line_length )); do
    local char="${sanitized:index:1}"
    local next_char="${sanitized:index+1:1}"

    if [[ "$escaped" == true ]]; then
      without_line_comment+="$char"
      escaped=false
      index=$((index + 1))
      continue
    fi

    if [[ "$char" == "\\" && ( "$in_single_quote" == true || "$in_double_quote" == true || "$in_template_string" == true ) ]]; then
      without_line_comment+="$char"
      escaped=true
      index=$((index + 1))
      continue
    fi

    if [[ "$in_single_quote" == true ]]; then
      without_line_comment+="$char"
      if [[ "$char" == "'" ]]; then
        in_single_quote=false
      fi
      index=$((index + 1))
      continue
    fi

    if [[ "$in_double_quote" == true ]]; then
      without_line_comment+="$char"
      if [[ "$char" == '"' ]]; then
        in_double_quote=false
      fi
      index=$((index + 1))
      continue
    fi

    if [[ "$in_template_string" == true ]]; then
      without_line_comment+="$char"
      if [[ "$char" == '`' ]]; then
        in_template_string=false
      fi
      index=$((index + 1))
      continue
    fi

    if [[ "$char" == "'" ]]; then
      in_single_quote=true
      without_line_comment+="$char"
      index=$((index + 1))
      continue
    fi

    if [[ "$char" == '"' ]]; then
      in_double_quote=true
      without_line_comment+="$char"
      index=$((index + 1))
      continue
    fi

    if [[ "$char" == '`' ]]; then
      in_template_string=true
      without_line_comment+="$char"
      index=$((index + 1))
      continue
    fi

    if [[ "$char" == "/" && "$next_char" == "/" ]]; then
      break
    fi

    without_line_comment+="$char"
    index=$((index + 1))
  done

  printf '%s\t%s\n' "$in_block_comment" "$without_line_comment"
}

# --- Lint Checks ---

check_spacing() {
  local file="$1"
  local content="$2"

  # Raw numeric spacing utilities: mt-3, px-4, gap-2, p-8, etc.
  # Match Tailwind numeric spacing:
  # - m/p: mt-2, px-4, m-8
  # - gap/space/inset: gap-x-4, space-y-2, inset-x-0
  # Exclude semantic tokens (xs, sm, md, lg, xl, 2xl) and responsive/state prefixes
  local line_num=0
  local prev_line=""
  local in_block_comment=false
  while IFS= read -r line || [[ -n "$line" ]]; do
    line_num=$((line_num + 1))

    local stripped
    stripped=$(strip_comment_segments "$line" "$in_block_comment")
    in_block_comment="${stripped%%$'\t'*}"
    local scan_line="${stripped#*$'\t'}"

    if [[ -z "${scan_line//[[:space:]]/}" ]]; then
      prev_line="$line"
      continue
    fi

    # Check for raw numeric spacing in className or class attributes
    if echo "$scan_line" | grep -qoE '(^|[" '\''`:])((!?-?((m|p)(t|b|l|r|x|y)?-([1-9][0-9]*(\.[0-9]+)?|0\.[0-9]*[1-9][0-9]*)))|(!?-?((gap|space|inset)(-[xy])?-([1-9][0-9]*(\.[0-9]+)?|0\.[0-9]*[1-9][0-9]*))))([" '\''`]|$)'; then
      if ! has_exception "$file" "$line_num" "$prev_line"; then
        local match
        match=$(echo "$scan_line" | grep -oE '(^|[" '\''`:])((!?-?((m|p)(t|b|l|r|x|y)?-([1-9][0-9]*(\.[0-9]+)?|0\.[0-9]*[1-9][0-9]*)))|(!?-?((gap|space|inset)(-[xy])?-([1-9][0-9]*(\.[0-9]+)?|0\.[0-9]*[1-9][0-9]*))))([" '\''`]|$)' | sed -nE '1{s/^[" '\''`:]+//; s/[" '\''`]+$//; p;}')
        report_violation "$file" "$line_num" "SPACING" \
          "Raw numeric spacing utility" \
          "$match" \
          "Use semantic token (xs=8px, sm=16px, md=24px, lg=32px, xl=48px)"
      fi
    fi
    prev_line="$line"
  done <<< "$content"
}

check_color() {
  local file="$1"
  local content="$2"
  local line_num=0
  local prev_line=""
  local in_block_comment=false

  while IFS= read -r line || [[ -n "$line" ]]; do
    line_num=$((line_num + 1))

    local stripped
    stripped=$(strip_comment_segments "$line" "$in_block_comment")
    in_block_comment="${stripped%%$'\t'*}"
    local scan_line="${stripped#*$'\t'}"

    if [[ -z "${scan_line//[[:space:]]/}" ]]; then
      prev_line="$line"
      continue
    fi

    # Arbitrary color values: text-[#xxx], bg-[#xxx], border-[#xxx]
    if echo "$scan_line" | grep -qE '(text|bg|border|ring|shadow|fill|stroke)-\[#[0-9a-fA-F]+\]'; then
      if ! has_exception "$file" "$line_num" "$prev_line"; then
        local match
        match=$(echo "$scan_line" | grep -oE '(text|bg|border|ring|shadow|fill|stroke)-\[#[0-9a-fA-F]+\]' | sed -n '1p')
        report_violation "$file" "$line_num" "COLOR" \
          "Arbitrary color value" \
          "$match" \
          "Use design token color class from palette"
      fi
    fi

    # Arbitrary rgb/hsl values
    if echo "$scan_line" | grep -qE '(text|bg|border)-\[(rgb|hsl)a?\('; then
      if ! has_exception "$file" "$line_num" "$prev_line"; then
        report_violation "$file" "$line_num" "COLOR" \
          "Arbitrary rgb/hsl color" \
          "$(echo "$scan_line" | grep -oE '(text|bg|border)-\[(rgb|hsl)a?\([^]]+\]' | sed -n '1p')" \
          "Use design token color class from palette"
      fi
    fi

    # Pure black: text-black, bg-black
    if echo "$scan_line" | grep -qE '(^|[" '\''`:])(text|bg)-black([" '\''`/]|$)'; then
      if ! has_exception "$file" "$line_num" "$prev_line"; then
        local which
        which=$(echo "$scan_line" | grep -oE '(^|[" '\''`:])(text|bg)-black([" '\''`/]|$)' | sed -nE '1{s/^[" '\''`:]+//; s/[" '\''`\/]+$//; p;}')
        report_violation "$file" "$line_num" "COLOR" \
          "Pure black causes eye strain" \
          "$which" \
          "Use text-gray-900 or bg-gray-950 instead"
      fi
    fi

    # Inline style hex/rgb colors
    if echo "$scan_line" | grep -qE "style=.*color:[[:space:]]*['\"]?#[0-9a-fA-F]"; then
      if ! has_exception "$file" "$line_num" "$prev_line"; then
        report_violation "$file" "$line_num" "COLOR" \
          "Hardcoded color in inline style" \
          "$(echo "$scan_line" | grep -oE "color:[[:space:]]*['\"]?#[0-9a-fA-F]+" | sed -n '1p')" \
          "Use CSS variable or design token"
      fi
    fi
    prev_line="$line"
  done <<< "$content"
}

check_typography() {
  local file="$1"
  local content="$2"
  local line_num=0
  local prev_line=""
  local in_block_comment=false

  while IFS= read -r line || [[ -n "$line" ]]; do
    line_num=$((line_num + 1))

    local stripped
    stripped=$(strip_comment_segments "$line" "$in_block_comment")
    in_block_comment="${stripped%%$'\t'*}"
    local scan_line="${stripped#*$'\t'}"

    if [[ -z "${scan_line//[[:space:]]/}" ]]; then
      prev_line="$line"
      continue
    fi

    # Arbitrary font sizes: text-[44px], text-[15px], etc.
    if echo "$scan_line" | grep -qE 'text-\[([0-9]+(\.[0-9]+)?|\.[0-9]+)(px|rem|em)\]'; then
      if ! has_exception "$file" "$line_num" "$prev_line"; then
        local match
        match=$(echo "$scan_line" | grep -oE 'text-\[([0-9]+(\.[0-9]+)?|\.[0-9]+)(px|rem|em)\]' | sed -n '1p')
        report_violation "$file" "$line_num" "TYPOGRAPHY" \
          "Arbitrary font size" \
          "$match" \
          "Use typography scale: text-h1 (44px), text-h2 (36px), text-h3 (28px), text-h4 (22px), text-body (18px), text-small (15px)"
      fi
    fi

    # leading-none or leading-tight on body text (not headings)
    if echo "$scan_line" | grep -qE 'leading-(none|tight)' && ! echo "$scan_line" | grep -qE '(text-h[1-4]|text-(2xl|3xl|4xl|5xl))'; then
      if ! has_exception "$file" "$line_num" "$prev_line"; then
        local match
        match=$(echo "$scan_line" | grep -oE 'leading-(none|tight)' | sed -n '1p')
        report_violation "$file" "$line_num" "TYPOGRAPHY" \
          "Tight line-height on body text" \
          "$match" \
          "Use leading-relaxed (1.625) or leading-normal (1.5) for body text"
      fi
    fi
    prev_line="$line"
  done <<< "$content"
}

check_accessibility() {
  local file="$1"
  local content="$2"
  local line_num=0
  local prev_line=""
  local in_block_comment=false
  local pending_outline_line=0
  local pending_outline_prev_line=""

  while IFS= read -r line || [[ -n "$line" ]]; do
    line_num=$((line_num + 1))

    local stripped
    stripped=$(strip_comment_segments "$line" "$in_block_comment")
    in_block_comment="${stripped%%$'\t'*}"
    local scan_line="${stripped#*$'\t'}"

    if [[ -z "${scan_line//[[:space:]]/}" ]]; then
      prev_line="$line"
      continue
    fi

    if [[ "$pending_outline_line" -gt 0 ]]; then
      if ! echo "$scan_line" | grep -qE 'focus-visible:|focus:ring|:focus-visible'; then
        if ! has_exception "$file" "$pending_outline_line" "$pending_outline_prev_line"; then
          report_violation "$file" "$pending_outline_line" "A11Y" \
            "Focus outline removed without replacement" \
            "outline-none" \
            "Add focus-visible:ring-2 focus-visible:ring-offset-2"
        fi
      fi
      pending_outline_line=0
      pending_outline_prev_line=""
    fi

    # outline-none without focus-visible replacement
    if echo "$scan_line" | grep -qE 'outline-none|outline:[[:space:]]*none'; then
      if ! echo "$scan_line" | grep -qE 'focus-visible:|focus:ring|:focus-visible'; then
        pending_outline_line="$line_num"
        pending_outline_prev_line="$prev_line"
      fi
    fi
    prev_line="$line"
  done <<< "$content"

  if [[ "$pending_outline_line" -gt 0 ]]; then
    if ! has_exception "$file" "$pending_outline_line" "$pending_outline_prev_line"; then
      report_violation "$file" "$pending_outline_line" "A11Y" \
        "Focus outline removed without replacement" \
        "outline-none" \
        "Add focus-visible:ring-2 focus-visible:ring-offset-2"
    fi
  fi
}

# --- Main ---

main() {
  local files
  files=$(get_files)

  if [[ -z "$files" ]]; then
    if [[ "$JSON_OUTPUT" == true ]]; then
      echo '{"violations":[],"exceptions":0,"files_checked":0}'
    elif [[ "$QUIET" != true ]]; then
      echo -e "${DIM}No UI files found to check.${NC}"
    fi
    exit 0
  fi

  local file_count=0

  if [[ "$JSON_OUTPUT" != true && "$QUIET" != true ]]; then
    echo ""
    echo -e "${BOLD}Design System Lint${NC}"
    echo -e "${DIM}──────────────────────────────────────────${NC}"
    echo ""
  fi

  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    if [[ "$STAGED" != true && ! -f "$file" ]]; then
      continue
    fi
    file_count=$((file_count + 1))
    local file_content
    file_content=$(read_file_content "$file")

    check_spacing "$file" "$file_content"
    check_color "$file" "$file_content"
    check_typography "$file" "$file_content"
    check_accessibility "$file" "$file_content"
  done <<< "$files"

  # --- Output ---
  if [[ "$JSON_OUTPUT" == true ]]; then
    echo -n '{"violations":['
    local first=true
    for v in "${VIOLATIONS_JSON[@]+"${VIOLATIONS_JSON[@]}"}"; do
      if [[ "$first" == true ]]; then
        first=false
      else
        echo -n ","
      fi
      echo -n "$v"
    done
    echo -n "],\"exceptions\":$EXCEPTION_COUNT,\"files_checked\":$file_count,\"violation_count\":$VIOLATION_COUNT}"
    echo ""
  elif [[ "$QUIET" == true ]]; then
    echo "$VIOLATION_COUNT violations, $EXCEPTION_COUNT exceptions in $file_count files"
  else
    echo -e "${DIM}──────────────────────────────────────────${NC}"

    if [[ "$VIOLATION_COUNT" -eq 0 ]]; then
      echo -e "${GREEN}✓ No design system violations${NC} ($file_count files checked)"
    else
      echo -e "${RED}✗ $VIOLATION_COUNT violation(s)${NC} in $file_count files"
    fi

    if [[ "$EXCEPTION_COUNT" -gt 0 ]]; then
      echo -e "${YELLOW}  $EXCEPTION_COUNT exception(s) with ds-exception markers${NC}"
    fi

    echo ""
  fi

  # Exit code
  if [[ "$STRICT" == true && "$VIOLATION_COUNT" -gt 0 ]]; then
    exit 1
  fi

  exit 0
}

main
