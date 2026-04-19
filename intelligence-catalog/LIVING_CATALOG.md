# Intelligence Catalog — Living Database Architecture

> "A living learning thing. Always evolving and expanding."

The Intelligence Catalog is designed to grow automatically. No new miner model, firmware version, or spec change should ever go unnoticed. This document describes the three-layer system that keeps the catalog current.

---

## Layer 1: Daily Automated Watchers (Cron Jobs)

Three scheduled tasks run every morning and compare the outside world against our catalog of 235+ models. They only alert when something NEW is found.

### Manufacturer Model Watcher (~6:00 AM CDT)
- Checks official product pages for Bitmain, MicroBT, Canaan, Bitdeer, and Auradine
- Looks for new Bitcoin SHA-256 model announcements
- Compares against `catalog_known_models.txt`
- If new model found: sends notification with model name, specs, source URL

### Aggregator Watcher (~6:30 AM CDT)
- Checks Hashrate Index, AsicMinerValue, F2Pool, and retailer sites
- Looks for new model listings AND spec corrections for existing models
- Cross-references against the catalog
- If new model or significant spec discrepancy found: sends notification

### Firmware Tracker (~7:00 AM CDT)
- Checks manufacturer support pages and mining news sites
- Tracks new firmware releases from Bitmain, MicroBT, Canaan, and third-party (Braiins OS, Vnish, LuxOS)
- Focuses on firmware that changes performance profiles (hashrate, efficiency, power modes)
- If new firmware found: sends notification with affected models and changes

### How Watchers Work
- Each watcher saves its findings to `/home/user/workspace/cron_tracking/<watcher_name>/latest_findings.json`
- Findings are compared against previous runs to avoid duplicate notifications
- No notification = nothing new happened (silent exit)
- The catalog_known_models.txt reference file should be regenerated after each catalog update

---

## Layer 2: Fleet Auto-Discovery (Scan Loop)

The Mining Guardian scan loop monitors miners via AMS (BiXBiT or other controllers). When it encounters something it hasn't seen before, it logs it automatically.

### discovery_log Table (guardian.db)
Every unknown model or firmware version gets recorded with:
- `device_name` — raw name from AMS
- `firmware_version` — firmware string
- `hashrate`, `temp_chip`, `consumption` — live readings at time of discovery
- `board_count`, `chip_count` — hardware details
- `raw_data` — full JSON dump of EVERYTHING AMS sends about that miner
- `first_seen` / `last_seen` — timestamps
- `acknowledged` — 0=new, 1=reviewed, 2=added to catalog

### What Gets Logged
1. **New Model**: `device_name` doesn't match any known catalog entry → logged as `discovery_type='new_model'`
2. **New Firmware**: firmware version string never seen before → logged as `discovery_type='new_firmware'`

### API Access
- `GET /api/discoveries` — View all unacknowledged discoveries
- `POST /api/discoveries/{id}/acknowledge` — Mark as reviewed or added-to-catalog

### Why This Matters
Bobby's rule: "if a new data point comes up that it has never seen before, mark it down, register it as a new data point, not skip over it."

This is how the S21E-XP-HYDRO, Sealminer A2, and Teraflux AH3880 in the USA 188 fleet would be auto-detected if they weren't already cataloged.

---

## Layer 3: Monthly Enrichment Sweeps

Once a month (or on-demand), a deep research pass processes all accumulated discoveries:

1. Take all `acknowledged=0` entries from `discovery_log`
2. Take all new model alerts from the daily watchers
3. Research full specs: hashrate, power, efficiency, cooling type, board count, chip count, release date, variants
4. Generate SQL INSERT statements for the PostgreSQL Intelligence Catalog
5. Bobby reviews and approves
6. Committed to the catalog, `acknowledged` updated to 2

---

## Catalog ID Numbering Convention

| Range | Manufacturer |
|-------|-------------|
| 1000s | Bitmain |
| 2000s | MicroBT |
| 3000s | Canaan |
| 4000s | Bitdeer |
| 5000s | Auradine |
| 6000s | Innosilicon |
| 7000s | Ebang |
| 8000s | StrongU |
| 9xxx  | Historical/Other |

---

## Design Principles

- **Capture everything. Discard nothing.** — 10-year design horizon
- **Every variant matters** — m63, m63s, m63+, m63s+ are all different models
- **Bitcoin SHA-256 ONLY** — No other algorithms
- **Auto-discovery is a hard requirement** — Unknown fields get registered, never skipped
- **Single source of truth** — ROBS-PC PostgreSQL is the golden copy, VPS guardian.db is operational

---

## File Locations

| File | Purpose |
|------|---------|
| `intelligence-catalog/data/unified_miner_index.json` | 235+ model catalog (JSON) |
| `intelligence-catalog/data/correction_rules.json` | Runtime spec correction rules |
| `catalog_known_models.txt` | Flat list for cron job comparison |
| `cron_tracking/manufacturer_watcher/` | Manufacturer watcher findings |
| `cron_tracking/aggregator_watcher/` | Aggregator watcher findings |
| `cron_tracking/firmware_tracker/` | Firmware tracker findings |
| `guardian.db → discovery_log` | Auto-discovered models/firmware from fleet |
