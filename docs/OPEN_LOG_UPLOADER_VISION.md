# Open Log Uploader & Auto-Learning System

**Captured: April 8, 2026 by Bobby (verbatim intent)**
**Status: VISION — not yet built. Designed but not implemented.**
**Bigger than `scripts/manual_log_upload.py` which only handles 3 hardcoded miner types.**

---

## The vision in Bobby's words

> "When I need a general uploader I might have 10,000 logs coming in of all different types and models. It is going to have to read through, determine what it is, then pull the web for the statistics of that miner and start building its stock database information and start running tests, confirming diagnosis, learning."

This is the long-term knowledge engine. Every log that lands in the system makes the system smarter about that miner family. After enough logs, Mining Guardian should be able to look at any log from any vendor and produce a confident diagnosis without a human ever having told it what the miner is.

---

## What it needs to do

### 1. Universal ingestion (any format)
- **Drag-and-drop zone** on the AI dashboard for one or many files at once
- **Folder upload** — point at a folder, ingest everything recursively
- **Zip / tar.gz / tar / 7z extraction** in-memory before parsing
- **PDF tech-support files** (Auradine ships these as 18MB+ PDFs with embedded log text)
- **Compressed cglog bundles** (BiXBiT firmware exports)
- **Plain text files** (`.log`, `.txt`)
- **Email attachments** if a friend forwards a repair shop dump
- **Filesystem watcher** on a designated `inbox/` directory — anything dropped there gets picked up automatically
- **Repair shop bulk drop** — Bobby has a friend with a miner repair shop sending ~1M+ data points + logs eventually

### 2. Auto-detect miner type, brand, model, firmware
Detection layered from cheap → expensive:

1. **Filename hints** — `S19jpro_53487.zip`, `AH3880_techsupport_*.pdf`, `cglog_init_*`
2. **Path/structure fingerprints** — `nvdata/cglog_init_*` = BiXBiT firmware; per-daemon directories (`gcminer/`, `monitord/`, `osutil/`) = Auradine FluxOS; `kern.log` + `monitorAPI.log` = stock Antminer
3. **Header lines** — first ~2KB of any text log: look for `AH3880`, `S19j Pro`, `S21 Hyd`, `FluxOS`, `gcminer`, `auradine`, `bitmain`, `whatsminer`, `MicroBT`
4. **Structured field signatures** — BiXBiT `cglog` uses `Chain[N]`; Auradine uses `chip N/M`; CGMiner uses `[ASIC0]`
5. **PDF text scan** — for tech support PDFs, extract the first 5 pages and look for the same brand/model markers

Output of detection:
```json
{
  "brand": "Auradine",
  "model": "AH3880",
  "firmware": "FluxOS 3.0.0",
  "chassis": "080010004D",
  "control_board_sn": "SE08CB250804002T",
  "mac": "04:25:e8:bd:66:f0",
  "confidence": 0.95,
  "evidence": ["filename match", "PDF header", "DVFS log format"]
}
```

### 3. Web spec lookup — build "stock database" entries
First time the system sees a model it doesn't recognize:

1. **Web search** the manufacturer site:
   - `auradine.com` for AH3880 → product page has Ths target, board count, chip count, power rating, voltage range
   - `bitmain.com` for S19j Pro → spec sheet
   - `microbt.com` for WhatsMiner M50/M60 → datasheet
2. **Search forums** as fallback — bitcointalk, miningforum, reddit r/BitcoinMining for community-confirmed specs
3. **Search the official docs PDFs** that operators upload (Bobby has `Teraflux Miner Hardware Reference 2025-03.pdf` in his Downloads — those should be ingestible too as a "spec source" not a "diagnostic log")
4. **Build a `model_specs` row** in the DB:
```sql
CREATE TABLE model_specs (
  model_id TEXT PRIMARY KEY,
  brand TEXT,
  model TEXT,
  firmware_family TEXT,
  ths_stock REAL,
  ths_min REAL,
  ths_max REAL,
  power_w_stock INTEGER,
  power_w_max INTEGER,
  voltage_v REAL,
  board_count INTEGER,
  chips_per_board INTEGER,
  total_chips INTEGER,
  cooling_type TEXT,  -- air | hydro | immersion
  release_date TEXT,
  source TEXT,  -- 'auradine.com', 'pdf:Teraflux Hardware Ref 2025-03', 'forum:r/BitcoinMining'
  source_url TEXT,
  specs_json TEXT,  -- the full extracted spec dict
  created_at TEXT,
  updated_at TEXT,
  confidence REAL,
  human_verified INTEGER DEFAULT 0
);
```
5. **Once a `model_specs` row exists**, every future log for that model uses it as the baseline. No more web search for that model unless an operator marks it stale.

### 4. Run diagnostic tests on every uploaded log
For every log the system runs a **diagnostic test battery** scoped to the detected model. Examples:

**Universal tests (any model):**
- Hashrate vs stock — is current hashrate within 10% of `ths_stock`?
- Power draw vs stock — is wattage within 10% of `power_w_stock`?
- Chip temp range — any chip ≥ 84°C? (operator rule)
- Dead chips — any chips reporting 0V or `null` from voltage table?
- Error/warn/fatal/panic line count — anomaly score
- Pool connection — any rejected shares > 1% of accepted?
- Uptime — any unexplained reboots in the log window?

**BiXBiT-specific tests:**
- Chain detached warnings (`Chain[N] detached`)
- Autotune empty/missing
- Power calibration missing
- Per-chain voltage/freq deltas across chains

**Auradine-specific tests:**
- DVFS voltage out-of-range alarms (`chip N/M` voltage)
- DVFS power reduction events (firmware backing off the tune target)
- PowerState voltage clip events (PSU pushing above Vmax)
- Board-level voltage zero (`avg_volt N:0.0000` = dead board)
- Hitrate < 0.90 (chips not hitting expected target)
- Inlet temp vs outlet temp delta — heat removal sanity check

**Stock Antminer / WhatsMiner tests:**
- (To be filled in as Bobby's friend's repair shop logs arrive — they'll define the baseline)

Each test produces:
```json
{
  "test_id": "auradine_dead_board",
  "miner_id": "192.168.188.28",
  "log_id": 12345,
  "result": "FAIL",
  "severity": "HIGH",
  "evidence": "avg_volt 3:0.0000 across 1,247 DVFS log lines spanning 6h22m",
  "first_seen": "2026-04-07T19:34:49Z",
  "last_seen": "2026-04-08T01:57:11Z",
  "confidence": 0.99,
  "diagnosis": "Board 3 electrically dead — boards 1+2 compensating, miner running at 70% of tune target 591 Ths (current 412 Ths)",
  "recommended_action": "Schedule physical board replacement at next service window. Continue mining on 2 boards meanwhile — no thermal risk."
}
```

### 5. Confirm / refine diagnoses across logs
- A **first** log from a model produces a tentative diagnosis with `confidence` in the test row
- A **second** log from the same miner_id confirms or contradicts each finding
- A **third** log establishes a pattern across time
- After **N≥5** logs from the same miner, the diagnosis is locked unless an operator manually opens it for re-evaluation
- After **N≥10** logs of the **same fault type across different miners of the same model**, the system creates a **model-level pattern** in `known_patterns` (e.g., "AH3880 Board 3 failures cluster around chassis serials 080010xxx batch — possible manufacturing defect")

### 6. Learning loop
- Every diagnosis run gets logged with both Qwen and Claude analyses (the dual-model jump-start phase Bobby asked for earlier today)
- After **10 dual-model runs** Claude's diagnoses become the "gold standard" against which Qwen is measured
- Every disagreement between Qwen and Claude becomes a training data point for the next weekly cohort training run
- The weekly training prompt gets updated with examples of "Qwen missed this, Claude caught it" pairs so Qwen progressively closes the gap
- Once Qwen matches Claude on **N consecutive cases**, the system can safely fall back to local-only for that fault type, freeing Claude API budget for new fault types it hasn't seen

### 7. Ingestion provenance
Every uploaded log gets a permanent record of:
- **Where it came from** (drag-drop, folder watch, email, repair shop bulk, AMS auto-fetch, manual API call)
- **Who uploaded it** (operator name from Slack ID, or "system" for auto-fetch)
- **When** (timestamp)
- **What was detected** (brand/model/firmware/serial)
- **What spec lookup ran** (web URL hit, PDF source consulted, cache hit)
- **What tests fired** and their results
- **What both LLMs said**
- **What the operator confirmed/rejected** (if any)

This becomes the audit trail for "how did the system reach this conclusion" — critical for the eventual switch to autonomous remediation.

---

## Architecture sketch

```
┌─────────────────────────────────────────────────────────────────────┐
│                       INGESTION LAYER                                │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐    │
│  │ Drag/   │  │ Folder   │  │ Email    │  │ AMS auto-fetch   │    │
│  │ Drop UI │  │ Watcher  │  │ Inbox    │  │ (existing daemon)│    │
│  └────┬────┘  └────┬─────┘  └────┬─────┘  └────────┬─────────┘    │
│       │            │              │                  │              │
│       └────────────┴──────────────┴──────────────────┘              │
│                          │                                          │
│                          ▼                                          │
│       ┌──────────────────────────────────────┐                     │
│       │  Universal extractor:                │                     │
│       │  zip/tar/7z/pdf/text → file dict    │                     │
│       └──────────────────┬───────────────────┘                     │
└──────────────────────────┼─────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     DETECTION LAYER                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ Filename     │→ │ Path/struct  │→ │ Header content scan      │ │
│  │ hints        │  │ fingerprints │  │ (first 2KB of each file) │ │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘ │
│                          │                                          │
│                          ▼                                          │
│       ┌──────────────────────────────────────┐                     │
│       │  detected_miner = {brand, model,     │                     │
│       │  firmware, sn, mac, confidence}      │                     │
│       └──────────────────┬───────────────────┘                     │
└──────────────────────────┼─────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  SPEC LOOKUP LAYER                                   │
│              (only if model_specs row missing)                       │
│  ┌──────────────┐  ┌────────────────┐  ┌────────────────────────┐ │
│  │ Manufacturer │  │ Forum / wiki   │  │ Operator-uploaded PDF  │ │
│  │ web search   │  │ fallback       │  │ docs (cached)          │ │
│  └──────────────┘  └────────────────┘  └────────────────────────┘ │
│                          │                                          │
│                          ▼                                          │
│       ┌──────────────────────────────────────┐                     │
│       │  INSERT INTO model_specs ...         │                     │
│       │  (one row per model, reused forever) │                     │
│       └──────────────────┬───────────────────┘                     │
└──────────────────────────┼─────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PARSING LAYER                                     │
│  Brand-specific parsers, each producing structured findings:        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────┐│
│  │ BiXBiT       │  │ Auradine     │  │ Stock        │  │ Future: ││
│  │ cglog parser │  │ DVFS parser  │  │ Antminer     │  │ Whats-  ││
│  │              │  │              │  │ kern parser  │  │ Miner   ││
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────┘│
└──────────────────────────┼─────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  DIAGNOSTIC TEST LAYER                               │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Test battery (model-aware) → test_results table             │  │
│  │  • Universal tests (always run)                               │  │
│  │  • Brand-specific tests (BiXBiT/Auradine/Stock/etc)          │  │
│  │  • Model-specific tests (S19jPro vs AH3880 vs M60)           │  │
│  └──────────────────────────────────────────────────────────────┘  │
└──────────────────────────┼─────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      LLM LAYER (dual-model)                          │
│  ┌──────────────────┐  ┌──────────────────┐                        │
│  │ Local Qwen 2.5   │  │ Claude Sonnet 4.6│                        │
│  │ 32B Q4           │  │ (jump-start)     │                        │
│  └────────┬─────────┘  └────────┬─────────┘                        │
│           │                      │                                  │
│           └──────────┬───────────┘                                  │
│                      ▼                                               │
│   ┌──────────────────────────────────────────┐                     │
│   │ Both analyses stored separately for      │                     │
│   │ side-by-side comparison and learning     │                     │
│   └──────────────────┬───────────────────────┘                     │
└──────────────────────┼─────────────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│             CONFIRMATION & PATTERN LAYER                             │
│  • If miner has prior logs → cross-check current diagnosis with    │
│    historical findings, update confidence scores                    │
│  • If model has prior logs from other miners → check if this       │
│    fault is becoming a model-level pattern                          │
│  • After N samples of same fault → promote to known_patterns       │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  PRESENTATION LAYER                                  │
│  • Slack #mining-guardian-alerts: per-upload summary               │
│  • AI dashboard: model_specs browser, fault history per miner,     │
│    cross-miner pattern view, trust scores per model                │
│  • Audit trail: every conclusion traceable to source logs          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Tables that need to exist

```sql
-- Provenance
CREATE TABLE log_uploads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uploaded_at TEXT NOT NULL,
  source TEXT NOT NULL,           -- 'drag_drop', 'folder_watch', 'email', 'ams_fetch', 'repair_shop_bulk'
  uploaded_by TEXT,                -- slack user id or 'system'
  original_filename TEXT,
  file_size_bytes INTEGER,
  file_count INTEGER,              -- for archives
  detected_brand TEXT,
  detected_model TEXT,
  detected_firmware TEXT,
  detected_sn TEXT,
  detected_mac TEXT,
  detection_confidence REAL,
  detection_evidence TEXT,
  notes TEXT
);

-- Stock specs library (reused across all logs of the same model)
CREATE TABLE model_specs (
  model_id TEXT PRIMARY KEY,
  brand TEXT, model TEXT, firmware_family TEXT,
  ths_stock REAL, ths_min REAL, ths_max REAL,
  power_w_stock INTEGER, power_w_max INTEGER,
  voltage_v REAL, board_count INTEGER,
  chips_per_board INTEGER, total_chips INTEGER,
  cooling_type TEXT, release_date TEXT,
  source TEXT, source_url TEXT,
  specs_json TEXT,
  created_at TEXT, updated_at TEXT,
  confidence REAL, human_verified INTEGER DEFAULT 0
);

-- Per-upload diagnostic test results
CREATE TABLE diagnostic_test_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  upload_id INTEGER NOT NULL,
  miner_id TEXT,
  test_id TEXT NOT NULL,
  result TEXT,                     -- PASS / WARN / FAIL
  severity TEXT,                   -- LOW / MEDIUM / HIGH / CRITICAL
  evidence TEXT,
  first_seen TEXT, last_seen TEXT,
  confidence REAL,
  diagnosis TEXT,
  recommended_action TEXT,
  created_at TEXT,
  FOREIGN KEY (upload_id) REFERENCES log_uploads(id)
);

-- Model-level cross-miner patterns
CREATE TABLE known_patterns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pattern_id TEXT UNIQUE,
  brand TEXT, model TEXT,
  fault_type TEXT,
  first_observed TEXT,
  last_observed TEXT,
  miner_count INTEGER,             -- distinct miners showing this fault
  evidence_count INTEGER,          -- total log uploads showing this fault
  description TEXT,
  recommended_action TEXT,
  confidence REAL,
  human_verified INTEGER DEFAULT 0
);

-- Spec source cache (so we don't re-fetch the same Auradine page 100 times)
CREATE TABLE spec_source_cache (
  url TEXT PRIMARY KEY,
  fetched_at TEXT,
  content_type TEXT,
  content TEXT,                    -- raw HTML / extracted text
  expires_at TEXT
);
```

---

## Open questions to resolve before building

1. **Drag-and-drop UI** — Retool? Custom React? FastAPI + a small HTML form? (Bobby's preference TBD)
2. **Folder watcher** — `watchdog` Python lib polling `inbox/` every 30s? Or systemd path unit?
3. **Email ingestion** — IMAP poll on a dedicated `mining-guardian-logs@bixbit.io` mailbox? Or just have ops forward attachments to a Slack channel and pick them up via Slack API?
4. **Web search budget** — Bobby OK with the system hitting auradine.com/bitmain.com/microbt.com on cold-cache? Should there be a per-model rate limit (max 1 fetch per week per model)?
5. **PDF spec ingestion** — when Bobby uploads `Teraflux Miner Hardware Reference 2025-03.pdf`, the system should recognize it as a SPEC SOURCE (not a diagnostic log) and use it to populate `model_specs` for ALL Teraflux models in one shot. How does the user signal "this is a spec sheet, not a log"? File naming convention? Upload UI button? Auto-detect from PDF content?
6. **Repair shop bulk drop** — when 1M+ logs land at once, do we process synchronously (slow but simple) or queue + worker (fast but more code)? Probably worker pool.
7. **Confidence thresholds** — at what confidence does the system auto-act vs ask for confirmation? Currently `0.85+` = AUTO, `0.60-0.85` = ASK, `<0.60` = HUMAN. Re-validate after the first few hundred uploads.
8. **Conflict resolution** — if Qwen says "dead chain" and Claude says "PSU failing", what does the system show the operator? Both verdicts side-by-side with confidence scores, no auto-resolution until enough training data exists.
9. **Spec authority hierarchy** — when manufacturer site says 110 TH/s but operator-uploaded PDF says 104 TH/s, which wins? Probably PDF (operator-curated > web-scraped).
10. **Model fingerprint stability** — what happens when a manufacturer ships a firmware update that changes log format? Detection has to handle versioned fingerprints.

---

## What's already built that this can reuse

- ✅ `core/mining_guardian.py` `GuardianDB.save_logs()` — already deduplicates by `(miner_id, log_file, health_status)`, already parses BiXBiT cglog into structured tables
- ✅ `core/mining_guardian.py` `parse_and_save_hardware()` — extracts board serial, chip die/bin, PCB version, control board, PSU version from BiXBiT miner.log
- ✅ `core/mining_guardian.py` `parse_log_metrics()` — per-chip hashrate, PSU voltage, system health, chain events from BiXBiT logs
- ✅ `ai/local_llm_analyzer.py` `analyze_restart_logs()` — Qwen comparison prompt + execution
- ✅ `ai/claude_log_comparison.py` `compare_logs_via_claude()` — Claude comparison prompt + execution (built today)
- ✅ `core/mining_guardian.py` `_run_post_action_log_comparison()` — dual-model wiring (built today)
- ✅ `scripts/manual_log_upload.py` — CLI tool with auto-detect for 3 hardcoded types (built today, will become the foundation for the open uploader)
- ✅ Auradine DVFS/PowerState/voltage parser inside `manual_log_upload.py` — recognizes the patterns from your screenshot

What needs to be added: web spec lookup, model_specs table, diagnostic test battery, drag-drop UI, folder watcher, email/Slack ingestion, pattern promotion engine.

---

## Estimate

This is **2-4 weeks of focused work** depending on how fancy we go on the UI. The DB tables + parser plumbing + test battery is maybe 5 days. Web spec lookup with caching is 2-3 days. Drag-drop UI is 2-5 days depending on Retool vs custom. Folder/email/Slack ingestion is 1 day each. Repair shop bulk-import worker pool is 2-3 days. Model-level pattern promotion engine is 3-5 days.

Recommend doing it in this order **after the demo lands**:
1. **Phase 1 (Week 1):** `model_specs` table + web spec lookup + basic drag-drop UI on the AI dashboard. Get to "I can drag a log onto a webpage and it tells me what miner it is."
2. **Phase 2 (Week 2):** Diagnostic test battery + dual-model analysis wired into upload flow. Get to "Drag a log, get a verdict and recommended action."
3. **Phase 3 (Week 3):** Folder watcher + Slack/email ingestion + audit trail UI. Get to "Operator can ingest from anywhere, see complete history of every conclusion."
4. **Phase 4 (Week 4):** Pattern promotion engine + repair shop bulk worker pool. Get to "1,000 logs from a partner shop become 50 model-level insights overnight."
