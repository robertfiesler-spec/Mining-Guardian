# Intelligence Catalog — Living Database Architecture

> **Status (2026-04-29 sweep):** Architectural reference. The Intelligence Catalog itself remains the canonical Bitcoin SHA-256 miner database (PostgreSQL `mining_guardian.intelligence_catalog.*`) and **all five layers below describe the going-forward architecture** — but the operational substrate moves from VPS to Mac Mini at the 2026-04-30 cutover. Specifically: (a) Layer 2's `discovery_log` table now lives in PostgreSQL on the Mac Mini, not in the VPS-era `guardian.db` SQLite snapshot; (b) cron schedules below describe the design — actual launchd plists ship with the installer; (c) anywhere this file says "VPS guardian.db," treat it as the **historical SQLite snapshot** (not live). Single-source-of-truth statement at line 150 has been corrected accordingly.

> "A living learning thing. Always evolving and expanding."

The Intelligence Catalog is designed to grow automatically. No new miner model, firmware version, or spec change should ever go unnoticed. This document describes the five-layer system that keeps the catalog current and makes it the most comprehensive Bitcoin SHA-256 miner database on the planet.

---

## Layer 1: Daily Automated Watchers (Cron Jobs)

Four scheduled tasks run every morning and compare the outside world against our catalog of 238+ models. They only alert when something NEW is found.

### Manufacturer Model Watcher (~6:00 AM CDT)
- Checks official product pages for Bitmain, MicroBT, Canaan, Bitdeer, and Auradine
- Looks for new Bitcoin SHA-256 model announcements
- Compares against `catalog_known_models.txt`
- If new model found: sends notification with model name, specs, source URL

### Community Intel Scanner (~7:19 AM CDT)
- Monitors Reddit (r/BitcoinMining, r/ASICMining), Twitter/X, BitcoinTalk, and mining YouTube
- Looks for model leaks/rumors, firmware experiences, field reports, hardware issues
- Categorizes findings: [NEW MODEL], [FIRMWARE], [FIELD REPORT], [ISSUE], [RUMOR]
- Captures real-world data that never makes it to official spec sheets

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

### discovery_log Table (PostgreSQL `mining_guardian.discovery_log` post-2026-04-30; historically in VPS `guardian.db` SQLite snapshot)
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

## Layer 3: Daily Deep Enrichment Sweep (Mon-Sat)

Every model in the catalog gets a comprehensive research sweep every week. The 238+ models are split across 6 days in a tiered rotation (~10am CDT daily).

### Tier System
- **Tier 1 (Current Gen)**: ~95 models — S21/S23, M60+, A15/A16, SealMiner A3/A4, Teraflux, Bitaxe. Checked **2x per week**.
- **Tier 2 (Recent)**: ~49 models — S19 series, M50/M53/M56, A1246-A1366, SealMiner A2. Checked **weekly**.
- **Tier 3 (Historical)**: ~94 models — S9, AvalonMiner 700-1100, Ebang, Innosilicon, etc. Checked **weekly**.

### 39 Data Points Tracked Per Model

**Hardware Deep Specs:** chip model, process node (nm), chips per board, boards per unit, voltage range, frequency range (MHz), PSU type, fan count/type, noise (dB), operating temp range, humidity tolerance, altitude limits

**Performance Profiles:** stock/low-power/turbo hashrate + power, real-world efficiency vs rated, degradation curve

**Firmware:** stock firmware versions, compatible 3rd-party firmware (Braiins, Vnish, LuxOS, Kratos), known bugs per version

**Lifecycle & Market:** announcement date, ship date, EOL date, MSRP at launch, current street price, warranty terms, hardware revisions

**Field Intelligence:** common failure modes, typical lifespan, hashboard interchangeability, immersion fluid compatibility, chip degradation issues

**Repair & Maintenance:** thermal paste specs, cleaning intervals, parts availability, repair difficulty rating

---

## Layer 4: Auto-Update Pipeline

The entire system is self-updating. When any layer discovers new data:

1. **Catalog Updater** (`intelligence-catalog/tools/catalog_updater.py`) writes changes to `unified_miner_index.json`
2. **API Hot-Reload** (`POST /api/catalog/reload`) refreshes the model list in memory — no restart needed
3. **Auto-Reload Daemon** checks the JSON file every 5 minutes for changes and reloads automatically
4. **Grafana Sync** (`--sync-grafana`) pushes the updated dropdown to the Intelligence Report dashboard
5. **Reference file** (`catalog_known_models.txt`) is regenerated so watchers compare against the latest list

### Catalog Updater CLI
```
python catalog_updater.py --add-model '{"slug": "...", ...}'
python catalog_updater.py --update-model antminer-s21 '{"specs": {...}}'
python catalog_updater.py --add-from-csv /path/to/enrichment_results.csv
python catalog_updater.py --notify-api http://localhost:8590
python catalog_updater.py --sync-grafana http://grafana.fieslerfamily.com
```

Deep merge: never overwrites existing data with null/empty values. Only adds or updates with real data.

---

## Layer 5: On-Demand Deep Dives

Bobby can request a deep dive on any specific model at any time. Also processes `acknowledged=0` entries from `discovery_log`.

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
- **Single source of truth** — Mac Mini PostgreSQL `mining_guardian` is the operational and canonical database (post-2026-04-30). The VPS-era `guardian.db` SQLite file is preserved as a historical snapshot only; SQLite is **not live**.

---

## File Locations

| File | Purpose |
|------|---------|
| `intelligence-catalog/data/unified_miner_index.json` | 238+ model catalog (JSON) |
| `intelligence-catalog/data/correction_rules.json` | Runtime spec correction rules |
| `catalog_known_models.txt` | Flat list for cron job comparison |
| `cron_tracking/manufacturer_watcher/` | Manufacturer watcher findings |
| `cron_tracking/aggregator_watcher/` | Aggregator watcher findings |
| `cron_tracking/firmware_tracker/` | Firmware tracker findings |
| `cron_tracking/community_scanner/` | Community intel scanner findings |
| `cron_tracking/enrichment_sweep/` | Daily enrichment sweep results (CSV) |
| `catalog_enrichment_schedule.json` | 7-day model rotation schedule |
| `catalog_enrichment_tiers.json` | Tier 1/2/3 model assignments |
| `intelligence-catalog/tools/catalog_updater.py` | Auto-updater CLI tool |
| PostgreSQL `mining_guardian.discovery_log` (post-2026-04-30; historical: VPS `guardian.db` snapshot) | Auto-discovered models/firmware from fleet |
