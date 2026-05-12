Mining Guardian — Two-Database Deep Dive

**MINING GUARDIAN**

**Two-Database Deep Dive**

*Operational DB (mining_guardian) and Intelligence Catalog (mining_guardian_catalog) — what each does, how they interact, and where the data flow stops short of full capability.*

**Scope**

Read-only analysis of the two-database architecture in the Mining Guardian repo as of May 9 2026. Covers schema responsibilities, the NOTIFY-driven feedback loop between operational and catalog, the four-times-daily Perplexity research feed, and the integration gaps where data is being captured but not consumed. Companion to Report 1 (Performance & Capability Audit). No code changes; reference material for Monday discussion.

# **Architecture at a Glance**

Mining Guardian runs against two physical Postgres databases inside a single Postgres 16 instance on the Mac Mini. Both databases share one server process, one set of tunables, and one connection ceiling. They are logically distinct, with separate schemas, separate writers, and separate read paths.

Per the planned monthly federation model, masters of both databases live on the operator's PC. Customer Mac Minis are derivatives. The monthly cycle is: push updated catalog from master to all sites, pull operational learnings from each site, merge centrally, push the merged catalog back out. This report assumes that model and treats the Mini's databases as production read/write replicas of the master rather than independent installations.

## **The Two Databases**

| **Aspect** | **Operational DB** | **Intelligence Catalog DB** |
| --- | --- | --- |
| **Database name** | mining_guardian | mining_guardian_catalog |
| **Role** | Runtime brain — what's happening right now | Reference brain — what's known about the world |
| **Schema(s)** | public.* (1 schema) | 9 schemas: hardware, firmware, ops, market, repair, pool, facility, regulatory, knowledge |
| **Approximate tables** | ~24 | ~95 |
| **Volume profile** | High insert rate (every scan); telemetry-heavy | Low insert rate; reference data with periodic enrichment |
| **Reachable via** | core.db_targets.operational_target() | core.db_targets.catalog_target() |
| **Recovery if lost** | Re-scan to rebuild ~24h of history | Months of curation; effectively irreplaceable |

## **How Each Database Feels Different**

The operational DB has the personality of a working foreman — it captures what just happened, correlates it briefly, and writes it down. Tables churn. Old rows lose value quickly. Indexes are tuned for time-window queries on the most recent N hours. Backups matter for incident reconstruction but not for the soul of the system.

The catalog DB has the personality of a research librarian — it accumulates carefully verified facts about the broader world of Bitcoin mining hardware. New rows are rare and considered. Old rows stay valuable for years. The schema reflects this: every table has soft-delete (deleted_at), every important row has a verified_by_bobby flag, search vectors are populated for fuzzy lookup, JSONB metadata captures everything that does not fit into typed columns. Losing the catalog means re-doing months of research and operator verification.

# **The Operational Database — mining_guardian**

This is the database I covered most heavily in Report 1. Recap of what is in it and what works versus does not.

## **What it does well**

- Captures every scan in scans, miner_readings, chain_readings, pool_readings, miner_state_readings, miner_ams_extended, miner_hardware, log_metrics, chip_readings — fourteen telemetry tables with sensible (miner_id, scanned_at) compound indexes.

- Tracks restart history with outcomes (miner_restarts) so the AI can score its own success rate. Outcomes feed the confidence_scorer module, which sets approval gates.

- Maintains a permanent action_audit_log with operator attribution — a paper trail you cannot fake. Critical for the trust model.

- Implements pending_approvals with a thread_ts index so Slack can resolve approve/deny against the right pending record.

- Has triggers (migration 003) that fire NOTIFY catalog_feedback on writes to the three tables that need cross-database aggregation. This is the foundation of the event-driven feedback loop covered later in this report.

## **Where it falls short individually**

These are the same items called out in Report 1, condensed:

- No psycopg2 connection pool — every database call opens a fresh connection (~5-15ms each, hundreds per scan).

- Timestamp comparisons routed through TO_CHAR string casts that defeat the planner.

- Postgres defaults assume a generous server; needs explicit tuning for 16GB shared with Ollama and nine services.

- No partitioning planned for high-churn timeseries tables; bites once data accumulates.

- No pgvector extension — semantic search over llm_analysis is not currently possible.

- Default autovacuum thresholds are too lax for high-churn miner_readings and log_metrics.

# **The Intelligence Catalog — mining_guardian_catalog**

This database is much better designed than the operational one. The schema author understood the problem — soft-delete columns everywhere, GIN indexes on JSONB metadata, gin_trgm_ops for fuzzy alias matching, range partitioning already in place on knowledge.raw_ingestion_log, search_vector columns on every text-rich table. This is a properly thought-through reference catalog. The issues are different in shape: a few maintenance gaps and a pattern of write-only tables where operational data flows in but no consumer reads it back out.

## **Schema overview by category**

| **Schema** | **Purpose** | **Read by AI?** |
| --- | --- | --- |
| **hardware** | Miner models (~317), chips, hashboards, PSU, control boards, aliases (12,852 Tier-1, 1,494 Tier-2) | Yes (miner_models, chips) |
| **firmware** | Firmware releases, compatibility, API capabilities, telemetry fields, bugs, changelogs, autotuning profiles | Yes (firmware_releases) |
| **ops** | Failure patterns, symptoms, thresholds, environmental correlations, alert rules, error codes | Partial (failure_patterns, thresholds) |
| **market** | User reviews, pricing history, manufacturer reputation, forum posts, teardowns, war stories | No — written but never read |
| **repair** | Parts, suppliers, repair procedures, repair shops, repair records, statistics | Yes (repair_procedures only) |
| **pool** | Mining pools, endpoints, stratum config, reliability history, incidents, BTC network snapshots | No |
| **facility** | Cooling solutions, PDUs, facilities, HVAC patterns, rack positions, immersion fluids, electricity rates, demand-response | No |
| **regulatory** | Frameworks, tax treatment, import/export, insurance, environmental regs | No |
| **knowledge** | Sources, contributors, citations, conflicts, freshness log, field registry, raw ingestion log, unknown fields | No |

## **Findings specific to the catalog**

### **Catalog issue 1 — knowledge.raw_ingestion_log partitions stop at 2027-Q1**

intelligence_catalog_schema_v3_additions.sql declares range partitions for 2026-Q1 through 2027-Q1. There is no pg_partman extension installed and no scheduled job to create future partitions. When 2027-Q2 arrives, every insert into raw_ingestion_log will fail with "no partition of relation raw_ingestion_log found for row." That is a year out, but the failure is silent until ingestion stops working.

Two acceptable resolutions: install pg_partman and let it auto-create partitions on a schedule, or add a quarterly cron that runs CREATE TABLE PARTITION OF for the next quarter. Either is small.

### **Catalog issue 2 — the staging.miner_model_proposals queue has no review surface**

catalog_updater.py --add-from-csv writes new model proposals into staging.miner_model_proposals. Promotion to hardware.miner_models requires you to run a manual command. There is no Slack notification when proposals pile up, no daily count in the morning briefing, no console listing. Proposals can accumulate indefinitely without you knowing they exist. Per the docs ("future console action") this is acknowledged.

### **Catalog issue 3 — knowledge.unknown_fields has the same problem**

When mg_import_tool ingests an archive and finds a field it does not recognize (a new firmware key, a new telemetry name), it stashes it in knowledge.unknown_fields with status='new'. There is even an index (idx_unknown_fields_new) for finding them quickly. But nothing surfaces them. The intent was clearly to drive an operator review queue. Without that queue exposed, they pile up unread.

### **Catalog issue 4 — search_vector populations may be incomplete**

The schema declares many GIN(search_vector) indexes — on knowledge.sources, hardware.miner_models, hardware.chips, hardware.psu_models, ops.failure_patterns, market.user_reviews, market.forum_posts, market.war_stories, repair.parts, repair.repair_procedures, repair.repair_shops, and others. These indexes work as expected only if a tsvector_update_trigger keeps the column populated on inserts and updates. A code-side audit suggests several tables initialize search_vector at seed time but never update it for subsequent rows. This means search works on initially-seeded data and silently misses later additions. Worth a one-time scan post-cutover to confirm which tables have the trigger and which need it added.

### **Catalog issue 5 — the catalog has roughly 180 indexes, some unused**

Index count across the three schema files is in the 180+ range. On a freshly-seeded catalog, harmless. Over time, every index slows writes proportionally. Two examples: market.user_reviews has both idx_reviews_pros and idx_reviews_cons as GIN indexes on JSONB array columns. If you are not doing pros/cons containment queries (and the codebase does not appear to), those indexes are pure overhead. Audit candidate for the second month, after pg_stat_statements has accumulated query data showing what is actually used.

# **How the Databases Talk to Each Other**

Two distinct paths connect operational and catalog. Both are good architectural decisions. Both are partially under-utilized.

## **Path A — Operational → Catalog (event-driven, working)**

migration 003 puts triggers on three operational tables that fire NOTIFY catalog_feedback on every insert. The feedback_loop_daemon, which runs as one of the nine launchd services, holds a LISTEN catalog_feedback connection in autocommit mode. When NOTIFY arrives, it debounces 100 milliseconds (so a burst of writes coalesces into one feedback run), then calls run_full_feedback_loop which performs three aggregations:

- public.action_audit_log → ops.failure_patterns (catalog) — failure modes derived from operator decisions

- public.llm_analysis → market.war_stories (catalog) — Bobby's operational experience accumulating as case studies

- public.miner_restarts → hardware.model_known_issues (catalog) — known-issue patterns by model

Each row written by this path is tagged with primary_source_id = 'a0000000-0000-0000-0000-00000000000f' (the bobby_operational seed source), making provenance auditable. End-to-end latency from operational write to catalog visibility is approximately 100ms. This is a textbook implementation of an event-sourced cross-database integration. It is the right pattern.

The two-connection split (P-018C) is also worth noting: each sync function opens an operational read connection AND a catalog write connection separately. The catalog write commits independently of the operational read. Clean transactional isolation between the two databases.

## **Path B — Catalog → AI (read-only at scan time, partial)**

ai/catalog_context.py reads the catalog whenever the AI builds a prompt. Concretely, the per-miner prompt-build step queries:

- hardware.miner_models — model spec

- hardware.chips — chip details

- firmware.firmware_releases — firmware family info

- ops.failure_patterns — known failure modes

- ops.operational_thresholds — per-model thresholds

- repair.repair_procedures — how-to-fix steps

Result is formatted into a prompt-context string and injected into Qwen and Claude prompts at scan time, daily deep dive, and weekly training (with caveats — see below). A circuit breaker (3 failures → open for 60s) prevents catalog issues from cascading into AI scan stalls. Good defensive design.

# **The Primary Integration Gap — Write-Only Catalog Tables**

This is the single largest unrealized value in the current architecture, and it is not a performance problem. It is a missing read path.

## **What the feedback loop writes that nobody reads**

Path A faithfully writes operational events into three catalog targets: ops.failure_patterns, market.war_stories, and hardware.model_known_issues. Path B (the AI reader) queries ops.failure_patterns. It does NOT query market.war_stories or hardware.model_known_issues.

In practice this means: every llm_analysis your system produces is being aggregated into a war story in the catalog, tagged as your story, indexed for search, ready to be cited. And no consumer reads it back. The data is being captured. It is just write-only right now.

Same with model_known_issues: every miner restart's outcome is being aggregated into a known-issue record. The catalog has soft-delete, commonality scoring, mitigation text. The AI never asks about it.

## **Other catalog data the AI never reads**

Beyond what the feedback loop writes, the catalog holds substantial reference data that the AI prompt-builder never touches:

- market.review_summaries, market.depreciation_schedules, market.resale_value_history — economics data Claude would benefit from when reasoning about repair-vs-scrap decisions.

- ops.environmental_correlations — table designed specifically to encode patterns like "this model degrades faster above ambient X." The hvac_correlator on the operational side could use these as inputs.

- hardware.chip_bins, hardware.psu_serial_batches, hardware.board_serial_batches — your fingerprint_builder is already collecting PCB/BOM data from miners. The catalog has reference rows for what those codes mean. Joining them would let the AI know "this miner's PCB=0110/BOM=0020 is a known bad batch" without re-learning it from scratch.

- repair.repair_records, repair.repair_statistics — operator-imported repair data. Currently consumable only via the catalog API, not via the AI prompt.

- facility.immersion_fluids, facility.electricity_rates, facility.demand_response_programs — relevant for fleet-wide synthesis prompts.

Rough estimate: approximately 60% of what the catalog stores is being written but not read. The data is already there, the connections are pooled (or will be once the connection pool lands), the read code is already calibrated for the catalog DB. Adding queries to ai/catalog_context.py::_fetch_miner_knowledge_pg is hours of work, not days.

## **Specific reads to add**

The highest-leverage small additions, ranked roughly by value:

- hardware.model_known_issues — joined on miner_model_id, filtered by deleted_at IS NULL and is_resolved=FALSE, ordered by bobby_experienced DESC. Returns the operator's actual experience with this model.

- market.war_stories — joined on tagged_model_ids array (the catalog uses ANY(tagged_model_ids)), or just is_bobby_story=TRUE for fleet-wide context. Most recent five.

- ops.environmental_correlations — joined on miner_model_id, filtered by current effective_to. Tells the prompt builder how this model interacts with the cooling type in use.

- hardware.chip_bins — joined on chip_id of the miner's chip. Tells the prompt builder whether this batch is a known winner or loser.

## **Pass 2 (weekly_train.py) does not read the catalog at all**

Worth calling out separately. Pass 2 is the Sunday Claude cohort training. It reads operational tables (miner_readings, action_audit_log, llm_analysis) and merges with knowledge.json. It does NOT query the catalog at any point.

That is a significant missed integration. Every Sunday Claude is asked to reason about the previous week's behavior with no awareness of the catalog's failure patterns, repair procedures, environmental correlations, or war stories. Pass 2 is the perfect place for catalog reads because it is the synthesis layer — it is where Claude is supposed to step back and pattern-match. Adding a small catalog-context section to the Pass 2 prompt would compound the value of the existing feedback loop investment.

# **The Perplexity Research Gap**

This section reflects a clarification from the operator: the four "Intel Catalog" scheduled tasks (Aggregator Watcher, Manufacturer Model Watcher, Firmware Tracker, Community Intel Scanner) run inside Perplexity's cloud, not inside Mining Guardian. They produce natural-language findings delivered to the operator's Perplexity inbox four times per day.

## **What the repo knows about these watchers**

Searching the entire codebase for any reference to those four watcher names or to "perplexity" yields zero hits in Python or shell. The repo is completely unaware that these scheduled tasks exist. The catalog schema includes tables that would naturally hold their findings (knowledge.sources, knowledge.citations, firmware.firmware_releases, knowledge.data_conflicts, knowledge.freshness_log) — but no code path delivers Perplexity output to those tables.

The 4:30 AM com.miningguardian.scheduled.catalog-import job looks for CSV files in cron_tracking/enrichment_sweep/ and finds nothing. Each morning it logs INFO no CSV files in .../enrichment_sweep — nothing to import and exits cleanly. core/discovery_sink.py:11 — a file added 2026-05-08 — explicitly documents this state: "cron_tracking/ is empty, no Perplexity watcher writes there."

## **Today's findings, mapped to where they should land**

Using the four findings produced this morning as concrete examples:

| **Watcher** | **Today's finding** | **Catalog target** |
| --- | --- | --- |
| **Aggregator** | S23e Hyd 2U release date discrepancy: Hashrate Index says Jan 1 2026, ASICMinerValue says Apr 2026 | knowledge.data_conflicts row |
| **Community Intel** | LuxOS now supports MicroBT WhatsMiner M50-series; M60/M60S planned | firmware.firmware_releases (multiple) + firmware.firmware_compatibility + firmware.firmware_api_capabilities |
| **Firmware Tracker** | No new SHA-256 firmware releases since 2026-05-06; 6 sources checked | knowledge.freshness_log row (verified-but-unchanged event) |
| **Manufacturer Model** | Would produce new model rows when manufacturers ship new SKUs | staging.miner_model_proposals (already wired) |

Of the four target paths, only one (staging.miner_model_proposals via dual_writer.propose_miner_model) is currently wired up. Three are not: there is no propose_data_conflict, no propose_firmware_release / propose_firmware_compatibility, no record_freshness_check function in dual_writer.py. The dual_writer module exposes only three propose functions today: propose_miner_model, propose_manufacturer, propose_alias.

## **Why the freshness gap matters more than it seems**

Without freshness logging, the system cannot distinguish between "Perplexity has not checked this category yet" and "Perplexity checked and found nothing." Today's Firmware Tracker finding is a verified-but-unchanged event — confirming six firmware vendor pages were inspected and no new releases were found. That is genuinely useful information. It tells the catalog "the firmware corpus is current as of this timestamp." Without that being recorded, the catalog cannot answer "how stale is our firmware data?" — which is the exact question the catalog was designed to answer (knowledge.freshness_log even has idx_freshness_due for this purpose).

The flip side: if Perplexity has an outage or your subscription lapses, the four scheduled tasks just stop. Mining Guardian has no signal of this. A morning-briefing line item — "did we hear from each of the four watchers in the last 36 hours?" — would catch a silent-failure within a day, regardless of whether the actual ingest is built.

## **Four ways to close the gap**

Ranked by effort and recommended last:

### **Option A — Manual paste (no code, status quo)**

Operator reads Perplexity output every morning, decides what to catalog, runs catalog_updater.py --add-model by hand. Lossy (you forget, you skip), freshness logs never land, doesn't scale to multi-site, depends entirely on manual discipline. This is what is happening today, by default.

### **Option B — Email or webhook bridge**

Build a small Mac Mini agent (~150 lines) that receives Perplexity findings either via webhook (Perplexity supports this for scheduled tasks) or via IMAP polling against a dedicated email folder. Routes each finding into the appropriate cron_tracking/<watcher>/ directory as JSON. The 4:30 AM catalog-import job picks them up — but only after dual_writer is extended to handle non-CSV finding shapes.

Pros: keeps Perplexity's research and saves cost on doing it locally. Cons: requires the watcher findings to land at a webhook URL the Mini can receive, which means either Tailscale Funnel or running the receiver during the transition window on the still-online VPS. Adds external infrastructure dependency.

### **Option C — Local LLM research replacement**

Skip Perplexity entirely. Stand up a local research loop on the Mini using the same Perplexity prompts (already documented in docs/PERPLEXITY_PROMPT_MINING_INTELLIGENCE_CATALOG.md) but routed through Claude or Qwen with web_search. Add a strict "respond ONLY in this JSON shape" instruction. Output goes directly to staging or to the new staging tables once dual_writer is extended.

Pros: removes external dependency entirely, fully aligned with Vision Anchor 7. Cons: requires extending the staging schema for non-model intake shapes, and Claude API costs may exceed Perplexity subscription depending on call volume. Less capable than Perplexity at aggregator-style web sweeps in some categories.

### **Option D — Slack /intel command (recommended)**

Add POST /api/catalog/intake to api/intelligence_report_api.py. Body: {event_type, payload, source}. Add a Slack slash command /intel that lets the operator paste a Perplexity finding directly:

/intel firmware "LuxOS now supports MicroBT WhatsMiner (initial M50-series variants; M60/M60S planned next), including thermal management, curtailment behavior, dynamic power targeting."

The Slack listener forwards to the API, which uses Claude with structure-extraction to convert the natural-language finding into the appropriate staging shape, writes it to staging, and posts a confirmation card back to Slack with an Approve/Reject button. Approve flips bobby_verified=TRUE the moment you confirm — collapsing "Perplexity said it" and "Bobby confirmed it" into one operator action.

Pros: zero workflow change for operator (you are already in Slack all day), keeps the operator-in-the-loop pattern that matches Vision Anchor 1, no external infrastructure dependencies, full audit trail. Cons: ~200 lines of new code plus a structure-extraction prompt that has to be reliable.

This is the recommended approach. It also has the side benefit of giving you a unified intake surface — you could later wire mg_import_tool or webhook agents to the same /api/catalog/intake endpoint without rebuilding the staging-write path.

# **Considerations for the Monthly Federation Model**

With masters living on the operator's PC and Mac Minis being derivative read/write replicas synced monthly, several catalog and operational mechanics deserve specific design attention. None require pre-cutover changes; raising them now so they inform the federation architecture conversations later.

### **Operational data does NOT federate**

Per-site telemetry (scans, miner_readings, miner_restarts, llm_analysis) is local to each site. It would be wasteful to push 18M+ rows of one site's miner readings to other sites. The right boundary is: catalog federates, operational does not. The aggregations the feedback_loop produces (failure_patterns, war_stories, model_known_issues) are the OPERATIONAL data that becomes catalog-shaped and should be included in the monthly push to master.

### **Conflict resolution on monthly merges**

When two sites both observe a known issue with model X and write feedback rows, the master's merge needs a strategy. Suggested model: catalog rows have a confidence score that climbs with multiple independent observations. Two sites independently reporting a PCB batch is bad raises confidence faster than one site reporting it twice.

The catalog already has primary_source_id; extending the merge to track sample counts (n_observations) and last_observed timestamp lets the master compute confidence-weighted truth across the fleet. The schema supports this — most catalog tables already have JSONB metadata where this can live without schema change.

### **Bobby's verification is the trump card**

Almost every catalog table has verified_by_bobby or is_bobby_review or bobby_experienced columns. The schema already encodes the principle that operator direct experience outranks any external source. The federation merge logic should respect this: a row with bobby_verified=TRUE should not be silently overwritten by a Perplexity scrape from another site.

### **Schema evolution across the fleet**

When the master schema gains a new column (say, you add a flux_capacitor_serial column to hardware.miner_models), every Mini in the field needs that column before the next push. Suggested approach: every monthly push begins with a schema-migration phase that runs any new migrations 0NN_*.sql files committed since the last sync, then proceeds to the data sync. This is exactly what the current migrations/ directory layout supports — there is just no orchestration around it yet.

### **The push-out window is a maintenance window**

During the monthly catalog push, the Mini's catalog reads must be either paused or routed at a snapshot. The simplest approach: take a brief lock, swap the entire catalog schema using a transaction (Postgres supports CREATE SCHEMA ... and rename atomically), commit. Reads resume against the new catalog. No data loss; brief read pause.

### **Operational learnings flowing back to master**

The pull side of the monthly cycle: each Mini has been writing into ops.failure_patterns, market.war_stories, and hardware.model_known_issues since the last sync. The master needs an efficient delta — "give me everything where last_modified > last_sync_timestamp." Most catalog tables already have updated_at; the ones that do not should add it as part of preparing for federation. This is a tiny migration.

# **Suggested Q****&****A Topics**

Open questions for Monday discussion:

- Confirm the master/site model: master DBs live on operator's PC, Minis are derivatives, monthly push/pull/merge cycle. Is that locked, or still being shaped?

- Of the four Perplexity-output integration options (manual, webhook bridge, local LLM replacement, Slack /intel command), which fits the workflow best? My recommendation is Slack /intel.

- Priority order for adding the missing AI catalog reads. model_known_issues and war_stories are the highest-value because the data is already being written. environmental_correlations is the highest-value where Pass 2 reads the catalog at all.

- Does Pass 2 weekly training get catalog awareness this cycle, or is it deferred? It is one of the largest single integration wins available.

- How are catalog backups handled relative to operational backups? Recommendation in Report 1 was to prioritize the catalog if only one can be set up immediately.

- Schema migration discipline: when the master gains a column, what triggers the corresponding migration on each Mini? Should the monthly push include automatic migration application?

- Federation merge conflict policy: when site A and site B disagree on a fact, who wins? Default suggestion is bobby_verified > sample_count > most_recent.

- Should staging.miner_model_proposals get a daily count posted to Slack, or wait for a proper review surface to be built?

- Catalog freshness — should the morning briefing report on age of last successful Perplexity-driven catalog update?

*End of report. Companion document: Mining Guardian — Performance **&** Capability Audit (Report 1).*

Page   ·  Prepared May 9, 2026