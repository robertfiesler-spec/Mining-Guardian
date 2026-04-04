#!/usr/bin/env bash
# Browser-based visual verification using agent-browser
# Usage: ./browser-verify.sh [OPTIONS] <url>
#
# This script:
# 1. Checks for agent-browser CLI (installs if missing)
# 2. Opens the URL in a headless browser
# 3. Captures screenshot and accessibility snapshot
# 4. Optionally compares against baseline
# 5. Reports results

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# Configuration defaults
DEFAULT_DEV_SERVER_URL="http://localhost:3000"
DEFAULT_DEV_SERVER_CMD="npm run dev"
DEFAULT_VIEWPORT_WIDTH=1280
DEFAULT_VIEWPORT_HEIGHT=720
DEFAULT_TIMEOUT=30000

# Script directory and project root detection
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect if we're in an installed toolkit (.claude/scripts/) or source (scripts/)
if [[ "$SCRIPT_DIR" == *".claude/scripts"* ]]; then
    # Installed toolkit - project root is parent of .claude
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
    VISUAL_DIR="$PROJECT_ROOT/.claude/visual"
else
    # Source toolkit - use current directory as project root
    PROJECT_ROOT="$(pwd)"
    VISUAL_DIR="$PROJECT_ROOT/.claude/visual"
fi

# Options
URL=""
ROUTE_NAME=""
COMPARE_BASELINE=false
UPDATE_BASELINE=false
CAPTURE_SNAPSHOT=true
FULL_PAGE=false
VERBOSE=false
QUIET=false
DRY_RUN=false
STRICT=false
SESSION_ID=""

# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════

print_help() {
    cat << 'EOF'
Browser-based visual verification using agent-browser

USAGE:
    browser-verify.sh [OPTIONS] <url>

ARGUMENTS:
    <url>               URL to verify (e.g., http://localhost:3000/login)

OPTIONS:
    --route <name>      Name for this route (default: derived from URL path)
    --compare           Compare against existing baseline
    --update-baseline   Accept current screenshot as new baseline
    --no-snapshot       Skip accessibility tree snapshot
    --full              Capture full-page screenshot
    --strict            Exit with error on visual regression
    --session <id>      Use specific browser session ID
    --viewport <WxH>    Set viewport size (default: 1280x720)
    --timeout <ms>      Wait timeout in milliseconds (default: 30000)
    -v, --verbose       Show detailed output
    -q, --quiet         Minimal output
    -n, --dry-run       Show what would be done without executing
    -h, --help          Show this help message

ENVIRONMENT VARIABLES:
    DEV_SERVER_URL      Dev server URL (default: http://localhost:3000)
    DEV_SERVER_CMD      Command to start dev server (default: npm run dev)

EXAMPLES:
    # Basic screenshot capture
    browser-verify.sh http://localhost:3000/login

    # Compare against baseline
    browser-verify.sh --compare http://localhost:3000/login

    # Update baseline with current state
    browser-verify.sh --update-baseline http://localhost:3000/login

    # Full-page screenshot with custom route name
    browser-verify.sh --full --route dashboard-main http://localhost:3000/dashboard

OUTPUT:
    Screenshots saved to: .claude/visual/current/
    Baselines stored in:  .claude/visual/baselines/
    Snapshots saved to:   .claude/visual/snapshots/
    Diffs generated in:   .claude/visual/diffs/
EOF
}

log_info() {
    if [ "$QUIET" = false ]; then
        echo -e "${BLUE}$1${NC}"
    fi
}

log_success() {
    if [ "$QUIET" = false ]; then
        echo -e "${GREEN}$1${NC}"
    fi
}

log_warn() {
    echo -e "${YELLOW}$1${NC}"
}

log_error() {
    echo -e "${RED}$1${NC}" >&2
}

log_verbose() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${GRAY}$1${NC}"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Agent-Browser Detection
# ═══════════════════════════════════════════════════════════════════════════════

check_agent_browser() {
    # Check if agent-browser is available
    if command -v agent-browser &> /dev/null; then
        log_verbose "agent-browser found: $(which agent-browser)"
        return 0
    fi

    # Check in node_modules
    if [ -f "$PROJECT_ROOT/node_modules/.bin/agent-browser" ]; then
        log_verbose "agent-browser found in node_modules"
        export PATH="$PROJECT_ROOT/node_modules/.bin:$PATH"
        return 0
    fi

    # Not found
    return 1
}

install_agent_browser() {
    log_info "agent-browser not found. Attempting to install..."

    if [ ! -f "$PROJECT_ROOT/package.json" ]; then
        log_error "No package.json found. Cannot install agent-browser."
        log_error "Please install manually: npm install -g agent-browser"
        return 1
    fi

    # Try to install as dev dependency
    if command -v npm &> /dev/null; then
        log_info "Installing agent-browser as dev dependency..."
        (cd "$PROJECT_ROOT" && npm install -D agent-browser) || {
            log_error "Failed to install agent-browser"
            return 1
        }

        # Run browser install
        log_info "Installing browser dependencies..."
        (cd "$PROJECT_ROOT" && npx agent-browser install) || {
            log_warn "Browser install may have failed. You may need to run: npx agent-browser install --with-deps"
        }

        export PATH="$PROJECT_ROOT/node_modules/.bin:$PATH"
        return 0
    fi

    log_error "npm not found. Please install agent-browser manually."
    return 1
}

# ═══════════════════════════════════════════════════════════════════════════════
# URL and Route Handling
# ═══════════════════════════════════════════════════════════════════════════════

# Extract route name from URL
derive_route_name() {
    local url="$1"

    # Extract path from URL
    local path
    path=$(echo "$url" | sed -E 's|^https?://[^/]+||' | sed 's|^/||' | sed 's|/$||')

    # Replace slashes with dashes, handle empty path as "index"
    if [ -z "$path" ]; then
        echo "index"
    else
        echo "$path" | tr '/' '-' | tr '?' '-' | tr '&' '-'
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Directory Setup
# ═══════════════════════════════════════════════════════════════════════════════

ensure_directories() {
    mkdir -p "$VISUAL_DIR/baselines"
    mkdir -p "$VISUAL_DIR/snapshots"
    mkdir -p "$VISUAL_DIR/current"
    mkdir -p "$VISUAL_DIR/diffs"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Browser Operations
# ═══════════════════════════════════════════════════════════════════════════════

# Generate timestamp for file naming
get_timestamp() {
    date +"%Y%m%d-%H%M%S"
}

# Capture screenshot and snapshot
capture_visual() {
    local url="$1"
    local route="$2"
    local timestamp
    timestamp=$(get_timestamp)

    local screenshot_file="$VISUAL_DIR/current/${route}-${timestamp}.png"
    local snapshot_file="$VISUAL_DIR/snapshots/${route}-${timestamp}.json"

    log_info "Capturing visual state for: $route"
    log_verbose "URL: $url"
    log_verbose "Screenshot: $screenshot_file"

    if [ "$DRY_RUN" = true ]; then
        echo "Would capture screenshot: $screenshot_file"
        echo "Would capture snapshot: $snapshot_file"
        return 0
    fi

    local session_arg=""
    if [ -n "$SESSION_ID" ]; then
        session_arg="--session $SESSION_ID"
    fi

    # Build viewport argument
    local viewport_arg="--viewport ${VIEWPORT_WIDTH}x${VIEWPORT_HEIGHT}"

    # Open URL with viewport settings
    log_verbose "Opening URL..."
    log_verbose "Viewport: ${VIEWPORT_WIDTH}x${VIEWPORT_HEIGHT}"
    agent-browser $session_arg open "$url" $viewport_arg || {
        log_error "Failed to open URL: $url"
        return 1
    }

    # Wait for page to be ready (network idle)
    # Convert timeout from ms to seconds for basic wait (capped at reasonable wait time)
    local wait_seconds=$(( TIMEOUT_MS / 1000 ))
    if [ "$wait_seconds" -lt 1 ]; then
        wait_seconds=1
    elif [ "$wait_seconds" -gt 10 ]; then
        wait_seconds=10  # Cap wait at 10s; agent-browser handles additional waiting
    fi
    log_verbose "Waiting ${wait_seconds}s for page to load (timeout: ${TIMEOUT_MS}ms)..."
    sleep "$wait_seconds"

    # Capture screenshot
    log_verbose "Capturing screenshot..."
    local screenshot_args=""
    if [ "$FULL_PAGE" = true ]; then
        screenshot_args="--full"
    fi

    agent-browser $session_arg screenshot "$screenshot_file" $screenshot_args || {
        log_error "Failed to capture screenshot"
        agent-browser $session_arg close 2>/dev/null || true
        return 1
    }

    log_success "  Screenshot: $screenshot_file"

    # Capture accessibility snapshot
    if [ "$CAPTURE_SNAPSHOT" = true ]; then
        log_verbose "Capturing accessibility snapshot..."
        agent-browser $session_arg snapshot > "$snapshot_file" 2>/dev/null || {
            log_warn "Failed to capture accessibility snapshot"
        }

        if [ -f "$snapshot_file" ] && [ -s "$snapshot_file" ]; then
            log_success "  Snapshot: $snapshot_file"
        fi
    fi

    # Close browser (unless using persistent session)
    if [ -z "$SESSION_ID" ]; then
        agent-browser close 2>/dev/null || true
    fi

    # Export paths for comparison
    export CAPTURED_SCREENSHOT="$screenshot_file"
    export CAPTURED_SNAPSHOT="$snapshot_file"

    return 0
}

# ═══════════════════════════════════════════════════════════════════════════════
# Baseline Comparison
# ═══════════════════════════════════════════════════════════════════════════════

compare_with_baseline() {
    local route="$1"
    local current_screenshot="$2"

    local baseline_screenshot="$VISUAL_DIR/baselines/${route}.png"

    if [ ! -f "$baseline_screenshot" ]; then
        log_warn "No baseline found for route: $route"
        log_info "Run with --update-baseline to create one"
        return 0
    fi

    log_info "Comparing against baseline..."

    # Check if ImageMagick is available for comparison
    if ! command -v compare &> /dev/null; then
        log_warn "ImageMagick not installed. Skipping visual diff."
        log_info "Install with: brew install imagemagick (macOS) or apt install imagemagick (Linux)"

        # Fall back to simple checksum comparison
        local baseline_hash current_hash
        baseline_hash=$(shasum -a 256 "$baseline_screenshot" | cut -d' ' -f1)
        current_hash=$(shasum -a 256 "$current_screenshot" | cut -d' ' -f1)

        if [ "$baseline_hash" = "$current_hash" ]; then
            log_success "  Visual: UNCHANGED (checksum match)"
            return 0
        else
            log_warn "  Visual: CHANGED (checksum mismatch)"
            if [ "$STRICT" = true ]; then
                return 1
            fi
            return 0
        fi
    fi

    # Generate diff image
    local timestamp
    timestamp=$(get_timestamp)
    local diff_file="$VISUAL_DIR/diffs/${route}-diff-${timestamp}.png"

    # Compare images and get difference metric
    local diff_result
    diff_result=$(compare -metric AE "$baseline_screenshot" "$current_screenshot" "$diff_file" 2>&1) || true

    # Parse the diff count (number of different pixels)
    local diff_pixels
    diff_pixels=$(echo "$diff_result" | grep -oE '^[0-9]+' || echo "0")

    if [ "$diff_pixels" = "0" ]; then
        log_success "  Visual: UNCHANGED"
        rm -f "$diff_file"  # No diff needed
        return 0
    else
        log_warn "  Visual: CHANGED ($diff_pixels pixels differ)"
        log_info "  Diff image: $diff_file"

        if [ "$STRICT" = true ]; then
            log_error "Visual regression detected in strict mode"
            return 1
        fi

        return 0
    fi
}

update_baseline() {
    local route="$1"
    local current_screenshot="$2"

    local baseline_screenshot="$VISUAL_DIR/baselines/${route}.png"

    if [ "$DRY_RUN" = true ]; then
        echo "Would update baseline: $baseline_screenshot"
        return 0
    fi

    cp "$current_screenshot" "$baseline_screenshot"
    log_success "  Baseline updated: $baseline_screenshot"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

main() {
    # Browser configuration (exported for use in capture_visual)
    VIEWPORT_WIDTH=$DEFAULT_VIEWPORT_WIDTH
    VIEWPORT_HEIGHT=$DEFAULT_VIEWPORT_HEIGHT
    TIMEOUT_MS=$DEFAULT_TIMEOUT

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --route)
                ROUTE_NAME="$2"
                shift 2
                ;;
            --compare)
                COMPARE_BASELINE=true
                shift
                ;;
            --update-baseline)
                UPDATE_BASELINE=true
                shift
                ;;
            --no-snapshot)
                CAPTURE_SNAPSHOT=false
                shift
                ;;
            --full)
                FULL_PAGE=true
                shift
                ;;
            --strict)
                STRICT=true
                shift
                ;;
            --session)
                SESSION_ID="$2"
                shift 2
                ;;
            --viewport)
                VIEWPORT_WIDTH=$(echo "$2" | cut -d'x' -f1)
                VIEWPORT_HEIGHT=$(echo "$2" | cut -d'x' -f2)
                shift 2
                ;;
            --timeout)
                TIMEOUT_MS="$2"
                shift 2
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -q|--quiet)
                QUIET=true
                shift
                ;;
            -n|--dry-run)
                DRY_RUN=true
                shift
                ;;
            -h|--help)
                print_help
                exit 0
                ;;
            -*)
                log_error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
            *)
                if [ -z "$URL" ]; then
                    URL="$1"
                else
                    log_error "Unexpected argument: $1"
                    exit 1
                fi
                shift
                ;;
        esac
    done

    # Validate URL
    if [ -z "$URL" ]; then
        log_error "Error: URL required"
        echo ""
        echo "Usage: browser-verify.sh [OPTIONS] <url>"
        echo "Use --help for full options"
        exit 1
    fi

    # Derive route name if not provided
    if [ -z "$ROUTE_NAME" ]; then
        ROUTE_NAME=$(derive_route_name "$URL")
    fi

    # Header
    if [ "$QUIET" = false ]; then
        echo ""
        echo -e "${BLUE}══════════════════════════════════════════════════════════════${NC}"
        echo -e "${BLUE}Browser Visual Verification${NC}"
        echo -e "${BLUE}══════════════════════════════════════════════════════════════${NC}"
        echo ""
        echo "  URL:      $URL"
        echo "  Route:    $ROUTE_NAME"
        echo "  Viewport: ${VIEWPORT_WIDTH}x${VIEWPORT_HEIGHT}"
        echo "  Timeout:  ${TIMEOUT_MS}ms"
        if [ "$DRY_RUN" = true ]; then
            echo -e "  Mode:     ${YELLOW}Dry run${NC}"
        fi
        echo ""
    fi

    # Ensure directories exist
    ensure_directories

    # Check for agent-browser
    if ! check_agent_browser; then
        if [ "$DRY_RUN" = true ]; then
            log_warn "agent-browser not found (would attempt install)"
        else
            install_agent_browser || {
                log_error "Could not set up agent-browser"
                log_info "Visual verification skipped"
                exit 0  # Soft failure - don't block workflow
            }
        fi
    fi

    # Capture visual state
    capture_visual "$URL" "$ROUTE_NAME" || {
        log_error "Failed to capture visual state"
        exit 1
    }

    # Compare with baseline if requested
    if [ "$COMPARE_BASELINE" = true ]; then
        compare_with_baseline "$ROUTE_NAME" "$CAPTURED_SCREENSHOT" || {
            if [ "$STRICT" = true ]; then
                exit 1
            fi
        }
    fi

    # Update baseline if requested
    if [ "$UPDATE_BASELINE" = true ]; then
        update_baseline "$ROUTE_NAME" "$CAPTURED_SCREENSHOT"
    fi

    # Summary
    echo ""
    log_success "Visual verification complete"
    echo ""
}

# Run main
main "$@"
