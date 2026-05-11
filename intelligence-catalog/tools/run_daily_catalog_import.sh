#!/bin/bash
# intelligence-catalog/tools/run_daily_catalog_import.sh
# P-021 (2026-05-07) — daily catalog import wrapper.
#
# Two-DB cooperative architecture (see docs/INTELLIGENCE_CATALOG_STATUS.md):
#   Operational DB (`mining_guardian`) and Catalog DB (`mining_guardian_catalog`)
#   stay distinct. The 5 Perplexity-driven scheduled tasks (Aggregator
#   Watcher, Manufacturer Model Watcher, Firmware Tracker, Community Intel
#   Scanner, Deep Enrichment Sweep) write JSON/CSV findings into
#   ${INSTALL_ROOT}/cron_tracking/<watcher>/ — they do NOT write directly to
#   the catalog DB. This wrapper is the daily glue that promotes the latest
#   Deep Enrichment Sweep CSV into the catalog DB via
#   `catalog_updater.py --add-from-csv`. Findings from the other four
#   watchers stay file-only until a future PR lights up their DB writers
#   (already noted in INTEL_CATALOG_FULL_BRIEF_2026-05-02.md §351-354).
#
# What this wrapper does:
#   1. Find the most recent enrichment-sweep CSV in
#      ${INSTALL_ROOT}/cron_tracking/enrichment_sweep/.
#   2. If found, invoke
#      ${INSTALL_ROOT}/venv/bin/python ${INSTALL_ROOT}/intelligence-catalog/tools/catalog_updater.py
#      --add-from-csv <csv>
#      with `cwd=${INSTALL_ROOT}/intelligence-catalog/data/` so
#      `catalog_known_models.txt` and `unified_miner_index.json` are
#      resolved at the documented relative paths.
#   3. If no CSV found, log INFO and exit 0 (not an error; means no
#      enrichment-sweep run produced output yet).
#
# Idempotent: catalog_updater.py's add-from-csv is itself idempotent
# (slug-keyed; existing slugs deep-merged). Re-running the same CSV is a
# no-op.
#
# This script is dispatched by `scheduled_job_launcher.sh` so it inherits
# the .env-sourced environment, including GUARDIAN_PG_* and MG_DB_* needed
# by `catalog_updater.py`'s dual-writer for staging.miner_model_proposals.

set -euo pipefail

INSTALL_ROOT="${MG_INSTALL_ROOT:-/Library/Application Support/MiningGuardian}"
SWEEP_DIR="${INSTALL_ROOT}/cron_tracking/enrichment_sweep"
UPDATER_DIR="${INSTALL_ROOT}/intelligence-catalog/tools"
UPDATER_DATA_DIR="${INSTALL_ROOT}/intelligence-catalog/data"
VENV_PYTHON="${INSTALL_ROOT}/venv/bin/python"

LABEL="catalog_import"

ts() { /bin/date -u +%Y-%m-%dT%H:%M:%SZ; }

# P-038 item #1 (2026-05-11): the duplicate "sweep dir not present" log
# block that USED to live here was removed. It only logged INFO and fell
# through to the scanner_discovery block, then to the canonical SWEEP_DIR
# guard below (which DOES `exit 0`). Removing the duplicate eliminates a
# confusing repeated log line; the canonical guard below is still the
# one that controls flow.

# P-022 (2026-05-08) — surface scanner_discovery findings so the file-
# based intake produced by core/discovery_sink.py is never silent. The
# scanner writes ${INSTALL_ROOT}/cron_tracking/scanner_discovery/
# latest_findings.json on every scan that observes an unknown model or
# new firmware. We don't import them into staging.miner_model_proposals
# yet (that's a follow-up PR); for now this job reports presence + the
# count of unique events so the operator sees the data is captured.
SCANNER_DISCOVERY_DIR="${INSTALL_ROOT}/cron_tracking/scanner_discovery"
SCANNER_DISCOVERY_LATEST="${SCANNER_DISCOVERY_DIR}/latest_findings.json"
if [[ -f "$SCANNER_DISCOVERY_LATEST" ]]; then
    # Count event keys without requiring `jq` (mac default install
    # doesn't ship it). Python is in the venv we already verify below.
    if [[ -x "$VENV_PYTHON" ]]; then
        # P-038 item #1 (2026-05-11): the JSON path must be passed as a
        # positional arg to the python process ON THE SAME LINE as the
        # heredoc redirection — see `man bash` §HERE DOCUMENTS. The
        # previous shape put `"$SCANNER_DISCOVERY_LATEST"` on a separate
        # line AFTER the PYEOF terminator, which bash treated as a new
        # command ("execute that JSON file"), failing with exit 126
        # `Permission denied`. The Python heredoc, even if it had run,
        # would have IndexError'd on sys.argv[1].
        count="$("$VENV_PYTHON" - "$SCANNER_DISCOVERY_LATEST" <<'PYEOF'
import json, sys
try:
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        data = json.load(f)
    events = data.get("events", {}) if isinstance(data, dict) else {}
    print(len(events))
except Exception:
    print(0)
PYEOF
)"
        echo "[$(ts)] [${LABEL}] INFO scanner_discovery findings present at ${SCANNER_DISCOVERY_LATEST}: ${count} unique events (NOT yet imported to staging.miner_model_proposals — see P-022 follow-up)"
    else
        echo "[$(ts)] [${LABEL}] INFO scanner_discovery findings present at ${SCANNER_DISCOVERY_LATEST}; venv python missing so count not reported"
    fi
else
    echo "[$(ts)] [${LABEL}] INFO no scanner_discovery findings yet at ${SCANNER_DISCOVERY_LATEST}"
fi

# Continue to enrichment_sweep CSV import. Both presence-or-not is fine
# — neither dir's emptiness is a job failure.
if [[ ! -d "$SWEEP_DIR" ]]; then
    exit 0
fi

# Pick the most recent .csv in the sweep dir. macOS BSD `ls -t` works
# identically here (no GNU-specific switches). Empty result is a no-op.
latest_csv="$(/bin/ls -1t "${SWEEP_DIR}"/*.csv 2>/dev/null | /usr/bin/head -n 1 || true)"
if [[ -z "$latest_csv" ]]; then
    echo "[$(ts)] [${LABEL}] INFO no CSV files in ${SWEEP_DIR} — nothing to import"
    exit 0
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "[$(ts)] [${LABEL}] FATAL venv python missing or not executable: ${VENV_PYTHON}" >&2
    exit 1
fi
if [[ ! -f "${UPDATER_DIR}/catalog_updater.py" ]]; then
    echo "[$(ts)] [${LABEL}] FATAL catalog_updater.py missing at ${UPDATER_DIR}" >&2
    exit 1
fi
if [[ ! -d "$UPDATER_DATA_DIR" ]]; then
    echo "[$(ts)] [${LABEL}] FATAL data dir missing: ${UPDATER_DATA_DIR}" >&2
    exit 1
fi

echo "[$(ts)] [${LABEL}] INFO importing ${latest_csv} via catalog_updater.py --add-from-csv"
cd "$UPDATER_DATA_DIR"
exec "$VENV_PYTHON" "${UPDATER_DIR}/catalog_updater.py" --add-from-csv "$latest_csv"
