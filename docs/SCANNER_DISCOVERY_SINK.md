# Scanner discovery JSON sink (P-022)

The scanner persists every unknown-model and new-firmware observation to a durable file under `${INSTALL_ROOT}/cron_tracking/scanner_discovery/` on every scan. This document describes the on-disk shape so future readers (catalog importer, console, federation export) can consume it without re-deriving the layout.

## Layout

```
${INSTALL_ROOT}/cron_tracking/scanner_discovery/
    latest_findings.json      ← rolling dedup'd snapshot
    events-YYYY-MM-DD.jsonl   ← append-only audit trail
```

`${INSTALL_ROOT}` defaults to `/Library/Application Support/MiningGuardian` on the Mac mini. Override via `MG_DISCOVERY_SINK_DIR` env (explicit) or `MG_INSTALL_ROOT` env (canonical). Falls back to `<repo>/cron_tracking/scanner_discovery/` for dev-tree invocation.

## `latest_findings.json` shape

```json
{
  "version": 1,
  "updated_at": "2026-05-08T15:42:00+00:00",
  "events": {
    "unknown_model|S19JPro": {
      "event_type": "unknown_model",
      "model_name": "S19JPro",
      "firmware_version": "",
      "first_seen": "2026-05-07T15:36:18+00:00",
      "last_seen":  "2026-05-08T15:42:00+00:00",
      "count": 36,
      "ips": ["192.168.188.36", "192.168.188.37", "..."],
      "miner_id_examples": ["54504", "63940"],
      "source": "scanner_discovery"
    },
    "new_firmware|S19JPro|0.9.9.3-stage29.2799": {
      "event_type": "new_firmware",
      "model_name": "S19JPro",
      "firmware_version": "0.9.9.3-stage29.2799",
      "first_seen": "2026-05-07T15:36:18+00:00",
      "last_seen":  "2026-05-08T15:42:00+00:00",
      "count": 36,
      "ips": ["192.168.188.36", "..."],
      "miner_id_examples": ["54504"],
      "source": "scanner_discovery"
    }
  }
}
```

- **Key format:** `unknown_model|<model>` or `new_firmware|<model>|<firmware>`. Stable across scans; dedup happens on this key.
- **`count`:** total times this key has been observed across all scans since the file was created or reset.
- **`ips`:** capped at 16 distinct entries (`_MAX_IPS_PER_KEY` in `core/discovery_sink.py`). Trimmed FIFO to bound file size on a noisy fleet.
- **`miner_id_examples`:** same cap; example AMS miner IDs for the operator/console to spot-check.
- **`first_seen` / `last_seen`:** ISO-8601 UTC.

## `events-YYYY-MM-DD.jsonl` shape

One JSON object per line, newline-terminated. Never deduped — this is the receipt that every observation was captured.

```json
{"ts":"2026-05-08T15:42:00+00:00","event_type":"unknown_model","model_name":"S19JPro","firmware_version":"","ip":"192.168.188.36","miner_id":54504,"source":"scanner_discovery"}
```

Use this file when you want to reconstruct the scan-by-scan history (e.g., when did a new firmware first appear on which IP). The rolling JSON is the dedup'd "latest state"; the JSONL is the audit log.

## Atomic-write safety

`record_discovery` writes via `tempfile.mkstemp` + `os.replace`, so a crash mid-write never leaves a corrupted `latest_findings.json`. If a reader observes a torn file (manually edited, or from a prior pre-P-022 build), the sink resets the snapshot in place rather than crashing — the JSONL audit trail is the source of truth for any data the snapshot reset would lose.

## Producers (current)

- `core/mining_guardian.py::_check_discoveries` — calls `record_discovery("unknown_model", …)` and `record_discovery("new_firmware", …)` alongside the existing `db.save_discovery(...)` write to `discovery_log`. Both writes happen on every observation; the file sink is the file-based intake surface, the DB write is the operational audit trail.

## Consumers (current)

- `intelligence-catalog/tools/run_daily_catalog_import.sh` — surfaces presence + count of unique events in its INFO output. **Does NOT yet promote to `staging.miner_model_proposals`.** Promotion is the P-022-followup PR scope.

## Consumers (planned)

- **`catalog_updater.py --add-from-scanner-discovery`** (future): read `latest_findings.json`, materialize one `staging.miner_model_proposals` row per `unknown_model` key with the AMS-emitted name, the live count + first_seen + last_seen, and the IPs as enrichment metadata. Operator review promotes to `hardware.miner_models`.
- **D-19 operator console** (future): expose the rolling JSON on a `/discoveries` page so the operator sees what the scanner is finding without reading scanner.err.log.
- **`combine_knowledge.py` federation** (future): merge per-customer `latest_findings.json` into `master_knowledge.json` so cross-customer model emergence is visible.

## Why a file sink (not just the DB)

Three reasons:

1. **Symmetry with the 5 Perplexity watchers.** Aggregator Watcher, Manufacturer Model Watcher, Firmware Tracker, Community Intel Scanner, and Deep Enrichment Sweep all write JSON to `cron_tracking/<watcher>/`. The scanner is the 6th source; making it write the same way means the same daily-import job pattern can consume them all.
2. **Audit-trail durability.** `discovery_log` is in `mining_guardian` (operational) by design — but the catalog-bound intake surface is `cron_tracking/`. The split-brain gap (data persisted in operational DB, never read by catalog importer) is closed by writing to BOTH.
3. **Federation-ready.** `knowledge.json` exports (Vision Anchor 4) are a file-copy operation. A file sink for scanner discovery means the same file-copy works without a Postgres dump.

## Operational checks

```bash
# On the Mini:
sudo cat "/Library/Application Support/MiningGuardian/cron_tracking/scanner_discovery/latest_findings.json" | python3 -m json.tool | head -40
sudo wc -l "/Library/Application Support/MiningGuardian/cron_tracking/scanner_discovery/events-$(date -u +%Y-%m-%d).jsonl"
sudo grep "scanner_discovery" "/Library/Application Support/MiningGuardian/logs/scheduled/catalog_import.out.log" | tail -10
```
