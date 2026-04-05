#!/bin/zsh
# ============================================================
# Mining Guardian — Customer Setup Script
# BiXBiT USA
#
# Run this once on a new Mac Mini to fully configure and
# activate Mining Guardian for a customer site.
#
# Usage:
#   zsh setup.sh
# ============================================================

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$REPO_DIR/venv"
ENV_FILE="$REPO_DIR/.env"
CONFIG_FILE="$REPO_DIR/config.json"
PLIST_SRC="$REPO_DIR/com.bixbit.mining-guardian.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.bixbit.mining-guardian.plist"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

divider() { echo "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}" }
ok()      { echo "${GREEN}  ✅ $1${NC}" }
warn()    { echo "${YELLOW}  ⚠️  $1${NC}" }
fail()    { echo "${RED}  ❌ $1${NC}"; exit 1 }
step()    { echo "\n${BOLD}$1${NC}" }

clear
echo ""
echo "${BOLD}  ██████╗ ██╗██╗  ██╗██████╗ ██╗████████╗${NC}"
echo "${BOLD}  ██╔══██╗██║╚██╗██╔╝██╔══██╗██║╚══██╔══╝${NC}"
echo "${BOLD}  ██████╔╝██║ ╚███╔╝ ██████╔╝██║   ██║   ${NC}"
echo "${BOLD}  ██╔══██╗██║ ██╔██╗ ██╔══██╗██║   ██║   ${NC}"
echo "${BOLD}  ██████╔╝██║██╔╝ ██╗██████╔╝██║   ██║   ${NC}"
echo "${BOLD}  ╚═════╝ ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝   ╚═╝  ${NC}"
echo ""
echo "  ${BOLD}Mining Guardian — Customer Setup${NC}"
echo "  BiXBiT USA"
divider

# ── Step 1: Collect customer info ─────────────────────────
step "STEP 1 — Customer Information"
echo ""
read "CUSTOMER_NAME?  Customer / Site name (e.g. AltaVista Mine II): "
read "AMS_URL?  AMS base URL (default: https://api.bixbit.io/api/v1): "
AMS_URL=${AMS_URL:-"https://api.bixbit.io/api/v1"}
read "AMS_EMAIL?  AMS email address: "
read "AMS_PASSWORD?  AMS password: "
read "AMS_WORKSPACE_ID?  AMS workspace ID (number): "
read "SLACK_WEBHOOK_URL?  Slack webhook URL: "
read "SCAN_INTERVAL?  Scan interval in seconds (default: 300): "
SCAN_INTERVAL=${SCAN_INTERVAL:-300}

echo ""
ok "Got it. Setting up Mining Guardian for: $CUSTOMER_NAME"

# ── Step 2: Check Python ──────────────────────────────────
step "STEP 2 — Checking Python"
if ! command -v python3 &>/dev/null; then
  fail "Python 3 not found. Install it from https://python.org and re-run this script."
fi
PYTHON_VERSION=$(python3 --version)
ok "$PYTHON_VERSION found"

# ── Step 3: Create virtual environment ───────────────────
step "STEP 3 — Setting up Python environment"
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV" || fail "Failed to create virtual environment"
  ok "Virtual environment created"
else
  ok "Virtual environment already exists"
fi

"$VENV/bin/pip" install --quiet requests websocket-client python-dotenv slack-sdk fastapi uvicorn || fail "Failed to install dependencies"
ok "Dependencies installed"

# ── Step 4: Write .env file ───────────────────────────────
step "STEP 4 — Writing credentials"
cat > "$ENV_FILE" << EOF
AMS_EMAIL=$AMS_EMAIL
AMS_PASSWORD=$AMS_PASSWORD
AMS_WORKSPACE_ID=$AMS_WORKSPACE_ID
SLACK_WEBHOOK_URL=$SLACK_WEBHOOK_URL
EOF
chmod 600 "$ENV_FILE"
ok "Credentials saved to .env (chmod 600 — private)"

# ── Step 5: Write config.json ─────────────────────────────
step "STEP 5 — Writing configuration"
cat > "$CONFIG_FILE" << EOF
{
  "ams_base_url": "$AMS_URL",
  "ams_email": "env:AMS_EMAIL",
  "ams_password": "env:AMS_PASSWORD",
  "ams_workspace_id": "env:AMS_WORKSPACE_ID",
  "openclaw_webhook_url": null,
  "slack_webhook_url": "env:SLACK_WEBHOOK_URL",
  "dry_run": true,
  "scan_interval_seconds": $SCAN_INTERVAL,
  "approval_mode": "manual",
  "miner_filters": {},
  "rules": []
}
EOF
ok "config.json written (dry_run: true — safe by default)"

# ── Step 6: Create logs directory ────────────────────────
step "STEP 6 — Creating log directory"
mkdir -p "$REPO_DIR/logs"
ok "logs/ directory ready"

# ── Step 7: Test scan ─────────────────────────────────────
step "STEP 7 — Running test scan"
echo "  Connecting to AMS and scanning miners..."
set -a; source "$ENV_FILE"; set +a
TEST_OUTPUT=$("$VENV/bin/python" "$REPO_DIR/mining_guardian.py" 2>&1)
TEST_EXIT=$?

if [ $TEST_EXIT -eq 0 ]; then
  SCANNED=$(echo "$TEST_OUTPUT" | grep "Fetched.*miners total" | tail -1)
  ok "Test scan successful — $SCANNED"
else
  warn "Test scan returned an error. Check credentials and try again."
  echo "$TEST_OUTPUT" | tail -5
  echo ""
  read "CONTINUE?  Continue with setup anyway? [y/N]: "
  [[ "$CONTINUE" != "y" ]] && fail "Setup cancelled."
fi

# ── Step 8: Install launchd watchdog ─────────────────────
step "STEP 8 — Installing watchdog (auto-start on boot)"

# Update plist to use correct Python path for this machine
sed "s|/Users/BigBobby|$HOME|g" "$PLIST_SRC" > "$PLIST_DEST"

launchctl unload "$PLIST_DEST" 2>/dev/null
launchctl load "$PLIST_DEST" || warn "launchd registration failed — run manually if needed"
sleep 2

STATUS=$(launchctl list | grep mining-guardian)
if echo "$STATUS" | grep -q "0\s"; then
  ok "Watchdog active — Mining Guardian will start on boot and restart if it crashes"
else
  warn "Watchdog registered but check status: $STATUS"
fi

# ── Step 9: Post to Slack ─────────────────────────────────
step "STEP 9 — Notifying Slack"
SLACK_MSG="🛡️ *Mining Guardian is online*\n*Site:* $CUSTOMER_NAME\n*Status:* Connected to AMS ✅\n*Scan interval:* every ${SCAN_INTERVAL}s\n*Mode:* DRY RUN (no actions taken until enabled)\n\nFleet monitoring is now active. Scan reports will appear in this channel."

curl -s -X POST -H 'Content-type: application/json' \
  --data "{\"text\": \"$SLACK_MSG\"}" \
  "$SLACK_WEBHOOK_URL" > /dev/null && ok "Slack notified" || warn "Slack notification failed — check webhook URL"

# ── Done ─────────────────────────────────────────────────
divider
echo ""
echo "  ${GREEN}${BOLD}✅ Mining Guardian is live for: $CUSTOMER_NAME${NC}"
echo ""
echo "  ${BOLD}What happens now:${NC}"
echo "  • Mining Guardian scans every ${SCAN_INTERVAL}s automatically"
echo "  • Reports post to Slack after each scan"
echo "  • Logs saved to: $REPO_DIR/logs/"
echo "  • Database at:   $REPO_DIR/guardian.db"
echo ""
echo "  ${BOLD}When ready to enable live actions:${NC}"
echo "  Edit $CONFIG_FILE and set \"dry_run\": false"
echo ""
echo "  ${BOLD}To stop Mining Guardian:${NC}"
echo "  launchctl unload ~/Library/LaunchAgents/com.bixbit.mining-guardian.plist"
echo ""
divider
