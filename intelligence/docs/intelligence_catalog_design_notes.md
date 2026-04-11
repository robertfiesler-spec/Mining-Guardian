# Mining Intelligence Catalog — Design Notes
**PostgreSQL 16 Schema for Mining Guardian**
Owner: Bobby (Rob Fiesler) | Product: Mining Guardian
Database: ROBS-PC (research/intelligence), read-only from Guardian VPS

---

## 1. Schema Summary

### Stats (Updated After V3 Audit)
| Metric | Count |
|---|---|
| Total tables | **~86** (63 base + 9 V2 + 14 V3) |
| Total columns | **~1,712+** |
| Total indexes | **~320+** |
| Total triggers | **~115+** |
| Enum types | **16** |
| Schemas/namespaces | **10** |
| V3 additions file | ~1,256 lines |
| V3 gap analysis | ~337 lines |

### V3 Key Additions
- **Auto-Discovery Mechanism**: field_registry + unknown_fields + raw_ingestion_log + field_discovery_log
- **Container/Facility Reference**: hydraulics, cooling equipment, environment norms
- **Immersion Fluid Intelligence**: comprehensive fluid properties reference
- **Power/Electricity Intelligence**: rate structures, demand response, curtailment
- **Depreciation/Financial**: MACRS schedules, resale value tracking
- **Diagnostic Reference**: chip diode-mode readings, signal chain, test fixtures
- **Weather Correlation**: monthly baselines, performance impact curves
- **Miner Model Completeness**: tear sheet fields, connector types, ROI metrics

### Tables by Schema
| Schema | Tables | Category |
|---|---|---|
| `knowledge` | 5 | Category 9: Source tracking foundation |
| `hardware` | 10 | Category 1: Miner hardware |
| `firmware` | 7 | Category 2: Firmware intelligence |
| `ops` | 8 | Category 3: Operational intelligence |
| `market` | 7 | Category 4: Community/Market |
| `repair` | 9 | Category 5: Repair/Service |
| `pool` | 7 | Category 6: Pool/Network |
| `facility` | 5 | Category 7: Facility/Infrastructure |
| `regulatory` | 5 | Category 8: Regulatory/Compliance |
| `seed` | 0 | (Reserved namespace) |

### Complete Table List

**knowledge schema (foundation — loaded first)**
- `knowledge.sources` — Master source registry with tier and trust scores
- `knowledge.contributors` — Humans and bots that contribute data
- `knowledge.citations` — Universal attribution: any row in any table → source
- `knowledge.data_conflicts` — When two sources disagree on a field value
- `knowledge.freshness_log` — When any data point was last verified

**hardware schema**
- `hardware.manufacturers` — Bitmain, Auradine, MicroBT, etc.
- `hardware.chips` — BM1362, BM1368, AT7200, BM1397, etc.
- `hardware.psu_models` — PSU specs with efficiency curves
- `hardware.control_boards` — Controller boards and SoC specs
- `hardware.hashboards` — PCB specs with per-revision known defects
- `hardware.miner_models` — Core miner model table (canonical names)
- `hardware.model_aliases` — Fuzzy matching alias table
- `hardware.model_spec_history` — Versioned spec changes over product lifetime
- `hardware.psu_compatibility` — Which PSUs work with which miners
- `hardware.cooling_compatibility` — Which cooling types work with which miners

**firmware schema**
- `firmware.firmware_releases` — All firmware versions across all families
- `firmware.firmware_compatibility` — Firmware × hardware matrix
- `firmware.firmware_api_capabilities` — Every API endpoint per firmware version
- `firmware.firmware_telemetry_fields` — Every telemetry field per firmware version
- `firmware.firmware_bugs` — Known bugs per firmware version
- `firmware.firmware_changelog` — Structured change tracking per version
- `firmware.firmware_autotuning_profiles` — Profile configs per firmware per model

**ops schema**
- `ops.failure_patterns` — Root cause knowledge base
- `ops.failure_symptoms` — Observable indicators (API, visual, thermal, sound)
- `ops.symptom_pattern_map` — Probabilistic symptom → pattern mapping
- `ops.operational_thresholds` — Alert limits per model/firmware/cooling
- `ops.environmental_correlations` — Quantified env impact on performance
- `ops.operational_profiles` — Complete operating configs per mode
- `ops.alert_rules` — Parameterized alert definitions for Mining Guardian
- `ops.miner_error_codes` — Error codes from firmware API responses

**market schema**
- `market.user_reviews` — User reviews with multi-dimension ratings
- `market.pricing_history` — Price over time, new/used, BTC-denominated
- `market.manufacturer_reputation` — Scored reputation by dimension
- `market.forum_posts` — Reddit/Telegram/Discord posts with insight extraction
- `market.teardown_reports` — Hardware teardown analysis with component inventory
- `market.war_stories` — Operational narrative lessons (lesson_learned required)
- `market.market_availability` — Current market supply/demand signals

**repair schema**
- `repair.parts` — Component-level parts with cross-references
- `repair.part_suppliers` — Supplier directory
- `repair.part_availability` — Stock/pricing per supplier
- `repair.repair_procedures` — Step-by-step repair guides
- `repair.repair_steps` — Ordered steps with checkpoints and warnings
- `repair.repair_shops` — Shop directory with capabilities
- `repair.repair_records` — 1M+ flexible ingestion with `raw_shop_data JSONB`
- `repair.repair_statistics` — Pre-computed rollup stats for fast queries
- `repair.shop_reviews` — Shop reputation from actual repair outcomes

**pool schema**
- `pool.mining_pools` — Pool directory with fee structure and performance
- `pool.pool_endpoints` — Stratum and API endpoint records
- `pool.stratum_configurations` — Ready-to-push config recipes per pool/firmware
- `pool.pool_reliability_history` — Time-series uptime, luck, reject rates
- `pool.pool_incidents` — Outage and degradation events
- `pool.bitcoin_network_snapshots` — Difficulty, hashrate, price, revenue/TH
- `pool.stratum_error_codes` — Stratum V1/V2 error code reference

**facility schema**
- `facility.cooling_solutions` — Immersion tanks, hydro loops, air units
- `facility.power_distribution_units` — PDU specs with outlet types
- `facility.facilities` — Physical locations (BiXBiT USA Fort Worth, etc.)
- `facility.hvac_patterns` — HVAC integration patterns and setpoints
- `facility.rack_positions` — Physical slot map with PDU and network links

**regulatory schema**
- `regulatory.frameworks` — Laws and regulations by jurisdiction
- `regulatory.tax_treatment` — Depreciation, deductions, income rules
- `regulatory.import_export_rules` — Tariffs, restrictions (Section 301, etc.)
- `regulatory.insurance_requirements` — Coverage requirements by facility type
- `regulatory.environmental_regs` — Noise limits, heat discharge, permits

---

## 2. Key Design Decisions

### 2.1 — Schema-per-category namespace isolation
Each of the 9 categories lives in its own PostgreSQL schema. Benefits:
- **Permission isolation**: Mining Guardian can get read-only access to specific schemas
- **Logical clarity**: `SELECT * FROM repair.repair_records` reads like documentation
- **Future microservices**: Each schema could become its own service boundary
- **Prevent naming collisions**: `firmware.firmware_bugs` and `ops.miner_error_codes` don't conflict

### 2.2 — knowledge schema as foundation layer
The `knowledge` schema is intentionally the first schema created. Every other table
has an optional or required `primary_source_id UUID REFERENCES knowledge.sources(id)`.
This means:
- You can always answer "where did we get this data point?"
- When two sources disagree, `knowledge.data_conflicts` stores both values
- `knowledge.freshness_log` enables staleness alerts: "this spec hasn't been verified in 90 days"
- `knowledge.citations` supports per-field attribution (not just per-row)

### 2.3 — Source tier hierarchy (5 tiers)
```
tier1_manufacturer    → Bobby's manufacturers (Bitmain, Auradine): trust ~0.88-0.92
tier2_operational     → Bobby's direct operational data: trust ~0.95 (highest)
tier3_repair_shop     → Repair shop empirical data: trust ~0.75-0.85
tier4_community       → Reddit, Discord, forums: trust ~0.40-0.60
tier5_market_external → Price feeds, external APIs: trust ~0.50-0.70
```
Note: Bobby's operational data (tier2) has *higher trust than manufacturer specs (tier1)*
because Bobby has personally verified equipment performance in-field.

### 2.4 — Fuzzy model name matching system
The `hardware.model_aliases` table + `pg_trgm` extension enables:
```sql
-- Find model from any alias string
SELECT miner_model_id
FROM hardware.model_aliases
WHERE similarity(alias_normalized, lower(regexp_replace($1, '[\s\-\_\.]', '', 'g'))) > 0.7
ORDER BY similarity DESC LIMIT 1;
```
Pre-seeded aliases for Bobby's fleet: 30+ variants covering common typos, abbreviations,
listing titles, and repair shop CSV header formats. When ingesting 1M+ repair records,
`model_name_raw` stores the original, and normalization runs asynchronously.

### 2.5 — AH3880 2-board hard constraint
The Auradine Teraflux AH3880 uses **exactly 2 hashboards**. This is architecturally fixed.
Enforced in:
1. `hardware.miner_models.board_count_is_fixed = TRUE` for this model
2. `hardware.miner_models.hashboard_count = 2` in seed data
3. A `market.war_stories` entry documents WHY this constraint exists
4. Application-layer validation should flag `board_count ≠ 2` in any AH3880 repair record

### 2.6 — Repair record flexible ingestion (1M+ records)
`repair.repair_records.raw_shop_data JSONB` is the key field:
- Every column in an incoming CSV that doesn't map to a schema column goes here
- **Nothing is ever discarded** (Bobby's "NO data point is too small" principle)
- `import_batch_id` enables rollback of a bad import
- `is_normalized = FALSE` means "in normalization queue"
- `model_name_raw` stores the original before alias resolution
- Recommend adding `PARTITION BY RANGE (created_at)` once records exceed 500K

### 2.7 — Full-text search strategy
All text-heavy tables have a `search_vector TSVECTOR` column maintained by trigger:
```sql
CREATE TRIGGER trg_xxx_search_vector
    BEFORE INSERT OR UPDATE ON xxx
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english', col1, col2, ...
    );
```
GIN indexes on `search_vector` enable fast `to_tsquery()` searches. Tables with
full-text search:
- `hardware.miner_models`, `hardware.chips`, `hardware.hashboards`
- `firmware.firmware_releases`, `firmware.firmware_bugs`
- `ops.failure_patterns`, `ops.failure_symptoms`, `ops.miner_error_codes`
- `market.user_reviews`, `market.forum_posts`, `market.teardown_reports`, `market.war_stories`
- `repair.repair_procedures`, `repair.repair_shops`
- `pool.mining_pools`
- All regulatory tables

### 2.8 — JSONB strategy
JSONB is used strategically (not as a crutch) for:
| Field | Reason |
|---|---|
| `raw_shop_data` | Unknown schema from diverse shops |
| `spec_snapshot` | Full spec capture at a point in time |
| `efficiency_curve` | Variable-length array of load/efficiency pairs |
| `known_defects` | Revision-specific defect lists |
| `key_insights` | LLM-extracted insights from forum posts |
| `response_schema` | JSON Schema of API responses |
| `component_inventory` | Teardown component lists |
| `server_locations` | Pool endpoint geographic list |

GIN indexes are created on all frequently-queried JSONB fields.

### 2.9 — Verified by Bobby flag
Multiple tables have `verified_by_bobby BOOLEAN NOT NULL DEFAULT FALSE`.
This is a first-class data quality signal: Bobby's direct operational verification
supersedes all other sources. Mining Guardian should surface Bobby-verified data
preferentially over unverified community data.

### 2.10 — Probabilistic symptom-to-failure mapping
`ops.symptom_pattern_map` stores Bayesian-style probabilities:
```sql
-- Differential diagnosis query
SELECT fp.pattern_name, spm.probability, fp.repair_success_rate
FROM ops.symptom_pattern_map spm
JOIN ops.failure_patterns fp ON fp.id = spm.pattern_id
JOIN ops.failure_symptoms fs ON fs.id = spm.symptom_id
WHERE fs.symptom_code IN ('SYM-BOARD-MISSING', 'SYM-TEMP-HIGH-ONE-BOARD')
ORDER BY spm.probability DESC;
```

### 2.11 — Versioned thresholds
`ops.operational_thresholds.effective_from/effective_to` enables threshold history.
Query for current thresholds:
```sql
WHERE effective_to IS NULL OR effective_to > NOW()
```
Most-specific threshold wins (most non-NULL scope fields). Mining Guardian should
implement: model-specific > cooling-specific > global thresholds.

### 2.12 — Economic intelligence
`pool.bitcoin_network_snapshots.revenue_per_th_day_usd` enables instant fleet revenue calculation:
```sql
SELECT SUM(mm.max_hashrate_th) * bns.revenue_per_th_day_usd AS daily_gross_revenue
FROM hardware.miner_models mm, pool.bitcoin_network_snapshots bns
WHERE bns.snapshot_at = (SELECT MAX(snapshot_at) FROM pool.bitcoin_network_snapshots)
```

---

## 3. Query Patterns Mining Guardian Supports

### 3.1 — Model identification from fuzzy name
```sql
-- "What model is 's19j pro 104th'?"
SELECT mm.canonical_name, mm.stock_hashrate_th, mm.cooling_type
FROM hardware.model_aliases ma
JOIN hardware.miner_models mm ON mm.id = ma.miner_model_id
WHERE similarity(ma.alias_normalized,
    lower(regexp_replace('s19j pro 104th', '[\s\-\_\.\+]', '', 'g'))) > 0.6
ORDER BY similarity(ma.alias_normalized,
    lower(regexp_replace('s19j pro 104th', '[\s\-\_\.\+]', '', 'g'))) DESC
LIMIT 1;
```

### 3.2 — Differential diagnosis from symptoms
```sql
-- "I see high temp on board 1, low hashrate on board 1, other boards fine"
WITH symptom_ids AS (
    SELECT id FROM ops.failure_symptoms
    WHERE symptom_code = ANY(ARRAY['SYM-TEMP-BOARD-HIGH', 'SYM-HASHRATE-ONE-BOARD-LOW'])
)
SELECT fp.pattern_name, fp.pattern_code, fp.repair_success_rate,
       AVG(spm.probability) as avg_probability
FROM ops.symptom_pattern_map spm
JOIN ops.failure_patterns fp ON fp.id = spm.pattern_id
WHERE spm.symptom_id IN (SELECT id FROM symptom_ids)
GROUP BY fp.id
ORDER BY avg_probability DESC;
```

### 3.3 — What firmware can I run on this miner?
```sql
SELECT fr.display_name, fc.max_achievable_th, fc.typical_hashrate_th,
       fc.is_officially_supported, fc.verified_by_bobby
FROM firmware.firmware_compatibility fc
JOIN firmware.firmware_releases fr ON fr.id = fc.firmware_id
WHERE fc.miner_model_id = '50000000-0000-0000-0000-000000000001'  -- S19j Pro
  AND fc.is_compatible = TRUE
ORDER BY fc.verified_by_bobby DESC, fc.max_achievable_th DESC;
```

### 3.4 — Get all telemetry fields for a firmware version
```sql
SELECT ft.field_name, ft.guardian_canonical_field, ft.unit,
       ft.alert_threshold_high, ft.is_key_metric
FROM firmware.firmware_telemetry_fields ft
JOIN firmware.firmware_releases fr ON fr.id = ft.firmware_id
WHERE fr.firmware_family = 'bixbit'
  AND fr.is_current_stable = TRUE
  AND ft.is_available = TRUE
ORDER BY ft.is_key_metric DESC, ft.field_name;
```

### 3.5 — Find repair shops that can fix this model
```sql
SELECT rs.shop_name, rs.city, rs.state_province,
       rs.accepts_mail_in, rs.turnaround_days_min, rs.reputation_score
FROM repair.repair_shops rs
WHERE '50000000-0000-0000-0000-000000000001' = ANY(rs.specializes_in)
  AND rs.is_active = TRUE
ORDER BY rs.reputation_score DESC NULLS LAST;
```

### 3.6 — What are the known bugs for my current firmware?
```sql
SELECT fb.bug_title, fb.severity, fb.impacts_telemetry, fb.workaround
FROM firmware.firmware_bugs fb
JOIN firmware.firmware_releases fr ON fr.id = fb.firmware_id
WHERE fr.firmware_family = 'bixbit'
  AND (fb.affected_model_id IS NULL
       OR fb.affected_model_id = '50000000-0000-0000-0000-000000000001')
  AND fb.is_fixed = FALSE
ORDER BY fb.severity DESC;
```

### 3.7 — Get complete stratum config for a pool/firmware combo
```sql
SELECT sc.full_config_json, pe.hostname, pe.port, pe.is_ssl
FROM pool.stratum_configurations sc
JOIN pool.pool_endpoints pe ON pe.id = sc.primary_endpoint_id
WHERE sc.pool_id = '80000000-0000-0000-0000-000000000001'  -- Foundry
  AND (sc.firmware_id = '60000000-0000-0000-0000-000000000002'  -- BiXBiT
       OR sc.firmware_id IS NULL)
ORDER BY sc.firmware_id NULLS LAST
LIMIT 1;
```

### 3.8 — Fleet revenue projection
```sql
SELECT bns.btc_price_usd, bns.revenue_per_th_day_usd, bns.difficulty,
       -- Bobby's fleet total hashrate
       (SELECT SUM(fap.measured_hashrate_th)
        FROM firmware.firmware_autotuning_profiles fap
        WHERE fap.verified_by_bobby = TRUE
          AND fap.operational_mode = 'turbo') AS fleet_th,
       (SELECT SUM(fap.measured_hashrate_th) FROM firmware.firmware_autotuning_profiles fap
        WHERE fap.verified_by_bobby = TRUE AND fap.operational_mode = 'turbo')
       * bns.revenue_per_th_day_usd AS daily_gross_usd
FROM pool.bitcoin_network_snapshots bns
ORDER BY bns.snapshot_at DESC LIMIT 1;
```

### 3.9 — Data freshness audit
```sql
-- Which hardware specs haven't been verified in 90+ days?
SELECT fl.tracked_table, fl.tracked_row_id, fl.tracked_field,
       fl.last_verified_at, fl.staleness_days
FROM knowledge.freshness_log fl
WHERE fl.staleness_days > 90
ORDER BY fl.staleness_days DESC;
```

### 3.10 — Source conflict resolution queue
```sql
SELECT dc.conflict_table, dc.conflict_field,
       dc.value_a, dc.value_b,
       sa.display_name AS source_a, sb.display_name AS source_b,
       dc.resolution_strategy
FROM knowledge.data_conflicts dc
JOIN knowledge.sources sa ON sa.id = dc.source_a_id
JOIN knowledge.sources sb ON sb.id = dc.source_b_id
WHERE dc.is_resolved = FALSE
ORDER BY dc.severity DESC, dc.created_at;
```

### 3.11 — Full-text search across failure knowledge
```sql
SELECT 'failure_pattern' AS type, pattern_name AS title, pattern_code AS code
FROM ops.failure_patterns
WHERE search_vector @@ to_tsquery('english', 'hashboard & temperature & dead')
UNION ALL
SELECT 'war_story', title, NULL
FROM market.war_stories
WHERE search_vector @@ to_tsquery('english', 'hashboard & temperature & dead')
UNION ALL
SELECT 'forum_post', title, NULL
FROM market.forum_posts
WHERE search_vector @@ to_tsquery('english', 'hashboard & temperature & dead')
ORDER BY type, title;
```

---

## 4. Seed Data Loaded

| Table | Records | Content |
|---|---|---|
| `knowledge.contributors` | 4 | Bobby, Bitmain official, Auradine official, BiXBiT team |
| `knowledge.sources` | 9 | Bitmain, Auradine, BiXBiT, Bobby ops, Braiins, VNish, ASICMinerValue, Reddit, internal |
| `hardware.manufacturers` | 3 | Bitmain, Auradine, MicroBT |
| `hardware.chips` | 4 | BM1362, BM1368, AT7200, BM1397 |
| `hardware.hashboards` | 4 | S19j Pro, S21 EXP Hydro, S21 Immersion, AH3880 boards |
| `hardware.miner_models` | 4 | All 4 fleet models with full specs |
| `hardware.model_aliases` | 30 | All known alias variants for all 4 models |
| `firmware.firmware_releases` | 6 | BiXBiT legacy, BiXBiT current, Bitmain stock ×2, Auradine native, Braiins OS+ |
| `firmware.firmware_compatibility` | 6 | All Bobby-relevant firmware×hardware combos |
| `firmware.firmware_autotuning_profiles` | 8 | Eco/Turbo/Max profiles for all models |
| `ops.operational_thresholds` | 4 | Thermal/power limits for all fleet models |
| `pool.mining_pools` | 5 | Foundry, AntPool, Braiins, Ocean, Luxor |
| `facility.facilities` | 1 | BiXBiT USA Fort Worth TX |
| `market.war_stories` | 1 | AH3880 2-board constraint documentation |

---

## 5. Migration Notes from guardian.db (SQLite)

### Architecture separation
The current `guardian.db` is an **operational** database: live miner data, current status,
active jobs, session tokens. The new PostgreSQL database is a **research/intelligence**
database: reference specs, historical patterns, community knowledge.

**They are NOT the same database and should NOT be merged.**

### guardian.db → intelligence_catalog mapping
| guardian.db table | Maps to | Notes |
|---|---|---|
| `miners` (live fleet) | Not migrated | Stays in guardian.db — operational data |
| `miner_types` / model names | `hardware.miner_models` + `hardware.model_aliases` | Normalize and seed |
| Any firmware version strings | `firmware.firmware_releases` | Map via firmware_family |
| Any threshold configs | `ops.operational_thresholds` | Migrate with source=bobby_operational |
| Any pool configs | `pool.stratum_configurations` | Migrate with verified=TRUE |
| Error logs / incidents | `repair.repair_records` (raw_shop_data) | Bobby's own incidents = tier2 |

### Read-only access from Guardian VPS
```sql
-- Create read-only role for Mining Guardian
CREATE ROLE mining_guardian_readonly;
GRANT CONNECT ON DATABASE intelligence_catalog TO mining_guardian_readonly;
GRANT USAGE ON SCHEMA hardware, firmware, ops, market, repair, pool, facility, regulatory, knowledge
    TO mining_guardian_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA hardware TO mining_guardian_readonly;
-- (repeat for each schema)
-- Create user
CREATE USER guardian_vps WITH PASSWORD 'strong_password_here';
GRANT mining_guardian_readonly TO guardian_vps;
```

### Connection string from Guardian VPS
```
postgresql://guardian_vps:PASSWORD@ROBS-PC_IP:5432/intelligence_catalog
```
Ensure pg_hba.conf on ROBS-PC allows connections from VPS IP.

---

## 6. Future Expansion Notes

### 6.1 — Partitioning repair.repair_records
Once records exceed 500K, add range partitioning by `created_at`:
```sql
-- Convert to partitioned table
ALTER TABLE repair.repair_records PARTITION BY RANGE (created_at);
CREATE TABLE repair.repair_records_2024 PARTITION OF repair.repair_records
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
```

### 6.2 — TimescaleDB for time-series
`pool.bitcoin_network_snapshots` and `pool.pool_reliability_history` are time-series
candidates. When data volume grows, convert to TimescaleDB hypertables:
```sql
SELECT create_hypertable('pool.bitcoin_network_snapshots', 'snapshot_at');
```

### 6.3 — pgvector for embedding-based search
Once Mining Guardian gains LLM-based features, add:
```sql
CREATE EXTENSION vector;
ALTER TABLE ops.failure_patterns ADD COLUMN embedding vector(1536);
ALTER TABLE market.war_stories ADD COLUMN embedding vector(1536);
```
This enables semantic search: "find failure patterns similar to my symptom description."

### 6.4 — UGREEN NAS migration (July 2026)
The UGREEN NAS will likely run PostgreSQL 16 or 17. Migration steps:
1. `pg_dump --format=custom intelligence_catalog > catalog_backup.dump`
2. Transfer to NAS
3. `pg_restore --dbname=intelligence_catalog catalog_backup.dump`
4. Update Guardian VPS connection string
5. No schema changes needed — the schema is NAS-agnostic

### 6.5 — New table candidates (not yet designed)
- `hardware.chip_binning` — Quality grades within same chip model
- `repair.repair_kits` — Pre-assembled repair kits (BOM + suppliers)
- `ops.performance_baselines` — Rolling 30-day performance baselines per miner
- `market.model_comparisons` — Pre-computed side-by-side model comparisons
- `pool.fee_optimizations` — Optimal pool routing by time of day / fee structure
- `knowledge.ai_extractions` — LLM-generated insights with confidence scores
- `regulatory.compliance_checklists` — Per-facility compliance status tracking

### 6.6 — Ingestion pipeline for 1M+ repair records
Recommended approach:
1. **Stage table**: Create `repair.repair_records_staging` (same schema) for raw imports
2. **Normalization job**: Background worker reads `is_normalized=FALSE` rows, resolves
   model aliases, maps fields, moves to production table
3. **Conflict detection**: After normalization, compare new data against existing
   and create `knowledge.data_conflicts` records where values differ
4. **Batch rollback**: `import_batch_id` allows `DELETE FROM repair.repair_records WHERE import_batch_id = 'bad_import_20250101'`

### 6.7 — Bobby's operational intelligence additions
As Bobby runs his fleet, data should flow INTO this database:
- BiXBiT API data snapshots → `ops.environmental_correlations` measured data points
- Anomalies Bobby investigates → `ops.failure_symptoms` and `market.war_stories`
- Any firmware updates → `firmware.firmware_compatibility` with `verified_by_bobby=TRUE`
- Any parts sourced for repair → `repair.part_availability` update

---

## 7. Index Strategy

### 7.1 — Index types used
| Index Type | Used For |
|---|---|
| B-tree (default) | All FK columns, date ranges, enum filters, boolean flags |
| GIN (pg_trgm) | Fuzzy text matching on model names and aliases |
| GIN (tsvector) | Full-text search on all text-heavy tables |
| GIN (jsonb) | JSONB containment and key queries |
| Partial indexes | Common filtered queries (is_active=TRUE, is_current=TRUE, is_resolved=FALSE) |

### 7.2 — Key partial indexes
- `WHERE is_active = TRUE` — reduces scan size for active records
- `WHERE is_resolved = FALSE` — conflict review queue
- `WHERE has_been_processed = FALSE` — forum post extraction queue
- `WHERE verified_by_bobby = TRUE` — premium data tier
- `WHERE is_current_stable = TRUE` — current firmware
- `WHERE is_normalized = FALSE` — repair record normalization queue

### 7.3 — Composite indexes for common query patterns
- `(miner_model_id, price_date DESC)` — latest price per model
- `(firmware_id, miner_model_id)` — compatibility matrix lookups
- `(cited_table, cited_row_id, cited_field)` — per-field citation lookup
- `(pool_id, period_start DESC)` — pool reliability history

---

## 8. Constraint Enforcement Summary

### Critical business rules enforced
| Rule | Enforcement |
|---|---|
| AH3880 = exactly 2 boards | `hardware.miner_models.hashboard_count=2`, `board_count_is_fixed=TRUE`, war story documenting constraint |
| Source tier validity | `ENUM` type constraint |
| Trust scores 0–1 | `CHECK (trust_score BETWEEN 0 AND 1)` |
| Ratings 1–10 | `CHECK (overall_rating BETWEEN 1 AND 10)` |
| Probability 0–1 | `CHECK (probability BETWEEN 0 AND 1)` |
| Unique aliases | `UNIQUE (alias_normalized)` prevents duplicate fuzzy keys |
| Unique firmware version | `UNIQUE (firmware_family, version_string)` |
| Unique model per manufacturer | `UNIQUE (manufacturer_id, canonical_name)` |
| All timestamps auto-set | Triggers on every table for `updated_at` |
| Balanced parens | Verified: 1,217 open = 1,217 close |

---

*Schema designed for Mining Guardian — Bobby's AI-first Bitcoin mining fleet management system.*
*10-year design horizon. NO data point is too small.*
