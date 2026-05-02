# Mining Guardian — Intelligence Catalog Full Brief
**Date:** 2026-05-02  
**Author:** Synthesized from full repo read (read-status table at end)  
**Purpose:** Single comprehensive reference for the Intelligence Catalog system — architecture, schemas, enrichment gaps, pipelines, decisions, and open work  
**Scope:** This is about ENRICHMENT COMPLETENESS — filling the catalog with chip types, board types, firmware locations, failure patterns, etc. — not about any routing or "split-brain" bugs.

---

## Section 1: Architecture Map

### Where Each Component Lives

| Component | Host | Current State |
|---|---|---|
| Mac Mini (customer site, Fort Worth TX) | Physical device on miner LAN `192.168.188.0/24` | **Canonical post-2026-04-30. Install attempted 2026-05-01, aborted pre-Phase-2 (see INSTALLER_UX_BACKLOG).** Mini is prepped (Xcode CLT, Homebrew, repo cloned, Tailscale, headless verified) but setup.sh never ran past Phase 1. |
| PostgreSQL 16 (on Mac Mini) | Mac Mini | Both `mining_guardian` (operational) and `intelligence_catalog` (reference) in same Postgres instance, port 5432, user `guardian_app` / `guardian_admin` |
| Ollama (local LLM) | Mac Mini | D-7 locked. `llama3.2:3b` for 16 GB RAM; `qwen2.5:14b-instruct-q4_K_M` for 24 GB+ RAM (D-13) |
| VPS Hostinger (srv1549463 / 187.124.247.182) | Hostinger cloud | **DECOMMISSIONED for Mining Guardian** as of 2026-04-30. Bobby still uses it for his own facility. Historical cron jobs ran here. |
| ROBS-PC (192.168.188.47 / Tailscale 100.110.87.1) | Bobby's PC, Windows 11, RTX 4090 | **Superseded.** Original plan had catalog Postgres on ROBS-PC. Cutover scope γ (locked 2026-04-28): ROBS-PC is decommissioned for MG. RTX 4090 Qwen hosted here historically; now Mac Mini owns Ollama (D-7). |
| BiXBiT AMS | Customer LAN | Miner controller. Mining Guardian polls it via WebSocket + REST + Cookie Auth. |
| catalog-api HTTP layer (`intelligence-catalog/catalog-api/catalog_api.py`, port 8420) | Was on ROBS-PC | **Retired on Mac Mini** per D-14 sub-lock 5: AI consumers talk psycopg-direct to catalog DB on the Mini, no HTTP round-trip. |

### Which Postgres Database Holds What

| Database | What it Holds | Notes |
|---|---|---|
| `mining_guardian` (operational) | Live fleet data: `miner_readings`, `miner_restarts`, `action_audit_log`, `llm_analysis`, `chain_readings`, `pool_readings`, `miner_hardware`, `scans`, `discovery_log`, `miner_baselines`, etc. | Written every scan by `core/mining_guardian.py`. Source of operational facts. |
| `mining_guardian` (same DB, intelligence_catalog schemas) | Catalog reference: all schemas listed in Section 2 below — `hardware.*`, `firmware.*`, `ops.*`, `market.*`, `repair.*`, `pool.*`, `facility.*`, `regulatory.*`, `knowledge.*`, `staging.*`, `seed.*` | Per D-14: same Postgres instance, both DBs are always reachable, live cross-reference, no TTL cache. |
| `mining_guardian_test` | Test database | Parallel test install; not operational. |

**Note on terminology:** CLAUDE.md and various docs sometimes say `intelligence_catalog` as the database name; the locked canonical is a single database `mining_guardian` containing both the operational tables (`public.*`) and the catalog schemas. The README.md confirms: "two databases on the Mac Mini — `mining_guardian` (operational) and `intelligence_catalog` (reference)" — this refers to the two logical halves, both in the same Postgres instance.

### VPS → Mac Mini Cutover — Where We Are

| Stage | Status |
|---|---|
| D-10 (install date 2026-05-05) | First attempt was 2026-05-01; aborted mid-Phase 2 due to install UX blockers (INSTALLER_UX_BACKLOG_2026-05-01.md). Mini is prepped but nothing past Phase 1 ran. |
| D-11 exit criteria | 8 criteria, all should be green before cutover. C4 (seed catalog) and C1/C3 (watchers write to Postgres) are the catalog-specific gates. |
| Schema deployed | Not yet (Postgres not yet installed on Mini — Phase 4 of setup.sh never ran) |
| Catalog seed (321 rows) | Not yet |
| Watchers writing to Postgres | Framework merged; per-source watchers are post-install work |
| C5 feedback loop (operational → catalog NOTIFY) | Code exists (`feedback_loop.py`, PR #22), launchd daemon built, **not yet invoked on any live system** |

### Role of unified_miner_index.json vs Postgres vs CSV

| Artifact | Role Post-D-12 | Current State |
|---|---|---|
| `intelligence-catalog/data/unified_miner_index.json` | **Debug / git-tracked export only.** Per D-12 (2026-04-27): Postgres is truth. The JSON is populated by enrichment research and the catalog_updater tool, but it is NOT the source of truth. | 288 slugs; 225 with enrichment dicts, 63 without. Enrichment keys are free-text fields (see Section 3). |
| `intelligence-catalog/data/miner_enrichment_master.csv` | Enrichment research results — 277 rows of curated spec data gathered from manufacturer pages, aggregator sites, community forums. CSV format with 16 enrichment columns. Source for populating the catalog. | Populated. See Section 3 for column list. |
| `hardware.miner_models` (Postgres) | **Canonical.** 317 rows (313 from seed + 4 from base schema). Anchor table. Written by `compile_all_miners.py` (seed) + `dual_writer.py` (D-12 contract). | 317 rows. Many normalized spec fields empty — see Section 3. |
| `staging.miner_model_proposals` (Postgres) | Intake buffer: watchers and `catalog_updater` write proposals here; human or automated validation promotes them to `hardware.miner_models`. | Empty (no watcher runs against live Postgres yet). |

---

## Section 2: Catalog Schemas — Every Table and What It Holds

The canonical schema lives in three files, applied in order:

1. `intelligence-catalog/seed-data/intelligence_catalog_schema.sql` — base, 4,430 lines, 63 tables  
2. `intelligence-catalog/seed-data/intelligence_catalog_schema_v2_additions.sql` — Bobby's gap audit, 886 lines, 9 more tables  
3. `intelligence-catalog/seed-data/intelligence_catalog_schema_v3_additions.sql` — exhaustive gap audit + auto-discovery, 1,256 lines, 14+ more tables  

Total: ~86+ tables across 10 schemas. Classification from CATALOG_ORPHAN_TABLES_2026-04-28.md (the authoritative audit):

- **19 KEEP tables** (9 KEEP-WIRED + 10 KEEP-SEEDED) — populated day one
- **62 DEFER tables** — empty by design, watchers will fill them
- **13 DROP tables** — speculative, scheduled for removal (may already be removed via N6/PR #12)

### Schema 1: `knowledge` — Provenance & Source Tracking (9 tables + partitions)

| Table | Purpose | Key Columns | Population Status |
|---|---|---|---|
| `knowledge.sources` | Registry of every data source (manufacturer pages, forums, research, etc.) | `source_key`, `tier`, `url`, `is_active`, `search_vector`, `metadata` | **23 rows (KEEP-WIRED)** — seed gives the set; watchers add more |
| `knowledge.contributors` | Human and automated contributors | `name`, `contributor_type`, `contact_email` | **4 rows (KEEP-SEEDED)** — Robert + 3 reference contributors |
| `knowledge.citations` | Per-field provenance trail | `cited_table`, `cited_row_id`, `cited_field`, `source_id`, `citation_date` | **0 rows (DEFER)** — watchers write on each update |
| `knowledge.data_conflicts` | When two sources disagree on a field | `conflict_table`, `conflict_row_id`, `field_name`, `value_a`, `value_b`, `is_resolved` | **0 rows (DEFER)** — C5 feedback loop writes |
| `knowledge.freshness_log` | When each row was last verified | `tracked_table`, `tracked_row_id`, `is_stale`, `next_verify_due` | **0 rows (DEFER)** — every watcher run writes here |
| `knowledge.field_registry` | Canonical dictionary of every known data field | `field_key`, `field_source`, `data_type`, `description` | **75 rows (KEEP-WIRED)** — seed; watchers reference these IDs |
| `knowledge.unknown_fields` | Fields watchers see that aren't in `field_registry` | `field_key`, `first_seen_in`, `raw_sample`, `triage_status` | **0 rows (DEFER)** — auto-discovery mechanism |
| `knowledge.field_discovery_log` | Log of unexpected fields for human triage | `field_key`, `discovered_at`, `source_tool`, `raw_value` | **0 rows (DEFER)** |
| `knowledge.raw_ingestion_log` | Partitioned log of every watcher run | `entity_label`, `archive_filename`, `source_file`, `parser`, `raw_payload`, `sha256`, `ingested_at` | **0 rows (DEFER)** — partitioned by quarter (2026-Q1 through 2027-Q1) |
| `knowledge.field_registry` (V3) | (already above) | | |
| `knowledge.llm_analysis_patterns` (V3) | Patterns Ollama identifies during analysis | `pattern_key`, `pattern_type`, `confidence_score`, `first_seen`, `example_case` | **0 rows (DEFER)** — Ollama writes post-install |

### Schema 2: `hardware` — Miner Hardware Identity (19 tables)

| Table | Purpose | Key Columns | Population Status |
|---|---|---|---|
| `hardware.manufacturers` | Brand registry | `brand` (enum), `full_name`, `country`, `website`, `is_active`, `search_vector` | **16 rows (KEEP-WIRED)** — seed + manufacturer_watcher upserts |
| `hardware.miner_models` | **Anchor table — one row per model/variant** | `manufacturer_id`, `canonical_name`, `model_number`, `cooling_type`, `hashboard_count`, `stock_hashrate_th`, `stock_power_w`, `chip_id`, `process_node_nm`, `release_date`, `is_current_product`, `msrp_usd`, `metadata` | **317 rows (KEEP-WIRED)** — many normalized columns empty; see Section 3 gap analysis |
| `hardware.model_aliases` | Alternative names for a model (AMS strings, community names) | `miner_model_id`, `alias`, `alias_normalized`, `alias_source`, `is_common` | **29 rows (KEEP-WIRED)** |
| `hardware.chips` | ASIC chip specifications | `chip_model`, `manufacturer_id`, `process_node`, `die_size_mm2`, `tdp_w`, `hash_algorithm` | **4 rows (KEEP-SEEDED)** — BM1398, BM1366, BM1397, KS3 only |
| `hardware.hashboards` | Hashboard reference specs | `manufacturer_id`, `chip_id`, `chip_count`, `pcb_revision`, `known_defects`, `metadata` | **4 rows (KEEP-SEEDED)** — top-4 reference boards |
| `hardware.model_spec_history` | History of spec changes over time | `miner_model_id`, `effective_date`, `spec_snapshot`, `superseded_date` | **0 rows (DEFER)** — trigger on UPDATE to miner_models writes history rows |
| `hardware.model_known_issues` | Documented hardware issues per model | `miner_model_id`, `issue_type`, `severity`, `description`, `affected_firmware`, `source_id` | **0 rows (DEFER)** — Wednesday community watcher |
| `hardware.chip_bins` (V2) | Chip bin/grade quality tracking | `chip_id`, `bin_grade`, `yield_pct`, `typical_efficiency_delta` | **0 rows (DEFER)** — deep-enrichment watcher (teardowns) |
| `hardware.fan_specifications` (V2) | Fan specs per model | `miner_model_id`, `fan_count`, `fan_model`, `max_rpm`, `noise_db` | **0 rows (DEFER)** — firmware/teardown watcher |
| `hardware.psu_models` (V1) | PSU model specifications | `manufacturer_id`, `model_name`, `output_power_w`, `efficiency_pct`, `input_voltage_range`, `serial_number_format` | **0 rows (DEFER)** — community watcher |
| `hardware.psu_compatibility` (V1) | Which PSUs work with which miners | `miner_model_id`, `psu_model_id`, `compatibility_level` | **0 rows (DEFER)** |
| `hardware.psu_voltage_rails` (V2) | PSU voltage rail detail | `psu_model_id`, `rail_name`, `nominal_v`, `min_v`, `max_v` | **0 rows (DEFER)** |
| `hardware.control_boards` (V1) | Control board reference specs | `manufacturer_id`, `board_model`, `cpu`, `ram_mb`, `storage_mb`, `os` | **0 rows (DEFER)** — teardown watcher |
| `hardware.cooling_compatibility` (V1) | Immersion/hydro/air compatibility per model | `miner_model_id`, `cooling_type`, `is_native`, `conversion_kit_available` | **0 rows (DEFER)** |
| `hardware.signal_chain_reference` (V3) | Signal chain topology | — | **0 rows (DROP)** — too rigid for ASIC diversity |
| `hardware.connector_pinouts` (V3) | Connector pin mapping | — | **0 rows (DROP)** — data lives in repair guides |
| `hardware.psu_serial_batches` (V2) | PSU serial batch quality tracking | — | **0 rows (DROP)** — speculative, not on roadmap |
| `hardware.control_board_serial_batches` (V2) | Control board serial batch tracking | — | **0 rows (DROP)** — same reason |
| `hardware.board_serial_batches` (V2) | Hashboard serial batch tracking | — | **0 rows (DROP)** — same reason |

### Schema 3: `firmware` — Firmware Knowledge (7 tables)

| Table | Purpose | Key Columns | Population Status |
|---|---|---|---|
| `firmware.firmware_releases` | Known firmware versions | `firmware_family`, `version_string`, `release_date`, `is_current_stable`, `download_url`, `release_notes_url` | **6 rows (KEEP-SEEDED)** — Antminer/Whatsminer current versions |
| `firmware.firmware_compatibility` | Which firmware runs on which models | `firmware_id`, `miner_model_id`, `verified_by_bobby`, `compatibility_level` | **6 rows (KEEP-SEEDED)** — hand-curated matrix |
| `firmware.firmware_autotuning_profiles` | Autotuning profiles (LuxOS, Vnish, Braiins) | `firmware_id`, `profile_name`, `target_hashrate_th`, `target_power_w`, `notes` | **8 rows (KEEP-SEEDED)** — top autotuning profiles |
| `firmware.firmware_changelog` | Per-version changelog | `firmware_id`, `change_type`, `description`, `affected_models` | **0 rows (DEFER)** — firmware watcher |
| `firmware.firmware_bugs` | Documented bugs per firmware version | `firmware_id`, `bug_key`, `severity`, `description`, `workaround` | **0 rows (DEFER)** — community watcher |
| `firmware.firmware_api_capabilities` | What API endpoints/fields each firmware exposes | `firmware_id`, `endpoint`, `data_category`, `response_schema`, `sample_response` | **0 rows (DEFER)** — populated by Mining Guardian runtime as it probes miners |
| `firmware.firmware_telemetry_fields` | What telemetry fields each firmware returns | `firmware_id`, `field_name`, `field_type`, `units`, `description` | **0 rows (DEFER)** — populated by runtime probes |

### Schema 4: `ops` — Operational Intelligence (9 tables)

| Table | Purpose | Key Columns | Population Status |
|---|---|---|---|
| `ops.operational_thresholds` | Default alert thresholds | `threshold_key`, `miner_model_id` (nullable), `warning_value`, `critical_value` | **4 rows (KEEP-SEEDED)** — chip temp, board temp, hashrate variance, fan RPM |
| `ops.alert_rules` | Customer-entered alert rules | `rule_name`, `condition_expr`, `severity`, `notify_channel` | **0 rows (KEEP-WIRED)** — customer enters post-install via UI |
| `ops.failure_patterns` | Known failure patterns (cross-model) | `pattern_key`, `category`, `severity`, `symptoms`, `root_cause`, `recommended_action`, `affected_models` | **0 rows (DEFER)** — runtime writes real-world patterns (D-12 separation: factory spec ≠ field-observed) |
| `ops.failure_symptoms` | Symptom library | `symptom_key`, `description`, `data_source`, `detection_logic` | **0 rows (DEFER)** — runtime |
| `ops.symptom_pattern_map` | Symptom → failure pattern mapping | `symptom_id`, `pattern_id`, `confidence_score` | **0 rows (DEFER)** — runtime |
| `ops.miner_error_codes` | Vendor error code library | `vendor`, `error_code`, `category`, `severity`, `description`, `possible_causes`, `recommended_actions` | **0 rows (DEFER)** — firmware watcher seeds common codes |
| `ops.miner_baseline_reference` (V3) | New-from-factory baseline specs | `miner_model_id`, `baseline_hashrate_th`, `baseline_power_w`, `baseline_efficiency` | **0 rows (DEFER)** — Wednesday seed |
| `ops.environmental_correlations` | Temp/humidity vs hashrate correlations | `miner_model_id`, `env_factor`, `correlation_coefficient`, `data_points` | **0 rows (DEFER)** — Mining Guardian runtime computes from time-series |
| `ops.operational_profiles` | Autotuning profile starting points | `miner_model_id`, `profile_name`, `target_hashrate_th`, `target_power_w` | **0 rows (DEFER)** — Wednesday seed |

### Schema 5: `market` — Community & Market Intelligence (10 tables)

| Table | Purpose | Key Columns | Population Status |
|---|---|---|---|
| `market.war_stories` | Field-observed real-world data (separate from factory specs per D-12) | `miner_model_id`, `story_type`, `title`, `content`, `observed_hashrate_th`, `observed_power_w`, `site_id`, `source_id` | **1 row (KEEP-WIRED)** — 1 reference story; dual_writer writes here for non-factory data |
| `market.pricing_history` | Historical price data | `miner_model_id`, `price_usd`, `price_date`, `condition`, `source_url` | **0 rows (DEFER)** — aggregator watcher |
| `market.market_availability` | Current market availability | `miner_model_id`, `retailer`, `price_usd`, `in_stock`, `lead_time_days` | **0 rows (DEFER)** — aggregator watcher |
| `market.depreciation_schedules` (V3) | Value degradation curves | `miner_model_id`, `months_in_service`, `residual_value_pct` | **0 rows (DEFER)** — computed by aggregator watcher |
| `market.resale_value_history` (V3) | Resale value tracking | `miner_model_id`, `date`, `resale_value_usd`, `source` | **0 rows (DEFER)** — aggregator watcher |
| `market.user_reviews` | Community reviews | `miner_model_id`, `source_type`, `source_url`, `rating`, `content`, `upvotes` | **0 rows (DEFER)** — community watcher |
| `market.review_summaries` (V2) | LLM-summarized review aggregates | `miner_model_id`, `summary`, `avg_rating`, `review_count`, `sentiment` | **0 rows (DEFER)** — Ollama summarizes post-install |
| `market.forum_posts` | Mining forum posts | `source_url`, `title`, `content`, `vendors`, `models`, `topics`, `search_vector` | **0 rows (DEFER)** — community watcher |
| `market.teardown_reports` | Physical teardown reports | `miner_model_id`, `source_url`, `author`, `findings`, `chip_count_verified`, `board_layout` | **0 rows (DEFER)** — deep-enrichment watcher |
| `market.manufacturer_reputation` | Brand reputation scores | `manufacturer_id`, `reputation_score`, `warranty_honor_rate`, `data_sources` | **0 rows (DEFER)** — computed from `manufacturer_reputation_v` view |

### Schema 6: `repair` — Repair Intelligence (10 tables)

All 10 tables are **0 rows (DEFER)**. The repair shop data from James Scaggs/ACS (1M+ records) is a future data source that is blocked until that dataset arrives.

| Table | Purpose |
|---|---|
| `repair.repair_procedures` | Step-by-step repair guides |
| `repair.repair_steps` | Individual steps |
| `repair.diagnostic_tools` | Test equipment reference |
| `repair.repair_records` | Customer's own repair history (customer-entered) |
| `repair.parts` | Spare parts catalog |
| `repair.part_suppliers` | Parts suppliers |
| `repair.part_availability` | Current parts availability |
| `repair.repair_shops` | Regional repair shop directory |
| `repair.shop_reviews` | Shop reviews |
| `repair.repair_statistics` | Computed from repair_records |

### Schema 7: `pool` — Pool & Network Intelligence (7 tables)

| Table | Purpose | Population Status |
|---|---|---|
| `pool.mining_pools` | Top pools (Foundry, Antpool, F2Pool, Luxor, Braiins) | **5 rows (KEEP-SEEDED)** |
| `pool.pool_endpoints` | Stratum endpoints | **0 rows (DEFER)** |
| `pool.stratum_configurations` | Working stratum configs | **0 rows (DEFER)** |
| `pool.stratum_error_codes` | Stratum error library | **0 rows (DEFER)** |
| `pool.bitcoin_network_snapshots` | Network difficulty/hashrate snapshots | **0 rows (DEFER)** — runtime writes from mempool.space polling |
| `pool.pool_reliability_history` | Pool uptime history | **0 rows (DEFER)** — computed from pool connect logs |
| `pool.pool_incidents` | Pool outage events | **0 rows (DEFER)** |

### Schema 8: `facility` — Facility & Infrastructure (13 tables)

| Table | Purpose | Population Status |
|---|---|---|
| `facility.facilities` | Customer facilities | **1 row (KEEP-WIRED)** — Bobby's house is row 1 |
| `facility.cooling_solutions` | Reference cooling equipment | **0 rows (DEFER)** |
| `facility.immersion_fluids` (V3) | Immersion fluid specs | **0 rows (DEFER)** |
| `facility.electricity_rates` (V3) | Electricity cost data | **0 rows (DEFER)** — customer-entered |
| `facility.demand_response_programs` (V3) | Grid demand response | **0 rows (DEFER)** — customer-entered |
| `facility.curtailment_events` (V3) | Grid curtailment events | **0 rows (DEFER)** — runtime |
| `facility.weather_reference` (V3) | Weather data | **0 rows (DEFER)** — NWS API watcher |
| `facility.hvac_patterns` | HVAC performance patterns | **0 rows (DEFER)** — runtime |
| `facility.power_distribution_units` | PDU specs | **0 rows (DEFER)** — customer-entered |
| `facility.rack_positions` | Rack/position mapping | **0 rows (DEFER)** — customer-entered |
| `facility.container_cooling_equipment` (V3) | Container-specific cooling | **0 rows (DROP)** — residential install, no container |
| `facility.container_environment_reference` (V3) | Container environment | **0 rows (DROP)** |
| `facility.container_hydraulics_reference` (V3) | Hydraulics reference | **0 rows (DROP)** |

### Schema 9: `regulatory` — Regulatory (5 tables)

All 5 tables (`frameworks`, `environmental_regs`, `import_export_rules`, `tax_treatment`, `insurance_requirements`) are **0 rows (DROP)** per the audit. Not on any roadmap through at least Q3 2026.

### Schema 10: Staging Tables (3 tables)

| Table | Purpose | Population Status |
|---|---|---|
| `staging.miner_model_proposals` | Intake buffer for watcher proposals | **0 rows** — watchers write here; human promotes to `hardware.miner_models` |
| `staging.manufacturer_proposals` | Intake for new manufacturer proposals | **0 rows** |
| `staging.alias_proposals` | Intake for new alias proposals | **0 rows** |

### Population Summary

| Schema | Total Tables | Non-Empty (current) | Rows |
|---|---|---|---|
| knowledge | 9+5 partitions | 3 | sources:23, contributors:4, field_registry:75 |
| hardware | 19 | 5 | manufacturers:16, miner_models:317, model_aliases:29, chips:4, hashboards:4 |
| firmware | 7 | 3 | firmware_releases:6, firmware_compatibility:6, firmware_autotuning_profiles:8 |
| ops | 9 | 1 | operational_thresholds:4 |
| market | 10 | 1 | war_stories:1 |
| repair | 10 | 0 | — |
| pool | 7 | 1 | mining_pools:5 |
| facility | 13 | 1 | facilities:1 |
| regulatory | 5 | 0 | — |
| staging | 3 | 0 | — |
| **Total** | **~94** | **~15** | **~502 rows total (mostly hardware.miner_models)** |

---

## Section 3: Enrichment Dimensions — What We Have vs What's Missing

### What the unified_miner_index.json Has Today (288 slugs)

**Top-level structure per entry:**
```json
{
  "display_name": "Antminer S21 (200 TH)",
  "enrichment": { ... 17 text fields ... },
  "entity": "bitmain Antminer S21 (200 TH)",
  "manufacturer": "bitmain",
  "specs": { ... structured fields ... }
}
```

**`enrichment` sub-keys (text fields from Perplexity research):**
- `Altitude Limit`, `Cooling Details`, `Dimensions (mm)`, `Distinguishing Features`
- `Firmware Support`, `Humidity Range`, `Known Issues`, `Network Interface`
- `Noise (dB)`, `Operating Temp Range`, `PSU Requirements`, `Release Date (exact)`
- `Sources`, `Voltage Range`, `Warranty`, `Weight (kg)`, `entity`

**`specs` sub-keys (structured machine-readable fields):**
- `algorithm`, `asic_chip`, `boards`, `chip_model`, `chip_process_nm`
- `chips_per_board`, `cooling`, `default_rated_ths`, `default_rated_watts`
- `dimensions_mm`, `display_name`, `efficiency_jth`, `hashboard_count`
- `hashrate_ths`, `is_current_product`, `manufacturer`, `msrp_usd`
- `notes`, `power_w`, `power_watts`, `process_node`, `profile_map`
- `release_date`, `variants`, `weight_kg`

**Coverage analysis — how many of the 288 slugs have each key populated:**

| Field | Count / 288 | Coverage % |
|---|---|---|
| `cooling` (in specs) | 288 / 288 | **100%** |
| enrichment dict present | 225 / 288 | 78% |
| `efficiency_jth` (in specs) | 52 / 288 | 18% |
| `process_node` (in specs) | 41 / 288 | 14% |
| `hashboard_count` (in specs) | 41 / 288 | 14% |
| `asic_chip` (in specs) | 41 / 288 | 14% |
| `release_date` (in specs) | 43 / 288 | 15% |
| `chip_model` (in specs) | 9 / 288 | 3% |
| `boards` (in specs) | 9 / 288 | 3% |
| `chip_process_nm` (in specs) | 10 / 288 | 3% |
| `chips_per_board` (in specs) | 9 / 288 | 3% |
| `msrp_usd` (in specs) | 2 / 288 | 0.7% |
| `is_current_product` (in specs) | 4 / 288 | 1% |

**63 slugs have NO enrichment dict at all.** These are typically older/obscure models.

### miner_enrichment_master.csv Columns

Header row (16 columns):
```
entity | Release Date (exact) | Dimensions (mm) | Weight (kg) | Operating Temp Range |
Humidity Range | Noise (dB) | Network Interface | PSU Requirements | Voltage Range |
Cooling Details | Known Issues | Firmware Support | Distinguishing Features |
Warranty | Sources
```

This CSV covers 277 models with richly sourced, text-format enrichment. It was produced by Perplexity-based research sweeps. The data feeds `unified_miner_index.json` enrichment dicts. The gap between CSV (277) and JSON (288) is 11 models not yet enriched in the CSV; separately, 63 JSON entries have no enrichment key, meaning some were added to the slug list after the CSV was populated.

### Layer 3 Daily Deep Enrichment Sweep — Tier System

From `intelligence-catalog/LIVING_CATALOG.md`:

| Tier | Models | Check Frequency | Examples |
|---|---|---|---|
| Tier 1 (Current Gen) | ~95 models | 2× per week | S21/S23, M60+, A15/A16, SealMiner A3/A4, Teraflux, Bitaxe |
| Tier 2 (Recent) | ~49 models | Weekly | S19 series, M50/M53/M56, A1246-A1366, SealMiner A2 |
| Tier 3 (Historical) | ~94 models | Weekly | S9, AvalonMiner 700-1100, Ebang, Innosilicon |

**39 data points tracked per model per sweep run** (from LIVING_CATALOG.md §Layer 3):

*Hardware Deep Specs:* chip model, process node (nm), chips per board, boards per unit, voltage range, frequency range (MHz), PSU type, fan count/type, noise (dB), operating temp range, humidity tolerance, altitude limits

*Performance Profiles:* stock/low-power/turbo hashrate + power, real-world efficiency vs rated, degradation curve

*Firmware:* stock firmware versions, compatible 3rd-party firmware (Braiins, Vnish, LuxOS, Kratos), known bugs per version

*Lifecycle & Market:* announcement date, ship date, EOL date, MSRP at launch, current street price, warranty terms, hardware revisions

*Field Intelligence:* common failure modes, typical lifespan, hashboard interchangeability, immersion fluid compatibility, chip degradation issues

*Repair & Maintenance:* thermal paste specs, cleaning intervals, parts availability, repair difficulty rating

**Current state:** The tier assignment JSON (`intelligence-catalog/data/catalog_enrichment_tiers.json`) exists. The deep enrichment cron output goes to `cron_tracking/enrichment_sweep/`. **The sweep has not been connected to write to Postgres yet** — it was wired to write JSON only.

### What Fields the Catalog Tables SHOULD Have vs What's There

The most critical gaps, cross-referencing JSON enrichment keys against `hardware.miner_models` column list:

| Enrichment Dimension | JSON has it? | hardware.miner_models column? | Current rows with value? | Verdict |
|---|---|---|---|---|
| Chip model / ASIC chip type | Yes (`asic_chip`, `chip_model`) | `chip_id` FK to hardware.chips | 317 rows, chip_id mostly NULL | **MAJOR GAP** |
| Process node (nm) | Yes (`chip_process_nm`, `process_node`) | `process_node_nm` | Mostly NULL | **MAJOR GAP** |
| Hashboard count | Yes (`hashboard_count`, `boards`) | `hashboard_count` | Some populated in seed | Partial |
| Chips per board | Yes (`chips_per_board`) | `chip_count_per_board` (in schema) | Mostly NULL | **MAJOR GAP** |
| PSU type / requirements | Yes (enrichment `PSU Requirements`) | `psu_model_id` FK — `hardware.psu_models` empty | 0 PSU records | **MAJOR GAP** |
| Firmware support | Yes (enrichment `Firmware Support`) | `firmware.firmware_releases` — 6 rows | 6 rows only | **MAJOR GAP** |
| Known issues | Yes (enrichment `Known Issues`) | `hardware.model_known_issues` — 0 rows | 0 | **MAJOR GAP** |
| Immersion/hydro/air compatibility | Yes (enrichment `Cooling Details`) | `hardware.cooling_compatibility` — 0 rows | 0 | DEFER |
| Voltage range | Yes (enrichment `Voltage Range`) | `voltage_min`, `voltage_max` on miner_models | Mostly NULL | **MAJOR GAP** |
| Efficiency (J/TH) | Yes (`efficiency_jth`) — 52/288 | `efficiency_j_per_th` on miner_models | Some in seed variants | Partial |
| Release date | Yes — 43/288 | `release_date` | Some in seed | Partial |
| MSRP | Yes — 2/288 | `msrp_usd` | Rare | **MAJOR GAP** |
| Control board type | Rarely | `hardware.control_boards` — 0 rows | 0 | DEFER |
| Fan count/type | Yes (enrichment `Cooling Details`) | `hardware.fan_specifications` — 0 rows | 0 | DEFER |
| Failure patterns (cross-model) | In enrichment `Known Issues` text | `ops.failure_patterns` — 0 rows | 0 | **MAJOR GAP** |
| Error codes | Not in CSV/JSON currently | `ops.miner_error_codes` — 0 rows | 0 | **MAJOR GAP** |
| Repair procedures | Not in CSV/JSON | `repair.repair_procedures` — 0 rows | 0 | DEFER (ACS data) |
| Pricing / market availability | Not currently | `market.pricing_history` — 0 rows | 0 | DEFER |

**The clearest gap**: `hardware.chips` has only 4 rows (BM1398, BM1366, BM1397, KS3), but there are dozens of distinct chips across 288 slug entries. The `chip_id` FK on `hardware.miner_models` is therefore NULL for the vast majority of models.

---

## Section 4: Cron / Watchers / Enrichment Pipelines

### Layer 1: Four Daily Watchers

All four watchers exist in `intelligence-catalog/watchers/`. The watcher framework is merged; each watcher was as of 2026-04-29 wired to write to Postgres staging tables via `dual_writer.py` for the manufacturer watcher (PR #16), with the other three wired for JSON only and awaiting Postgres integration.

| Watcher | Schedule | Output Path | What It Enriches |
|---|---|---|---|
| **Manufacturer Watcher** (~6:00 AM CDT) | Daily | `cron_tracking/manufacturer_watcher/latest_findings.json` | New model announcements from Bitmain, MicroBT, Canaan, Bitdeer, Auradine product pages. Compares against `catalog_known_models.txt`. Upserts to `hardware.miner_models` + `hardware.manufacturers` + `hardware.model_aliases` via `dual_writer.py` (PR #16, wired) |
| **Community Intel Scanner** (~7:19 AM CDT) | Daily | `cron_tracking/community_scanner/latest_findings.json` | Reddit (r/BitcoinMining, r/ASICMining), Twitter/X, BitcoinTalk, YouTube. Categories: [NEW MODEL], [FIRMWARE], [FIELD REPORT], [ISSUE], [RUMOR]. Targets `market.forum_posts`, `hardware.model_known_issues`. **Not yet wired to Postgres.** |
| **Aggregator Watcher** (~6:30 AM CDT) | Daily | `cron_tracking/aggregator_watcher/latest_findings.json` | Hashrate Index, AsicMinerValue, F2Pool, retailer sites. New listings + spec discrepancies. Targets `market.pricing_history`, `market.market_availability`. **Not yet wired to Postgres.** |
| **Firmware Tracker** (~7:00 AM CDT) | Daily | `cron_tracking/firmware_tracker/latest_findings.json` | Manufacturer support pages, mining news. New firmware releases for Bitmain, MicroBT, Canaan, Braiins OS, Vnish, LuxOS. Targets `firmware.firmware_releases`, `firmware.firmware_changelog`, `firmware.firmware_bugs`. **Not yet wired to Postgres.** |

**How watchers work:** Each watcher compares findings to previous run to avoid duplicate notifications. Silent exit if nothing new.

### Layer 3: Daily Deep Enrichment Sweep

**Schedule:** Mon–Sat, ~10 AM CDT  
**Script:** `ai/daily_deep_dive.py` (calls Ollama/Qwen locally)  
**Tier rotation:** 238+ models split across 6 days per tier assignments in `intelligence-catalog/data/catalog_enrichment_tiers.json`  
**Output:** `cron_tracking/enrichment_sweep/` (CSV results), then `catalog_updater.py` writes to `unified_miner_index.json`  
**Postgres wiring:** NOT YET CONNECTED to Postgres. Results are written to JSON only. The dual_writer.py contract means results should go to `staging.miner_model_proposals` for promotion to `hardware.miner_models`.

**39 data points tracked** per model per run — see Section 3 tier system table.

### The dual_writer.py Contract (D-12, Postgres-as-truth, locked 2026-04-27)

`intelligence-catalog/db/dual_writer.py` is the canonical write path:

1. **`propose_miner_model(slug, payload, source_tool, ...)`** — UPSERTs into `staging.miner_model_proposals`. Returns UUID of proposal or None if Postgres down.
2. **`propose_manufacturer(brand, payload, source_tool, ...)`** — UPSERTs into `staging.manufacturer_proposals`.
3. **`propose_alias(miner_slug, alias, source_tool, ...)`** — UPSERTs into `staging.alias_proposals`.
4. **`promote_validated_miner_models()`** — Promotes validated proposals from staging into `hardware.miner_models`. Manual or automated step.

**Key design choices:**
- Best-effort on write path: if Postgres is unreachable, log and continue (JSON write not blocked)
- Payload dedup: `payload_hash` + slug unique index; identical re-writes are no-ops
- Staging holds raw JSONB; normalization happens at promotion time
- Connection uses `MG_DB_PASSWORD` (D-1) + standard `PGHOST`/`PGPORT`/`PGUSER`/`PGDATABASE` env vars

**What D-12 means:** The legacy `unified_miner_index.json` file is NOT modified by watchers for truth — it becomes a git-tracked export/debug copy. Watchers must write to Postgres staging tables. Only 1 watcher (manufacturer_watcher) has been wired to this contract as of 2026-04-29.

### Cron Schedule (Historical VPS, now migrated to Mac Mini launchd)

The old cron (`docs/CRON_SCHEDULE.md`) ran on the VPS (decommissioned). Mac Mini uses launchd `.plist` files. Relevant to enrichment:

| Time | Job | Notes |
|---|---|---|
| 4:00 PM | `ai/daily_deep_dive.py` | Per-miner deep dive; consults catalog via `ai/catalog_context.py` (D-14 implementation pending) |
| 12:00 AM | `ai/weekly_train.py` | Claude cohort analysis — consumes deep dive results |
| 1:00 AM | `ai/refinement_chain.py` | Qwen reflection + Claude merge |
| ~6:00 AM | Manufacturer watcher | Catalog enrichment Layer 1 |
| ~6:30 AM | Aggregator watcher | Catalog enrichment Layer 1 |
| ~7:00 AM | Firmware tracker | Catalog enrichment Layer 1 |
| ~7:19 AM | Community scanner | Catalog enrichment Layer 1 |
| ~10:00 AM (Mon–Sat) | Deep enrichment sweep | Layer 3 tier rotation |

### C5 Feedback Loop (Operational → Catalog)

Per D-14: every write to `public.action_audit_log`, `public.miner_restarts`, and `public.llm_analysis` should fire a Postgres `NOTIFY catalog_feedback`. A `feedback_loop_daemon.py` LISTENs and runs the sync logic in `intelligence-catalog/db/feedback_loop.py` within ~100 ms.

**Current state:** `feedback_loop.py` (PR #22, 30 KB) is fully implemented and tested. The launchd plist exists. **But the daemon is NOT invoked by any running system** — the NOTIFY triggers on the three operational tables are not yet wired, and the daemon is not running on the Mini (Mini install hasn't completed).

---

## Section 5: Locked Decisions & Invariants

### All D-N Decisions from docs/DECISIONS.md

| ID | Title | One-Line Meaning |
|---|---|---|
| **D-1** | `MG_DB_PASSWORD` rotation | New 192-bit password in `.env` only, chmod 600, never committed. Old password `MiningGuardian2026!` was leaked in 29 locations. |
| **D-2** | `auto_approve_enabled` default | Defaults to `False` — customers must explicitly opt in to autonomous restarts. |
| **D-3** | `outcome_checker.py` rewrite via psycopg | Replaced SQLite-era module with clean psycopg — no shim. Done PR #4. |
| **D-4** | `mg_import` session TTL | `MG_IMPORT_SESSION_TTL_SECONDS=28800` (8 hours). |
| **D-5** | `mg_import` HTML password input | Empty default value in HTML; archived handoff doc keeps old password as forensic record with rotation note. |
| **D-6** | `migrate_to_postgres.py` import guard | Migration scripts raise exception unless `MG_ALLOW_MIGRATION=1` set — prevents accidental re-runs. |
| **D-7** | Ollama hosting | Ollama runs on Mac Mini exclusively. Not on ROBS-PC. |
| **D-8** | Ollama model (superseded by D-13) | Was `qwen2.5:14b-instruct-q4_K_M`. Now superseded. |
| **D-9** | Mac Mini network | Mini on miner LAN `192.168.188.0/24`. Tailscale for remote ops only. Data plane stays local. |
| **D-10** | Mac Mini install date | 2026-05-05 originally (first attempt 2026-05-01 was aborted — see INSTALLER_UX_BACKLOG). |
| **D-11** | Cutover gate | 8 exit criteria must be green before install: no leaked secrets, no dead code, one canonical catalog schema (N6 done), AI has data (C4 + C1/C3 done), installer works from blank Mac, daily paper trail, customer-facing docs done. |
| **D-12** | Documentation cadence | Every working day gets a `SESSION_LOG_YYYY-MM-DD.md`. Decisions appended here. **NOTE: Despite the number "D-12" aligning with "documentation cadence," the repo also uses "D-12" informally to mean "Postgres-as-truth" in some older docs. The actual Postgres-as-truth contract is the rationale of D-14 and the `dual_writer.py` docstring which cites "D-12 (Postgres-as-truth, locked 2026-04-27)". Both meanings exist in the repo — D-12 in DECISIONS.md is documentation cadence; D-12 as cited in code/dual_writer.py is the Postgres-as-truth contract established when dual_writer was written.** |
| **D-13** | RAM-tier model selection (supersedes D-8) | 16 GB RAM → `llama3.2:3b`; 24 GB+ → `qwen2.5:14b-instruct-q4_K_M`. Installer auto-detects + lets customer override. |
| **D-14** | Operational ↔ Catalog live-reference architecture | Five sub-locks: (1) both DBs always reachable, no client-side TTL cache; (2) scan daemon must consult catalog before evaluating any miner; (3) catalog read failure is loud/blocking, not silent; (4) C5 feedback loop is event-driven NOTIFY/LISTEN, not cron; (5) HTTP catalog-api retired post-cutover — psycopg-direct on Mini. None of the 5 sub-locks are implemented yet on a live system. |

### Standing Rules from CLAUDE.md (key invariants)

- **Session kickoff protocol**: Read `CLAUDE.md`, `docs/VISION.md`, `docs/DECISIONS.md` before ANY action.
- **Option β branch cadence**: One narrow branch per PR, deleted on squash-merge.
- **Over-document always**: "comprehensive + over-document" — every decision gets a log entry.
- **Append-only docs**: DECISIONS.md and session logs are never edited, only appended.
- **Catalog is sacred**: "The Intelligence Catalog is the single source of truth for everything known about Bitcoin SHA-256 ASIC miners."
- **LLM is the product**: Every scan feeds it; every denial refines it.
- **No VPS references in new code**: VPS is decommissioned for MG. Mac Mini is the operational host.
- **Factory specs ≠ field-observed data**: `hardware.*` holds factory specs; `market.war_stories` and `ops.failure_patterns` hold field observations. Never conflate.

---

## Section 6: Open Work Specifically About the Catalog

### docs/MG_UNIFIED_TODO_LIST.md — Catalog-Related Items

| Item | ID | Status | Notes |
|---|---|---|---|
| C4 — Run seed SQL against catalog Postgres | §4.1 | 🔴 **OPEN** | 208 catalog tables, only 5 have data. AI sees nothing. (Note: INSTALLER_UX_BACKLOG says Phase 4/5 of setup.sh never ran on Mini — catalog not yet seeded on live machine.) |
| C1 — Catalog split-brain: watchers write JSON, API reads Postgres | §4.2 | 🟢 Partially done | `dual_writer.py` (PR #15) written, manufacturer watcher wired (PR #16). 4 remaining watchers not wired. |
| C3 — 5 background watchers write JSON, never to catalog DB | §4.3 | 🟡 Partial | 1 of 5 watchers wired (manufacturer). Aggregator, firmware, community, deep-enrichment still JSON-only. |
| C5 — Operational→Catalog feedback loop missing | §4.4 | 🔴 Open (code exists, not wired) | `feedback_loop.py` implemented, daemon built, NOTIFY triggers not on live system. |
| N6 — 4 versions of catalog schema in repo | §8.2 | ✅ Done | `intelligence/` directory deleted 2026-04-29. One canonical schema in `intelligence-catalog/seed-data/`. |
| N7 — Grafana intelligence report uses JSON catalog | §listed | 🔴 OPEN | Re-point to Postgres after C1 fully lands |
| H7 — `discovery_log` not piped to enrichment | §listed | 🔴 OPEN | Build promotion cron: `acknowledged=0` → deep enrichment queue |
| H8 — `knowledge.freshness_log` empty | §listed | 🔴 OPEN | Wire freshness writes from enrichment watchers |
| Grafana dropdown hard-coded, doesn't expand from DB | §15.6.1 | 🟡 OPEN | Dashboard JSON has literal miner list instead of `type: "query"` driven by SQL |
| B-9 — Catalog count drift (313 vs 320) | §B-9 | 🔴 OPEN | Multiple docs say 313; catalog is actually 320 after PR #102 (Bitaxe). Update 6 docs. |

### docs/INSTALLER_UX_BACKLOG_2026-05-01.md — Catalog-Tangential Items

The install attempt on 2026-05-01 was aborted before Phase 4 (Postgres install) or Phase 5 (catalog seed) ever ran. The following bugs are directly in the way of getting catalog data onto the live machine:

| Bug | Impact on Catalog | Fix Effort |
|---|---|---|
| B-1 · APFS disk check false-negative | Blocks install from even starting | ~30 min PR |
| B-2 · Phase 2 customer-info prompt UX | Blocks getting past Phase 2; `.env` never written | ~2-3 hr PR |
| B-13 · `.pkg` rejected by macOS Tahoe | ✅ Fixed in v1.0.1 | Fixed |
| B-9 · Catalog count drift (313 vs 320) | Misleading docs | ~10 min PR |

The 4 phases that would run the catalog seed are Phases 3–5 of `setup.sh`:
- Phase 3: Homebrew + Postgres install
- Phase 4: Create `guardian_app` user, 3 databases, apply schemas
- Phase 5: Run `seed-data/seed_miner_models.sql` (closes C4)

**None of these ran on 2026-05-01.** The Mini is in a clean state waiting for fixes.

### docs/REMAINING_WORK_2026-04-28.md — Catalog Work

D-14 implementation — 5 PRs still pending (none have landed on a live system):
1. Drop the 5-minute cache in `ai/catalog_context.py`
2. Wire `core/mining_guardian.py` to consult the catalog per miner eval
3. Make catalog read failure loud (raise/log-at-ERROR) instead of silent
4. Build C5 daemon: NOTIFY triggers + `feedback_loop_daemon.py` + launchd plist
5. Retire HTTP catalog-api on Mini — psycopg-direct instead

### docs/CATALOG_ORPHAN_TABLES_2026-04-28.md

Comprehensive audit (historically accurate as of 2026-04-29):
- 3 tables KEEP-WIRED (actively written today)
- 13 tables KEEP-SEEDED (seed data only)
- 62 tables DEFER (empty, watchers planned)
- 13 tables DROP (speculative — may already be removed via N6)

See the full classification in Section 2 above.

### docs/EMPTY_STUB_TABLES.md

Historical VPS-era SQLite stubs. Post-cutover equivalents tracked in `MG_UNIFIED_TODO_LIST.md`:
- `chip_readings` — dropped via migration 004 (PR #84)
- `miner_baselines` — PostgreSQL version tracked under H5 (OPEN: wire to cross-miner anomaly detection)
- `s19jpro_overheat_tracking` — PostgreSQL table kept; handler archived; reconnect to `ops.failure_patterns` is future work

### docs/LATENT_BUGS.md — Catalog-Relevant Bugs

| Bug | Impact | Status |
|---|---|---|
| B-3 — `000_bootstrap_field_log_tables.sql` non-partitioned shape | Fresh install could create wrong table shapes | ✅ Fixed 2026-04-28 |
| B-4 — `mg_import.insert_raw_json` silently swallows errors | Raw log import data loss (124/127 rows lost in one run) | ✅ Fixed 2026-04-28 |
| B-7 — Live migrations 002_layer2 + staging not committed to repo | Fresh install cannot reproduce live DB shape | 📘 Runbook landed; VPS exec pending |

### docs/UNUSED_DATA_OPPORTUNITIES.md

10 high-value datasets in the historical operational DB not yet wired to the catalog:
1. Chip-level failure prediction (2.6M rows in `log_metrics.chip_hashrate`)
2. PSU health trending (9.5M rows, voltage curves)
3. System health correlation (2.3M rows)
4. Board serial batch correlation (90 boards)
5. Pool rejection leading indicator (30.8K rows)
6. LLM drift detection (860 analyses)
7. Operator approval patterns (663 approvals)
8. Action effectiveness by model (857 actions)
9. Restart timing + HVAC correlation
10. Weather → hashrate correlation

Of these, items 1, 3, 4 are the highest ROI per the doc. All data is flowing; no schema changes needed to start using it.

### docs/REFINED_INSIGHTS_DESIGN.md

Refined insights is the "flagship feature" of the Grafana dashboard. Categories that require catalog enrichment to be complete:
- Chip quality (requires `hardware.chips` + `hardware.chip_bins` populated)
- PCB/BOM failure (requires board serial tracking in `hardware.hashboards`)
- PSU reliability (requires `hardware.psu_models` populated)
- Firmware insight (requires `firmware.firmware_releases` more fully populated)
- Error code patterns (requires `ops.miner_error_codes` populated)

### docs/DAILY_DEEP_DIVE_DESIGN.md

The daily deep dive reads `miner_hardware` for per-miner hardware identity including `chip_bin`, `pcb_version`. These fields in the operational DB are rich; the catalog currently doesn't have corresponding lookup tables populated to cross-reference against.

---

## Section 7: What "More Enrichment" Actually Means — Top 10 Gaps

Based on all docs read, ranked by how many systems depend on the missing data and how often it's cited as absent:

### Gap 1: ASIC Chip Types — `hardware.chips` (4 rows, should be 30+)

**Why it's #1:** The chip is the fundamental unit of ASIC analysis. Everything downstream — failure patterns, process node comparisons, chip bin yield analysis, thermal models — keys off the chip. The `hardware.miner_models.chip_id` FK is NULL for the vast majority of the 317 models because `hardware.chips` only has 4 entries (BM1398, BM1366, BM1397, KS3).

**What to add:** Every unique ASIC chip across all 288 model slugs: BM1362, BM1364, BM1366, BM1368, BM1397, BM1398, AT6600, AT7200, KS3, WM3, and all others. Fields: `chip_model`, `manufacturer_id`, `process_node`, `die_size_mm2`, `hash_algorithm`, `tdp_w`, `typical_frequency_mhz`.

**Fills:** `hardware.chips`, then allows `hardware.miner_models.chip_id` to be set for all models.

### Gap 2: Hashboard Count + Chips Per Board — `hardware.miner_models` columns

**Why it's #2:** The scan daemon uses hashboard count constantly (S19J Pro = 3 boards, AH3880 = 2 boards is a critical distinction). Currently only 41/288 (14%) of JSON entries have `hashboard_count` in specs; 9/288 (3%) have `chips_per_board`.

**What to add:** Populate `hardware.miner_models.hashboard_count` and `chip_count_per_board` for all 317 rows in Postgres. Source data is available in the enrichment CSV (`boards` inferred from `Distinguishing Features`) and from manufacturer spec sheets.

### Gap 3: PSU Types and Compatibility — `hardware.psu_models` (0 rows)

**Why it's #3:** PSU health is one of the 10 top unused data opportunities (9.5M voltage curve rows exist in operational DB). PSU compatibility is needed for safe autotune profiles. The `PSU Requirements` enrichment field is populated for most models in the CSV (e.g., "APW17; adapted output 4000 W") but none of this has been promoted to `hardware.psu_models`.

**What to add:** Extract PSU models from the enrichment CSV `PSU Requirements` column. Populate `hardware.psu_models` (model_name, output_power_w, efficiency_pct, input_voltage_range) and wire `hardware.psu_compatibility` (miner_model_id ↔ psu_model_id).

### Gap 4: Firmware Locations and Known-Good Versions — `firmware.firmware_releases` (6 rows)

**Why it's #4:** The firmware tracker runs daily but writes to JSON only. The catalog has 6 hardcoded firmware rows (Antminer/Whatsminer only). Braiins OS, Vnish, LuxOS, and Auradine firmware are completely absent. The `Firmware Support` column in the enrichment CSV is rich but not yet promoted.

**What to add:** For each of the 288 models: current stable stock firmware version + download URL, current Braiins OS support status + download URL, Vnish support + download URL, LuxOS support + download URL. Populate `firmware.firmware_releases` + `firmware.firmware_compatibility`.

### Gap 5: Model-Level Known Issues — `hardware.model_known_issues` (0 rows)

**Why it's #5:** Every enrichment entry has a `Known Issues` text field (e.g., "Hash board failures (EEPROM read errors, low hashrate); power/voltage errors; fan failures..."). None of this has been structured into `hardware.model_known_issues`. The scan daemon per D-14 should query this table before evaluating each miner — currently there's nothing there.

**What to add:** Parse `Known Issues` enrichment field for each model into structured rows: `miner_model_id`, `issue_type` (enum), `severity`, `description`, `affected_firmware`.

### Gap 6: Miner Error Codes — `ops.miner_error_codes` (0 rows)

**Why it's #6:** Bitmain, MicroBT, Canaan, and Auradine all have documented error code libraries. The `REFINED_INSIGHTS_DESIGN.md` explicitly lists "Error Code Patterns" as a refined insight category requiring this data. Currently zero records.

**What to add:** Seed common error codes for S19 series (chain comm failures, chip detection failures, PSU voltage errors, temp sensor failures, fan failures), S21 series, M5x series, and AH-series.

### Gap 7: Voltage Range + Frequency Range — `hardware.miner_models` columns

**Why it's #7:** The `Voltage Range` enrichment field is populated (e.g., "220-277 V AC") but `hardware.miner_models.voltage_min` and `voltage_max` are NULL for most rows. Frequency range is needed for tuning profiles. Source data is in the enrichment CSV.

**What to add:** Parse `Voltage Range` from enrichment CSV into `voltage_min`/`voltage_max`/`frequency_min`/`frequency_max` columns on `hardware.miner_models`. 277 models in CSV have this data.

### Gap 8: Release Date and EOL Date — `hardware.miner_models.release_date` (43/288 populated)

**Why it's #8:** Only 15% of JSON entries have a release date. The `Release Date (exact)` column is the most consistently populated enrichment field in the CSV. Release date drives depreciation schedules, EOL decisions, and procurement patterns.

**What to add:** Parse `Release Date (exact)` from enrichment CSV into `hardware.miner_models.release_date`. Also derive `is_current_product` (currently only 4/288 marked) from release date + market status.

### Gap 9: Immersion/Hydro/Air Compatibility — `hardware.cooling_compatibility` (0 rows)

**Why it's #9:** Bobby's fleet is mixed (air, hydro, immersion). The `cooling_compatibility` table would allow the system to know which models can be converted to immersion, which are native hydro, etc. The `Cooling Details` enrichment field has this info.

**What to add:** For each model in the enrichment CSV, parse `Cooling Details` into `hardware.cooling_compatibility` rows: `miner_model_id`, `cooling_type` (air/hydro/immersion), `is_native`, `conversion_kit_available`.

### Gap 10: Failure Patterns (Cross-Model) — `ops.failure_patterns` (0 rows)

**Why it's #10:** The scan daemon per D-14 must read `ops.failure_patterns` before evaluating any miner. Currently there are zero rows. The `REFINED_INSIGHTS_DESIGN.md` and the daily deep dive both depend on cross-model failure pattern matching. The `Known Issues` enrichment text has seeds for this.

**What to add:** Seed initial failure patterns from enrichment data: hashboard detection failures (affects S19/S21 models), PSU voltage instability patterns (affects multiple models), thermal shutdown patterns, chain communication errors.

---

## Section 8: Open Questions to Bring Back to the User

1. **Install retry date and sequence**: The 2026-05-01 install was aborted. The fix sequence in `INSTALLER_UX_BACKLOG_2026-05-01.md` requires 4-6 hours of PR work before re-attempt. What's the target date for the second install attempt?

2. **D-12 "Postgres-as-truth" naming collision**: DECISIONS.md D-12 is "documentation cadence." But `dual_writer.py` and other code files cite "D-12 (Postgres-as-truth, locked 2026-04-27)." These are different decisions with the same number. Should the dual_writer docstring be updated to reference D-14 (the live-reference architecture decision), or is there a separate unlisted Postgres-as-truth lock?

3. **Enrichment sweep wiring priority**: 3 of the 4 Layer 1 watchers (community, aggregator, firmware) and the Layer 3 deep enrichment sweep still write to JSON only. Which one should be wired to Postgres staging first? The manufacturer watcher is already wired as the template. Recommendation order: firmware tracker (most structured data), then aggregator, then community.

4. **chip_id back-fill approach**: `hardware.chips` has 4 rows but there are 30+ distinct chip types across the catalog. Should a human manually populate `hardware.chips` from the enrichment CSV/research, or should a one-time seed script extract chip models from the enrichment data and populate the table automatically?

5. **B-9 catalog count**: Multiple docs say 313 rows; actual is 320 after PR #102 (Bitaxe). Confirm the count and approve the search-replace PR to update CLAUDE.md, README.md, AI_ROADMAP.md, CAPABILITIES.md, CATALOG_ORPHAN_TABLES, and RUNBOOK_INSTALL_DAY.

6. **ACS repair shop dataset**: The James Scaggs/ACS 1M+ repair records dataset is referenced as future data for `repair.*` tables. Is this still expected? If yes, what's the delivery timeline? This affects whether `repair.*` tables should remain DEFER or be re-classified.

7. **`ops.failure_patterns` write ownership**: Per D-12, factory specs go in `hardware.*` and field-observed data goes in `market.war_stories` / `ops.failure_patterns`. But who writes to `ops.failure_patterns` — the watchers, the scan daemon, or a manual process? The table is DEFER per the orphan audit, but it's also cited as a critical scan-time lookup per D-14. Needs clarification.

8. **Staging → hardware.miner_models promotion**: The `dual_writer.py` promotion step (`promote_validated_miner_models()`) is "intentionally manual / batched so a human can review." Should this be automated (e.g., auto-promote proposals from a trusted source_tool like the manufacturer watcher), or always manual? The current design requires human intervention to get any watcher data into `hardware.*`.

9. **Catalog database name**: Some docs say `mining_guardian` (operational) and `intelligence_catalog` (reference) as separate databases; the setup.sh and seed-data README confirm both live in a single `mining_guardian` database under different schemas. Is there ever a plan to split them into separate database instances? (D-14 sub-lock 1 says "same Postgres 16 container," which implies no split.)

10. **63 unenriched slugs**: 63 of 288 slugs in `unified_miner_index.json` have no `enrichment` dict. These are presumably older or obscure models. Should a Perplexity enrichment run be queued to fill these gaps, and if so, what's the priority — depth (fill more fields per already-enriched model) or breadth (give basic enrichment to the 63 blank ones)?

---

## Read-Status Table

Every file opened in this session and a one-line summary of what it contains:

| Doc | Summary |
|---|---|
| `CLAUDE.md` | Master session rules, binding invariants, repo architecture overview, per-subsystem tour |
| `docs/DECISIONS.md` | 14 locked decisions D-1 through D-14; append-only ADR log |
| `intelligence-catalog/seed-data/intelligence_catalog_schema.sql` | Base PostgreSQL schema: 10 schemas, 63 tables, enums, triggers, indexes — the foundation |
| `intelligence-catalog/seed-data/intelligence_catalog_schema_v2_additions.sql` | Bobby's gap audit additions: PSU serials, chip bins, board serial batches, fan specs, psu voltage rails, model known issues, review summaries, control board serials, connector pinouts (9 tables) |
| `intelligence-catalog/seed-data/intelligence_catalog_schema_v3_additions.sql` | Exhaustive gap audit: field registry, unknown fields, raw ingestion log (partitioned), field discovery log, container/facility tables, immersion fluids, electricity rates, depreciation schedules, weather reference, LLM analysis patterns, miner baseline reference (14+ tables) |
| `intelligence-catalog/seed-data/README.md` | Canonical install order for the 3-file schema + seed; explains `\\ir` path agnosticism; schema layering summary |
| `intelligence-catalog/LIVING_CATALOG.md` | Five-layer auto-growing catalog architecture; tier system; 39 data points; file locations |
| `docs/INTELLIGENCE_CATALOG_STATUS.md` | Historical April 13–16 status snapshot; 165 tables, 1712+ columns, 226 models on ROBS-PC (all superseded by Mac Mini) |
| `docs/MONDAY_INTELLIGENCE_CATALOG_PLAN.md` | Historical plan for ROBS-PC Postgres (superseded); appendix has before/after comparison table |
| `docs/CATALOG_ORPHAN_TABLES_2026-04-28.md` | Comprehensive table-by-table classification: KEEP-WIRED / KEEP-SEEDED / DEFER / DROP for all 94 tables; sandbox row counts; appendix confirms every recommendation shipped |
| `docs/EMPTY_STUB_TABLES.md` | Historical VPS SQLite stub tables (chip_readings, miner_baselines, s19jpro_overheat_tracking); historical only |
| `intelligence-catalog/data/unified_miner_index.json` | 288 miner slugs; 225 with enrichment dicts; coverage analysis shows ~3–18% completeness on structured spec fields |
| `intelligence-catalog/data/miner_enrichment_master.csv` | 277 rows; 16 columns of text-format enrichment from Perplexity research sweeps; richest enrichment source currently |
| `intelligence-catalog/data/catalog_enrichment_tiers.json` | (existence confirmed via directory listing; not read deeply — contains tier assignments) |
| `intelligence-catalog/db/dual_writer.py` | D-12 Postgres-as-truth write contract: `propose_*` → staging tables → `promote_validated_*` → hardware.*; best-effort, payload dedup via SHA-256 hash |
| `docs/CRON_SCHEDULE.md` | Historical VPS cron schedule (9 jobs); LLM routing notes; now migrated to Mac Mini launchd |
| `docs/CRON_RECONCILIATION.md` | Historical VPS cron list vs Mac launchd; historical record only |
| `docs/MG_UNIFIED_TODO_LIST.md` | Master todo list: Section 4 is the catalog/database critical path; all C1–C5 items; LATENT_BUGS cross-refs |
| `docs/REMAINING_WORK_2026-04-28.md` | 4-bucket work queue as of 2026-04-28; Bucket 1 = D-14 5 PRs + high bugs; now partially historical |
| `docs/LATENT_BUGS.md` | 8 bugs B-1 through B-8; B-3/B-4/B-5 are data-ingestion issues; B-7 is missing migrations; all either fixed or runbooked |
| `docs/UNUSED_DATA_OPPORTUNITIES.md` | 10 unused operational datasets (historical VPS counts); chip-level, PSU, board serial, pool rejection are Tier 1 ROI |
| `docs/FINGERPRINTS_VS_PROFILES.md` | Explains miner_fingerprints (42 ML fields, weekly) vs miner_profiles (5 operational fields, per-scan) in knowledge.json |
| `docs/CONFIDENCE_SCORING.md` | Three-component scoring: miner history (60%), fleet history (25%), stability (15%); gates AUTO/ASK/HOLD at 80%/50%/threshold |
| `docs/DAILY_DEEP_DIVE_DESIGN.md` | Per-miner + fleet synthesis Qwen analysis at 4 PM daily; reads miner_hardware.chip_bin, pcb_version, etc.; 30-day rolling storage in knowledge.json |
| `docs/REFINED_INSIGHTS_DESIGN.md` | Flagship Grafana feature: permanent data-backed insights by hardware category; requires chip, PSU, error code, firmware catalog tables populated |
| `docs/INSTALLER_UX_BACKLOG_2026-05-01.md` | 10 bugs from aborted 2026-05-01 install; B-1 disk check, B-2 UX, B-13 Tahoe rejection (fixed v1.0.1); Mini in prepped state |
| `docs/VISION.md` | Canonical one-paragraph vision + 7 anchors + target architecture ASCII diagram + learning loop description |
| `docs/DECISIONS.md` | (already listed above) |
| `docs/AI_ROADMAP.md` | (found in directory list but not read deeply — superseded by VISION.md per file header) |
| `docs/ROADMAP_TO_MAC_MINI_2026-05-05.md` | (found in directory list; not read deeply — summary: day-by-day plan through Mac Mini install) |

---

*End of INTEL_CATALOG_FULL_BRIEF_2026-05-02.md*
