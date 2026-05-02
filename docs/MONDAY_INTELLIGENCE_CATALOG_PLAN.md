# Mining Intelligence Catalog — Monday Build Plan

> **⚠️ DEPRECATED ARCHITECTURE — historical reference only.**
> This document describes the original April 2026 plan to host the catalog on **ROBS-PC** with a Thunderbolt 4 SSD enclosure. That architecture was superseded on 2026-04-27 by the **Mac Mini** plan. The canonical schema and seed now live in `intelligence-catalog/seed-data/` (not `intelligence/`). The legacy `intelligence/` directory is deprecated — see `intelligence/DEPRECATED.md`. For the current architecture see `intelligence-catalog/seed-data/README.md` and `docs/CATALOG_ORPHAN_TABLES_2026-04-28.md`. The instructions below are kept for historical traceability and should not be followed for the **2026-04-30** customer install (install date was previously referenced as May 5 in this doc; the locked date is now 2026-04-30).
>
> **Status as of 2026-04-29 PM:** VPS connectivity references in this doc (Phase 6, "Test VPS Connectivity") are historical context only — the VPS (srv1549463 / 187.124.247.182) is decommissioned for Mining Guardian. The ROBS-PC references describe the original plan that was superseded by Mac Mini. The catalog Postgres now lives on the Mac Mini at port 5432, user `guardian_app`, db `mining_guardian`. Do not follow the Phase 6 VPS connectivity test for the 2026-04-30 install. See `CATALOG_ORPHAN_TABLES_2026-04-28.md` for current catalog status.

**Date:** April 10, 2026 (created for Monday April 13 session)
**Status:** READY TO BUILD
**Hardware:** ROBS-PC (Windows 11, Ryzen 7 7800X3D, 32GB RAM, RTX 4090)
**Target:** PostgreSQL 16 research database for miner specs, repair data, and fleet intelligence

---

## Executive Summary

The Mining Intelligence Catalog is a **separate research database** on ROBS-PC that will hold:
- Miner spec sheets (TH/s, watts, boards, chips, PSU specs)
- Repair shop historical data (1M+ records from James Scaggs/ACS when available)
- Community knowledge (forum posts, teardowns, war stories)
- Log archives and parsed metrics
- Cross-miner pattern library

**This is NOT production infrastructure.** It's a research environment that Mining Guardian can query read-only for spec lookups. If ROBS-PC is offline, Guardian keeps running on its existing knowledge.

---

## Current Blockers (from AI_ROADMAP.md)

1. **WSL2/Docker virtualization conflict** — Memory Integrity may need disabling
2. **30-minute hard cap** on WSL2 debugging — if it doesn't work, fall back to native Postgres

---

## Monday Plan of Attack

### Phase 1: Environment Check (15 min)

```powershell
# On ROBS-PC, run these checks:

# 1. Verify Docker Desktop is installed and running
docker --version
docker run hello-world

# 2. Check if WSL2 works
wsl --status
wsl --list --verbose

# 3. Check Memory Integrity status (if Docker fails)
# Settings > Privacy & Security > Windows Security > Device Security > Core Isolation
```

**Decision Point:** If Docker/WSL2 fails after 30 minutes of debugging, STOP and install native Postgres via EnterpriseDB installer instead.

### Phase 2: Directory Setup (5 min)

```powershell
# Create the directory structure on ROBS-PC
# NOTE: Using internal SATA SSD, NOT Thunderbolt enclosure (enclosure not arrived)
# Can use C: drive temporarily, migrate to D: when enclosure arrives

mkdir C:\miner-intelligence
mkdir C:\miner-intelligence\postgres-data
mkdir C:\miner-intelligence\backups
mkdir C:\miner-intelligence\logs
```

**UPDATE docker-compose.yml** to use `C:\miner-intelligence\` instead of `D:\` for now.

### Phase 3: Docker Postgres Startup (10 min)

```powershell
# 1. Copy intelligence/ folder from repo to ROBS-PC
# Either via git clone or manual copy

# 2. Create .env file from template
copy .env.example .env
# Edit .env and set a strong random password (32+ chars)

# 3. Start the container
cd C:\miner-intelligence
docker compose up -d

# 4. Verify it's running
docker compose ps
docker compose logs miner-intel-db

# 5. Test connection
docker exec -it miner-intel-db psql -U miner_intel -d miner_intelligence -c "SELECT 1;"
```

### Phase 4: Create Initial Schema (20 min)

Create `intelligence/schema/001_initial.sql`:

```sql
-- Mining Intelligence Catalog — Initial Schema
-- PostgreSQL 16

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- Fuzzy text search
CREATE EXTENSION IF NOT EXISTS btree_gin; -- Faster JSON indexing

-- ============================================================================
-- MODEL SPECS — vendor-published specifications
-- ============================================================================
CREATE TABLE model_specs (
    id SERIAL PRIMARY KEY,
    vendor TEXT NOT NULL,           -- 'Bitmain', 'MicroBT', 'Auradine', etc.
    model TEXT NOT NULL,            -- 'S19J Pro', 'M50S', 'AH3880'
    model_code TEXT,                -- AMS model code if different
    
    -- Performance specs
    hashrate_th_stock DECIMAL(10,2),
    hashrate_th_max DECIMAL(10,2),
    power_watts_stock INTEGER,
    power_watts_max INTEGER,
    efficiency_jth DECIMAL(6,2),
    
    -- Hardware specs  
    board_count INTEGER NOT NULL,   -- CRITICAL: S19JPro=3, AH3880=2
    chip_type TEXT,                 -- 'BM1397', 'AT6600', etc.
    chip_count_per_board INTEGER,
    psu_type TEXT,                  -- 'APW12', 'APW9+', etc.
    cooling_type TEXT,              -- 'air', 'hydro', 'immersion'
    
    -- Voltage/frequency ranges
    voltage_min DECIMAL(4,2),
    voltage_max DECIMAL(4,2),
    frequency_min INTEGER,
    frequency_max INTEGER,
    
    -- Operating limits
    temp_chip_max INTEGER DEFAULT 95,
    temp_board_max INTEGER DEFAULT 85,
    
    -- Metadata
    source_url TEXT,
    source_date DATE,
    confidence TEXT DEFAULT 'MEDIUM', -- 'HIGH', 'MEDIUM', 'LOW'
    notes TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(vendor, model, cooling_type)
);

-- ============================================================================
-- KNOWN PATTERNS — cross-miner failure patterns
-- ============================================================================
CREATE TABLE known_patterns (
    id SERIAL PRIMARY KEY,
    pattern_key TEXT UNIQUE NOT NULL,  -- 'chain3_detachment_s19jpro'
    
    category TEXT NOT NULL,            -- 'PSU', 'Board', 'Firmware', 'Thermal'
    severity TEXT DEFAULT 'MEDIUM',    -- 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
    
    -- Pattern definition
    symptoms JSONB NOT NULL,           -- Array of symptom signatures
    root_cause TEXT,
    recommended_action TEXT,
    
    -- Scope
    affected_vendors TEXT[],
    affected_models TEXT[],
    affected_firmware TEXT[],
    affected_pcb_versions TEXT[],
    
    -- Statistics
    occurrences INTEGER DEFAULT 0,
    success_rate DECIMAL(5,2),         -- When recommended_action is followed
    
    -- Source
    first_seen DATE,
    last_seen DATE,
    source TEXT,                       -- 'mining_guardian', 'repair_shop', 'community'
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- ERROR CODE LIBRARY — vendor error code definitions
-- ============================================================================
CREATE TABLE error_codes (
    id SERIAL PRIMARY KEY,
    vendor TEXT NOT NULL,
    error_code TEXT NOT NULL,
    
    -- Classification
    category TEXT,                     -- 'PSU', 'Hashboard', 'Network', 'Thermal'
    severity TEXT DEFAULT 'MEDIUM',
    
    -- Description
    description TEXT NOT NULL,
    possible_causes TEXT[],
    recommended_actions TEXT[],
    
    -- Source
    source_url TEXT,
    source_date DATE,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(vendor, error_code)
);

-- ============================================================================
-- COMMUNITY KNOWLEDGE — forum posts, teardowns, war stories
-- ============================================================================
CREATE TABLE community_knowledge (
    id SERIAL PRIMARY KEY,
    
    -- Source
    source_type TEXT NOT NULL,         -- 'reddit', 'bitcointalk', 'blog', 'youtube'
    source_url TEXT UNIQUE NOT NULL,
    source_date DATE,
    author TEXT,
    
    -- Content
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    
    -- Tagging
    vendors TEXT[],
    models TEXT[],
    topics TEXT[],                     -- 'teardown', 'repair', 'firmware', 'cooling'
    
    -- Quality
    upvotes INTEGER DEFAULT 0,
    relevance_score DECIMAL(3,2),      -- 0.00 to 1.00, set by LLM analysis
    
    -- Full-text search
    search_vector TSVECTOR,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Full-text search index
CREATE INDEX idx_community_search ON community_knowledge USING GIN(search_vector);

-- ============================================================================
-- INGESTION LOG — provenance tracking
-- ============================================================================
CREATE TABLE ingestion_log (
    id SERIAL PRIMARY KEY,
    
    source_type TEXT NOT NULL,         -- 'spec_sheet', 'repair_dump', 'community', 'guardian'
    source_path TEXT,
    source_url TEXT,
    
    records_total INTEGER,
    records_success INTEGER,
    records_failed INTEGER,
    
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'running',     -- 'running', 'success', 'partial', 'failed'
    error_message TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- INDEXES for common queries
-- ============================================================================
CREATE INDEX idx_model_specs_vendor_model ON model_specs(vendor, model);
CREATE INDEX idx_known_patterns_category ON known_patterns(category);
CREATE INDEX idx_error_codes_vendor ON error_codes(vendor);

-- ============================================================================
-- Trigger to auto-update updated_at
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER model_specs_updated_at
    BEFORE UPDATE ON model_specs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER known_patterns_updated_at
    BEFORE UPDATE ON known_patterns
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### Phase 5: Seed Initial Data (15 min)

Create `intelligence/schema/002_seed_data.sql` with Bobby's fleet specs:

```sql
-- Seed data from Bobby's fleet

-- S19J Pro (3 boards, runs in immersion at Bobby's site)
INSERT INTO model_specs (vendor, model, board_count, hashrate_th_stock, hashrate_th_max, 
    power_watts_stock, chip_type, cooling_type, confidence, notes)
VALUES 
    ('Bitmain', 'Antminer S19J Pro', 3, 104, 160, 3068, 'BM1362', 'immersion', 'HIGH',
     'Air machine converted to immersion. Stock 104 TH/s, BiXBiT firmware allows up to 160 TH/s.'),
    ('Bitmain', 'Antminer S19J Pro', 3, 104, 104, 3068, 'BM1362', 'air', 'HIGH',
     'Stock air-cooled version. Some in fleet running stock firmware.');

-- AH3880 Auradine (2 boards only!)
INSERT INTO model_specs (vendor, model, board_count, hashrate_th_stock, hashrate_th_max,
    power_watts_stock, chip_type, cooling_type, confidence, notes)
VALUES 
    ('Auradine', 'Teraflux AH3880', 2, 300, 600, 3000, 'AT7200', 'hydro', 'HIGH',
     'ONLY 2 BOARDS. Eco mode 300 TH/s, Turbo mode 600 TH/s. Direct API on port 8443.');

-- S21 EXP Hydro (3 boards)
INSERT INTO model_specs (vendor, model, board_count, hashrate_th_stock, hashrate_th_max,
    power_watts_stock, chip_type, cooling_type, confidence, notes)
VALUES 
    ('Bitmain', 'Antminer S21 EXP Hydro', 3, 430, 506, 5200, 'BM1368', 'hydro', 'HIGH',
     'Factory hydro-cooled. BiXBiT firmware enables max 506 TH/s.');

-- S21 Immersion (3 boards)
INSERT INTO model_specs (vendor, model, board_count, hashrate_th_stock, hashrate_th_max,
    power_watts_stock, chip_type, cooling_type, confidence, notes)
VALUES 
    ('Bitmain', 'Antminer S21 Immersion', 3, 208, 360, 3500, 'BM1368', 'immersion', 'HIGH',
     'Immersion-specific variant. Two units in fleet: .22 (max 360) and .23 (max 347).');

-- Known error codes for S19J Pro
INSERT INTO error_codes (vendor, error_code, category, severity, description, possible_causes, recommended_actions)
VALUES
    ('Bitmain', '101', 'Hashboard', 'MEDIUM', 
     'Hashboard communication error',
     ARRAY['Loose ribbon cable', 'Damaged control board connector', 'Hashboard failure'],
     ARRAY['Reseat ribbon cables', 'Check control board', 'Test with known-good hashboard']),
    ('Bitmain', '412', 'Hashboard', 'HIGH',
     'Hashboard voltage regulation fault',
     ARRAY['PSU voltage instability', 'Hashboard power delivery failure', 'Bad solder joints on voltage regulators'],
     ARRAY['Check PSU voltage with multimeter', 'Inspect hashboard for burnt components', 'Thermal inspection for hot spots']);
```

### Phase 6: Test VPS Connectivity (10 min)

From the VPS, test that Mining Guardian can reach the new database:

```bash
# On VPS (187.124.247.182)
# ROBS-PC is at 192.168.188.47 via Tailscale subnet route

# Test TCP connectivity
nc -zv 192.168.188.47 5432

# Test psql connection (install if needed: apt install postgresql-client)
PGPASSWORD='your_password' psql -h 192.168.188.47 -U miner_intel -d miner_intelligence -c "SELECT COUNT(*) FROM model_specs;"
```

---

## Fallback: Native Postgres (if Docker/WSL2 fails)

If Docker doesn't work after 30 minutes of debugging:

1. **Download EnterpriseDB installer:** https://www.enterprisedb.com/downloads/postgres-postgresql-downloads
2. **Install PostgreSQL 16 for Windows**
3. **During install:**
   - Set password for postgres user
   - Keep default port 5432
   - Set data directory to `C:\miner-intelligence\postgres-data`
4. **Create database and user:**
   ```sql
   CREATE USER miner_intel WITH PASSWORD 'your_password';
   CREATE DATABASE miner_intelligence OWNER miner_intel;
   ```
5. **Edit `pg_hba.conf`** to allow connections from Tailscale subnet
6. **Apply same schema** from Phase 4

---

## Future Phases (not Monday)

### Phase 7: Connect Mining Guardian (after Monday)

Add a read-only connection from Mining Guardian to the catalog:

```python
# In ai/spec_lookup.py (new file)
import psycopg2

def get_model_spec(vendor: str, model: str) -> dict:
    """Look up miner specs from the Intelligence Catalog."""
    conn = psycopg2.connect(
        host="192.168.188.47",  # ROBS-PC via Tailscale
        database="miner_intelligence",
        user="miner_intel",
        password=os.environ.get("INTEL_DB_PASSWORD")
    )
    # ... query and return
```

### Phase 8: Repair Shop Data Ingestion (blocked on James/ACS dataset)

When the 1M+ repair records arrive:
1. Define ingestion schema for their format
2. Build worker pool for parallel parsing
3. Extract failure signatures
4. Cross-reference with model_specs and known_patterns

### Phase 9: NAS Migration (July 2026)

When the UGREEN NASync arrives:
1. `pg_dump` from ROBS-PC
2. Copy to NAS
3. `pg_restore` on NAS
4. Update Mining Guardian connection string
5. Keep ROBS-PC as hot standby for 30 days

---

## Monday Success Criteria

✅ PostgreSQL 16 running on ROBS-PC (Docker or native)
✅ `model_specs` table created with Bobby's fleet data  
✅ `error_codes` table created with known S19JPro codes
✅ `known_patterns` table created (empty, ready for data)
✅ VPS can connect to the database via Tailscale
✅ Basic backup script created and tested

---

## Files to Create/Update

| File | Action |
|------|--------|
| `intelligence/schema/001_initial.sql` | CREATE — initial schema |
| `intelligence/schema/002_seed_data.sql` | CREATE — Bobby's fleet specs |
| `intelligence/docker-compose.yml` | UPDATE — change D:\ to C:\ temporarily |
| `intelligence/.env` | CREATE from .env.example — set password |
| `intelligence/scripts/backup.ps1` | CREATE — daily backup script |

---

## Time Budget

| Phase | Time |
|-------|------|
| Environment check | 15 min |
| Directory setup | 5 min |
| Docker startup | 10 min |
| Schema creation | 20 min |
| Seed data | 15 min |
| VPS connectivity test | 10 min |
| **Total** | **~75 min** |

**Hard cap on WSL2/Docker debugging: 30 minutes.** If it's not working, switch to native Postgres.

---

*This plan created April 10, 2026 for Monday April 13 execution.*

---

## Appendix — Sweep update 2026-04-29 PM

| Item | Original plan | Actual outcome (2026-04-29) |
|---|---|---|
| Catalog host | ROBS-PC (Windows 11, Docker/Postgres) | ✅ Mac Mini (macOS, Homebrew Postgres 17, port 5432) |
| Catalog user | `miner_intel` | ✅ `guardian_app` (canonical across all MG services) |
| Catalog DB name | `miner_intelligence` | ✅ `mining_guardian` (single unified DB) |
| Schema files | `intelligence/schema/001_initial.sql` | ✅ `intelligence-catalog/seed-data/` (canonical, 320-row seed) |
| `intelligence/` directory | Active | ✅ Deprecated and deleted (2026-04-29 doc-sweep Commit 2) |
| VPS connectivity test (Phase 6) | VPS → ROBS-PC:5432 | ❌ Not applicable — VPS decommissioned for MG; catalog is local to Mac Mini |
| Install date | Monday April 13 (ROBS-PC) | ✅ 2026-04-30 (Mac Mini) |
| `intelligence/README.md` reference | Active architecture doc | ✅ Redirected to `intelligence-catalog/seed-data/README.md` |

**Net:** This entire document is historical. The ROBS-PC + VPS architecture was evaluated and not taken. The catalog lives on the Mac Mini, started from migrations 001–005 + 320-row Bitcoin SHA-256 seed. See `docs/CATALOG_ORPHAN_TABLES_2026-04-28.md` for current table status.
