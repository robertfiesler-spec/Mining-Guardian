#!/usr/bin/env bash
# Self-update AI Toolkit from remote repository
# Usage: ./self-update.sh [OPTIONS]
#
# This script:
# 1. Reads repository URL from .toolkit-manifest.json
# 2. Clones the latest version from main branch to temp directory
# 3. Runs update.sh from the fresh clone
# 4. Cleans up temp directory
#
# Run from project directory that has .claude/ installed

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default options
DRY_RUN=false
FORCE=false
SKIP_CONFLICTS=false
VERBOSE=false
QUIET=false
BRANCH="main"

# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════

print_help() {
    cat << 'EOF'
Self-update AI Toolkit from remote repository

USAGE:
    self-update.sh [OPTIONS]

OPTIONS:
    -n, --dry-run         Show what would change without making changes
    -f, --force           Skip all prompts, overwrite everything (with backups)
    --skip-conflicts      Skip files with conflicts (user customizations preserved)
    -b, --branch <name>   Branch to update from (default: main)
    -v, --verbose         Show detailed output
    -q, --quiet           Minimal output
    -h, --help            Show this help message

EXAMPLES:
    # Preview changes
    self-update.sh --dry-run

    # Update from main branch
    self-update.sh

    # Update and preserve all customizations
    self-update.sh --skip-conflicts

    # Update from a specific branch
    self-update.sh --branch develop

REQUIREMENTS:
    - Run from a project directory with .claude/ installed
    - Git must be available
    - Internet connection to clone from remote

FILES:
    .claude/.toolkit-manifest.json - Contains repository URL
    .claude/.toolkit-version       - Current installed version
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
        echo -e "${CYAN}$1${NC}"
    fi
}

# Cleanup function for trap
cleanup() {
    if [ -n "${TEMP_DIR:-}" ] && [ -d "$TEMP_DIR" ]; then
        log_verbose "Cleaning up temp directory: $TEMP_DIR"
        rm -rf "$TEMP_DIR"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Detection Functions
# ═══════════════════════════════════════════════════════════════════════════════

# Find the toolkit installation directory
find_installation() {
    local dir="$1"

    if [ -d "$dir/.claude" ] && [ -f "$dir/.claude/.toolkit-manifest.json" ]; then
        echo "$dir/.claude"
        return 0
    fi

    # Check for legacy .ai installation
    if [ -d "$dir/.ai" ] && [ -f "$dir/.ai/.toolkit-manifest.json" ]; then
        echo "$dir/.ai"
        return 0
    fi

    return 1
}

# Get repository URL from manifest
get_repository_url() {
    local manifest_file="$1"

    if [ -f "$manifest_file" ]; then
        grep '"repository"' "$manifest_file" 2>/dev/null | sed 's/.*: *"\([^"]*\)".*/\1/' | head -1
    fi
}

# Get current version from version file
get_current_version() {
    local install_dir="$1"

    if [ -f "$install_dir/.toolkit-version" ]; then
        cat "$install_dir/.toolkit-version"
    else
        echo "unknown"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Main Update Process
# ═══════════════════════════════════════════════════════════════════════════════

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -n|--dry-run)
                DRY_RUN=true
                shift
                ;;
            -f|--force)
                FORCE=true
                shift
                ;;
            --skip-conflicts)
                SKIP_CONFLICTS=true
                shift
                ;;
            -b|--branch)
                BRANCH="$2"
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
                log_error "Unexpected argument: $1"
                exit 1
                ;;
        esac
    done

    # Set up cleanup trap
    trap cleanup EXIT

    # Find project directory (current directory)
    local project_dir
    project_dir="$(pwd)"

    # Header
    if [ "$QUIET" = false ]; then
        echo ""
        echo -e "${BLUE}══════════════════════════════════════════════════════════════${NC}"
        echo -e "${BLUE}AI Toolkit Self-Update${NC}"
        echo -e "${BLUE}══════════════════════════════════════════════════════════════${NC}"
        echo ""
    fi

    # Find installation
    local install_dir
    if ! install_dir=$(find_installation "$project_dir"); then
        log_error "No toolkit installation found in current directory"
        echo ""
        echo "Expected to find .claude/.toolkit-manifest.json"
        echo "Make sure you're in a project directory with the toolkit installed."
        exit 1
    fi

    log_info "Installation found: $install_dir"

    # Get repository URL
    local manifest_file="$install_dir/.toolkit-manifest.json"
    local repo_url
    repo_url=$(get_repository_url "$manifest_file")

    if [ -z "$repo_url" ]; then
        log_error "No repository URL found in manifest"
        echo ""
        echo "The manifest file doesn't contain a repository URL."
        echo "This may be an older installation. Try reinstalling the toolkit."
        exit 1
    fi

    # Get current version
    local current_version
    current_version=$(get_current_version "$install_dir")

    log_info "Current version: $current_version"
    log_info "Repository: $repo_url"
    log_info "Branch: $BRANCH"
    echo ""

    # Check git is available
    if ! command -v git &> /dev/null; then
        log_error "Git is not installed or not in PATH"
        exit 1
    fi

    # Create temp directory
    TEMP_DIR=$(mktemp -d)
    log_verbose "Created temp directory: $TEMP_DIR"

    # Clone repository (shallow clone for speed)
    log_info "Fetching latest from remote..."

    if ! git clone --depth 1 --branch "$BRANCH" "$repo_url" "$TEMP_DIR/ai-toolkit" 2>&1; then
        log_error "Failed to clone repository"
        echo ""
        echo "Could not fetch from: $repo_url"
        echo "Check your internet connection and repository access."
        exit 1
    fi

    local cloned_dir="$TEMP_DIR/ai-toolkit"

    # Get new version from cloned repo
    local new_version="unknown"
    if [ -f "$cloned_dir/config.json" ]; then
        new_version=$(grep '"version"' "$cloned_dir/config.json" | sed 's/.*: *"\([^"]*\)".*/\1/' | head -1)
    fi

    log_success "Fetched version: $new_version"
    echo ""

    # Check if update.sh exists in cloned repo
    if [ ! -f "$cloned_dir/scripts/update.sh" ]; then
        log_error "update.sh not found in cloned repository"
        exit 1
    fi

    # Build update.sh arguments
    local update_args=()

    if [ "$DRY_RUN" = true ]; then
        update_args+=("--dry-run")
    fi

    if [ "$FORCE" = true ]; then
        update_args+=("--force")
    fi

    if [ "$SKIP_CONFLICTS" = true ]; then
        update_args+=("--skip-conflicts")
    fi

    if [ "$VERBOSE" = true ]; then
        update_args+=("--verbose")
    fi

    if [ "$QUIET" = true ]; then
        update_args+=("--quiet")
    fi

    # Run update.sh from the cloned repository
    log_info "Running update..."
    echo ""

    # Make update.sh executable
    chmod +x "$cloned_dir/scripts/update.sh"

    # Execute update.sh with project directory as target
    if "$cloned_dir/scripts/update.sh" "${update_args[@]}" "$project_dir"; then
        echo ""
        log_success "Self-update complete!"

        if [ "$DRY_RUN" = true ]; then
            echo ""
            echo "This was a dry run. No changes were made."
            echo "Run without --dry-run to apply changes."
        fi
    else
        local exit_code=$?
        log_error "Update failed with exit code: $exit_code"
        exit $exit_code
    fi
}

# Run main
main "$@"
