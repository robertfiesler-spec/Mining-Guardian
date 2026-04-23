# Mining Guardian — Intelligence Catalog Importer  v3.3

> *Capture Everything. Discard Nothing.*

A single-file Python web application for importing research data into PostgreSQL. Drag-and-drop CSVs, SQL scripts, ZIP bundles, JSON arrays, Excel files, TSVs, and miner log archives (`.tar`/`.tgz`/`.tar.gz`/`.rar`) into the `knowledge` schema with auto-generated, dollar-quoted INSERT statements.

**v3.3** adds mass-import hardening for large batch runs (50+ archives): streaming SSE progress, per-archive error isolation, sha256 deduplication, cancel kill-switch, resolver stats visibility, and an unresolved sample preview endpoint.

**v3.2** adds Miner Identity extraction, per-file raw JSON capture, and per-archive resolver stamping of `field_log_miner_identity`.

**v3.1** upgrades to the Layer 2 **Two-Tier Resolver**: a clean, independently-testable `resolver.py` module implementing the full five-step resolution pipeline (normalizer → Tier-1 exact → Tier-1 V-code-stripped → Tier-2 hashrate-bin → unresolved fallback).

**v3** adds the Layer 2 Field Intelligence Pipeline: alias resolution, catalog slug stamping, raw JSON capture, unknown field surveillance, RMA tracking, dormant miner detection, and structured run logging.

---

## Quick Start

### 1. Install dependencies

```bash
pip install flask psycopg2-binary openpyxl rarfile
```

- `flask` — web server
- `psycopg2-binary` — PostgreSQL driver (self-contained binary, no libpq needed)
- `openpyxl` — optional, only needed for `.xlsx` support
- `rarfile` — optional, only needed for `.rar` archive support

### 2. (Optional) Install `unrar` binary for RAR support

RAR extraction requires the `unrar` binary on your PATH:

| Platform | Command |
|----------|---------| 
| Ubuntu/Debian | `apt-get install unrar` |
| macOS | `brew install unrar` |
| Windows | Download from [rarlab.com](https://www.rarlab.com/rar_add.htm) and add to PATH |

The tool will report a clear error if `unrar` is missing when a `.rar` file is uploaded.

### 3. Apply the database migrations (v3 new step)

Apply in **strict numerical order**. Each migration is idempotent (all statements use `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`), so re-running is safe.

```bash
# 1. Bootstrap the field_log_* tables and mg.import_runs (extracted from
#    mg_import.py's runtime bootstrap block)
psql -U guardian_admin -d mining_guardian -f sql/migrations/000_bootstrap_field_log_tables.sql

# 2. Apply the Layer 2 resolver schema (hardware.model_aliases,
#    mg.model_family_aliases, mg.unresolved_models, partitioned raw_json, etc.)
psql -U guardian_admin -d mining_guardian -f sql/migrations/002_layer2_and_learning_foundation.sql

# 3. Seed the Tier-1 alias table (12,852 rows — canonical slugs + V-code variants)
psql -U guardian_admin -d mining_guardian -f sql/seed/001_hardware_model_aliases_tier1.sql

# 4. Seed the Tier-2 family alias table (1,494 rows — ambiguous aliases resolved by hashrate)
psql -U guardian_admin -d mining_guardian -f sql/seed/002_mg_family_aliases_tier2.sql
```

**Ordering matters:** 000 must run before 002 because 002 expects `knowledge.field_log_miner_identity` to exist so it can add resolver-stamp columns. If you skip 000, `mg_import.py`'s own runtime bootstrap block will create the tables anyway on first connection — but the formal migration path is what a fresh environment should use.

**Note:** there is no `001_initial_schema.sql` in this tool. The repo-level `migrations/001_initial_schema.sql` at the project root is the VPS Mining Guardian Postgres schema (monolithic `public.*` tables) and is unrelated to the catalog.

### 4. Run the tool

```bash
python mg_import.py
```

Opens at **http://localhost:5050**

To use a different port:

```bash
PORT=8080 python mg_import.py
```

Enable debug logging:

```bash
MG_DEBUG=1 python mg_import.py
```

---

## Requirements

- Python 3.8+
- Flask 2.x or 3.x
- psycopg2-binary 2.9+
- openpyxl (optional, for `.xlsx`)
- rarfile (optional, for `.rar`)

---

## Default Database Connection

| Setting  | Default             |
|----------|---------------------|
| Host     | `localhost`         |
| Port     | `5432`              |
| Database | `mining_guardian`   |
| User     | `guardian_admin`    |
| Password | `MiningGuardian2026!` |

All connection settings are editable in the GUI — no config file needed.

---

## Supported File Types

| Extension | Handling |
|-----------|----------|
| `.csv`    | Auto-generates `CREATE TABLE` + `INSERT` statements in `knowledge.research_<name>` |
| `.tsv`    | Same as CSV but tab-delimited |
| `.txt`    | Treated as CSV (comma-delimited) |
| `.sql`    | Passed through directly to PostgreSQL |
| `.json`   | Array of objects → same treatment as CSV |
| `.xlsx`   | First sheet → same treatment as CSV (requires openpyxl) |
| `.zip`    | Extracted recursively; each `.csv`, `.sql`, `.xlsx`, `.json` inside is processed |
| `.tar`    | Miner log bundle → parsed into `knowledge.field_log_*` tables |
| `.tgz`    | Same as `.tar` (gzip-compressed) |
| `.tar.gz` | Same as `.tar` (gzip-compressed, alternate extension) |
| `.rar`    | Same as `.tar` (requires rarfile + unrar binary) |

---

## Miner Log Archive Support

When a `.tar`, `.tgz`, `.tar.gz`, or `.rar` file is dropped, the tool:

1. Computes SHA-256 of the archive bytes
2. Detects the archive shape (WhatsMiner or Antminer) by peeking at member names
3. Extracts to a temp directory (cleaned up after import)
4. Parses all recognized log files
5. Generates dollar-quoted `INSERT` SQL for 8 `knowledge.field_log_*` tables
6. Executes (Auto-Import) or displays (Review First)
7. **v3:** Runs Layer 2 post-processing if a DB connection is available (alias lookup, raw JSON, unknown fields)

### Archive Shapes

**WhatsMiner bundles** — root folder is `<ip>.logs/` containing:
- `miner_overview.log` — INI-style identity/EEPROM data
- `power.log` / `power_error.log` — time-series power telemetry
- `api.log` — per-board STATS sections (PHP-array or colon format)
- `pools.log` — pool change log
- `temp{N}_{T}.xls` — board temperature snapshots
- `chip_temp_slot{N}_{serial}` — chip temperature maps
- `ams_bixbit.json` — AMS device registration (api_key is redacted)

**Antminer bundles** — root tree is `nvdata/YYYY-MM/DD/cglog_init_*/`:
- `miner.log` — timestamped log with autotune events, errors, device info
- `config/cgminer.conf` — pool configuration

### Trust Context

Archives are from Bobby's own fleet. Lenient extraction via standard `tarfile.extractall` / `rarfile.RarFile.extractall` is intentional. **Do not use this tool with untrusted archives from unknown sources.**

---

## New Tables (field_log_*)

All 8 tables are auto-created on first import (`CREATE TABLE IF NOT EXISTS`).

```
knowledge.field_log_imports
  One row per archive. Stores sha256, detected shape, IP, model, firmware,
  timestamp, file count, and any parse warnings.
  v3 adds: catalog_slug (stamped by Layer 2 alias resolution)

knowledge.field_log_miner_identity
  One row per EEPROM slot (WhatsMiner). Stores PCB serial, chip data,
  hashrate, firmware version, MAC, control board, kernel version.

knowledge.field_log_power_samples
  One row per line in power.log / power_error.log.
  Columns: en/eset, iout, vout/vset, iin0/1/2, vin0/1/2, pin, t0/t1/t2, stat.

knowledge.field_log_temp_snapshots
  Board temperature snapshots (temp{N}_{T}.xls) and chip temperature maps
  (chip_temp_slot{N}_{serial}). Raw content stored as TEXT.

knowledge.field_log_pools
  Pool URLs and usernames extracted from pools.log (WhatsMiner) or
  cgminer.conf (Antminer).

knowledge.field_log_api_stats
  Per-STATS-section rows from api.log. Elapsed, chip count, freq avg,
  temperature, work count, nonce counts.

knowledge.field_log_antminer_boots
  One row per boot session (cglog_init_* folder). Boot timestamp and
  list of files present.

knowledge.field_log_antminer_autotune
  Autotune events from miner.log: freq_set, temp_max, voltage, init_done,
  autotune_profile. Indexed by boot session and event number.
  v3: streaming generator prevents runaway on large archives (60s timeout guard).

knowledge.field_log_events
  ERROR/WARN severity events from miner.log and other log files.
```

### Table Relationships Diagram

```
field_log_imports (entity_label = filename)
├── field_log_miner_identity    (archive_filename FK, per slot)
├── field_log_power_samples     (archive_filename FK, per sample line)
├── field_log_temp_snapshots    (archive_filename FK, per snapshot file)
├── field_log_pools             (archive_filename FK, per pool)
├── field_log_api_stats         (archive_filename FK, per STATS section)
├── field_log_antminer_boots    (archive_filename FK, per boot session)
│   └── field_log_antminer_autotune  (boot_session FK, per event)
└── field_log_events            (archive_filename FK, per WARNING/ERROR)
```

All tables use `ON CONFLICT DO NOTHING` on their UNIQUE constraints — re-importing the same archive is idempotent.

---

## v3.1: Layer 2 Two-Tier Resolver

The resolver logic lives in `resolver.py` (independently importable, fully unit-tested). `mg_import.py` calls it during `_do_layer2_postprocessing` after each archive import.

### Resolution Pipeline (Steps A–E)

For each archive, both `miner_type` and `control_board_version` columns are checked (brief: “always check BOTH columns for alias matching”).

**Step A — Normalize**

```
normalize('  m31s+_v100  ') -> 'M31S+_V100'
```

Rules:
- Strip surrounding whitespace; collapse internal whitespace to a single space
- Uppercase
- Preserve trailing `+` and `++` (S5 vs S5+, M30S+ vs M30S++ are different products)
- Do NOT strip V-codes at this stage (Step B tries the full string first)

**Step B — Tier-1 exact lookup**

Queries `hardware.model_aliases WHERE alias_normalized = <normalised_string>`. UNIQUE constraint guarantees 0 or 1 hit. On hit: returns `model_id` (UUID), `tier='tier1'`.

**Step C — Tier-1 with V-code stripped**

If Step B misses and the string ends with a recognised V-code (`V10`…`V100`, `VE30`, `VE50`, `VE80`, `VK10`, `VK30`), the V-code is stripped and the base string is re-tried in Tier-1. On hit: returns `model_id`, `tier='tier1_vcode_stripped'`, `hardware_revision=<vcode>`.

**Step D — Tier-2 family lookup**

Queries `mg.model_family_aliases WHERE alias_normalized = <normalised_string>`. Each row has `candidate_model_ids UUID[]` and `candidate_hashrates NUMERIC[]` (rated TH/s).

- The `hashrate_gh` TEXT field (GH/s) from the field_log row is parsed and converted to TH/s (÷ 1000).
- The candidate with the smallest absolute difference from observed TH/s is selected.
- **Ties go to the lower-rated bin.**
- If `hashrate_gh` is null / empty / non-numeric: inserts to `mg.unresolved_models` with `reason='tier2_hit_no_hashrate'`, returns `tier='unresolved'`.

**Step E — Fallback**

No Tier-1 or Tier-2 hit: inserts to `mg.unresolved_models` with `reason='no_alias_match'`. Returns `tier='unresolved'`.

### Resolver Return Contract

```python
ResolverResult(
    model_id          = 'uuid-str' | None,
    tier              = 'tier1' | 'tier1_vcode_stripped' | 'tier2' | 'unresolved',
    hardware_revision = 'V100'  | None,
    reason            = 'no_alias_match' | 'tier2_hit_no_hashrate' | None,
)
```

### Recognised V-codes

`V10 V20 V30 V40 V50 V60 V70 V80 V90 V100 VE30 VE50 VE80 VK10 VK30`

V-codes are valid only for manufacturers `microbt` and `bitmain`. The resolver attempts the V-code strip and lets the DB decide whether the stripped alias hits.

### Raw JSON Capture (v3.1 schema)

Every JSON log file's raw content is written to `knowledge.field_log_raw_json`:

```sql
CREATE TABLE IF NOT EXISTS knowledge.field_log_raw_json (
    id                   BIGSERIAL PRIMARY KEY,
    archive_filename     TEXT NOT NULL,
    file_path_in_archive TEXT NOT NULL DEFAULT '',
    raw_content          JSONB NOT NULL,
    ingested_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (archive_filename, file_path_in_archive)
);
```

This table is created by the idempotent bootstrap DDL in `FIELD_LOG_DDL` (runs on every `process_archive` call). Re-importing the same archive is idempotent via `ON CONFLICT DO NOTHING`.

### Import Run Logging (v3.1)

After each import session a summary row is written to `mg.import_runs`:

```sql
CREATE TABLE IF NOT EXISTS mg.import_runs (
    id            BIGSERIAL PRIMARY KEY,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at   TIMESTAMPTZ,
    archive_count INTEGER,
    row_counts    JSONB,
    errors        TEXT[],
    status        TEXT
);
```

---

## v3: Layer 2 Field Intelligence Pipeline

Layer 2 runs automatically after each successful archive import when a PostgreSQL connection is available. It enriches the raw import with catalog-level intelligence.

### Alias Resolution & V-Code Stripping

WhatsMiner miner types frequently include hardware revision suffixes (e.g. `M31S+_V100`, `M56S++_VK10`). Layer 2:

1. Strips the `_Vxxx` suffix using `V_SUFFIX_RE` (handles V10–V100, VE30–VE50, VK10, etc.)
2. Looks up both the full string and the stripped base in `mg.model_aliases`
3. Stamps the matched `catalog_slug` back to `knowledge.field_log_imports.catalog_slug`
4. If no match is found, writes a row to `mg.unresolved_models` for human review

**Supported match types** (from seed):

| match_type | Description |
|------------|-------------|
| `exact` | Raw miner_type exactly matches alias_string |
| `exact_hw_revision` | Exact match with hardware revision suffix |
| `normalized` | Case/punctuation-normalized match |
| `normalized_hw_revision` | Normalized with hardware revision |
| `exact_observed` | Observed field value match (from real archives) |
| `normalized_observed` | Normalized observed value match |

### Raw JSON Capture

Every archive's parsed data is stored as a JSONB blob in `knowledge.field_log_raw_json` with:
- `archive_filename` + `file_path_in_archive` — unique key, idempotent on re-import
- `raw_content JSONB` — full parsed data for future replay/re-parsing

### Unknown Field Surveillance

Any field key found in a log file that is not in the known-keys registry (`KNOWN_KEYS_BY_FILE`) is recorded in `mg.unknown_fields` with:
- Field name, observed values, occurrence count, source file pattern
- Automatically promoted to `mg.field_promotion_queue` when seen ≥3 times

This enables discovery of new firmware-introduced fields without code changes.

---

## v3: New mg.* Tables (Migration 002)

Applied via `sql/migrations/002_layer2_and_learning_foundation.sql`.

```
mg.model_aliases         — miner_type string → catalog_slug lookup table (5,724 rows)
mg.unresolved_models     — miner_type strings with no alias match (for human review)
mg.unknown_fields        — field keys not in the known-keys registry
mg.field_promotion_queue — unknown fields promoted for schema addition
mg.miners                — deduplicated miner identity (MAC + serial)
mg.miner_archives        — archive ↔ miner join table
mg.catalog_field_stats   — per-catalog-slug field coverage metrics
mg.enrichment_proposals  — AI-generated enrichment suggestions
mg.rma_records           — RMA submissions linked to miners
mg.dormant_miners        — miners with no imports for ≥30 days
mg.pools                 — pool URL + username registry

knowledge.field_log_raw_json  — raw JSON blobs per source file per archive
```

All new tables are created with `IF NOT EXISTS` — the migration is fully idempotent.

---

## v3: New Flask Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/rma` | GET | RMA submission form (HTML) |
| `/rma` | POST | Create RMA record (JSON `{miner_ip, issue, submitted_by}`) |
| `/rma/csv` | GET | Download all RMA records as CSV |
| `/rma/csv` | POST | Bulk import RMA records from uploaded CSV |
| `/dormant` | GET | List miners with no imports ≥30 days (JSON) |
| `/dormant/resolve` | POST | Mark a dormant miner as resolved (JSON `{miner_id}`) |

The dormant miner check runs automatically at the end of each `/api/import-files` call.

---

## v3: Structured Logging

Every run writes a timestamped log file to the `logs/` directory:

```
logs/import_2024-07-01_193812.log
```

Log format:
```
2024-07-01 19:38:12,456 [INFO] mg_archive: BEGIN archive: M31S-_V100_2024-07-01_19-38-2.tgz (124.3 KB, sha256=a3f8d12e...)
2024-07-01 19:38:12,891 [INFO] mg_archive: END archive: M31S-_V100_2024-07-01_19-38-2.tgz (0.4s, 6 blocks, 0 errors)
```

Enable verbose debug logging:
```bash
MG_DEBUG=1 python mg_import.py
```

---

## v3: Model Alias Seed

The seed file `sql/seed/001_model_aliases_seed.sql` contains **5,724 rows** covering **243 WhatsMiner models**. It is generated by `generate_alias_seed.py` at the workspace root and includes full V-code expansion for all known hardware revisions (V10–V100, VE30, VE50, VK10).

To regenerate the seed (e.g. after adding new models):

```bash
python /home/user/workspace/generate_alias_seed.py > sql/seed/001_model_aliases_seed.sql
```

---

## v3: Antminer Streaming Fix

The v2 importer used a naive line-accumulation approach for `miner.log` that caused runaway memory use on Antminer S19 archives with autotune logging enabled. v3 replaces this with a streaming generator (`_stream_antminer_miner_log`) that:

- Yields parsed event dicts one at a time (never accumulates >50k rows in memory)
- Has a hard 60-second timeout per file
- Batches SQL INSERTs at 1,000 rows per statement (avoids single-statement overflows)

---

## API Key Redaction

`ams_bixbit.json` files contain AMS BixBit device registration credentials.
When present, the `api_key` field is replaced with `REDACTED_` + first 8 hex
characters of its SHA-256 hash. The `device_id` integer is preserved unchanged.
A note is written to the `parse_warnings` column of `field_log_imports`.

---

## How CSV Import Works

Given a file like `bitcoin_miners.csv`:

```
Model Name, Manufacturer, TH/s, Watts
Antminer S21 Pro, Bitmain, 234, 3510
```

The tool generates:

```sql
BEGIN;

CREATE SCHEMA IF NOT EXISTS knowledge;

CREATE TABLE IF NOT EXISTS knowledge.research_bitcoin_miners (
    id BIGSERIAL PRIMARY KEY,
    entity_label TEXT NOT NULL UNIQUE,
    manufacturer TEXT,
    th_s TEXT,
    watts TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO knowledge.research_bitcoin_miners (entity_label, manufacturer, th_s, watts)
VALUES ($$Antminer S21 Pro$$, $$Bitmain$$, $$234$$, $$3510$$)
ON CONFLICT (entity_label) DO NOTHING;

COMMIT;
```

### Key rules:
- **Table name**: `knowledge.research_<filename>` — lowercase, underscores, leading dates/numbers and trailing version suffixes stripped
- **First CSV column** becomes `entity_label TEXT NOT NULL UNIQUE`
- **All remaining columns** become `TEXT` columns in snake_case
- **Dollar-quoting** (`$$value$$`) used for all text values — safe for apostrophes, quotes, special chars
- **`ON CONFLICT (entity_label) DO NOTHING`** — re-importing the same file is idempotent
- Wrapped in `BEGIN`/`COMMIT`

---

## Modes

### Auto-Import Mode
Drop files → SQL is generated and immediately run against PostgreSQL. The Import Log shows real-time results.

### Review First Mode
Drop files → SQL is generated and shown in the preview editor. Review/edit the SQL, then click **Run Import** to execute.

---

## ZIP File Handling

When a `.zip` is dropped:
- All `.csv`, `.sql`, `.xlsx`, `.json` files inside are extracted and processed individually
- Nested ZIPs are handled recursively
- If the ZIP contains `run_master.sql` or `run_all.sql`, it is identified as the master script in the Review panel

---

## Import Log

The bottom log panel shows:
- **Green** — successful INSERT, CREATE TABLE, COMMIT
- **Red** — errors (logged individually, import continues for remaining rows)
- **Orange** — file headers / section breaks
- **Blue** — informational messages

Summary bar at the end shows: statements run · rows affected · error count · files processed.

---

## Architecture

```
mg_import.py              ← Single Python file (~5,400 lines as of v3.1)
resolver.py               ← Layer 2 two-tier resolver (independently importable) [v3.1]
├── Flask routes
│   ├── GET  /                     → serves embedded HTML page
│   ├── POST /api/test-connection  → test PostgreSQL connectivity
│   ├── POST /api/generate-sql     → generate SQL from uploaded files (no DB write)
│   ├── POST /api/run-sql          → execute SQL string against PostgreSQL
│   ├── POST /api/import-files     → generate + immediately execute (auto-import)
│   ├── GET  /rma                  → RMA submission form          [v3]
│   ├── POST /rma                  → create RMA record            [v3]
│   ├── GET  /rma/csv              → download RMA records as CSV  [v3]
│   ├── POST /rma/csv              → bulk import RMA records      [v3]
│   ├── GET  /dormant              → list dormant miners          [v3]
│   └── POST /dormant/resolve      → resolve dormant miner        [v3]
├── Python helpers
│   ├── sanitize_identifier()      → filename → snake_case table name
│   ├── header_to_column()         → CSV header → snake_case column name
│   ├── dollar_quote()             → wrap value in $$ quoting
│   ├── read_csv_bytes()           → multi-encoding CSV reader
│   ├── read_xlsx_bytes()          → XLSX → headers + rows
│   ├── generate_csv_sql()         → full Bobby-rules SQL generation
│   ├── execute_sql_block()        → run SQL against PostgreSQL with per-stmt error handling
│   ├── split_sql_statements()     → dollar-quote-aware SQL splitter
│   └── process_zip()              → extract + classify ZIP contents
├── Archive support
│   ├── process_archive()          → main entry point: .tar/.tgz/.tar.gz/.rar
│   ├── detect_archive_shape()     → 'whatsminer' | 'antminer' | 'unknown'
│   ├── parse_whatsminer_bundle()  → WhatsMiner log bundle parser
│   ├── parse_antminer_bundle()    → Antminer log bundle parser
│   ├── _parse_miner_overview()    → INI-style miner_overview.log
│   ├── _parse_power_log()         → power.log / power_error.log telemetry
│   ├── _parse_api_log()           → api.log STATS sections (PHP + colon format)
│   ├── _parse_pools_log()         → pools.log change log
│   ├── _stream_antminer_miner_log() → streaming generator (60s timeout) [v3]
│   ├── _parse_antminer_miner_log()  → wrapper with 50k row cap        [v3]
│   ├── _build_antminer_autotune_sql_batched() → 500-row batch SQL [v3.1: 500 default]
│   ├── _parse_cgminer_conf()      → cgminer.conf JSON pools
│   ├── _build_*_sql()             → SQL builders for each table
│   └── FIELD_LOG_DDL              → DDL for 8 knowledge.field_log_* tables
├── v3.1 Layer 2 helpers (new two-tier resolver path)
│   ├── _do_layer2_postprocessing()     → orchestrates all Layer 2 steps
│   ├── stamp_import_with_model_id()    → UPDATE with model_id + tier + hw_revision [v3.1]
│   ├── write_import_run()              → writes run summary to mg.import_runs [v3.1]
│   ├── insert_raw_json()               → writes to knowledge.field_log_raw_json [v3.1 schema]
│   ├── _legacy_resolve()               → fallback to old lookup_alias path
│   ├── RESOLVER_AVAILABLE              → True when resolver.py is importable
│   └── detect_dormant_miners()         → queries mg.miners, writes mg.dormant_miners
├── v3 Layer 2 helpers (legacy, preserved for compatibility)
│   ├── strip_v_suffix()           → 'M31S+_V100' → ('M31S+', 'V100')
│   ├── lookup_alias()             → DB lookup: alias_string → catalog_slug
│   ├── resolve_model()            → tries exact then stripped lookup
│   ├── record_unresolved_model()  → writes to mg.unresolved_models
│   ├── stamp_import_with_catalog() → UPDATE field_log_imports.catalog_slug
│   ├── _guess_value_type()        → infer INTEGER/FLOAT/TIMESTAMP/TEXT
│   └── record_unknown_fields()    → writes to mg.unknown_fields
├── v3 constants
│   ├── KNOWN_MINER_OVERVIEW_KEYS  → known keys for miner_overview.log
│   ├── KNOWN_MINER_LOG_KEYS       → known keys for miner.log
│   ├── KNOWN_CGMINER_CONF_KEYS    → known keys for cgminer.conf
│   ├── KNOWN_KEYS_BY_FILE         → registry mapping filename → frozenset
│   └── V_SUFFIX_RE                → regex for _Vxxx suffix extraction
└── HTML_PAGE string
    ├── CSS (dark theme, #F7931A accent)
    ├── HTML layout (header, panels, drop zone, log, v3 nav links)
    └── JavaScript (drag-drop, API calls, log rendering, tab switching)
```

No external CDN dependencies. Runs fully offline/air-gapped after `pip install`.

---

## File Layout

```
mg_import_tool/
├── mg_import.py                      ← Main application (~5,400 lines, v3.1)
├── resolver.py                       ← Layer 2 two-tier resolver module [v3.1]
├── README.md                         ← This file
├── logs/                             ← Per-run structured log files (v3)
├── sql/
│   ├── migrations/
│   │   ├── 000_bootstrap_field_log_tables.sql  ← knowledge.field_log_* + mg.import_runs (v2 shape) [v3.3]
│   │   └── 002_layer2_and_learning_foundation.sql  ← Layer 2 resolver tables [v3]
│   └── seed/
│       ├── 001_hardware_model_aliases_tier1.sql  ← 12,852-row Tier-1 alias table [v3.1]
│       └── 002_mg_family_aliases_tier2.sql       ← 1,494-row Tier-2 family table [v3.1]
├── tests/
│   ├── test_alias_matching.py        ← V-suffix regex unit tests (20 cases) [v3]
│   ├── test_streaming_autotune.py    ← Streaming parser + batch SQL tests [v3]
│   ├── test_layer2_unmatched.py      ← Layer 2 offline/mocked DB tests [v3]
│   ├── test_unknown_field.py         ← Unknown field surveillance tests [v3]
│   ├── test_integration_samples.py  ← 6-archive integration tests (43 cases) [v3]
│   └── test_resolver.py             ← Two-tier resolver tests (66 cases) [v3.1]
└── tools/
    └── test_archive_parsers.py       ← Legacy offline archive parser runner
```

---

## Testing

### Run all tests (recommended)

```bash
cd mg_import_tool
python -m pytest tests/ -v
```

Expected: **178 tests pass** in ~15 seconds. No PostgreSQL required.

- 112 original tests (v3: alias matching, streaming autotune, layer2 unmatched, unknown fields, integration)
- 66 new tests (v3.1: resolver normalizer, strip_vcode, Tier-1/Tier-2 mocks, hashrate parsing, bin selection, batch_size=500, 15k streaming, raw JSON capture)

### Run integration tests only

```bash
python -m pytest tests/test_integration_samples.py -v
```

Runs all 6 sample archives through the full `process_archive()` pipeline. Asserts:
- No error blocks produced
- Expected tables have ≥ N INSERT rows
- Total wall-clock time < 180 seconds
- Antminer S19 84-file archive completes in < 60 seconds (streaming fix verified)
- V-suffix model `M31S+_V100` correctly parsed

### Run the legacy offline test (uses tarballs)

```bash
python tools/test_archive_parsers.py
```

---

## Error Handling

| Situation | Behavior |
|-----------|----------|
| PostgreSQL unreachable | Clear error message with connection details |
| CSV encoding issues | Tries UTF-8-sig → UTF-8 → Latin-1 → CP1252 |
| Single INSERT fails | Logs error, continues with remaining rows |
| Unsupported file type | Logs warning, skips file |
| Malformed JSON | Logs error with detail |
| openpyxl missing | Error shown when .xlsx is dropped |
| rarfile missing | Error shown when .rar is dropped |
| unrar binary missing | Clear error: install instructions for Linux/macOS/Windows |
| Truncated archive (< 100 bytes) | Clear error message, no crash |
| Malformed archive member | Warning logged, parsing continues |
| Unknown archive shape | Import record written with shape='unknown', warning in parse_warnings |
| Antminer miner.log > 60s | Streaming timeout fires, partial results written, warning logged |
| Unresolved miner_type alias | Row written to mg.unresolved_models; import continues |
| Layer 2 DB unavailable | All Layer 2 steps silently no-op; core import unaffected |

---

## Troubleshooting

**"Connection refused"**
- Ensure PostgreSQL is running: `pg_lscluster` or `systemctl status postgresql`
- Check host/port match your PostgreSQL configuration (`pg_hba.conf`, `postgresql.conf`)

**"role does not exist"**
- Create the user: `CREATE USER guardian_admin WITH PASSWORD 'MiningGuardian2026!';`
- Grant access: `GRANT ALL PRIVILEGES ON DATABASE mining_guardian TO guardian_admin;`

**"psycopg2 not installed"**
- Run: `pip install psycopg2-binary`
- On some systems: `pip3 install psycopg2-binary`

**"openpyxl not installed"**
- Run: `pip install openpyxl` (only needed for .xlsx files)

**"rarfile not installed"** or **"unrar binary missing"**
- Run: `pip install rarfile`
- Then install the unrar binary (see Quick Start above)

**"Archive appears truncated"**
- The archive file is less than 100 bytes or otherwise corrupt
- Re-download or re-export the archive from the miner

**Port already in use**
- `PORT=5051 python mg_import.py`

**Large files (>512 MB)**
- Edit `app.config['MAX_CONTENT_LENGTH']` in `mg_import.py`

**Miner model not resolved to catalog_slug**
- Check `mg.unresolved_models` for the raw miner_type string
- Add a row to `mg.model_aliases` manually, or regenerate the seed via `generate_alias_seed.py`

---

## v3.3 New Endpoints

### `/api/import-files-stream` — Streaming batch import (SSE)

Use this for all batch runs of 5+ archives. Emits real-time Server-Sent Events so you can watch progress archive-by-archive.

**Method:** `POST`  
**Content-Type:** `multipart/form-data`  
**Body:** Same as `/api/import-files` — `conn_params` JSON field + one or more archive files  
**Response:** `text/event-stream`

**Events emitted in order:**

| Event | Key fields |
|-------|------------|
| `batch_started` | `archive_count`, `filenames[]` |
| `archive_started` | `archive`, `index`, `total`, `elapsed_s` |
| `archive_skipped` | `archive`, `reason: duplicate_sha256`, `sha256` |
| `archive_parsed` | `archive`, `elapsed_s`, `rows_found` |
| `archive_persisted` | `archive`, `rows_affected`, `statements_run`, `sql_errors[]` |
| `resolver_stats_updated` | `archive`, `tier1`, `tier1_vcode`, `tier2`, `unresolved`, `total` |
| `archive_completed` | `archive`, `elapsed_s`, `rows_affected`, `error` (null on success) |
| `batch_completed` | `status`, `archives_ok`, `archives_error`, `archives_skipped`, `total_rows`, `elapsed_s`, `resolver_totals`, `coverage_pct` |

**Batch status values:** `ok` / `partial_failure` / `failed` / `cancelled`

**Watch in real time with curl:**
```bash
curl -N -X POST http://localhost:5050/api/import-files-stream \
  -F 'conn_params={"host":"localhost","port":5432,"database":"mining_guardian","user":"guardian_admin","password":"MiningGuardian2026!"}' \
  -F 'file0=@/path/to/your/archive.tar.gz'
```

**Batch recipe for 83 archives in a ZIP:**
```bash
curl -N -X POST http://localhost:5050/api/import-files-stream \
  -F 'conn_params={"host":"localhost","port":5432,"database":"mining_guardian","user":"guardian_admin","password":"MiningGuardian2026!"}' \
  -F 'file0=@/path/to/all_83_archives.zip'
```

---

### `/api/resolver-summary` — Per-archive resolver tier breakdown

Returns resolver tier statistics from the most recent import session. Call this after the batch completes.

**Method:** `GET`  
**Response:**
```json
{
  "success": true,
  "per_archive": {
    "archive1.tar": {"tier1": 14, "tier1_vcode": 0, "tier2": 0, "unresolved": 0, "total": 14},
    "archive2.tar": {"tier1": 10, "tier1_vcode": 2, "tier2": 1, "unresolved": 1, "total": 14}
  },
  "totals": {"tier1": 24, "tier1_vcode": 2, "tier2": 1, "unresolved": 1, "total": 28},
  "coverage_pct": 96.43
}
```

Note: data is in-memory and resets on server restart. For persistent stats, query `mg.import_runs.row_counts`.

```bash
curl http://localhost:5050/api/resolver-summary
```

---

### `/api/unresolved-sample` — Preview unresolved model strings

Returns recent rows from `mg.unresolved_models` without SSH or psql.

**Method:** `GET`  
**Query params:**
- `limit` — number of rows (default 50, max 500)
- `host`, `port`, `database`, `user`, `password` — DB connection (defaults to standard config)

```bash
curl "http://localhost:5050/api/unresolved-sample?limit=50"
```

**Response:**
```json
{
  "success": true,
  "count": 3,
  "rows": [
    {"raw_string": "M30S+_VK30", "archive_filename": "miner_type", "reason": "no_alias_match",
     "count": "2", "first_seen": "2026-04-22 21:40:00+00"}
  ]
}
```

---

### `/api/cancel-batch` — Stop an in-flight batch

Sets a module-level cancel flag checked between archives.

**Method:** `POST`

```bash
curl -X POST http://localhost:5050/api/cancel-batch
```

> **Important:** Closing the browser does NOT cancel an in-flight batch. The Flask thread continues running. To cancel: `curl -X POST http://localhost:5050/api/cancel-batch` or stop the server process. The batch will stop after the archive currently in progress finishes and records a `status='cancelled'` event.

---

## How to Read `mg.import_runs`

```sql
SELECT started_at, archive_count, status,
       row_counts->'total_rows'    AS total_rows,
       row_counts->'errors'        AS error_count,
       row_counts->'resolver'      AS resolver_summary,
       errors
FROM mg.import_runs
ORDER BY started_at DESC
LIMIT 5;
```

**`row_counts` JSONB structure (v3.3):**
```json
{
  "total_rows": 14178,
  "errors": 0,
  "resolver": {
    "tier1": 280, "tier1_vcode": 12, "tier2": 5, "unresolved": 3, "total": 300
  }
}
```

**`errors` array:** List of `"archive_name:error_message"` strings for any archives that failed during the run. Empty on clean runs.

**`status` values:** `ok` | `partial_failure` | `failed` | `cancelled`

---

## Troubleshooting

### Import hangs with no UI feedback

The legacy `/api/import-files` endpoint is synchronous — it returns only when all archives are processed. For 10+ archives this can take many minutes.

**Fix:** Switch to the streaming endpoint `/api/import-files-stream`. Watch progress with:
```bash
curl -N -X POST http://localhost:5050/api/import-files-stream \
  -F 'conn_params={...}' -F 'file0=@batch.zip'
```

### One bad archive killed my batch

This was the v3.2 behaviour. In v3.3 every archive is isolated in its own try/except block. A corrupted archive logs an error and is recorded in `mg.import_runs.errors`, but processing continues for all remaining archives.

### Duplicate archive included in batch

v3.3 checks sha256 before processing each archive. If the identical bytes were previously imported, the archive is skipped with an `archive_skipped` SSE event and a `SKIP duplicate` log line. No DB write is attempted.

---

## Bobby's Rules

- **Capture Everything. Discard Nothing.** — 10-year design horizon
- **Bitcoin SHA-256 miners ONLY**
- **Every variant, every data point preserved**
- **Dollar-quoting for safe text handling**
- **Layer 2: every unknown field is a future feature** — nothing is silently dropped

---

## License

Internal tool — Mining Guardian Intelligence Platform.
