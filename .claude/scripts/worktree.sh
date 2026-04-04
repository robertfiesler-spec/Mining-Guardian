#!/usr/bin/env bash
#
# worktree.sh - Create a git worktree with branch, deps, and env symlinks
#
# Standalone worktree setup extracted from multitask.sh. Creates an isolated
# working directory for a feature branch without spawning an autonomous loop.
#
# Usage: ./scripts/worktree.sh <branch-name> [OPTIONS]
#
# Options:
#   --cleanup              Remove worktree if it already exists
#   --no-install           Skip dependency installation
#   --no-env               Skip .env/.env.local symlinks
#   --copy-env             Copy env files instead of symlinking
#   --cd                   Print the worktree path (for cd integration)
#
# Examples:
#   ./scripts/worktree.sh feature/auth-flow
#   ./scripts/worktree.sh feature/auth-flow --cleanup
#   cd $(./scripts/worktree.sh feature/auth-flow --cd)

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "  ${BLUE}*${NC} $1" >&2; }
log_success() { echo -e "  ${GREEN}+${NC} $1" >&2; }
log_warn()    { echo -e "  ${YELLOW}!${NC} $1" >&2; }
log_error()   { echo -e "  ${RED}x${NC} $1" >&2; }

# Defaults
CLEANUP=false
INSTALL_DEPS=true
LINK_ENV=true
COPY_ENV=false
CD_MODE=false
BRANCH=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --cleanup)    CLEANUP=true; shift ;;
    --no-install) INSTALL_DEPS=false; shift ;;
    --no-env)     LINK_ENV=false; shift ;;
    --copy-env)   COPY_ENV=true; shift ;;
    --cd)         CD_MODE=true; shift ;;
    --help|-h)
      echo "Usage: $0 <branch-name> [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --cleanup      Remove worktree if it already exists"
      echo "  --no-install   Skip dependency installation"
      echo "  --no-env       Skip .env/.env.local symlinks"
      echo "  --copy-env     Copy env files instead of symlinking"
      echo "  --cd           Print the worktree path only (for cd integration)"
      echo "  --help         Show this help"
      exit 0
      ;;
    -*)
      log_error "Unknown option: $1"
      exit 1
      ;;
    *)
      if [[ -z "$BRANCH" ]]; then
        BRANCH="$1"
      else
        log_error "Unexpected argument: $1"
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "$BRANCH" ]]; then
  log_error "Branch name required"
  echo "Usage: $0 <branch-name> [OPTIONS]"
  exit 1
fi

# Ensure we're in a git repo
if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
  log_error "Not in a git repository"
  exit 1
fi

REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_NAME=$(basename "$REPO_ROOT")
PARENT_DIR=$(dirname "$REPO_ROOT")
BRANCH_SUFFIX=$(echo "$BRANCH" | sed 's/\//-/g')
WORKTREE_PATH="$PARENT_DIR/${REPO_NAME}-wt-${BRANCH_SUFFIX}"

# In --cd mode, just print path and exit if worktree exists
if [[ "$CD_MODE" == true && -d "$WORKTREE_PATH" ]]; then
  echo "$WORKTREE_PATH"
  exit 0
fi

# Handle existing worktree
if [[ -d "$WORKTREE_PATH" ]]; then
  if [[ "$CLEANUP" == true ]]; then
    log_warn "Removing existing worktree: $WORKTREE_PATH"
    git worktree remove "$WORKTREE_PATH" --force 2>/dev/null || true
    rm -rf "$WORKTREE_PATH"
  else
    log_error "Worktree already exists: $WORKTREE_PATH"
    log_info "Use --cleanup to remove it first, or --cd to get the path"
    exit 1
  fi
fi

if [[ "$CD_MODE" != true ]]; then
  echo -e "${BLUE}Creating worktree${NC}"
  echo -e "  Branch: ${GREEN}$BRANCH${NC}"
  echo -e "  Path:   ${GREEN}$WORKTREE_PATH${NC}"
  echo ""
fi

# Create worktree + branch
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  log_info "Branch exists, checking out: $BRANCH"
  git worktree add "$WORKTREE_PATH" "$BRANCH"
else
  log_info "Creating new branch: $BRANCH"
  git worktree add "$WORKTREE_PATH" -b "$BRANCH"
fi

# Symlink or copy env files
if [[ "$LINK_ENV" == true ]]; then
  for env_file in .env .env.local; do
    if [[ -f "$REPO_ROOT/$env_file" ]]; then
      if [[ "$COPY_ENV" == true ]]; then
        cp "$REPO_ROOT/$env_file" "$WORKTREE_PATH/$env_file"
        log_info "Copied $env_file"
      else
        ln -sf "$REPO_ROOT/$env_file" "$WORKTREE_PATH/$env_file"
        log_info "Symlinked $env_file"
      fi
    fi
  done
fi

# Install dependencies
if [[ "$INSTALL_DEPS" == true ]]; then
  log_info "Installing dependencies..."
  if (
    cd "$WORKTREE_PATH"

    if [[ -f "pnpm-lock.yaml" ]]; then
      pnpm install > /dev/null 2>&1
    elif [[ -f "package-lock.json" ]]; then
      npm install > /dev/null 2>&1
    elif [[ -f "yarn.lock" ]]; then
      yarn install > /dev/null 2>&1
    elif [[ -f "bun.lockb" || -f "bun.lock" ]]; then
      bun install > /dev/null 2>&1
    elif [[ -f "package.json" ]]; then
      npm install > /dev/null 2>&1
    else
      exit 10
    fi
  ); then
    log_success "Dependencies installed"
  else
    install_status=$?
    if [[ "$install_status" -eq 10 ]]; then
      log_info "No supported Node dependency file found, skipping install"
    else
      exit "$install_status"
    fi
  fi
fi

if [[ "$CD_MODE" == true ]]; then
  echo "$WORKTREE_PATH"
else
  echo ""
  log_success "Worktree ready: $WORKTREE_PATH"
  echo ""
  echo -e "  ${BLUE}Next steps:${NC}"
  echo -e "    cd $WORKTREE_PATH"
  echo -e "    /create-plan   # Plan your feature"
  echo -e "    /iterate       # Start implementation"
fi
