#!/bin/zsh
# ============================================================
# Mining Guardian — Grafana provisioning installer
# BiXBiT USA  •  Bucket 6d  •  §7.3 row 7g of docs/MG_UNIFIED_TODO_LIST.md
#
# Copies the Grafana provisioning bundle from
# installer/macos-pkg/resources/grafana/ into the Grafana data dir on this
# Mac, plus copies dashboards into the runtime path referenced by the
# dashboard provider yaml.
#
# Called by scripts/setup.sh Phase 11. Also runnable standalone after a
# bundle update (e.g. new dashboard added in PR).
#
# Usage:
#   zsh install_grafana_provisioning.sh \
#       --target=/opt/homebrew/var/lib/grafana \
#       --bundle=/path/to/installer/macos-pkg/resources/grafana \
#       --runtime-dashboards=/Library/Application Support/MiningGuardian/grafana/dashboards
#
#   zsh install_grafana_provisioning.sh --auto      (auto-detect target;
#                                                    bundle = repo-rel; runtime = /Library/Application Support/MiningGuardian/grafana/dashboards)
#   zsh install_grafana_provisioning.sh --dry-run   (no writes; print plan)
#   zsh install_grafana_provisioning.sh --help
#
# Idempotent: every copy uses `cp -f` and `mkdir -p`. Re-running overwrites
# with the latest committed bundle. Validates JSON/YAML before any write.
#
# Exit codes:
#   0  success (or --dry-run completed)
#   1  bad argv / help
#   2  bundle not found / malformed
#   3  Grafana target not found / not writable
#   4  validation failure (JSON or YAML parse error)
# ============================================================
set -euo pipefail

# ---- ANSI helpers (same pattern as setup.sh / restore_from_snapshot.sh) ----
if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
  C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YEL=$'\033[33m'; C_BLU=$'\033[34m'; C_CYA=$'\033[36m'
else
  C_RESET=''; C_BOLD=''; C_DIM=''; C_RED=''; C_GRN=''; C_YEL=''; C_BLU=''; C_CYA=''
fi
divider() { print -- "${C_DIM}────────────────────────────────────────────────────────────${C_RESET}"; }
banner()  { divider; print -- "${C_BOLD}${C_CYA}== $1 ==${C_RESET}"; divider; }
ok()      { print -- "  ${C_GRN}✓${C_RESET} $1"; }
warn()    { print -- "  ${C_YEL}!${C_RESET} $1"; }
fail()    { print -- "  ${C_RED}✗${C_RESET} $1" >&2; }
step()    { print -- "  ${C_BLU}→${C_RESET} $1"; }
info()    { print -- "  ${C_DIM}· $1${C_RESET}"; }

# ---- Argv parsing ----
TARGET=""           # Grafana data dir (will create $TARGET/provisioning/{datasources,dashboards})
BUNDLE=""           # path to installer/macos-pkg/resources/grafana
RUNTIME_DASH=""     # where dashboard JSONs live at runtime
DRY_RUN=0
AUTO=0

usage() {
  cat <<EOF
${C_BOLD}Mining Guardian — Grafana provisioning installer${C_RESET}

  Usage:
    zsh install_grafana_provisioning.sh \\
        --target=<grafana_var_dir> \\
        --bundle=<repo>/installer/macos-pkg/resources/grafana \\
        --runtime-dashboards=<dashboards_dir>

    zsh install_grafana_provisioning.sh --auto
    zsh install_grafana_provisioning.sh --dry-run
    zsh install_grafana_provisioning.sh --help

  Flags:
    --target=<dir>               Grafana data dir (default auto-detect)
    --bundle=<dir>               Repo bundle path (default: this script's
                                  ../installer/macos-pkg/resources/grafana)
    --runtime-dashboards=<dir>   Where dashboard JSONs live at runtime
                                  (default: /Library/Application Support/MiningGuardian/grafana/dashboards)
    --auto                       Use defaults for all three paths
    --dry-run                    Print plan without writing
    --help                       Print this help

  Exit codes:
    0 success      1 bad argv     2 bundle problem
    3 target problem               4 validation failure

  See: installer/macos-pkg/resources/grafana/README.md
EOF
}

for arg in "$@"; do
  case "$arg" in
    --target=*)               TARGET="${arg#*=}" ;;
    --bundle=*)               BUNDLE="${arg#*=}" ;;
    --runtime-dashboards=*)   RUNTIME_DASH="${arg#*=}" ;;
    --auto)                   AUTO=1 ;;
    --dry-run)                DRY_RUN=1 ;;
    -h|--help)                usage; exit 0 ;;
    *)                        fail "unknown flag: $arg"; usage; exit 1 ;;
  esac
done

# ---- Defaults / auto-detect ----
SCRIPT_DIR="${0:A:h}"
REPO_ROOT="${SCRIPT_DIR:h}"

if [[ -z "$BUNDLE" ]]; then
  BUNDLE="${REPO_ROOT}/installer/macos-pkg/resources/grafana"
fi
if [[ -z "$RUNTIME_DASH" ]]; then
  RUNTIME_DASH="/Library/Application Support/MiningGuardian/grafana/dashboards"
fi
if [[ -z "$TARGET" ]]; then
  if [[ -d /opt/homebrew/var/lib/grafana ]]; then
    TARGET="/opt/homebrew/var/lib/grafana"
  elif [[ -d /usr/local/var/lib/grafana ]]; then
    TARGET="/usr/local/var/lib/grafana"
  elif [[ "$AUTO" -eq 1 ]]; then
    TARGET="/usr/local/var/lib/grafana"   # not yet created — Phase 11 mkdirs it
  else
    fail "could not auto-detect Grafana data dir; pass --target=<dir>"
    exit 3
  fi
fi

banner "Mining Guardian — Grafana provisioning installer"
info "bundle:             $BUNDLE"
info "target (Grafana):   $TARGET"
info "runtime dashboards: $RUNTIME_DASH"
info "dry-run:            $DRY_RUN"
print

# ============================================================
# PHASE 1 — Validate bundle layout
# ============================================================
banner "Phase 1 — Validate bundle layout"
if [[ ! -d "$BUNDLE" ]]; then
  fail "bundle dir does not exist: $BUNDLE"
  exit 2
fi
ok "bundle directory exists"

REQUIRED_FILES=(
  "$BUNDLE/provisioning/datasources/mining_guardian.yml"
  "$BUNDLE/provisioning/dashboards/mining_guardian.yml"
  "$BUNDLE/README.md"
)
for f in $REQUIRED_FILES; do
  if [[ ! -f "$f" ]]; then
    fail "missing required bundle file: $f"
    exit 2
  fi
done
ok "all required yaml files present"

DASHBOARDS=("$BUNDLE/dashboards"/*.json(N))
if [[ ${#DASHBOARDS[@]} -eq 0 ]]; then
  fail "no dashboard JSONs found in $BUNDLE/dashboards/"
  exit 2
fi
ok "${#DASHBOARDS[@]} dashboard JSON file(s) found"

# ============================================================
# PHASE 2 — Validate JSON / YAML parses
# ============================================================
banner "Phase 2 — Validate JSON/YAML parses"
if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 not found — cannot validate"
  exit 4
fi

for yml in "$BUNDLE/provisioning/datasources/mining_guardian.yml" \
           "$BUNDLE/provisioning/dashboards/mining_guardian.yml"; do
  if python3 -c "import yaml,sys; yaml.safe_load(open('$yml'))" 2>/dev/null; then
    ok "yaml ok: ${yml#$BUNDLE/}"
  else
    fail "yaml parse error: $yml"
    exit 4
  fi
done

for j in $DASHBOARDS; do
  if python3 -c "import json,sys; d=json.load(open('$j')); assert 'uid' in d and 'title' in d and 'panels' in d" 2>/dev/null; then
    ok "json ok: ${j#$BUNDLE/}"
  else
    fail "json parse error or missing required keys (uid/title/panels): $j"
    exit 4
  fi
done

# ============================================================
# PHASE 3 — Prepare target dirs
# ============================================================
banner "Phase 3 — Prepare target directories"
TARGET_DS="$TARGET/provisioning/datasources"
TARGET_DASH_PROV="$TARGET/provisioning/dashboards"

step "would create: $TARGET_DS"
step "would create: $TARGET_DASH_PROV"
step "would create: $RUNTIME_DASH"

if [[ "$DRY_RUN" -eq 0 ]]; then
  if ! mkdir -p "$TARGET_DS" "$TARGET_DASH_PROV" 2>/dev/null; then
    fail "could not create $TARGET_DS / $TARGET_DASH_PROV (need sudo?)"
    exit 3
  fi
  if ! mkdir -p "$RUNTIME_DASH" 2>/dev/null; then
    fail "could not create $RUNTIME_DASH (need sudo?)"
    exit 3
  fi
  ok "directories ready"
else
  warn "dry-run: skipped mkdir"
fi

# ============================================================
# PHASE 4 — Copy provisioning yaml
# ============================================================
banner "Phase 4 — Install provisioning yaml"
SRC_DS="$BUNDLE/provisioning/datasources/mining_guardian.yml"
SRC_DASH_PROV="$BUNDLE/provisioning/dashboards/mining_guardian.yml"
DST_DS="$TARGET_DS/mining_guardian.yml"
DST_DASH_PROV="$TARGET_DASH_PROV/mining_guardian.yml"

step "$SRC_DS  →  $DST_DS"
step "$SRC_DASH_PROV  →  $DST_DASH_PROV"

if [[ "$DRY_RUN" -eq 0 ]]; then
  cp -f "$SRC_DS"        "$DST_DS"
  cp -f "$SRC_DASH_PROV" "$DST_DASH_PROV"
  ok "datasource yaml installed"
  ok "dashboard provider yaml installed"
else
  warn "dry-run: skipped cp"
fi

# ============================================================
# PHASE 5 — Copy dashboard JSONs
# ============================================================
banner "Phase 5 — Install dashboard JSONs"
COUNT=0
for j in $DASHBOARDS; do
  base="${j:t}"
  step "$j  →  $RUNTIME_DASH/$base"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    cp -f "$j" "$RUNTIME_DASH/$base"
  fi
  COUNT=$((COUNT + 1))
done
if [[ "$DRY_RUN" -eq 0 ]]; then
  ok "$COUNT dashboard JSON(s) installed"
else
  warn "dry-run: skipped $COUNT cp(s)"
fi

# ============================================================
# PHASE 6 — Summary
# ============================================================
banner "Phase 6 — Summary"
ok "bundle:             $BUNDLE"
ok "datasource yaml:    $DST_DS"
ok "dashboard provider: $DST_DASH_PROV"
ok "dashboard JSONs:    $COUNT files in $RUNTIME_DASH"
print
if [[ "$DRY_RUN" -eq 1 ]]; then
  warn "DRY-RUN complete — no files written."
else
  ok  "Provisioning installed. Restart Grafana to pick up changes:"
  info "  brew services restart grafana"
fi
print
exit 0
