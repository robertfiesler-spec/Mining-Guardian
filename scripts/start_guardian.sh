#!/bin/zsh
# Mining Guardian startup script
# Used by launchd to load credentials before starting the daemon

REPO="/Users/BigBobby/Documents/GitHub/Mining Gaurdian"

# Load credentials from .env
set -a
source "$REPO/.env"
set +a

# Run Mining Guardian in loop mode
exec "$REPO/venv/bin/python" "$REPO/mining_guardian.py" --loop
