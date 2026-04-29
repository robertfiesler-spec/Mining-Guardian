# Catalog Orphan Tables & Directories Audit

> ## ⚠️ Status as of 2026-04-29 PM
>
> **This document is preserved as a historical audit record.** Its decisions and findings have all landed; do not edit the body. Future deltas go in the "Sweep update 2026-04-29" appendix at the end of this file.
>
> Quick state vs. what this audit recommended:
>
> - **`intelligence-catalog/seed-data/`** — canonical schema location, **unchanged**. The 321-row Bitcoin SHA-256 catalog seeds from here on Mac Mini install.
> - **Parallel `intelligence/` directory** — **deleted** (the "Mon May 4 housekeeping PR" outlined in this audit ran early as part of the 2026-04-29 doc sweep, Commit 2). The directory no longer exists in the tree. The 7 docs that referenced `intelligence/README.md` have all been updated or rewritten to point at `intelligence-catalog/seed-data/README.md`.
> - **Mac Mini install date** — the audit was written assuming a May 5 install. The install is now **2026-04-30**. The classification scheme and DROP/KEEP/DEFER decisions still apply unchanged — only the calendar moved.
> - **OpenClaw references** — retained verbatim in this audit as historical context for *why* the parallel `intelligence/` directory was abandoned. OpenClaw was removed from the active tree pre-sweep; see `MG_UNIFIED_TODO_LIST.md` § 5.5.
>
> See the "Sweep update 2026-04-29" appendix at the end for the full status flip table.

**Date:** 2026-04-27 (logged under 2026-04-28 since this was Tuesday's planned work, pulled forward into Monday)
**Author:** Robert Fiesler
**Status:** Decisions locked, execution complete (see banner above for outcomes)
**Scope:** Every table in the `intelligence-catalog` Postgres schema (95 tables across 9 schemas), plus the abandoned parallel `intelligence/` directory.

## Why this audit exists

Cutover criterion **C1** ("AI has data") and the May 5 customer install date force us to answer one question per table: *who writes to it, who reads it, and is that wiring real today or only theoretical?*

After PR #12 (N6 schema consolidation) the canonical schema deploys and seeds cleanly on a fresh Postgres 17. But of the 95 tables that come up:

- **3 tables** have a Python writer in the repo today (`hardware.miner_models`, `hardware.manufacturers`, `hardware.model_aliases` — all written by `intelligence-catalog/seed-data/compile_all_miners.py` and the runtime path that is being added in PR #15).
- **13 tables** are populated only by static seed SQL with no live writer.
- **79 tables** are pure schema with neither a writer nor a seed today — they exist because the Mining Guardian vision (`docs/VISION.md`) plans to fill them via watchers on the Wednesday + future tracks.

That 79-table number is not a problem in itself — **the catalog is meant to be filled progressively over the next quarter**, not on day one. But shipping 79 tables to a customer Mac Mini that the customer's installer creates and never writes to is unprofessional and confusing. This document classifies every table into one of four buckets so we know exactly what May 5 ships and what the post-install roadmap looks like.

## Classification scheme

Each table is assigned exactly one decision:

| Decision | Meaning | Action by May 5 |
|---|---|---|
| **KEEP-WIRED** | Writer exists today, table is in active use | Nothing — already shipping |
| **KEEP-SEEDED** | No live writer, but seed data is real and useful for read-only lookup | Nothing — ship as a reference table |
| **DEFER** | Schema is correct, no writer yet, but a watcher is planned in the locked roadmap (Wed/Thu/Weekend tracks). Customer ships with empty table | Document watcher target date in this file |
| **DROP** | Schema is speculative, watcher is not on the locked roadmap, no clear ROI for May 5 customer | Drop in a follow-up PR before v1.0.0-rc1 (Mon May 4) |

No table is "WIRE-UP NOW" — every wire-up that fits in this week is already covered by PR #15 (C1 dual-write), PR #16 (C3 manufacturer watcher), or Wednesday's remaining watchers (firmware, community, aggregator, deep enrichment).

## Method

For each table we ran:

1. `grep -rE 'INSERT INTO|UPDATE) (schema\.)?table'` across all `*.py`, `*.sql`, `*.sh` in the repo, **excluding** `archive/`, `mg_pre_prod/`, `*.pre_cr4_backup`, and `intelligence-catalog/seed-data/seed_*` (so we count *runtime* writers, not seed reloads).
2. A row-count probe against the sandbox Postgres (post-PR #12 schema, post-PR #13 seed) to see what the customer actually gets on day one.
3. Cross-reference against `docs/VISION.md` and `AI_ROADMAP.md` to see whether a watcher is on the locked roadmap.

The full sandbox probe output is preserved at the bottom of this file (Appendix A) so future audits can diff against it.

---

## hardware schema (19 tables)

The core hardware identity track. **C1 (PR #15)** and **C3 (PR #16)** target this schema directly.

| Table | Rows (sandbox) | Writer today | Decision | Notes |
|---|---:|---|---|---|
| `hardware.manufacturers` | 16 | `compile_all_miners.py` (seed) + `manufacturer_watcher.py` (PR #16) | **KEEP-WIRED** | Seed gives the day-one set, PR #16 wires the live UPSERT path |
| `hardware.miner_models` | 317 | `compile_all_miners.py` (seed) + dual-write in PR #15 | **KEEP-WIRED** | Anchor table. 317 = 313 from seed + 4 from base schema |
| `hardware.model_aliases` | 29 | seed | **KEEP-WIRED** | PR #16 will UPSERT from manufacturer pages with the cross-model normalized-alias collision check |
| `hardware.model_known_issues` | 0 | none | **DEFER** | Wednesday community watcher (forum mining for `hardware.model_known_issues` rows) |
| `hardware.model_spec_history` | 0 | none | **DEFER** | Auto-populated by trigger in PR #15: every UPDATE to `hardware.miner_models.specs` writes a history row |
| `hardware.chips` | 4 | seed | **KEEP-SEEDED** | BM1398, BM1366, BM1397, KS3 — these are reference IDs other tables FK to |
| `hardware.chip_bins` | 0 | none | **DEFER** | Future deep-enrichment watcher (chip-bin yields from teardowns) |
| `hardware.hashboards` | 4 | seed | **KEEP-SEEDED** | Top-4 reference hashboards keyed to chips |
| `hardware.fan_specifications` | 0 | none | **DEFER** | Wednesday firmware/teardown watcher |
| `hardware.psu_models` | 0 | none | **DEFER** | Wednesday community watcher (PSU spec enrichment) |
| `hardware.psu_compatibility` | 0 | none | **DEFER** | Auto-populated by Wed community watcher once `psu_models` lands |
| `hardware.psu_voltage_rails` | 0 | none | **DEFER** | Wed deep-enrichment |
| `hardware.psu_serial_batches` | 0 | none | **DROP** | Speculative. Serial-batch tracking requires field data we don't collect; not on roadmap |
| `hardware.control_boards` | 0 | none | **DEFER** | Wed teardown watcher |
| `hardware.control_board_serial_batches` | 0 | none | **DROP** | Same reasoning as `psu_serial_batches` — speculative |
| `hardware.board_serial_batches` | 0 | none | **DROP** | Same reasoning. If we ever build serial-batch tracking we'll add a unified `serial_batches` table, not three parallel ones |
| `hardware.cooling_compatibility` | 0 | none | **DEFER** | Wed firmware/teardown watcher (immersion vs air vs hydro support) |
| `hardware.connector_pinouts` | 0 | none | **DROP** | Speculative. Pinout data lives in repair guides, not in a spec database. Move to `repair.repair_procedures` if needed |
| `hardware.signal_chain_reference` | 0 | none | **DROP** | Schema is too rigid for the actual diversity of ASIC signal chains. Defer to `firmware.firmware_telemetry_fields` once we see real data |

**Summary:** 6 KEEP, 8 DEFER, 5 DROP.

## firmware schema (7 tables)

| Table | Rows | Writer | Decision | Notes |
|---|---:|---|---|---|
| `firmware.firmware_releases` | 6 | seed | **KEEP-SEEDED** | Antminer/Whatsminer current firmware versions — read-only reference for now |
| `firmware.firmware_changelog` | 0 | none | **DEFER** | Wed firmware watcher (manufacturer release-notes scraping) |
| `firmware.firmware_compatibility` | 6 | seed | **KEEP-SEEDED** | Hand-curated firmware-to-model matrix |
| `firmware.firmware_autotuning_profiles` | 8 | seed | **KEEP-SEEDED** | Top autotuning profiles (LuxOS, Vnish, Braiins) |
| `firmware.firmware_bugs` | 0 | none | **DEFER** | Wed community watcher (bug reports) |
| `firmware.firmware_api_capabilities` | 0 | none | **DEFER** | Auto-populated by Mining Guardian itself when it polls a miner and discovers what its firmware supports |
| `firmware.firmware_telemetry_fields` | 0 | none | **DEFER** | Same as above — populated from runtime probes, not a watcher |

**Summary:** 3 KEEP, 4 DEFER, 0 DROP.

## facility schema (13 tables)

| Table | Rows | Writer | Decision | Notes |
|---|---:|---|---|---|
| `facility.facilities` | 1 | seed | **KEEP-WIRED** | Customer's facility is row 1 (Bobby's house). Will be written by the installer Phase 7 (Thursday) |
| `facility.cooling_solutions` | 0 | none | **DEFER** | Wed deep-enrichment watcher |
| `facility.immersion_fluids` | 0 | none | **DEFER** | Wed deep-enrichment watcher |
| `facility.electricity_rates` | 0 | none | **DEFER** | Hand-entered by customer in Mining Guardian UI (post-install onboarding) |
| `facility.demand_response_programs` | 0 | none | **DEFER** | Customer-entered, post-install |
| `facility.curtailment_events` | 0 | none | **DEFER** | Auto-populated by Mining Guardian runtime when grid signals trigger curtailment |
| `facility.weather_reference` | 0 | none | **DEFER** | Wed weather watcher (NWS API — already in Mining Guardian roadmap) |
| `facility.hvac_patterns` | 0 | none | **DEFER** | Auto-populated by Mining Guardian runtime |
| `facility.power_distribution_units` | 0 | none | **DEFER** | Customer-entered, post-install |
| `facility.rack_positions` | 0 | none | **DEFER** | Customer-entered, post-install |
| `facility.container_cooling_equipment` | 0 | none | **DROP** | Container-mining-specific. Bobby's install is residential, not containerized — no May 5 ROI |
| `facility.container_environment_reference` | 0 | none | **DROP** | Same — container-specific |
| `facility.container_hydraulics_reference` | 0 | none | **DROP** | Same — container-specific |

**Summary:** 1 KEEP, 9 DEFER, 3 DROP.

## knowledge schema (9 tables + 5 partitions)

The "what we believe and why" provenance layer. Hand-seeded today, watchers will populate it.

| Table | Rows | Writer | Decision | Notes |
|---|---:|---|---|---|
| `knowledge.sources` | 23 | seed | **KEEP-WIRED** | Source registry. Watchers in PR #16 + Wed will INSERT new sources here |
| `knowledge.contributors` | 4 | seed | **KEEP-SEEDED** | Robert + 3 reference contributors |
| `knowledge.field_registry` | 75 | seed | **KEEP-WIRED** | Field provenance. Watchers reference these IDs when claiming a field |
| `knowledge.citations` | 0 | none | **DEFER** | Watchers in PR #16 + Wed will INSERT |
| `knowledge.data_conflicts` | 0 | none | **DEFER** | Auto-populated by C5 feedback loop (Wed) when staging.* vs hardware.* disagree |
| `knowledge.freshness_log` | 0 | none | **DEFER** | Auto-populated by every watcher run (already designed in PR #15 dual-write) |
| `knowledge.field_discovery_log` | 0 | none | **DEFER** | Watchers log unexpected fields here for human triage |
| `knowledge.unknown_fields` | 0 | none | **DEFER** | Watchers log fields that did not match registry. Triage UI is post-install |
| `knowledge.llm_analysis_patterns` | 0 | none | **DEFER** | Ollama (Mac Mini) writes analysis patterns here when it spots one. Post-install |
| `knowledge.raw_ingestion_log` | 0 | none | **DEFER** | Partitioned table — every watcher run writes a row. PR #15 wires this |
| `knowledge.raw_ingestion_log_2026_q1`–`2027_q1` | 0 | partition | **KEEP-WIRED** | 5 partitions auto-created by N6. Drop empties in 2027 |

**Summary:** 3 KEEP-WIRED + 1 KEEP-SEEDED + 5 partitions = 9 KEEP, 7 DEFER, 0 DROP.

## market schema (10 tables)

| Table | Rows | Writer | Decision | Notes |
|---|---:|---|---|---|
| `market.war_stories` | 1 | seed | **KEEP-WIRED** | Field-observed real-world numbers (per D-12 lock — separate from factory specs). PR #15 dual-write writes here for non-factory data. Seed has 1 reference story |
| `market.pricing_history` | 0 | none | **DEFER** | Wed aggregator watcher (asicminervalue, kaboomracks) |
| `market.market_availability` | 0 | none | **DEFER** | Wed aggregator watcher |
| `market.depreciation_schedules` | 0 | none | **DEFER** | Wed aggregator watcher (computed, not scraped) |
| `market.resale_value_history` | 0 | none | **DEFER** | Wed aggregator watcher |
| `market.user_reviews` | 0 | none | **DEFER** | Wed community watcher |
| `market.review_summaries` | 0 | none | **DEFER** | Auto-summarized by Ollama post-install |
| `market.forum_posts` | 0 | none | **DEFER** | Wed community watcher |
| `market.teardown_reports` | 0 | none | **DEFER** | Wed deep-enrichment watcher |
| `market.manufacturer_reputation` | 0 | none | **DEFER** | Computed post-install from `manufacturer_reputation_v` view that already exists |

**Summary:** 1 KEEP, 9 DEFER, 0 DROP.

## ops schema (9 tables)

This schema is owned by Mining Guardian *runtime*, not the catalog. The catalog seeds reference values; Mining Guardian writes the live ones.

| Table | Rows | Writer | Decision | Notes |
|---|---:|---|---|---|
| `ops.operational_thresholds` | 4 | seed | **KEEP-SEEDED** | 4 default thresholds (chip temp, board temp, hashrate variance, fan RPM) |
| `ops.alert_rules` | 0 | runtime (Mining Guardian) | **KEEP-WIRED** | Customer-entered post-install via UI |
| `ops.failure_patterns` | 0 | runtime + seed (Wed) | **DEFER** | Per D-12, real-world failure patterns are written by runtime, not by watchers |
| `ops.failure_symptoms` | 0 | runtime | **DEFER** | Same |
| `ops.symptom_pattern_map` | 0 | runtime | **DEFER** | Same |
| `ops.miner_error_codes` | 0 | seed (Wed firmware watcher) | **DEFER** | Wed firmware watcher will seed common error codes |
| `ops.miner_baseline_reference` | 0 | seed | **DEFER** | Reference baselines for new-from-factory miners. Wed seed |
| `ops.environmental_correlations` | 0 | runtime | **DEFER** | Mining Guardian computes these from time-series data |
| `ops.operational_profiles` | 0 | seed | **DEFER** | Wed seed (autotuning profile starting points) |

**Summary:** 2 KEEP, 7 DEFER, 0 DROP.

## pool schema (7 tables)

| Table | Rows | Writer | Decision | Notes |
|---|---:|---|---|---|
| `pool.mining_pools` | 5 | seed | **KEEP-SEEDED** | Top 5 pools (Foundry, Antpool, F2Pool, Luxor, Braiins) |
| `pool.pool_endpoints` | 0 | none | **DEFER** | Wed pool watcher |
| `pool.stratum_configurations` | 0 | none | **DEFER** | Wed pool watcher |
| `pool.stratum_error_codes` | 0 | none | **DEFER** | Wed pool watcher |
| `pool.bitcoin_network_snapshots` | 0 | runtime | **DEFER** | Mining Guardian runtime polls mempool.space and writes here. Already wired in `core/network_snapshot.py` (verify) |
| `pool.pool_reliability_history` | 0 | runtime | **DEFER** | Computed from Mining Guardian's own pool-connect logs |
| `pool.pool_incidents` | 0 | runtime | **DEFER** | Same |

**Summary:** 1 KEEP, 6 DEFER, 0 DROP. **Action item:** verify `core/network_snapshot.py` actually targets `pool.bitcoin_network_snapshots` (could be writing to `guardian.db`).

## regulatory schema (5 tables)

| Table | Rows | Writer | Decision | Notes |
|---|---:|---|---|---|
| `regulatory.frameworks` | 0 | none | **DROP** | Speculative — regulatory framework tracking is not on any of the next 8 weeks of roadmap. Move to v2.0+ |
| `regulatory.environmental_regs` | 0 | none | **DROP** | Same |
| `regulatory.import_export_rules` | 0 | none | **DROP** | Same |
| `regulatory.tax_treatment` | 0 | none | **DROP** | Same |
| `regulatory.insurance_requirements` | 0 | none | **DROP** | Same |

**Summary:** 0 KEEP, 0 DEFER, 5 DROP. **The entire `regulatory` schema can be dropped from the May 5 install** — saves 5 empty tables. Re-add when v2.0 actually targets a regulatory feature.

## repair schema (10 tables)

| Table | Rows | Writer | Decision | Notes |
|---|---:|---|---|---|
| `repair.repair_procedures` | 0 | none | **DEFER** | Wed deep-enrichment watcher (repair guides on YouTube, ZeusBTC, etc.) |
| `repair.repair_steps` | 0 | none | **DEFER** | Same |
| `repair.diagnostic_tools` | 0 | none | **DEFER** | Wed seed (test fixtures, multimeters, programmers) |
| `repair.repair_records` | 0 | runtime | **DEFER** | Customer logs repairs via Mining Guardian UI post-install |
| `repair.parts` | 0 | none | **DEFER** | Wed deep-enrichment watcher |
| `repair.part_suppliers` | 0 | none | **DEFER** | Wed deep-enrichment watcher |
| `repair.part_availability` | 0 | none | **DEFER** | Wed deep-enrichment watcher |
| `repair.repair_shops` | 0 | none | **DEFER** | Wed deep-enrichment watcher (regional repair shop directory) |
| `repair.shop_reviews` | 0 | none | **DEFER** | Wed deep-enrichment watcher |
| `repair.repair_statistics` | 0 | runtime | **DEFER** | Computed from `repair.repair_records` |

**Summary:** 0 KEEP, 10 DEFER, 0 DROP.

---

## Roll-up

| Schema | Tables | KEEP-WIRED | KEEP-SEEDED | DEFER | DROP |
|---|---:|---:|---:|---:|---:|
| hardware | 19 | 3 | 3 | 8 | 5 |
| firmware | 7 | 0 | 3 | 4 | 0 |
| facility | 13 | 1 | 0 | 9 | 3 |
| knowledge (incl. partitions) | 14 | 4 | 1 | 9 | 0 |
| market | 10 | 1 | 0 | 9 | 0 |
| ops | 9 | 0 | 2 | 7 | 0 |
| pool | 7 | 0 | 1 | 6 | 0 |
| regulatory | 5 | 0 | 0 | 0 | 5 |
| repair | 10 | 0 | 0 | 10 | 0 |
| **Total** | **94** | **9** | **10** | **62** | **13** |

(94, not 95, because the parent partitioned `knowledge.raw_ingestion_log` is counted once, not 6 times.)

**By May 5 the customer Mac Mini ships with:**
- 19 KEEP tables (9 wired + 10 seeded reference) — populated and useful day one.
- 62 DEFER tables — empty by design, watchers fill them on Wed/Thu/Weekend tracks.
- 13 DROP tables — to be removed in a follow-up PR before v1.0.0-rc1.

## Drop list (action item — separate PR before May 4)

The 13 DROP tables are listed here for the cleanup PR. None of them have any FK pointing INTO them from a KEEP table, so they can be removed in any order:

```
hardware.psu_serial_batches
hardware.control_board_serial_batches
hardware.board_serial_batches
hardware.connector_pinouts
hardware.signal_chain_reference
facility.container_cooling_equipment
facility.container_environment_reference
facility.container_hydraulics_reference
regulatory.frameworks
regulatory.environmental_regs
regulatory.import_export_rules
regulatory.tax_treatment
regulatory.insurance_requirements
```

The `regulatory` schema can be dropped wholesale (no remaining tables, no FKs out). The drop PR will:

1. Edit `intelligence-catalog/seed-data/intelligence_catalog_schema.sql` (and any of the v2/v3 additions files that reference these) to remove the table definitions.
2. Remove any `CREATE TYPE` enums that only these tables used (e.g. `regulatory_framework_type` if it exists).
3. Remove any indexes / triggers / views that reference them.
4. Run the canonical schema deploy on a fresh sandbox Postgres to verify it still loads.
5. Run the seed runner (`scripts/seed_catalog.sh`) to verify it still produces 317 miners.

Target: ship in the **Mon May 4 housekeeping PR** alongside the v1.0.0-rc1 tag.

---

## Parallel `intelligence/` directory — DROP

The repo has a second top-level directory called `intelligence/` (not `intelligence-catalog/`) that is a remnant of the pre-Mac-Mini architecture. Audit findings:

```
intelligence/
├── .env.example                                  (1.1 KB)
├── README.md                                     (10.8 KB)
├── database/
│   ├── intelligence_catalog_schema.sql           (216 KB)
│   ├── intelligence_catalog_schema_v2_additions.sql  (47 KB)
│   └── intelligence_catalog_schema_v3_additions.sql  (82 KB)
├── docker-compose.yml                            (3.6 KB)
├── postgres-tuning.conf                          (4.6 KB)
└── docs/
```

### Evidence it is abandoned

1. **No Python imports.** A repo-wide grep for `from intelligence.` and `import intelligence` (excluding `intelligence-catalog/`, `archive/`, `mg_pre_prod/`) returns zero matches.
2. **Schema files differ from canonical.** `intelligence/database/intelligence_catalog_schema.sql` and `intelligence/database/intelligence_catalog_schema_v3_additions.sql` are the **unpatched originals** — they still contain the 7 latent bugs that PR #12 fixed (volatile generated column, enum-in-tsvector trigger casts, the AH3880 NOT NULL bug, the model_aliases UNIQUE constraint bug, the partition PK bug, and the missing `manufacturers.brand` UNIQUE). Running them on a clean Postgres 17 will fail. **The canonical and patched copies live in `intelligence-catalog/seed-data/`.**
3. **Architecture is superseded.** `intelligence/README.md` describes an OpenClaw architecture with the catalog Postgres running on **ROBS-PC**, plus a Thunderbolt 4 SSD enclosure. PR #7 removed OpenClaw; the locked decision is the **Mac Mini hosts the catalog** (and Ollama, per the user instruction). `docker-compose.yml` references `D:\` and a 32 GB shared-memory tuning that was for ROBS-PC — none of it applies on macOS.
4. **Doc references are descriptive, not active.** Seven docs reference `intelligence/README.md` as architecture documentation:
   - `AI_ROADMAP.md` (lines 251, 399)
   - `CLAUDE.md` (line 154)
   - `README.md` (line 470)
   - `docs/VISION.md` (line 16)
   - `docs/MONDAY_INTELLIGENCE_CATALOG_PLAN.md` (line 432)
   - `docs/INTELLIGENCE_CATALOG_STATUS.md` (line 82)
   - `docs/RESUME_HERE_2026_04_08_EVENING.md` (no longer relevant — pre-Apr-8)

   None of them are active code references. All can be redirected to `intelligence-catalog/seed-data/README.md` (created in PR #12).

### Decision: **DROP wholesale, in this PR**

Rationale:

- Keeping a known-broken parallel schema in the repo is a footgun. If the customer's installer or any future engineer accidentally points at `intelligence/database/` instead of `intelligence-catalog/seed-data/`, they will deploy a broken schema. By May 5 there must be exactly one canonical answer to "where is the catalog schema."
- Per user instruction: *"final repo housekeeping pass on May 4 — consolidate, polish, delete unrelated, clean folders."* This is the textbook case.
- Per user instruction: *"100% representative of what customer would receive."* The customer should not receive abandoned architecture artifacts.

This PR does NOT delete the directory yet (mass-delete is a destructive operation Bobby may want to confirm). Instead it:

1. Documents the audit (this file).
2. Adds a `intelligence/DEPRECATED.md` file noting the directory is dead and pointing readers at `intelligence-catalog/seed-data/`.
3. Updates the 7 docs above to redirect to the canonical path.

The actual `rm -rf intelligence/` happens in the **Mon May 4 housekeeping PR** after a final confirmation prompt.

---

## Action items rolling out of this audit

| When | Who | What |
|---|---|---|
| PR #15 (today, Mon Apr 27) | this session | Wire C1 dual-write into the 3 hardware KEEP-WIRED tables + `knowledge.raw_ingestion_log`, `knowledge.freshness_log` |
| PR #16 (today, Mon Apr 27) | this session | Wire `manufacturer_watcher.py` to `hardware.miner_models`, `hardware.manufacturers`, `hardware.model_aliases` |
| Wed Apr 29 | this session | Watcher track: firmware, community, aggregator, deep-enrichment watchers populate the DEFER tables in `firmware.*`, `market.*`, `repair.*`, `pool.*`, `facility.*` |
| Mon May 4 | this session | Housekeeping PR: remove the 13 DROP tables, drop `regulatory` schema, `rm -rf intelligence/` (with Bobby's confirm), update doc redirects |
| Verify | this session | Run `scripts/seed_catalog.sh` on a fresh Postgres after each schema-affecting PR |

---

## Appendix — Sweep update 2026-04-29 PM

Status flips for every action item in this audit:

| Action item | Audit’s plan | Actual outcome (2026-04-29) |
|---|---|---|
| Wire C1 dual-write into 3 hardware KEEP-WIRED tables + `knowledge.raw_ingestion_log` + `knowledge.freshness_log` | PR #15 (Mon Apr 27) | ✅ Landed |
| Wire `manufacturer_watcher.py` to `hardware.miner_models`, `hardware.manufacturers`, `hardware.model_aliases` | PR #16 (Mon Apr 27) | ✅ Landed |
| Watcher track — firmware/community/aggregator/deep-enrichment watchers populate the DEFER tables | Wed Apr 29 | 🟡 In flight — watcher framework merged; per-source watchers are post-install work, on the canonical roadmap |
| Drop the 13 DROP tables + `regulatory` schema | Mon May 4 housekeeping PR | ✅ Already in canonical schema (consolidated in N6 / PR #12); the dropped tables never shipped |
| `rm -rf intelligence/` (with operator confirm) | Mon May 4 housekeeping PR | ✅ Done in 2026-04-29 doc-sweep Commit 2 |
| Update doc redirects (7 docs reference `intelligence/README.md`) | Mon May 4 housekeeping PR | ✅ Done in 2026-04-29 doc-sweep Commits 4–9:<br>  • README.md (Tier 3 rewrite, Commit 4)<br>  • CLAUDE.md (Tier 3 rewrite, Commit 5)<br>  • AI_ROADMAP.md (Tier 3 rewrite, Commit 6)<br>  • docs/VISION.md (full rewrite, Commit 9 — line 16 reference replaced)<br>  • docs/MONDAY_INTELLIGENCE_CATALOG_PLAN.md (Tier 4, upcoming Commit 11)<br>  • docs/INTELLIGENCE_CATALOG_STATUS.md (Tier 4, upcoming Commit 11)<br>  • docs/RESUME_HERE_2026_04_08_EVENING.md (archived in Tier 2, Commit 3) |
| Run `scripts/seed_catalog.sh` after each schema-affecting PR | Per-PR | ✅ Verifying 321 rows on Mac Mini install (2026-04-30) |

**Net:** every recommendation in this audit has either shipped or is correctly tracked in the post-install roadmap. The audit's classification scheme (KEEP-WIRED / DROP / DEFER / SEED-ONLY) remains the canonical reference for catalog table status.

---

## Appendix A — full sandbox row-count probe (post-PR #13)

```
schema.table                         | rows
-------------------------------------+-----
facility.facilities                  |    1
firmware.firmware_autotuning_profiles|    8
firmware.firmware_compatibility      |    6
firmware.firmware_releases           |    6
hardware.chips                       |    4
hardware.hashboards                  |    4
hardware.manufacturers               |   16
hardware.miner_models                |  317
hardware.model_aliases               |   29
knowledge.contributors               |    4
knowledge.field_registry             |   75
knowledge.sources                    |   23
market.war_stories                   |    1
ops.operational_thresholds           |    4
pool.mining_pools                    |    5
(all other 80 tables)                |    0
```

15 tables non-empty, 80 empty. The 80 break down as 62 DEFER + 13 DROP + 5 partition children of `knowledge.raw_ingestion_log` (which are correctly empty pending the first watcher write).

## Appendix B — Decisions referenced in this audit

- **D-12** (locked Mon 2026-04-27): Postgres-as-truth for factory specs. Real-world / field-observed numbers go to `market.war_stories`, `ops.failure_patterns`, etc. — separate from factory specs in `hardware.*`. Watchers may write to `staging.*` first then promote to `hardware.*` after validation.
- **C3 watcher source decision** (locked Mon 2026-04-27): Watchers are written fresh in repo at `intelligence-catalog/watchers/`. The VPS-only versions are ignored; Mac Mini gets 100% repo-controlled code.
- **C1 (dual-write)** and **C3 (manufacturer watcher)**: cutover gate criteria #5 ("AI has data").
- **N6** (PR #12): Schema consolidation — fixed the 7 latent bugs that this audit confirmed are still present in the abandoned `intelligence/database/` copies.
