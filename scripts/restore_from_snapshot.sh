#!/bin/zsh
# ============================================================
# Mining Guardian — Restore from VPS Snapshot
# BiXBiT USA  •  Bucket 6c  •  §7.3 row 7d / docs/MG_UNIFIED_TODO_LIST.md
#
# Restores a Mining Guardian VPS snapshot tarball onto a fresh Mac Mini.
# Designed to be called by scripts/setup.sh Phase 15 when the operator
# passes --restore-from-snapshot=<tarball>, OR run standalone after a
# vanilla setup.sh has finished and the operator wants to import VPS
# state retroactively.
#
# Usage:
#   zsh restore_from_snapshot.sh --tarball=<path>
#   zsh restore_from_snapshot.sh --tarball=<path> --skip-postgres-restore
#   zsh restore_from_snapshot.sh --tarball=<path> --skip-grafana-restore
#   zsh restore_from_snapshot.sh --tarball=<path> --dry-run
#   zsh restore_from_snapshot.sh --help
#
# Required tarball convention (see "Snapshot tarball layout" below):
#
#   mg_snapshot_<vps>_<YYYYMMDD_HHMMSS>.tar.gz
#       ├── manifest.txt
#       ├── env/.env                       (from /root/Mining-Guardian/.env)
#       ├── env/config.json                (from /root/Mining-Guardian/config.json)
#       ├── postgres/mining_guardian.dump  (pg_dump --format=custom)
#       ├── postgres/mining_guardian_catalog.dump
#       ├── grafana/grafana.db             (the SQLite operational DB)
#       ├── logs/                          (last 7 days of /root/Mining-Guardian/logs)
#       └── crontab.txt                    (`crontab -l` from VPS, for diff)
#
# Outputs:
#   /Library/Application Support/MiningGuardian/.env            (mode 0600, owner root:wheel)
#   /Library/Application Support/MiningGuardian/config.json
#   /Library/Application Support/MiningGuardian/logs/           (merged with existing)
#   Postgres restored into local mining_guardian + mining_guardian_catalog
#   /usr/local/var/lib/grafana/grafana.db     (overwritten if --skip-grafana-restore not set)
#   /tmp/mg_restore_<TS>/                     (extracted tarball, kept until reboot)
#
# Exit codes:
#   0 — success
#   1 — argv / pre-flight failure
#   2 — tarball missing / unreadable / wrong shape
#   3 — Postgres restore failure
#   4 — Grafana restore failure
#   5 — env / config restore failure
# ============================================================

setopt err_exit pipefail
set -euo pipefail

# ── Colors + helpers (mirror scripts/setup.sh) ─────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

divider() { echo "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}" }
ok()      { echo "${GREEN}  ✅ $1${NC}" }
warn()    { echo "${YELLOW}  ⚠️  $1${NC}" }
fail()    { echo "${RED}  ❌ $1${NC}"; exit "${2:-1}" }
step()    { echo "\n${BOLD}$1${NC}" }

# ── Argv parse ────────────────────────────────────────────
TARBALL=""
SKIP_POSTGRES=0
SKIP_GRAFANA=0
DRY_RUN=0
SHOW_HELP=0

for arg in "$@"; do
  case "$arg" in
    --tarball=*)               TARBALL="${arg#*=}" ;;
    --skip-postgres-restore)   SKIP_POSTGRES=1 ;;
    --skip-grafana-restore)    SKIP_GRAFANA=1 ;;
    --dry-run)                 DRY_RUN=1 ;;
    --help|-h)                 SHOW_HELP=1 ;;
    *)                         fail "Unknown argument: $arg (use --help)" 1 ;;
  esac
done

if [[ $SHOW_HELP -eq 1 ]]; then
  cat <<'HELP'
restore_from_snapshot.sh — Mining Guardian VPS-to-Mac snapshot restore

Required:
  --tarball=<path>           Path to mg_snapshot_<vps>_<TS>.tar.gz

Optional:
  --skip-postgres-restore    Don't touch local Postgres (keep what setup.sh built)
  --skip-grafana-restore     Don't touch local Grafana DB
  --dry-run                  Print every action, take none
  --help                     This message

Tarball layout (see script header for full convention):
  manifest.txt
  env/{.env, config.json}
  postgres/{mining_guardian.dump, mining_guardian_catalog.dump}
  grafana/grafana.db
  logs/
  crontab.txt

Typical flow:
  # On VPS — produce the tarball
  zsh /root/Mining-Guardian/scripts/build_snapshot_tarball.sh
  # (Bucket 6c follow-up — not yet committed; for now the
  #  operator runs the equivalent commands by hand. See
  #  the inline comment block in this script's "Tarball
  #  build hints (VPS-side)" section near the bottom.)

  # On Mac Mini — install + restore
  zsh /Library/Application Support/MiningGuardian/scripts/setup.sh \
      --restore-from-snapshot=/Volumes/USB/mg_snapshot_srv1549463_20260505_0900.tar.gz
HELP
  exit 0
fi

# Inputs
if [[ -z "$TARBALL" ]]; then
  fail "Missing --tarball=<path> (use --help)" 1
fi

if [[ ! -f "$TARBALL" ]]; then
  fail "Tarball not found: $TARBALL" 2
fi

if [[ ! -r "$TARBALL" ]]; then
  fail "Tarball not readable: $TARBALL" 2
fi

# Install root convention (matches scripts/setup.sh)
INSTALL_ROOT="/Library/Application Support/MiningGuardian"
TS=$(date +%Y%m%d_%H%M%S)
EXTRACT_ROOT="/tmp/mg_restore_${TS}"

# ── Banner ────────────────────────────────────────────────
clear
echo ""
echo "${BOLD}  Mining Guardian — Snapshot Restore${NC}"
echo "  BiXBiT USA"
echo ""
echo "  Tarball:        $TARBALL"
echo "  Install root:   $INSTALL_ROOT"
echo "  Extract dir:    $EXTRACT_ROOT"
[[ $DRY_RUN     -eq 1 ]] && echo "  Mode:           ${YELLOW}DRY RUN — no changes will be made${NC}"
[[ $SKIP_POSTGRES -eq 1 ]] && echo "  ${YELLOW}Postgres restore: SKIPPED${NC}"
[[ $SKIP_GRAFANA  -eq 1 ]] && echo "  ${YELLOW}Grafana restore:  SKIPPED${NC}"
divider

# ── do_or_skip wrapper for --dry-run ──────────────────────
do_or_skip() {
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "  ${YELLOW}[dry-run] would run:${NC} $*"
  else
    "$@"
  fi
}

# ── Phase 1 — Pre-flight ──────────────────────────────────
step "PHASE 1 — Pre-flight checks"

if [[ ! -d "$INSTALL_ROOT" ]]; then
  fail "$INSTALL_ROOT does not exist. Run scripts/setup.sh first, then --restore-from-snapshot." 1
fi

# We need root for /Library/LaunchDaemons writes + Postgres role manipulation.
# setup.sh already validated this — we re-check here in case this is run standalone.
if [[ "$EUID" -ne 0 ]]; then
  fail "This script must run as root (sudo). Re-run with: sudo zsh $0 --tarball=$TARBALL" 1
fi

# Required tools
for tool in tar shasum pg_restore createdb dropdb psql; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    fail "Required tool missing: $tool" 1
  fi
done
ok "All required tools present (tar, shasum, pg_restore, createdb, dropdb, psql)"

# Disk space — need ~3x tarball size for extract + Postgres restore
TARBALL_BYTES=$(stat -f%z "$TARBALL" 2>/dev/null || stat -c%s "$TARBALL")
NEEDED_BYTES=$(( TARBALL_BYTES * 3 ))
NEEDED_GB=$(( NEEDED_BYTES / 1024 / 1024 / 1024 + 1 ))

# df -m gives megabytes on the partition holding /tmp
FREE_MB=$(df -m /tmp | awk 'NR==2 {print $4}')
FREE_GB=$(( FREE_MB / 1024 ))

if (( FREE_GB < NEEDED_GB )); then
  fail "Need ~${NEEDED_GB} GB free on /tmp; have ${FREE_GB} GB. Free space and re-run." 1
fi
ok "Disk space: ${FREE_GB} GB free on /tmp (need ~${NEEDED_GB} GB)"

# ── Phase 2 — Extract + verify shape ──────────────────────
step "PHASE 2 — Extracting tarball"

do_or_skip mkdir -p "$EXTRACT_ROOT"
do_or_skip tar -xzf "$TARBALL" -C "$EXTRACT_ROOT"

if [[ $DRY_RUN -eq 0 ]]; then
  # Verify shape — every required path exists
  REQUIRED=(
    "$EXTRACT_ROOT/manifest.txt"
    "$EXTRACT_ROOT/env/.env"
    "$EXTRACT_ROOT/env/config.json"
    "$EXTRACT_ROOT/postgres/mining_guardian.dump"
    "$EXTRACT_ROOT/postgres/mining_guardian_catalog.dump"
    "$EXTRACT_ROOT/grafana/grafana.db"
    "$EXTRACT_ROOT/crontab.txt"
  )

  for required in "${REQUIRED[@]}"; do
    if [[ ! -e "$required" ]]; then
      fail "Tarball is missing required entry: ${required#$EXTRACT_ROOT/}" 2
    fi
  done
  ok "Tarball shape verified — all 7 required entries present"

  # Optional: logs/ directory is a nice-to-have, warn but don't fail
  if [[ ! -d "$EXTRACT_ROOT/logs" ]]; then
    warn "logs/ directory missing from tarball — will skip log restore (snapshot was minimal)"
  fi

  # Manifest + checksums
  echo ""
  echo "  ${BOLD}Snapshot manifest:${NC}"
  sed 's/^/    /' "$EXTRACT_ROOT/manifest.txt" | head -20
fi

# ── Phase 3 — Restore .env + config.json ──────────────────
step "PHASE 3 — Restoring .env + config.json"

# Back up whatever setup.sh wrote, then overlay the snapshot versions.
# Customer creds in .env from setup.sh (AMS, Slack) take precedence; the
# snapshot's MG_DB_PASSWORD does NOT — Postgres on Mac was just freshly
# created with a NEW password. We merge: snapshot's catalog tunables +
# setup.sh's customer creds + setup.sh's Postgres creds.
ENV_DEST="$INSTALL_ROOT/.env"
ENV_BACKUP="$INSTALL_ROOT/.env.pre_restore_${TS}"
CONFIG_DEST="$INSTALL_ROOT/config.json"
CONFIG_BACKUP="$INSTALL_ROOT/config.json.pre_restore_${TS}"

if [[ -f "$ENV_DEST" ]]; then
  do_or_skip cp -p "$ENV_DEST" "$ENV_BACKUP"
  ok "Backed up existing .env to ${ENV_BACKUP##*/}"
fi
if [[ -f "$CONFIG_DEST" ]]; then
  do_or_skip cp -p "$CONFIG_DEST" "$CONFIG_BACKUP"
  ok "Backed up existing config.json to ${CONFIG_BACKUP##*/}"
fi

# Merge .env: take ALL keys from existing (setup.sh-written) .env, then
# overlay any keys from the snapshot that the local .env does NOT have.
# This is conservative: customer creds, locally-generated CATALOG_API_KEY,
# locally-generated MG_DB_PASSWORD all win. Catalog tunables, debug flags,
# feature toggles all migrate from the snapshot.
if [[ $DRY_RUN -eq 0 ]]; then
  python3 - <<PY
import os, sys

local_env  = "$ENV_DEST"
snap_env   = "$EXTRACT_ROOT/env/.env"

def parse(path):
    out = {}
    if not os.path.exists(path):
        return out
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v
    return out

local = parse(local_env)
snap  = parse(snap_env)

# Keys that ALWAYS come from local (setup.sh / Mac-Mini-fresh values)
LOCAL_WINS = {
    "MG_DB_PASSWORD", "PGPASSWORD",
    "CATALOG_API_KEY",
    "AMS_USER", "AMS_PASSWORD", "AMS_PASS", "AMS_WORKSPACE_ID",
    "SLACK_WEBHOOK_URL", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_SIGNING_SECRET",
    "PGHOST", "PGPORT", "PGUSER", "PGDATABASE",
}

merged = dict(snap)        # start with snapshot
for k, v in local.items(): # local always overlays
    merged[k] = v
for k in LOCAL_WINS:       # extra-belt-and-suspenders for password-class keys
    if k in local:
        merged[k] = local[k]

with open(local_env, "w") as f:
    f.write("# Mining Guardian .env — merged by restore_from_snapshot.sh\n")
    f.write(f"# Backup of pre-restore .env: ${ENV_BACKUP##*/}\n")
    f.write(f"# Snapshot source: $TARBALL\n")
    for k in sorted(merged):
        f.write(f"{k}={merged[k]}\n")
PY
  do_or_skip chmod 600 "$ENV_DEST"
  do_or_skip chown root:wheel "$ENV_DEST"
  ok ".env merged (local-wins for creds, snapshot supplies catalog tunables)"
fi

# config.json — full overwrite is safe because setup.sh already moved
# dry_run: true into config.json and the restore puts it back to the
# operator's last-known-good state. We do NOT preserve the local config.json.
do_or_skip cp -p "$EXTRACT_ROOT/env/config.json" "$CONFIG_DEST"
do_or_skip chmod 644 "$CONFIG_DEST"
do_or_skip chown root:wheel "$CONFIG_DEST"
ok "config.json restored from snapshot"

# ── Phase 4 — Restore Postgres ────────────────────────────
if [[ $SKIP_POSTGRES -eq 1 ]]; then
  step "PHASE 4 — Postgres restore  ${YELLOW}[SKIPPED via --skip-postgres-restore]${NC}"
else
  step "PHASE 4 — Postgres restore"

  # Source local creds (just-merged .env) so PGPASSWORD is set.
  if [[ $DRY_RUN -eq 0 ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_DEST"
    set +a
  fi

  # We restore into mining_guardian + mining_guardian_catalog. The DBs
  # already exist (setup.sh Phase 4 created them). We:
  #   1. Drop + recreate the schema(s) inside each DB (pg_restore --clean).
  #   2. Restore.
  # We do NOT drop the DB itself because that would also drop the
  # guardian_app role's privileges and we'd have to re-grant.

  for db in mining_guardian mining_guardian_catalog; do
    DUMP="$EXTRACT_ROOT/postgres/${db}.dump"
    if [[ ! -f "$DUMP" ]]; then
      warn "No dump for $db — skipping"
      continue
    fi

    DUMP_BYTES=$(stat -f%z "$DUMP" 2>/dev/null || stat -c%s "$DUMP")
    DUMP_MB=$(( DUMP_BYTES / 1024 / 1024 ))
    echo "  Restoring $db (${DUMP_MB} MB) ..."

    # --clean drops objects before recreating; --if-exists swallows the
    # noise on objects that aren't there. --no-owner means we don't
    # carry root@srv1549463's role identity onto the Mac.
    if [[ $DRY_RUN -eq 0 ]]; then
      if pg_restore \
            --host=127.0.0.1 \
            --username=guardian_app \
            --dbname="$db" \
            --clean --if-exists \
            --no-owner --no-privileges \
            --jobs=2 \
            "$DUMP" 2>&1 | tee "/tmp/mg_restore_${db}_${TS}.log" | tail -5; then
        ok "Restored $db"
      else
        # pg_restore returns non-zero even on benign warnings — check
        # the log for actual ERROR lines before failing hard.
        if grep -E "^pg_restore: error: " "/tmp/mg_restore_${db}_${TS}.log" | grep -v "does not exist" > /dev/null; then
          fail "$db restore had errors — see /tmp/mg_restore_${db}_${TS}.log" 3
        else
          ok "Restored $db (only benign 'does not exist' warnings)"
        fi
      fi
    else
      do_or_skip pg_restore --host=127.0.0.1 --username=guardian_app --dbname="$db" \
                            --clean --if-exists --no-owner --no-privileges --jobs=2 "$DUMP"
    fi
  done

  # Verification — row count sanity
  if [[ $DRY_RUN -eq 0 ]]; then
    echo ""
    echo "  ${BOLD}Post-restore row counts:${NC}"
    psql -h 127.0.0.1 -U guardian_app -d mining_guardian -t -c \
         "SELECT 'miner_state_readings: ' || COUNT(*) FROM knowledge.miner_state_readings;" 2>/dev/null \
         | sed 's/^/    /' || warn "Couldn't read knowledge.miner_state_readings count"
    psql -h 127.0.0.1 -U guardian_app -d mining_guardian_catalog -t -c \
         "SELECT 'hardware.miner_models: ' || COUNT(*) FROM hardware.miner_models;" 2>/dev/null \
         | sed 's/^/    /' || warn "hardware.miner_models not yet populated (Bucket 3.1)"
  fi
fi

# ── Phase 5 — Restore Grafana DB ──────────────────────────
if [[ $SKIP_GRAFANA -eq 1 ]]; then
  step "PHASE 5 — Grafana restore  ${YELLOW}[SKIPPED via --skip-grafana-restore]${NC}"
else
  step "PHASE 5 — Grafana restore"

  GRAFANA_DEST_DIR="/usr/local/var/lib/grafana"
  GRAFANA_DEST="$GRAFANA_DEST_DIR/grafana.db"
  GRAFANA_BACKUP="$GRAFANA_DEST.pre_restore_${TS}"
  GRAFANA_SRC="$EXTRACT_ROOT/grafana/grafana.db"

  if [[ ! -f "$GRAFANA_SRC" ]]; then
    warn "No grafana.db in tarball — skipping (operator will start with blank Grafana)"
  else
    # Stop grafana, swap the DB file, restart.
    do_or_skip brew services stop grafana

    if [[ -f "$GRAFANA_DEST" ]]; then
      do_or_skip cp -p "$GRAFANA_DEST" "$GRAFANA_BACKUP"
      ok "Backed up existing grafana.db to ${GRAFANA_BACKUP##*/}"
    fi

    do_or_skip mkdir -p "$GRAFANA_DEST_DIR"
    do_or_skip cp -p "$GRAFANA_SRC" "$GRAFANA_DEST"
    do_or_skip chown _grafana:_grafana "$GRAFANA_DEST" 2>/dev/null \
      || do_or_skip chown $(stat -f%Su "$GRAFANA_DEST_DIR" 2>/dev/null || echo root) "$GRAFANA_DEST"
    do_or_skip chmod 600 "$GRAFANA_DEST"
    ok "grafana.db restored to $GRAFANA_DEST"

    do_or_skip brew services start grafana
    sleep 3
    if [[ $DRY_RUN -eq 0 ]]; then
      if curl -fsS http://127.0.0.1:3000/api/health >/dev/null 2>&1; then
        ok "Grafana restarted and healthy"
      else
        warn "Grafana didn't respond on :3000 within 3s — check ${BOLD}brew services list${NC} and /usr/local/var/log/grafana/"
      fi
    fi
  fi
fi

# ── Phase 6 — Restore logs (best-effort) ──────────────────
step "PHASE 6 — Log restore (best-effort)"

if [[ -d "$EXTRACT_ROOT/logs" ]]; then
  do_or_skip mkdir -p "$INSTALL_ROOT/logs"
  # rsync is the cleanest way to merge without overwriting newer local logs.
  if command -v rsync >/dev/null 2>&1; then
    do_or_skip rsync -a --update "$EXTRACT_ROOT/logs/" "$INSTALL_ROOT/logs/"
    ok "Logs merged into $INSTALL_ROOT/logs/ (rsync --update — older snapshot logs do not overwrite newer local ones)"
  else
    do_or_skip cp -Rn "$EXTRACT_ROOT/logs/." "$INSTALL_ROOT/logs/"
    ok "Logs copied into $INSTALL_ROOT/logs/ (cp -n — only files that didn't exist locally)"
  fi
else
  warn "No logs/ in tarball — skipping (snapshot was minimal)"
fi

# ── Phase 7 — Crontab diff ────────────────────────────────
step "PHASE 7 — Crontab diff (operator review)"

if [[ -f "$EXTRACT_ROOT/crontab.txt" ]]; then
  CURRENT_CRON_FILE="/tmp/mg_current_crontab_${TS}.txt"
  do_or_skip crontab -l > "$CURRENT_CRON_FILE" 2>/dev/null || echo "" > "$CURRENT_CRON_FILE"

  echo ""
  echo "  ${BOLD}Diff (snapshot crontab → current Mac crontab):${NC}"
  if [[ $DRY_RUN -eq 0 ]]; then
    if diff -u "$EXTRACT_ROOT/crontab.txt" "$CURRENT_CRON_FILE" | head -40; then
      ok "Crontabs are identical (or no diff to show)"
    else
      echo ""
      warn "Crontabs differ. setup.sh Phase 10 already wrote the canonical 10 entries with"
      warn "/root/Mining-Guardian → /Library/Application Support/MiningGuardian rewrites. The diff above is"
      warn "informational — do NOT blindly overwrite the local crontab with the snapshot's,"
      warn "because the snapshot's paths still point at /root."
    fi
  fi
else
  warn "No crontab.txt in tarball — skipping diff"
fi

# ── Phase 8 — Restart services ────────────────────────────
step "PHASE 8 — Restart Mining Guardian services"

# Whatever just changed in Postgres or .env, every running service is now
# stale. Reload them all. We don't bootstrap fresh — setup.sh did that;
# we just kickstart so they re-read .env.
PLISTS=(
  com.miningguardian.scanner
  com.miningguardian.dashboard-api
  com.miningguardian.approval-api
  com.miningguardian.slack-listener
  com.miningguardian.slack-commands
  com.miningguardian.overnight-automation
  com.miningguardian.alerts
  com.miningguardian.intelligence-report
  com.miningguardian.feedback-loop-daemon
)

for label in "${PLISTS[@]}"; do
  do_or_skip launchctl kickstart -k "system/$label" 2>/dev/null \
    || warn "$label not loaded — was setup.sh Phase 9 completed?"
done
ok "All 9 services kickstarted"

# Health check
if [[ $DRY_RUN -eq 0 ]]; then
  sleep 3
  echo ""
  echo "  ${BOLD}launchctl list | grep com.miningguardian:${NC}"
  launchctl list | grep com.miningguardian | sed 's/^/    /' || warn "No services visible — check /Library/LaunchDaemons/"
fi

# ── Done ──────────────────────────────────────────────────
divider
echo ""
echo "  ${GREEN}${BOLD}✅ Snapshot restore complete${NC}"
echo ""
echo "  ${BOLD}What got restored:${NC}"
echo "  • Postgres:       $( [[ $SKIP_POSTGRES -eq 1 ]] && echo skipped || echo "mining_guardian + mining_guardian_catalog" )"
echo "  • Grafana DB:     $( [[ $SKIP_GRAFANA  -eq 1 ]] && echo skipped || echo "/usr/local/var/lib/grafana/grafana.db" )"
echo "  • .env / config:  merged (local creds win, snapshot tunables overlay)"
echo "  • Logs:           best-effort merge into $INSTALL_ROOT/logs/"
echo "  • Services:       all 9 kickstarted"
echo ""
echo "  ${BOLD}Backups (in case you need to roll back):${NC}"
[[ -f "$ENV_BACKUP"     ]] && echo "  • $ENV_BACKUP"
[[ -f "$CONFIG_BACKUP"  ]] && echo "  • $CONFIG_BACKUP"
[[ -f "$GRAFANA_BACKUP" ]] && echo "  • $GRAFANA_BACKUP"
echo ""
echo "  ${BOLD}Cleanup:${NC}  $EXTRACT_ROOT will be wiped at next reboot, or:"
echo "                rm -rf $EXTRACT_ROOT"
echo ""
divider

# ============================================================
# Tarball build hints (VPS-side) — Bucket 6c follow-up
# ============================================================
#
# The companion script that PRODUCES the tarball this script consumes is
# scripts/build_snapshot_tarball.sh — to be landed in a follow-up commit.
# Until that ships, the operator builds a tarball by hand on the VPS:
#
#   ssh root@srv1549463
#   cd /root/Mining-Guardian
#   TS=$(date +%Y%m%d_%H%M%S)
#   STAGE=/tmp/mg_snapshot_srv1549463_${TS}
#   mkdir -p ${STAGE}/{env,postgres,grafana,logs}
#
#   cp .env config.json ${STAGE}/env/
#   PGPASSWORD="$MG_DB_PASSWORD" pg_dump -h 127.0.0.1 -U guardian_app -d mining_guardian \
#     --format=custom --compress=9 --file=${STAGE}/postgres/mining_guardian.dump
#   PGPASSWORD="$MG_DB_PASSWORD" pg_dump -h 127.0.0.1 -U guardian_app -d mining_guardian_catalog \
#     --format=custom --compress=9 --file=${STAGE}/postgres/mining_guardian_catalog.dump
#
#   systemctl stop grafana-server
#   cp /var/lib/grafana/grafana.db ${STAGE}/grafana/grafana.db
#   systemctl start grafana-server
#
#   find logs/ -mtime -7 -type f -exec cp --parents {} ${STAGE}/ \;
#   crontab -l > ${STAGE}/crontab.txt
#
#   {
#     echo "Mining Guardian Snapshot"
#     echo "VPS:    srv1549463"
#     echo "Built:  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
#     echo "Built by: $(whoami)@$(hostname)"
#     echo ""
#     echo "Sizes:"
#     du -sh ${STAGE}/* | sed 's/^/  /'
#     echo ""
#     echo "Postgres dump shasums:"
#     cd ${STAGE}/postgres && shasum -a 256 *.dump | sed 's/^/  /'
#   } > ${STAGE}/manifest.txt
#
#   tar -czf /tmp/mg_snapshot_srv1549463_${TS}.tar.gz -C /tmp $(basename ${STAGE})
#   shasum -a 256 /tmp/mg_snapshot_srv1549463_${TS}.tar.gz > /tmp/mg_snapshot_srv1549463_${TS}.tar.gz.sha256
#
# Then scp to the Mac (or copy via USB) and run:
#   sudo zsh /Library/Application Support/MiningGuardian/scripts/restore_from_snapshot.sh \
#       --tarball=/Volumes/USB/mg_snapshot_srv1549463_<TS>.tar.gz
#
# ============================================================
