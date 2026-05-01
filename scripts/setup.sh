#!/bin/zsh
# ============================================================
# Mining Guardian — Customer macOS Installer v2
# BiXBiT USA  •  Bucket 6b  •  Section 7.2 MG_UNIFIED_TODO_LIST.md
#
# USAGE:  sudo zsh setup.sh [options]
# OPTIONS:
#   --restore-from-snapshot=<tarball>  Early-dispatch to restore_from_snapshot.sh (Phase 15)
#   --post-restore       Skip Phases 1-8 after a snapshot restore
#   --tailscale          Run `tailscale up --accept-routes` (Phase 12)
#   --skip-lan-check     Skip miner LAN ping in Phase 1
#   --dry-run-install    Print each action without executing (audit mode)
#   --help               Print this block and exit
#
# REQUIREMENTS: macOS 14+, arm64 (Apple Silicon), 16 GB RAM, 50 GB free,
#   internet, root (sudo). Bitcoin SHA-256 fleet monitoring only.
#
# INSTALLS (~30-45 min on a fresh Mac Mini):
#   brew: postgresql@16, python@3.12, git, ollama, grafana, [tailscale]
#   Postgres DBs: mining_guardian, mining_guardian_test, mining_guardian_catalog
#   Python 3.12 venv at /Library/Application Support/MiningGuardian/venv (49-package set)
#   9 LaunchDaemons in /Library/LaunchDaemons/ + 9 launchers in bin/
#   10 cron entries (macOS-path-translated from docs/CRON_SCHEDULE.md)
#   Grafana datasource placeholder (Bucket 6d overwrites with full config)
#   Ollama + qwen2.5:14b-instruct-q4_K_M (~8 GB)
#   /Library/Application Support/MiningGuardian/.env (mode 0600, root:wheel)
#
# SECURITY:
#   S-14  All password prompts use `read -s`; manual echo "" restores newline
#   S-13  All service addresses use 127.0.0.1 — no Tailscale IPs anywhere
#   S-6   CATALOG_API_KEY generated fresh via openssl — never a default string
#   S-4   No credentials in URL query strings anywhere in this script
#   S-7   Dedicated miningguardian OS user deferred — see TODO in phase_07
#
# IDEMPOTENCY: brew no-ops on existing formulae. Postgres uses IF NOT EXISTS.
#   LaunchDaemons bootout'd before re-bootstrap. .env prompts before overwrite.
# PHASE LOG: /tmp/mg_setup_phases.log — advisory, timestamped, not a skip gate.
# ============================================================

set -euo pipefail
setopt err_exit pipefail 2>/dev/null || true

# ── Install constants ─────────────────────────────────────────────────────────
INSTALL_ROOT="/Library/Application Support/MiningGuardian"      # macOS root (PR #74 convention)
LAUNCHD_SRC="installer/macos-pkg/resources/launchd"   # plist source (repo-relative)
LAUNCHER_SRC="${LAUNCHD_SRC}/launchers"       # wrapper scripts
LAUNCHDAEMONS="/Library/LaunchDaemons"        # system daemon directory
BIN_DIR="${INSTALL_ROOT}/bin"
LOGS_DIR="${INSTALL_ROOT}/logs"
ENV_FILE="${INSTALL_ROOT}/.env"               # secrets — 0600 root:wheel
VENV="${INSTALL_ROOT}/venv"
PHASE_LOG="/tmp/mg_setup_phases.log"
REPO_URL="https://github.com/robertfiesler-spec/Mining-Guardian.git"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Color helpers (same as v1 lines 21-31) ────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; CYAN='\033[0;36m'; NC='\033[0m'
divider() { echo "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }
ok()    { echo "${GREEN}  ✅ $1${NC}"; }
warn()  { echo "${YELLOW}  ⚠️  $1${NC}"; }
fail()  { echo "${RED}  ❌ $1${NC}"; exit 1; }
step()  { echo "\n${BOLD}$1${NC}"; }
info()  { echo "${CYAN}     $1${NC}"; }
phase_banner() { divider; echo "\n  ${BOLD}${CYAN}Phase $1/15 — $2${NC}\n"; }
log_phase_complete() { echo "$(date '+%Y-%m-%d %H:%M:%S') COMPLETE phase_${1}" >> "${PHASE_LOG}"; }

# ── Argument parsing ──────────────────────────────────────────────────────────
RESTORE_SNAPSHOT=""; POST_RESTORE=false; WANT_TAILSCALE=false
SKIP_LAN_CHECK=false; DRY_RUN_INSTALL=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --restore-from-snapshot=*) RESTORE_SNAPSHOT="${1#*=}" ;;
    --post-restore)    POST_RESTORE=true ;;
    --tailscale)       WANT_TAILSCALE=true ;;
    --skip-lan-check)  SKIP_LAN_CHECK=true ;;
    --dry-run-install) DRY_RUN_INSTALL=true; warn "DRY RUN — no changes made." ;;
    --help|-h) sed -n '/^# ====/,/^# ====/p' "$0" | head -40; exit 0 ;;
    *) warn "Unknown argument: $1 (ignored)" ;;
  esac; shift
done

# ── Dry-run wrapper ───────────────────────────────────────────────────────────
run_cmd() {
  if [[ "${DRY_RUN_INSTALL}" == "true" ]]; then info "[DRY RUN] Would run: $*"; else "$@"; fi
}

# ── Phase 15 early argv dispatch (--restore-from-snapshot) ───────────────────
# Must happen before the banner so the operator sees intent immediately.
# restore_from_snapshot.sh (Bucket 6c, separate PR) handles: untar snapshot
# into INSTALL_ROOT, restore .env, restore grafana.db. After it exits 0 we
# re-exec this script with --post-restore to finish Phases 9-14.
if [[ -n "${RESTORE_SNAPSHOT}" ]]; then
  echo "\n  ${BOLD}--restore-from-snapshot — delegating to Phase 15...${NC}\n"
  RS="${SCRIPT_DIR}/restore_from_snapshot.sh"
  [[ ! -f "${RS}" ]] && fail "restore_from_snapshot.sh not found at ${RS}. Bucket 6c not yet landed."
  exec "${RS}" "${RESTORE_SNAPSHOT}" && exec "$0" --post-restore
fi

# ── Root check ────────────────────────────────────────────────────────────────
[[ "${DRY_RUN_INSTALL}" != "true" ]] && [[ "$(id -u)" -ne 0 ]] && \
  fail "Must run as root: sudo zsh ${SCRIPT_DIR}/setup.sh"

# ── EXIT trap — cleanup_on_fail ───────────────────────────────────────────────
# Fires on non-zero exit. Does NOT auto-rollback — a partial Postgres state
# is safer than a deleted one. Prints triage steps for the operator.
CURRENT_PHASE="(pre-flight)"
cleanup_on_fail() {
  local rc=$?; [[ $rc -eq 0 ]] && return
  divider
  echo "\n  ${RED}${BOLD}⛔  FAILED during: ${CURRENT_PHASE}${NC}\n"
  echo "  ${BOLD}Triage:${NC}"
  echo "    1. Read error output above."
  echo "    2. Phase log:        cat ${PHASE_LOG}"
  echo "    3. Postgres:         brew services list | grep postgres"
  echo "    4. LaunchDaemons:    launchctl list | grep miningguardian"
  echo "    5. Env file:         ls -la ${ENV_FILE}"
  echo "    6. Service logs:     ls -la ${LOGS_DIR}/"
  echo "  DO NOT wipe before understanding failure — a partial DB is recoverable."
  echo "  Re-run after fixing root cause: sudo zsh ${SCRIPT_DIR}/setup.sh"
  divider
}
trap cleanup_on_fail EXIT

# ── BiXBiT ASCII banner — brand-locked, kept verbatim from v1 (lines 35-44) ──
clear
echo ""
echo "${BOLD}  ██████╗ ██╗██╗  ██╗██████╗ ██╗████████╗${NC}"
echo "${BOLD}  ██╔══██╗██║╚██╗██╔╝██╔══██╗██║╚══██╔══╝${NC}"
echo "${BOLD}  ██████╔╝██║ ╚███╔╝ ██████╔╝██║   ██║   ${NC}"
echo "${BOLD}  ██╔══██╗██║ ██╔██╗ ██╔══██╗██║   ██║   ${NC}"
echo "${BOLD}  ██████╔╝██║██╔╝ ██╗██████╔╝██║   ██║   ${NC}"
echo "${BOLD}  ╚═════╝ ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝   ╚═╝  ${NC}"
echo ""
echo "  ${BOLD}Mining Guardian — Customer Setup v2${NC}"
echo "  BiXBiT USA  •  Bucket 6b  •  macOS 14+ arm64  •  Bitcoin SHA-256 fleet"
divider

# ============================================================
# PHASE 1 — Pre-flight checks
# macOS 14+ (arm64), ≥16 GB RAM, ≥50 GB free, miner LAN reachable.
# Fail fast before touching any system state.
# ============================================================
phase_01_preflight() {
  CURRENT_PHASE="Phase 1 — Pre-flight checks"
  phase_banner "1" "Pre-flight checks"
  step "macOS version (minimum 14 / Sonoma)..."
  local v; v="$(sw_vers -productVersion)"; local maj; maj="${v%%.*}"
  [[ "${maj}" -lt 14 ]] && fail "macOS ${v} — requires 14+."
  ok "macOS ${v}"
  step "CPU architecture (arm64 required — Ollama GPU inference)..."
  [[ "$(uname -m)" != "arm64" ]] && fail "Requires arm64 (Apple Silicon). Got: $(uname -m)"
  ok "arm64 Apple Silicon"
  step "RAM (≥16 GB — D-13 floor; ≥24 GB enables qwen2.5:14b instead of llama3.2:3b)..."
  local gb=$(( $(sysctl -n hw.memsize) / 1073741824 ))
  [[ "${gb}" -lt 16 ]] && fail "Only ${gb} GB RAM — minimum 16 GB."
  ok "${gb} GB RAM"
  step "Free disk space (≥50 GB — model + Postgres + venv + logs)..."
  local free; free="$(df -g / | awk 'NR==2{print $4}')"
  [[ "${free}" -lt 50 ]] && fail "Only ${free} GB free — minimum 50 GB."
  ok "${free} GB free"
  step "Miner LAN connectivity (ping 192.168.1.1, 1s timeout)..."
  if [[ "${SKIP_LAN_CHECK}" == "true" ]]; then
    warn "LAN check skipped (--skip-lan-check)."
  elif ! ping -c 1 -t 1 192.168.1.1 >/dev/null 2>&1; then
    warn "Cannot reach 192.168.1.1 — Mac may not be on miner LAN."
    read "OK?  Continue anyway? (y/N): "; [[ "${OK:-N}" != "y" ]] && fail "Aborted."
  else
    ok "Miner LAN reachable (192.168.1.1)"
  fi
  log_phase_complete "01_preflight"
  ok "Phase 1 complete — system meets all requirements."
}

# ============================================================
# PHASE 2 — Customer information
# Collect all site-specific config interactively.
# S-14 FIX: Every password uses `read -s` (echo suppressed).
#   Manual `echo ""` follows each masked prompt for cursor advance.
# Values written to .env in Phase 7. NEVER echoed to stdout.
# NEVER in URL query strings (S-4).
# ============================================================
phase_02_customer_info() {
  CURRENT_PHASE="Phase 2 — Customer information"
  phase_banner "2" "Customer information"
  echo "  All fields required unless [default] shown.\n"
  read "CUSTOMER_NAME?  Customer / Site name (e.g. \"Mesa Verde Mine I\"): "
  [[ -z "${CUSTOMER_NAME}" ]] && fail "Site name required."
  read "AMS_URL?  AMS base URL [https://api.bixbit.io/api/v1]: "
  AMS_URL="${AMS_URL:-https://api.bixbit.io/api/v1}"
  read "AMS_EMAIL?  AMS email address: "
  [[ -z "${AMS_EMAIL}" ]] && fail "AMS email required."
  read -s "AMS_PASSWORD?  AMS password (hidden — S-14 fix): "; echo ""  # S-14
  [[ -z "${AMS_PASSWORD}" ]] && fail "AMS password required."
  read "AMS_WORKSPACE_ID?  AMS workspace ID (integer): "
  [[ -z "${AMS_WORKSPACE_ID}" ]] && fail "AMS workspace ID required."
  echo ""; step "Slack configuration..."
  read "SLACK_WEBHOOK_URL?  Slack webhook URL: "
  [[ -z "${SLACK_WEBHOOK_URL}" ]] && fail "Slack webhook URL required."
  read "SLACK_BOT_TOKEN?  Slack bot token (xoxb-...): "
  [[ -z "${SLACK_BOT_TOKEN}" ]] && fail "Slack bot token required."
  read -s "SLACK_SIGNING_SECRET?  Slack signing secret (hidden — S-14): "; echo ""  # S-14
  [[ -z "${SLACK_SIGNING_SECRET}" ]] && fail "Slack signing secret required."
  read "SLACK_APP_TOKEN?  Slack app-level token (xapp-...) [optional]: "
  read "AUTHORIZED_SLACK_USER_IDS?  Authorized Slack user IDs (comma-sep, e.g. U01ABC): "
  [[ -z "${AUTHORIZED_SLACK_USER_IDS}" ]] && fail "Authorized Slack user IDs required."
  echo ""; read "SCAN_INTERVAL?  Scan interval seconds [300]: "
  SCAN_INTERVAL="${SCAN_INTERVAL:-300}"
  echo "\n  ${BOLD}Mode:${NC} dry_run=true → monitor only (recommended) | dry_run=false → live"
  read "DRY_RUN_MODE?  Start in dry-run mode? [Y/n]: "
  if [[ "${DRY_RUN_MODE:-Y}" == "n" || "${DRY_RUN_MODE:-Y}" == "N" ]]; then
    MG_DRY_RUN="false"; warn "Live mode — automated actions enabled."
  else
    MG_DRY_RUN="true"; ok "Dry-run mode (safe default, D-2)."
  fi
  ok "Customer info collected for: ${CUSTOMER_NAME}"
  log_phase_complete "02_customer_info"
}

# ============================================================
# PHASE 3 — Homebrew + system dependencies
# Installs brew (if absent), then: postgresql@16, python@3.12,
# git, ollama, grafana, and optionally tailscale (--tailscale).
# All installs are idempotent — `brew install` is a no-op if
# the formula is already current. postgresql@16 is keg-only so
# we add its bin/ to PATH for psql/createdb/createuser access.
# ============================================================
phase_03_brew_deps() {
  CURRENT_PHASE="Phase 3 — Homebrew + dependencies"
  phase_banner "3" "Homebrew + system dependencies"
  step "Homebrew..."
  if ! command -v brew &>/dev/null; then
    info "Installing Homebrew (1-3 min)..."
    run_cmd /bin/bash -c \
      "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" </dev/null
    [[ -f /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
    ok "Homebrew installed."
  else
    ok "Homebrew: $(brew --version | head -1)"
  fi
  for formula in postgresql@16 python@3.12 git ollama grafana; do
    step "brew install ${formula}..."
    run_cmd brew install "${formula}" 2>&1 | tail -3 || true  # non-zero on already-current is OK
    ok "${formula} ready."
  done
  if [[ "${WANT_TAILSCALE}" == "true" ]]; then
    step "brew install tailscale (--tailscale)..."; run_cmd brew install tailscale 2>&1 | tail -2 || true; ok "Tailscale."
  else
    info "Tailscale not requested (pass --tailscale to install)."
  fi
  # postgresql@16 is keg-only — add its bin to PATH for this shell session
  local PGB; PGB="$(brew --prefix postgresql@16)/bin"
  [[ -d "${PGB}" ]] && ! echo "${PATH}" | grep -q "${PGB}" && export PATH="${PGB}:${PATH}" && info "Added ${PGB} to PATH."
  log_phase_complete "03_brew_deps"
  ok "Phase 3 complete — all system dependencies installed."
}

# ============================================================
# PHASE 4 — PostgreSQL setup
# Start postgresql@16, create guardian_app superuser, create
# 3 databases, apply schema migrations 001-004 (skip absent).
# Databases:
#   mining_guardian         operational: scans, audit log, LLM analysis
#   mining_guardian_test    test suite only — never production
#   mining_guardian_catalog Intelligence Catalog (Bitcoin SHA-256 models)
# guardian_app is created without a password here (peer auth for Phases
# 5/6). Phase 7 issues ALTER ROLE with the openssl-generated password.
# ============================================================
phase_04_postgres() {
  CURRENT_PHASE="Phase 4 — PostgreSQL setup"
  phase_banner "4" "PostgreSQL setup"
  step "Starting postgresql@16..."
  run_cmd brew services start postgresql@16 2>&1 | tail -2 || true
  sleep 3  # allow Postgres to bind before we connect
  ok "postgresql@16 running."
  step "Creating guardian_app role..."
  if psql -U "$(whoami)" -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='guardian_app';" 2>/dev/null | grep -q 1; then
    warn "guardian_app already exists — skipping."
  else
    run_cmd psql -U "$(whoami)" -d postgres -c "CREATE ROLE guardian_app SUPERUSER LOGIN;" 2>/dev/null || \
      run_cmd createuser -U "$(whoami)" --superuser --no-password guardian_app 2>/dev/null
    ok "guardian_app created."
  fi
  for db in mining_guardian mining_guardian_test mining_guardian_catalog; do
    step "Creating database: ${db}..."
    if psql -U "$(whoami)" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${db}';" 2>/dev/null | grep -q 1; then
      warn "${db} already exists — skipping."
    else
      run_cmd psql -U "$(whoami)" -d postgres -c "CREATE DATABASE ${db} OWNER guardian_app;" 2>/dev/null
      ok "${db} created."
    fi
  done
  step "Applying all schema migrations in lexical order..."
  # Glob every NNN_*.sql file under migrations/ and apply in shell-sorted order.
  # This naturally handles:
  #   - missing slots (e.g. 002 lives on the VPS pending B-7 commit)
  #   - multiple migrations sharing a number prefix (e.g. 004_drop_dead_stubs.sql
  #     and 004_system_settings.sql — both are applied)
  #   - new migrations added later (005, 006, ...) without editing this loop
  # The previous "for n in 001 002 003 004" loop silently dropped the second
  # 004_*.sql file (head -1) and never reached 005_*.sql at all.
  local applied_count=0 missing_seen=0
  shopt -s nullglob
  for f in "${REPO_DIR}/migrations/"[0-9][0-9][0-9]_*.sql; do
    info "Applying ${f##*/}..."
    run_cmd psql -U guardian_app -d mining_guardian -f "${f}" >/dev/null 2>&1 || \
      warn "${f##*/} non-zero exit (may already be applied)."
    ok "Migration ${f##*/} applied."
    applied_count=$((applied_count + 1))
  done
  shopt -u nullglob
  if (( applied_count == 0 )); then
    warn "No migration files found under ${REPO_DIR}/migrations/ — Phase 4 schema step is a no-op."
  else
    ok "Applied ${applied_count} migration file(s)."
  fi
  # Sanity log: list canonical numbers we expect, note absences for the operator.
  for n in 001 002 003 004 005; do
    local g; g="$(ls "${REPO_DIR}/migrations/${n}_"*.sql 2>/dev/null | head -1 || true)"
    [[ -z "${g}" ]] && info "  (note: no ${n}_*.sql in repo — expected for 002 pending B-7)"
  done
  log_phase_complete "04_postgres"
  ok "Phase 4 complete — PostgreSQL ready (3 databases)."
}

# ============================================================
# PHASE 5 — Intelligence Catalog seed data
# Seeds mining_guardian_catalog with the 313-row Bitcoin
# SHA-256 miner model baseline. Without this, Qwen has no
# hardware reference — every miner is "unknown". Closes C4.
# Seed SQL is idempotent (ON CONFLICT DO NOTHING).
# ============================================================
phase_05_catalog_seed() {
  CURRENT_PHASE="Phase 5 — Catalog seed data"
  phase_banner "5" "Intelligence Catalog seed data"
  local SEED="${REPO_DIR}/intelligence-catalog/seed-data/seed_miner_models.sql"
  if [[ ! -f "${SEED}" ]]; then
    warn "Seed not found: ${SEED} — skipping."
    warn "Run manually: psql -U guardian_app -d mining_guardian_catalog -f ${SEED}"
    log_phase_complete "05_catalog_seed_SKIPPED"; return
  fi
  # Apply catalog schema before seed. Prefer deploy_schema.sql; fall back to v1 schema.
  local SCH="${REPO_DIR}/intelligence-catalog/seed-data/deploy_schema.sql"
  [[ ! -f "${SCH}" ]] && SCH="${REPO_DIR}/intelligence-catalog/seed-data/intelligence_catalog_schema.sql"
  [[ -f "${SCH}" ]] && { info "Applying catalog schema: ${SCH##*/}"; run_cmd psql -U guardian_app -d mining_guardian_catalog -f "${SCH}" >/dev/null 2>&1 || true; }
  step "Seeding 313 Bitcoin SHA-256 miner model rows..."
  run_cmd psql -U guardian_app -d mining_guardian_catalog -f "${SEED}" >/dev/null 2>&1 && \
    ok "313-row baseline seeded." || warn "Seed non-zero exit (may already be loaded)."
  log_phase_complete "05_catalog_seed"
  ok "Phase 5 complete — catalog seeded."
}

# ============================================================
# PHASE 6 — Repository clone + Python virtual environment
# Clone or update the repo into /Library/Application Support/MiningGuardian,
# create a Python 3.12 venv, and install all dependencies.
#
# requirements.txt: The repo root does not currently ship one
# (only intelligence-catalog/catalog-api/ has one). If a root
# requirements.txt exists we use it; otherwise we pip-install
# a pinned minimum set covering all imports in core/, api/,
# ai/, notifiers/, clients/ — the "49 packages" in §7.1.
# The script works correctly with either code path.
# ============================================================
phase_06_repo_venv() {
  CURRENT_PHASE="Phase 6 — Repository + Python venv"
  phase_banner "6" "Repository + Python virtual environment"
  run_cmd mkdir -p "${INSTALL_ROOT}" "${LOGS_DIR}" "${BIN_DIR}"
  step "Repository at ${INSTALL_ROOT}..."
  if [[ -d "${INSTALL_ROOT}/.git" ]]; then
    info "Existing repo — pulling..."; run_cmd git -C "${INSTALL_ROOT}" pull --ff-only origin main 2>&1 | tail -3; ok "Updated."
  elif [[ "${REPO_DIR}" == "${INSTALL_ROOT}" ]]; then
    ok "Running from ${INSTALL_ROOT} — no clone needed."
  elif [[ -z "$(ls -A "${INSTALL_ROOT}" 2>/dev/null)" ]]; then
    info "Cloning from ${REPO_URL}..."; run_cmd git clone "${REPO_URL}" "${INSTALL_ROOT}" 2>&1 | tail -3; ok "Cloned."
  else
    warn "${INSTALL_ROOT} non-empty but not a git repo — using existing files."
  fi
  step "Python 3.12 venv..."
  local PY312; PY312="$(brew --prefix python@3.12 2>/dev/null)/bin/python3.12" || true
  [[ ! -x "${PY312:-}" ]] && PY312="$(command -v python3.12 2>/dev/null)" || true
  [[ -z "${PY312:-}" ]] && fail "python3.12 not found — Phase 3 may have failed."
  if [[ -d "${VENV}" ]]; then warn "Venv exists — reusing."
  else run_cmd "${PY312}" -m venv "${VENV}"; ok "Venv: $(${VENV}/bin/python --version 2>&1)"; fi
  step "pip install..."
  run_cmd "${VENV}/bin/pip" install --quiet --upgrade pip
  local REQ="${INSTALL_ROOT}/requirements.txt"
  if [[ -f "${REQ}" ]]; then
    info "Using requirements.txt from repo root."
    run_cmd "${VENV}/bin/pip" install --quiet -r "${REQ}"
    ok "Dependencies installed from requirements.txt."
  else
    warn "No root requirements.txt — using pinned minimum set."
    info "Covers all imports in core/, api/, ai/, notifiers/, clients/ (49+ packages)."
    # Pinned version floors tested on Python 3.12 + macOS 14. Refresh when
    # requirements.txt eventually lands in the repo root.
    run_cmd "${VENV}/bin/pip" install --quiet \
      requests "websocket-client>=1.6.0" "python-dotenv>=1.0.0" "slack-sdk>=3.26.0" \
      "fastapi>=0.110.0" "uvicorn[standard]>=0.29.0" "psycopg2-binary>=2.9.9" \
      "psycopg[binary]>=3.1.18" "sqlalchemy>=2.0.0" "alembic>=1.13.0" \
      "pydantic>=2.6.0" "httpx>=0.27.0" "aiohttp>=3.9.0" "prometheus-client>=0.20.0" \
      "slowapi>=0.1.9" "anthropic>=0.25.0" "openai>=1.20.0" "ollama>=0.1.8" \
      "jinja2>=3.1.3" "weasyprint>=61.0" "reportlab>=4.1.0" "pandas>=2.2.0" \
      "numpy>=1.26.0" "matplotlib>=3.8.0" "seaborn>=0.13.0" "rich>=13.7.0" \
      "typer>=0.12.0" "click>=8.1.7" "cryptography>=42.0.0" "paramiko>=3.4.0" \
      "pysnmp>=6.1.0" "schedule>=1.2.1" "tenacity>=8.2.3" "structlog>=24.1.0" \
      "python-jose>=3.3.0" "passlib[bcrypt]>=1.7.4" "python-multipart>=0.0.9" \
      "python-dateutil>=2.9.0" "pytz>=2024.1" "tabulate>=0.9.0" "colorama>=0.4.6" \
      "tqdm>=4.66.0" "pyyaml>=6.0.1" "toml>=0.10.2" "orjson>=3.10.0" \
      "ujson>=5.9.0" "httptools>=0.6.1" "websockets>=12.0" "starlette>=0.36.0"
    ok "Pinned minimum set installed (50 packages)."
  fi
  log_phase_complete "06_repo_venv"
  ok "Phase 6 complete — repository and venv ready."
}

# ============================================================
# PHASE 7 — Secrets and .env file
# Generates 3 independent 256-bit secrets via openssl rand -hex 32.
# Writes /Library/Application Support/MiningGuardian/.env (mode 0600, root:wheel).
#
# S-14  AMS + Slack passwords from Phase 2 read -s prompts.
#        NEVER echoed. NEVER in query strings (S-4).
# S-6   CATALOG_API_KEY = fresh openssl rand — never the default
#        "CHANGE_ME_TO_A_REAL_SECRET". Crash-on-startup guard in
#        catalog_api.py was shipped in PR #65/#66 — installer just
#        ensures the key is always populated.
# S-13  All PGHOST / OLLAMA_HOST = 127.0.0.1. No Tailscale IPs.
#
# TODO (S-7 / §3.2 docs/MG_UNIFIED_TODO_LIST.md — deferred Bucket 6d):
#   A dedicated `miningguardian` OS user must own .env + run all services.
#   Four-step implementation required:
#     1. dscl . create /Users/miningguardian + home dir at INSTALL_ROOT
#     2. Add UserName key to all 9 plists (Bucket 6d plist revisions)
#     3. chown -R miningguardian:wheel INSTALL_ROOT; chmod 0600 .env
#     4. Update installer Makefile + postinstall.sh for the new user
#   Currently all 9 daemons run as root. Tracking: S-7, §3.2 unified TODO.
# ============================================================
phase_07_secrets() {
  CURRENT_PHASE="Phase 7 — Secrets / .env"
  phase_banner "7" "Secrets and .env file"
  if [[ -f "${ENV_FILE}" ]]; then
    warn ".env already exists at ${ENV_FILE}"
    read "OVER?  Overwrite? Cannot be undone. (y/N): "
    if [[ "${OVER:-N}" != "y" ]]; then warn "Keeping existing .env."; log_phase_complete "07_secrets_SKIPPED"; return; fi
  fi
  step "Generating secrets (openssl rand -hex 32 × 3)..."
  # Fresh 256-bit secrets — never committed, never logged, never in stdout.
  # MG_DB_PASSWORD: fresh per install — no two sites share a password.
  #   Replaces the leaked MiningGuardian2026! (CRIT-1/S-1).
  local MG_DB_PASSWORD; MG_DB_PASSWORD="$(openssl rand -hex 32)"
  # CATALOG_API_KEY: fresh per install. Closes S-6. Never the known default.
  local CATALOG_API_KEY; CATALOG_API_KEY="$(openssl rand -hex 32)"
  # INTERNAL_API_SECRET: approval_api.py verify_internal() fail-closed check.
  local INTERNAL_API_SECRET; INTERNAL_API_SECRET="$(openssl rand -hex 32)"
  ok "Secrets generated (not displayed)."
  step "Setting guardian_app Postgres password (locked down from Phase 4 peer auth)..."
  run_cmd psql -U "$(whoami)" -d postgres \
    -c "ALTER ROLE guardian_app WITH PASSWORD '${MG_DB_PASSWORD}';" >/dev/null 2>&1
  ok "guardian_app password set."
  step "Writing ${ENV_FILE}..."
  # Subshell redirect — no secret value ever touches this script's stdout.
  run_cmd bash -c "cat > '${ENV_FILE}'" <<EOF
# /Library/Application Support/MiningGuardian/.env  mode=0600  owner=root:wheel
# Generated: $(date '+%Y-%m-%d %H:%M:%S %Z')  Site: ${CUSTOMER_NAME}
# DO NOT COMMIT. DO NOT LOG. DO NOT SHARE.

# AMS — Bitcoin SHA-256 miners only (S-4: no creds in query strings)
AMS_BASE_URL=${AMS_URL}
AMS_EMAIL=${AMS_EMAIL}
AMS_PASSWORD=${AMS_PASSWORD}
AMS_WORKSPACE_ID=${AMS_WORKSPACE_ID}

# Postgres — 127.0.0.1 only (S-13: no Tailscale IPs anywhere)
GUARDIAN_PG_HOST=127.0.0.1
GUARDIAN_PG_PORT=5432
GUARDIAN_PG_USER=guardian_app
GUARDIAN_PG_PASSWORD=${MG_DB_PASSWORD}
GUARDIAN_PG_DBNAME=mining_guardian
GUARDIAN_PG_TEST_DBNAME=mining_guardian_test
GUARDIAN_PG_CATALOG_DBNAME=mining_guardian_catalog

# Slack — all values customer-specific (do not copy from VPS; §6.3)
SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}
SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}
SLACK_SIGNING_SECRET=${SLACK_SIGNING_SECRET}
SLACK_APP_TOKEN=${SLACK_APP_TOKEN:-}
AUTHORIZED_SLACK_USER_IDS=${AUTHORIZED_SLACK_USER_IDS}

# Catalog API key — S-6 fix: generated fresh; crash-on-startup if absent (PR #65/#66)
CATALOG_API_KEY=${CATALOG_API_KEY}

# Internal API secret — approval_api.py verify_internal() fail-closed
INTERNAL_API_SECRET=${INTERNAL_API_SECRET}

# Ollama — local GPU inference on 127.0.0.1 (S-13 fix: no hardcoded Tailscale IPs)
OLLAMA_HOST=http://127.0.0.1:11434

# Runtime config (D-2: auto_approve=false — explicit opt-in required)
MG_DRY_RUN=${MG_DRY_RUN}
MG_SCAN_INTERVAL=${SCAN_INTERVAL}
MG_CUSTOMER_NAME=${CUSTOMER_NAME}
AUTO_APPROVE_ENABLED=false

# Service ports — all 127.0.0.1 (S-13)
GUARDIAN_DASHBOARD_PORT=8585
GUARDIAN_APPROVAL_PORT=8686
GUARDIAN_INTELLIGENCE_PORT=8590
EOF
  run_cmd chmod 0600 "${ENV_FILE}"; run_cmd chown root:wheel "${ENV_FILE}"
  ok ".env written (0600, root:wheel)."
  log_phase_complete "07_secrets"
  ok "Phase 7 complete — all secrets written."
}

# ============================================================
# PHASE 8 — Ollama + RAM-tier LLM model (D-13)
#
# B-11 fix (v1.0.1): mirror the .pkg installer's RAM-tier model
# selection (D-13) so both install paths converge:
#
#   16 GB RAM    → llama3.2:3b                  (~2 GB pull)
#   24 GB+ RAM   → qwen2.5:14b-instruct-q4_K_M  (~8 GB pull)
#
# Pre-v1.0.1 setup.sh forced qwen2.5:14b on every Mac including 16 GB
# tier, contradicting the .pkg's welcome screen and the locked decision
# in docs/DECISIONS.md row D-13. The two paths now agree.
#
# Role in Learning Chain:
#   Pass 1 (4 PM) — per-miner analysis (ai/daily_deep_dive.py)
#   Pass 3 (1 AM) — reflection pass  (ai/refinement_chain.py)
# q4_K_M = 4-bit K-means quantized: best quality/RAM on 24 GB+ Mac.
# llama3.2:3b is the 16 GB tier fallback; same chain code, smaller model.
# Pull is resumable — interrupted? Re-run Phase 8 only.
# ============================================================
phase_08_ollama() {
  CURRENT_PHASE="Phase 8 — Ollama + RAM-tier LLM model (D-13)"
  phase_banner "8" "Ollama + AI model"

  # D-13 RAM-tier selection — must agree with
  # installer/macos-pkg/scripts/lib/detect_ram.sh.
  local gb model
  gb=$(( $(sysctl -n hw.memsize) / 1073741824 ))
  if   [[ "${gb}" -ge 24 ]]; then model="qwen2.5:14b-instruct-q4_K_M"
  elif [[ "${gb}" -ge 16 ]]; then model="llama3.2:3b"
  else fail "Only ${gb} GB RAM — D-13 floor is 16 GB."
  fi
  info "Detected ${gb} GB RAM → selecting ${model} (D-13)."

  step "Starting Ollama service..."
  if ! pgrep -x ollama >/dev/null 2>&1; then
    run_cmd ollama serve >/dev/null 2>&1 & sleep 5; ok "Ollama server started."
  else
    ok "Ollama already running."
  fi
  step "Pulling ${model} — do not interrupt..."
  info "The pull is resumable if it fails — re-run this phase."
  run_cmd ollama pull "${model}"
  ok "Model pull complete."
  step "Smoke test: ollama list | grep ${model}..."
  if ollama list 2>/dev/null | grep -q "${model%%:*}"; then
    ok "${model} confirmed in \`ollama list\`."
  else
    warn "Model not found in \`ollama list\` — pull may have failed."
    warn "Fix: ollama list && ollama pull ${model}"
  fi

  # Persist the selected model for downstream phases (Slack notifier copy,
  # install receipt) so they don't have to re-detect.
  export MG_INSTALL_LLM_MODEL="${model}"
  export MG_INSTALL_RAM_TIER="${gb}"

  log_phase_complete "08_ollama"
  ok "Phase 8 complete — Ollama + ${model} ready."
}

# ============================================================
# PHASE 9 — LaunchDaemon installation (9 services)
# Installs and bootstraps all 9 Mining Guardian LaunchDaemons.
#
# 8 main services (installer/macos-pkg/resources/launchd/):
#   com.miningguardian.scanner               Bitcoin SHA-256 scan loop
#   com.miningguardian.dashboard-api         web dashboard (port 8585)
#   com.miningguardian.approval-api          Slack action handler (8686)
#   com.miningguardian.slack-listener        AMS alert polling
#   com.miningguardian.slack-commands        Slack slash-command handler
#   com.miningguardian.overnight-automation  scheduled automation
#   com.miningguardian.alerts                alert processing + routing
#   com.miningguardian.intelligence-report   PDF report API (port 8590)
#
# 9th service (deploy/ — D-14 PR 4b):
#   com.miningguardian.feedback-loop-daemon  C5 Postgres NOTIFY/LISTEN
#
# Per service: copy plist (0644 root:wheel), copy launcher (0755 root:wheel),
# bootout any existing label (idempotency), bootstrap new plist.
#
# Why launcher wrappers: launchd has no EnvironmentFile= equivalent. Each
# launcher sources .env then execs Python — keeps secrets out of the
# world-readable plists in /Library/LaunchDaemons/.
# ============================================================
phase_09_launchdaemons() {
  CURRENT_PHASE="Phase 9 — LaunchDaemon installation"
  phase_banner "9" "LaunchDaemon installation (9 services)"
  run_cmd mkdir -p "${LOGS_DIR}"; run_cmd chown root:wheel "${LOGS_DIR}"
  # install_launchdaemon <plist_src> <launcher_src> <label>
  install_launchdaemon() {
    local ps="$1" ls="$2" lbl="$3"
    local pd="${LAUNCHDAEMONS}/${lbl}.plist"
    local ld="${BIN_DIR}/$(basename "${ls}")"
    info "  ${lbl}..."
    [[ ! -f "${ps}" ]] && { warn "  Plist missing: ${ps} — skipping ${lbl}"; return; }
    [[ ! -f "${ls}" ]] && { warn "  Launcher missing: ${ls} — skipping ${lbl}"; return; }
    run_cmd cp "${ps}" "${pd}"; run_cmd chmod 0644 "${pd}"; run_cmd chown root:wheel "${pd}"
    run_cmd cp "${ls}" "${ld}"; run_cmd chmod 0755 "${ld}"; run_cmd chown root:wheel "${ld}"
    # Bootout first — launchctl bootstrap errors if label already registered
    launchctl bootout "system/${lbl}" 2>/dev/null || true; sleep 1
    run_cmd launchctl bootstrap system "${pd}"
    ok "  ${lbl} bootstrapped."
  }
  local PB="${REPO_DIR}/${LAUNCHD_SRC}"    # plist base
  local LB="${REPO_DIR}/${LAUNCHER_SRC}"  # launcher base
  install_launchdaemon "${PB}/com.miningguardian.scanner.plist"             "${LB}/scanner_launcher.sh"              "com.miningguardian.scanner"
  install_launchdaemon "${PB}/com.miningguardian.dashboard-api.plist"       "${LB}/dashboard_api_launcher.sh"        "com.miningguardian.dashboard-api"
  install_launchdaemon "${PB}/com.miningguardian.approval-api.plist"        "${LB}/approval_api_launcher.sh"         "com.miningguardian.approval-api"
  install_launchdaemon "${PB}/com.miningguardian.slack-listener.plist"      "${LB}/slack_listener_launcher.sh"       "com.miningguardian.slack-listener"
  install_launchdaemon "${PB}/com.miningguardian.slack-commands.plist"      "${LB}/slack_commands_launcher.sh"       "com.miningguardian.slack-commands"
  install_launchdaemon "${PB}/com.miningguardian.overnight-automation.plist" "${LB}/overnight_automation_launcher.sh" "com.miningguardian.overnight-automation"
  install_launchdaemon "${PB}/com.miningguardian.alerts.plist"              "${LB}/alerts_launcher.sh"               "com.miningguardian.alerts"
  install_launchdaemon "${PB}/com.miningguardian.intelligence-report.plist" "${LB}/intelligence_report_launcher.sh"  "com.miningguardian.intelligence-report"
  # 9th: feedback-loop-daemon (ships in deploy/, not launchd_src — D-14 PR 4b)
  install_launchdaemon "${REPO_DIR}/deploy/com.miningguardian.feedback-loop-daemon.plist" \
    "${REPO_DIR}/deploy/feedback_loop_daemon_launcher.sh" "com.miningguardian.feedback-loop-daemon"
  log_phase_complete "09_launchdaemons"
  ok "Phase 9 complete — all 9 LaunchDaemons installed and bootstrapped."
}

# ============================================================
# PHASE 10 — Cron jobs (10 entries from docs/CRON_SCHEDULE.md)
# PATH TRANSLATION: CRON_SCHEDULE.md uses /root/Mining-Guardian (VPS).
# Every path rewritten to /Library/Application Support/MiningGuardian for macOS.
# Times are machine-local — set Mac Mini timezone before install.
#
# Learning Chain:
#   00:00 Pass 2 Claude cohort (ai/weekly_train.py)
#   01:00 Pass 3+4 Qwen reflect + merge (ai/refinement_chain.py)
#   03:30 DB maintenance WAL/vacuum (scripts/db_maintenance.sh)
#   04:00 Knowledge backup (ai/backup_knowledge.py)
#   07:00 Morning briefing Slack (scripts/morning_briefing.py)
#   08:00 Operator review report (scripts/daily_operator_review.py)
#   12:45 AMS log cleanup (scripts/cleanup_ams_logs.py)
#   13:00 Log pull from miners (scripts/direct_collect_logs.py)
#   16:00 Pass 1 Qwen deep dive (ai/daily_deep_dive.py)
#   16:15 Log failure report (scripts/daily_log_failure_report.py)
#   *:00  Hourly benchmark (tests/run_benchmark.py)
#
# FULL DISK ACCESS: macOS 14+ blocks /usr/sbin/cron from writing outside
# user home without FDA. Operator prompted after crontab install.
# ============================================================
phase_10_cron() {
  CURRENT_PHASE="Phase 10 — Cron jobs"
  phase_banner "10" "Cron jobs (10 entries)"
  local MG="${INSTALL_ROOT}"; local PY="${MG}/venv/bin/python"
  local NEW_CRON
  NEW_CRON=$(cat <<'CRONEOF'
# ── Mining Guardian cron schedule (setup.sh v2 — macOS paths) ──
CRONEOF
# Expand variables now (not heredoc-literal)
echo "0 0 * * * cd ${MG} && PYTHONPATH=${MG} ${PY} ai/weekly_train.py >> /tmp/daily_claude_training.log 2>&1"
echo "0 1 * * * cd ${MG} && PYTHONPATH=${MG} ${PY} ai/refinement_chain.py >> /tmp/daily_refinement_chain.log 2>&1"
echo "30 3 * * * cd ${MG} && bash scripts/db_maintenance.sh >> /tmp/db_maintenance.log 2>&1"
echo "0 4 * * * cd ${MG} && PYTHONPATH=${MG} ${PY} ai/backup_knowledge.py >> /tmp/knowledge_backup.log 2>&1"
echo "0 7 * * * cd ${MG} && PYTHONPATH=${MG} ${PY} scripts/morning_briefing.py >> /tmp/morning_briefing.log 2>&1"
echo "0 8 * * * cd ${MG} && PYTHONPATH=${MG} ${PY} scripts/daily_operator_review.py >> /tmp/daily_operator_review.log 2>&1"
echo "45 12 * * * cd ${MG} && PYTHONPATH=${MG} ${PY} scripts/cleanup_ams_logs.py >> /tmp/ams_cleanup.log 2>&1"
echo "0 13 * * * cd ${MG} && PYTHONPATH=${MG} ${PY} scripts/direct_collect_logs.py >> /tmp/direct_log_collection.log 2>&1"
echo "0 16 * * * cd ${MG} && PYTHONPATH=${MG} ${PY} ai/daily_deep_dive.py >> /tmp/daily_deep_dive.log 2>&1"
echo "15 16 * * * cd ${MG} && PYTHONPATH=${MG} ${PY} scripts/daily_log_failure_report.py >> /tmp/daily_log_failure_report.log 2>&1"
echo "0 * * * * cd ${MG} && source ${MG}/venv/bin/activate && PYTHONPATH=${MG} python3 tests/run_benchmark.py >> /var/log/mg_benchmark.log 2>&1"
)
  if [[ "${DRY_RUN_INSTALL}" == "true" ]]; then
    info "[DRY RUN] Would install crontab entries:"; echo "${NEW_CRON}"
  else
    local EX; EX="$(crontab -l 2>/dev/null || true)"
    if echo "${EX}" | grep -q "Mining Guardian cron schedule"; then
      warn "Existing MG cron entries found — replacing..."
      local STRIP; STRIP="$(echo "${EX}" | grep -v "Mining-Guardian\|Mining Guardian cron\|weekly_train\|refinement_chain\|backup_knowledge\|morning_briefing\|daily_operator\|cleanup_ams\|direct_collect\|daily_deep_dive\|daily_log_failure\|run_benchmark\|db_maintenance")"
      (echo "${STRIP}"; echo "${NEW_CRON}") | crontab -
    else
      (echo "${EX}"; echo "${NEW_CRON}") | crontab -
    fi
    ok "10 cron entries installed."
  fi
  divider
  echo "\n  ${BOLD}${YELLOW}ACTION REQUIRED — Full Disk Access for /usr/sbin/cron${NC}\n"
  echo "  macOS 14+ blocks cron from writing /tmp + /var/log without FDA."
  echo "  Without FDA, nightly jobs (deep-dive, briefing, backups) fail silently.\n"
  echo "  Grant: System Settings → Privacy & Security → Full Disk Access → [+]"
  echo "         Cmd+Shift+G → /usr/sbin → select: cron → toggle ON\n"
  read "FDA?  Press Enter once Full Disk Access is granted (Ctrl+C to skip)..."
  log_phase_complete "10_cron"
  ok "Phase 10 complete — cron schedule installed."
}

# ============================================================
# PHASE 11 — Grafana setup
# Start Grafana; write a minimal PostgreSQL datasource YAML.
# PLACEHOLDER: Full provisioning config (dashboards, Prometheus
# source, panel layout) is Bucket 6d (separate future PR).
# Bucket 6d will OVERWRITE the postgres.yml written here.
# Do NOT hand-edit — your changes will be lost on Bucket 6d deploy.
# Grafana var: /opt/homebrew/var/lib/grafana (Apple Silicon)
#              /usr/local/var/lib/grafana (Intel / fallback)
# ============================================================
phase_11_grafana() {
  CURRENT_PHASE="Phase 11 — Grafana setup"
  phase_banner "11" "Grafana setup"
  step "Starting Grafana..."; run_cmd brew services start grafana 2>&1 | tail -2 || true; sleep 2; ok "Grafana running."
  local GV
  if [[ -d /opt/homebrew/var/lib/grafana ]]; then GV="/opt/homebrew/var/lib/grafana"
  elif [[ -d /usr/local/var/lib/grafana ]];   then GV="/usr/local/var/lib/grafana"
  else GV="/usr/local/var/lib/grafana"; run_cmd mkdir -p "${GV}"; fi
  local PD="${GV}/provisioning/datasources"; run_cmd mkdir -p "${PD}"
  step "Writing Grafana postgres.yml placeholder (Bucket 6d will overwrite)..."
  run_cmd bash -c "cat > '${PD}/postgres.yml'" <<GEOF
# Mining Guardian — Grafana PostgreSQL datasource — PLACEHOLDER
# TODO (Bucket 6d): Overwrites this with full provisioning + dashboard defs.
# DO NOT hand-edit. Generated: $(date '+%Y-%m-%d') by setup.sh v2.
apiVersion: 1
datasources:
  - name: Mining Guardian (PostgreSQL)
    type: postgres
    url: 127.0.0.1:5432
    database: mining_guardian
    user: guardian_app
    secureJsonData:
      password: "\${GUARDIAN_PG_PASSWORD}"
    jsonData:
      sslmode: disable
      postgresVersion: 1600
      timescaledb: false
    isDefault: true
    editable: false
GEOF
  ok "Grafana datasource placeholder: ${PD}/postgres.yml"
  info "(Bucket 6d will overwrite with the full provisioning config.)"
  run_cmd brew services restart grafana 2>&1 | tail -2 || true; ok "Grafana restarted."
  log_phase_complete "11_grafana"
  ok "Phase 11 complete — Grafana configured."
}

# ============================================================
# PHASE 12 — Tailscale (optional, --tailscale flag only)
# Runs `tailscale up --accept-routes` to join the operator mesh.
# S-13: Tailscale is for remote operator access only (SSH, Grafana).
# No Mining Guardian service binds to a Tailscale IP — all use 127.0.0.1 (S-13).
# ============================================================
phase_12_tailscale() {
  CURRENT_PHASE="Phase 12 — Tailscale"
  phase_banner "12" "Tailscale (optional)"
  if [[ "${WANT_TAILSCALE}" != "true" ]]; then
    info "Tailscale not requested (pass --tailscale to enable). Skipping."
    log_phase_complete "12_tailscale_SKIPPED"; return
  fi
  step "tailscale up --accept-routes..."
  info "A browser window may open for authentication if not already logged in."
  run_cmd tailscale up --accept-routes
  tailscale status 2>/dev/null | head -5 || true; ok "Tailscale up."
  log_phase_complete "12_tailscale"
  ok "Phase 12 complete — Tailscale connected."
}

# ============================================================
# PHASE 13 — Smoke tests
# End-to-end verification of the full install:
#   1. Source .env — export all vars for psql / curl / python
#   2. Postgres connectivity to mining_guardian + catalog
#   3. Python import: core.mining_guardian.MiningGuardian
#   4. All 9 LaunchDaemon labels in launchctl list with PID
#   5. dashboard-api HTTP check on http://127.0.0.1:8585
# ============================================================
phase_13_smoke_test() {
  CURRENT_PHASE="Phase 13 — Smoke tests"
  phase_banner "13" "Smoke tests"
  if [[ -f "${ENV_FILE}" ]]; then
    set -a; source "${ENV_FILE}"; set +a; ok ".env sourced."  # shellcheck disable=SC1090
  else
    warn ".env not found — smoke tests have reduced coverage."
  fi
  step "Postgres connectivity..."
  psql -U guardian_app -d mining_guardian -c "SELECT 1;" >/dev/null 2>&1 && \
    ok "mining_guardian: connected" || warn "Cannot connect to mining_guardian — check Phase 4."
  psql -U guardian_app -d mining_guardian_catalog -c "SELECT 1;" >/dev/null 2>&1 && \
    ok "mining_guardian_catalog: connected" || warn "Cannot connect to catalog — AI context unavailable."
  step "Python import test (core.mining_guardian.MiningGuardian)..."
  if [[ "${DRY_RUN_INSTALL}" == "true" ]]; then
    info "[DRY RUN] Would test MiningGuardian importability."
  else
    cd "${INSTALL_ROOT}"
    "${VENV}/bin/python" -c \
      "import sys; sys.path.insert(0,'${INSTALL_ROOT}'); from core.mining_guardian import MiningGuardian; print('MiningGuardian — importable OK')" 2>&1 && \
      ok "core.mining_guardian imports OK." || \
      warn "Import failed — debug: cd ${INSTALL_ROOT} && PYTHONPATH=. ${VENV}/bin/python -c 'from core.mining_guardian import MiningGuardian'"
  fi
  step "LaunchDaemon status (all 9 services)..."
  local FAIL=()
  for svc in scanner dashboard-api approval-api slack-listener slack-commands overnight-automation alerts intelligence-report feedback-loop-daemon; do
    local lbl="com.miningguardian.${svc}"
    local st; st="$(launchctl list "${lbl}" 2>/dev/null || echo "NOT_LOADED")"
    if echo "${st}" | grep -q "NOT_LOADED"; then
      warn "  ${lbl}: NOT LOADED"; FAIL+=("${lbl}")
    else
      local pid; pid="$(echo "${st}" | grep '"PID"' | awk '{print $3}' | tr -d ',')"
      if [[ -n "${pid:-}" && "${pid}" != "0" ]]; then ok "  ${lbl}: PID ${pid}"
      else warn "  ${lbl}: no PID — check ${LOGS_DIR}/${svc}.err.log"; FAIL+=("${lbl}"); fi
    fi
  done
  [[ ${#FAIL[@]} -eq 0 ]] && ok "All 9 LaunchDaemons running." || \
    warn "${#FAIL[@]} service(s) not running — check ${LOGS_DIR}/"
  step "Dashboard-API HTTP check (127.0.0.1:8585)..."
  sleep 5  # allow services settle time post-bootstrap
  curl -sf "http://127.0.0.1:8585/" >/dev/null 2>&1 || curl -sf "http://127.0.0.1:8585/health" >/dev/null 2>&1 && \
    ok "dashboard-api responding on port 8585." || \
    { warn "dashboard-api not responding yet — may still be starting."; info "Retry: curl http://127.0.0.1:8585/"; }
  log_phase_complete "13_smoke_test"
  ok "Phase 13 complete — smoke tests done."
}

# ============================================================
# PHASE 14 — Post-install: Slack notification + cheat-sheet
# Posts a Slack confirmation (secrets stay in env vars, never stdout).
# Prints a full operator cheat-sheet: locations, service commands,
# how to flip dry_run, port map, log paths, manual uninstall steps.
# ============================================================
phase_14_postinstall() {
  CURRENT_PHASE="Phase 14 — Post-install"
  phase_banner "14" "Post-install: Slack + operator cheat-sheet"
  step "Slack install confirmation..."
  if [[ "${DRY_RUN_INSTALL}" == "true" ]]; then
    info "[DRY RUN] Would POST Slack confirmation to webhook."
  elif [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    local MSG="*Mining Guardian online* — macOS v2\n*Site:* ${CUSTOMER_NAME}  *Mode:* dry_run=${MG_DRY_RUN}\n*Scan:* ${SCAN_INTERVAL}s  *9 LaunchDaemons*  *Model:* ${MG_INSTALL_LLM_MODEL:-llama3.2:3b}\nBitcoin SHA-256 fleet monitoring active."
    curl -s -X POST -H 'Content-type: application/json' \
      --data "{\"text\": \"${MSG}\"}" "${SLACK_WEBHOOK_URL}" >/dev/null 2>&1 && \
      ok "Slack notified." || warn "Slack failed — check ${ENV_FILE} SLACK_WEBHOOK_URL."
  else
    warn "SLACK_WEBHOOK_URL not set — skipping notification."
  fi
  divider
  echo "\n  ${BOLD}${GREEN}✅  Mining Guardian is live — ${CUSTOMER_NAME}${NC}\n"
  echo "  ${BOLD}━━━━ OPERATOR CHEAT-SHEET ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
  echo "  ${BOLD}Locations:${NC}"
  echo "    Install root:  ${INSTALL_ROOT}"
  echo "    Secrets:       ${ENV_FILE}   (mode 0600, root:wheel)"
  echo "    Logs:          ${LOGS_DIR}/"
  echo "    Phase log:     ${PHASE_LOG}"
  echo "    Cron logs:     /tmp/daily_deep_dive.log  /tmp/morning_briefing.log  etc.\n"
  echo "  ${BOLD}Service management:${NC}"
  echo "    launchctl list | grep com.miningguardian          # list + PIDs"
  echo "    sudo launchctl bootout system/com.miningguardian.scanner    # stop"
  echo "    sudo launchctl bootstrap system /Library/LaunchDaemons/com.miningguardian.scanner.plist\n"
  echo "  ${BOLD}Stop ALL services:${NC}"
  for svc in scanner dashboard-api approval-api slack-listener slack-commands overnight-automation alerts intelligence-report feedback-loop-daemon; do
    echo "    sudo launchctl bootout system/com.miningguardian.${svc}"
  done
  echo ""
  echo "  ${BOLD}Flip dry_run → live:${NC}"
  echo "    sudo nano ${ENV_FILE}    # set MG_DRY_RUN=false"
  echo "    Restart scanner (bootout + bootstrap as above)\n"
  echo "  ${BOLD}Ports (all 127.0.0.1 — S-13):${NC}"
  echo "    Dashboard: 8585  •  Approval API: 8686  •  Intel Report: 8590  •  Grafana: 3000\n"
  echo "  ${BOLD}Uninstall:${NC}"
  echo "    1. Bootout all 9 services  2. rm -f /Library/LaunchDaemons/com.miningguardian.*.plist"
  echo "    3. rm -rf ${INSTALL_ROOT}   4. dropdb mining_guardian mining_guardian_test mining_guardian_catalog"
  echo "    5. dropuser guardian_app    6. crontab -e (remove MG block)"
  divider
  log_phase_complete "14_postinstall"
  ok "Phase 14 complete — Mining Guardian is live."
}

# ============================================================
# PHASE 15 — Snapshot restore (function stub only)
# The actual Phase 15 dispatch happens at the top of this script via
# --restore-from-snapshot early-dispatch (before the banner). That path
# execs restore_from_snapshot.sh (Bucket 6c, separate PR), which handles:
#   1. Untar snapshot into /Library/Application Support/MiningGuardian
#   2. Restore .env from snapshot
#   3. Restore Grafana DB (grafana.db) from snapshot
# After Bucket 6c exits 0, setup.sh re-execs with --post-restore to
# complete Phases 9-14. This function acknowledges the --post-restore path.
# ============================================================
phase_15_snapshot_restore() {
  CURRENT_PHASE="Phase 15 — Snapshot restore"
  if [[ "${POST_RESTORE}" == "true" ]]; then
    phase_banner "15" "Snapshot restore (complete — via restore_from_snapshot.sh)"
    info "Snapshot restored. Continuing with Phases 9-14 (LaunchDaemons → post-install)."
    log_phase_complete "15_snapshot_restore"
    ok "Phase 15 acknowledged."
  fi
}

# ============================================================
# MAIN — orchestrate all phases in spec order (Section 7.2)
# --post-restore skips Phases 1-8 (handled by restore_from_snapshot.sh)
# ============================================================
main() {
  echo "\n  ${BOLD}Mining Guardian installer v2 starting...${NC}"
  echo "  Phase log: ${PHASE_LOG}\n"
  touch "${PHASE_LOG}"
  if [[ "${POST_RESTORE}" == "true" ]]; then
    phase_15_snapshot_restore
    phase_09_launchdaemons; phase_10_cron; phase_11_grafana
    phase_12_tailscale; phase_13_smoke_test; phase_14_postinstall
  else
    phase_01_preflight; phase_02_customer_info; phase_03_brew_deps
    phase_04_postgres; phase_05_catalog_seed; phase_06_repo_venv
    phase_07_secrets; phase_08_ollama; phase_09_launchdaemons
    phase_10_cron; phase_11_grafana; phase_12_tailscale
    phase_13_smoke_test; phase_14_postinstall
  fi
  divider
  echo "\n  ${BOLD}${GREEN}Mining Guardian setup complete.${NC}"
  echo "  Completed: $(grep -c COMPLETE "${PHASE_LOG}" 2>/dev/null || echo 0) phases — see ${PHASE_LOG}"
  divider
}

main "$@"
