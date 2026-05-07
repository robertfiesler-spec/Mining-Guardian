# Mining Intelligence Catalog — Database Design Prompt for Perplexity

## Context for the AI

I'm building the **Mining Intelligence Catalog**, a PostgreSQL reference database for my Bitcoin mining monitoring system called Mining Guardian. This database will be a **read-only reference** that Mining Guardian queries when it needs specifications, thresholds, repair patterns, or operational intelligence about miners it monitors.

Mining Guardian originally ran on a VPS with SQLite for operational data (scan readings, restart history, predictions) — **historical context: VPS decommissioned for MG as of Mac Mini install 2026-04-30; operational DB is now PostgreSQL on the Mac Mini.** The intelligence catalog PostgreSQL database ran on ROBS-PC (Windows PC) and is also migrating to the Mac Mini as part of cutover scope γ.

---

## What This Database Needs to Store

### 1. Miner Model Specifications (the core reference)

Every Bitcoin ASIC miner model has specs that never change. Mining Guardian needs to look these up to know what "normal" means for each model.

**Key fields per model:**
- Manufacturer (Bitmain, MicroBT, Auradine, Canaan, etc.)
- Model name and variants (S19J Pro, S19J Pro+, S19 XP, etc.)
- Cooling type (air, hydro, immersion)
- Board count (usually 3, sometimes 2 or 4)
- Chip architecture (e.g., "BM1362" for Bitmain S21)
- Stock hashrate (TH/s) — what Bitmain says it does
- Max hashrate (TH/s) — with overclocking/custom firmware
- Min hashrate (TH/s) — efficiency mode
- Power consumption at stock (Watts)
- Efficiency (J/TH) at stock
- Operating temp range (chip temp yellow/red thresholds)
- Release date
- Firmware compatibility notes

**Example data I already have in config.json:**
```json
{
  "S19JPro": {
    "display_name": "Antminer S19J Pro",
    "firmware": "BiXBiT",
    "boards": 3,
    "stock_ths": 104,
    "min_ths": 104,
    "max_ths": 160,
    "note": "BiXBiT firmware allows profiles from 104-160 TH/s"
  },
  "AH3880": {
    "display_name": "Teraflux AH3880",
    "firmware": "Auradine",
    "boards": 2,
    "stock_ths": 300,
    "max_ths": 600
  },
  "S21EXPHyd": {
    "display_name": "Antminer S21e XP Hydro",
    "firmware": "BiXBiT",
    "boards": 3,
    "stock_ths": 430,
    "max_ths": 506
  }
}
```

### 2. Chip/Board Intelligence

Mining Guardian collects PCB versions, BOM versions, chip bins, and serial number patterns from miners. I need a reference to know which combinations are good vs. problematic.

**Example insight my AI system has already learned:**
> "PCB=0110/BOM=0020 boards averaging 13.6% hashrate while PCB=0130/BOM=0010 hit 73.5%. Reject all 0110/0020 combinations."

The database should store:
- PCB version codes and what they mean
- BOM version codes and what they mean  
- Chip bin codes (bin 1, 2, 3, etc.) and their quality implications
- Known bad combinations to flag
- Serial number patterns (what prefix = what manufacturing batch)

### 3. Firmware Reference

Different firmware unlocks different capabilities:
- Stock Bitmain/MicroBT firmware: limited API, no overclocking
- BiXBiT firmware: full API access, profile control, extensive telemetry
- Auradine firmware: different API entirely (port 8443)
- VNish, Braiins, etc.: other custom firmware

For each firmware:
- API endpoints and authentication methods
- Available commands (restart, profile change, etc.)
- Telemetry available (chip-level temps, voltages, etc.)
- Known issues or quirks

### 4. Failure Patterns & Repair Knowledge

This is the real intelligence. When something fails, what does it mean?

**Example patterns to store:**
- "Hashboard showing 0 TH/s but chips responding = dead power stage, PSU ticket"
- "Chain detach cycling every few minutes = EEPROM corruption, needs reflash"
- "Voltage drop below 11.5V on one board = PSU cable issue or dead PSU rail"
- "All boards offline simultaneously = control board issue, not hashboards"

Each pattern should have:
- Symptom signature (what the telemetry shows)
- Root cause
- Recommended action (restart? profile change? ticket?)
- Confidence level
- Which models this applies to
- Source (learned from data, repair shop, manufacturer)

### 5. Threshold Profiles by Cooling Type

Different cooling = different thresholds:

| Cooling | Chip Temp Yellow | Chip Temp Red | Board Temp Yellow |
|---------|-----------------|---------------|-------------------|
| Air     | 85°C            | 95°C          | 75°C              |
| Hydro   | 76°C            | 86°C          | 65°C              |
| Immersion | 80°C          | 90°C          | 70°C              |

### 6. Pool Configuration Reference

For each pool:
- URL patterns
- Default port
- Authentication method
- Known status codes and what they mean

---

## How Mining Guardian Will Query This

The queries will be simple lookups:

```sql
-- Get specs for a model
SELECT * FROM miner_models WHERE model_name = 'S19JPro';

-- Get chip thresholds for a cooling type
SELECT * FROM threshold_profiles WHERE cooling_type = 'hydro';

-- Find failure patterns matching symptoms
SELECT * FROM failure_patterns 
WHERE symptom_tags @> ARRAY['hashrate_zero', 'chips_responding']
  AND (model_filter IS NULL OR model_filter = 'S19JPro');

-- Get firmware API info
SELECT * FROM firmware_reference WHERE firmware_name = 'BiXBiT';

-- Check if a PCB/BOM combo is known bad
SELECT * FROM board_quality_intel 
WHERE pcb_version = '0110' AND bom_version = '0020';
```

---

## Technical Requirements

1. **PostgreSQL 16** on the Mac Mini (`mining_guardian_catalog` DB inside the
   `mining-guardian-db` Docker container, bound to `127.0.0.1:5432` per D-9 /
   S-13). Pre-cutover the catalog Postgres ran on Windows ROBS-PC over
   Tailscale at `100.110.87.1` — that host is decommissioned for MG.
2. **Read-only for Mining Guardian** — it only queries, never writes
3. **Separate admin connection** for me to load/update data
4. **JSONB columns** where flexible schema is useful (like firmware API details)
5. **Array columns** for tags/symptoms that need `@>` containment queries
6. **Full-text search** on description/notes fields for natural language lookup

---

## Schema Design Questions I Need Answered

1. How should I model the miner_models table with all the variants (S19J Pro vs S19J Pro+ vs S19 XP)?
2. Should firmware_reference be a separate table or embedded in miner_models?
3. How do I structure failure_patterns for efficient symptom matching?
4. What indexes do I need for the query patterns above?
5. How should I handle "this applies to all models" vs "only specific models"?
6. Should chip/board intelligence be normalized into multiple tables or denormalized?

---

## Data Sources I'll Be Loading

1. **Bitmain spec sheets** (PDFs with model specs)
2. **My config.json** (current model profiles)
3. **My knowledge.json** (refined_insights, patterns, known_issues)
4. **Repair shop data** (1M+ data points, TBD format)
5. **Manual entry** (what I've learned operating the mine)

---

## Constraints

- This is NOT an OLTP database — it's a reference catalog
- Queries will be simple key lookups, not complex joins
- Data changes slowly (new models added quarterly, patterns added weekly)
- Must be query-able from Mining Guardian's Python code via `psycopg2`
- No ORM — raw SQL queries for clarity

---

## What I Need From You

1. **Complete PostgreSQL schema** with CREATE TABLE statements
2. **Recommended indexes** for my query patterns
3. **Example INSERT statements** showing how to load data
4. **Python query examples** showing how Mining Guardian would fetch data
5. **Any PostgreSQL-specific features** I should use (JSONB operators, array functions, etc.)

Design this as a production-ready schema that can grow as I add more miner models and learn more failure patterns.
