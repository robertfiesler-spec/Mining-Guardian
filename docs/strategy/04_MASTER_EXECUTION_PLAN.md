Mining Guardian — Master Execution Plan

**MINING GUARDIAN**

**Master Execution Plan**

*B+ to A+ in six phases*

*Derived from Reports 1, 2, and 3. Twenty-two work items in dependency order, each with files, scope, verification, and definition of done. Designed to be picked up one item at a time and worked through in sequence.*

# **How to Use This Document**

This is the working plan, not another report. The three audit reports describe the system; this document describes what to do about it. Each work item is structured the same way:

- ID and title — short reference for the item, used for tracking.

- Source — which report(s) the item came from, so the rationale can be re-read in context.

- Effort — t-shirt-sized: XS (under an hour), S (under a day), M (one to three days), L (one to two weeks).

- Risk — Low, Medium, or High in terms of what could break in production.

- Blocked by — items that must complete first, when applicable.

- Files — concrete paths in the repo so there is no hunting.

- What to do — the change, in plain language.

- Why now — the dependency or sequencing rationale for this phase.

- How to verify — how to know it works.

- Definition of done — the exit criterion for the item.

Items are numbered globally (W01 through W22) so you can reference them in commit messages, Slack threads, and chat with future Claude sessions: "working on W08 today" is unambiguous.

## **Three principles before starting**

These are the operating rules for the whole plan, not just any one phase:

- Reversible before irreversible. If a change can be cleanly reverted with git, it is safer than one that requires a database migration to undo. Within a phase, do the easy reverts first to build confidence before committing to bigger ones.

- Stay in one code area as long as possible. Context-switching between core/database_pg.py and ai/catalog_context.py and api/intelligence_report_api.py costs mental load. When you are in the prompt-builder, do all the prompt-builder work.

- Always have one between-batches task ready. Some days you do not have the headspace for the big refactor. On those days, pick up an XS item and keep momentum without requiring deep focus.

## **How to track progress**

Suggested approach. Create a short tracking file in the repo at docs/EXECUTION_PLAN_STATUS.md. Each line is:

W03  Postgres connection pool          [X]  2026-05-13  commit abc1234

Updated as items complete. Replaces the chaos of trying to remember what is done. Future Claude sessions can read this file to know where you are without having to ask.

# **Plan at a Glance**

| **Phase** | **Items** | **Timeframe** | **End state** |
| --- | --- | --- | --- |
| **1 · Foundation** | W01-W05 | Week 1 | System is faster, observable, and stable on Mac Mini |
| **2 · Closing the integration gap** | W06-W09 | Weeks 2-3 | Closed learning loop fully wired; AI reads what feedback writes |
| **3 · External intake ****&**** operator surfaces** | W10-W13 | Week 4 | Perplexity findings flow into catalog through Slack /intel |
| **4 · Architectural correctness** | W14-W17 | Weeks 5-6 | Two-Postgres-instance split; design intent restored |
| **5 · Performance polish** | W18-W22 | Weeks 7-8 | Layer 1 of three-layer ceiling reached: A-grade single-site |
| **6 · Federation** | (separate plan) | Months 3-6 | Multi-site monthly push/pull/merge; A+ system |

# **Phase 1 — Foundation (Week 1)**

| **PHASE 1  ·  ***Week of May 11, post-cutover* **Stop bleeding, get observability, build on solid ground** **Goal: **Make the Mac Mini deployment fast, observable, and stable. Everything else in the plan stands on this foundation. |
| --- |

Order within this phase is critical. Each item depends on the previous one being stable. Do not skip ahead even if a later item looks easier.

**W01  ****Verify cutover succeeded**

**Source: **Report 1, Tier 1    **Effort: **XS (1-2 hours)    **Risk: **Low — verification only, no changes

**Files: **

DEPLOYMENT_CHECKLIST.md

/Library/LaunchDaemons/com.miningguardian.*.plist

**What to do**

Run sudo pmset -a sleep 0 disksleep 0 to disable Mini sleep. Without this, StartCalendarInterval jobs miss their fire window when the Mini sleeps.

Confirm exactly nine launchd services loaded with launchctl list | grep com.miningguardian | wc -l.

Confirm no PIDs are dashes with launchctl list | grep com.miningguardian — every line should show a numeric PID.

Tail the catalog-import job log after 4:30 AM to confirm it logs INFO no CSV files in .../enrichment_sweep — nothing to import. This is the expected baseline.

Verify backup destination is configured and not on the same SSD as the live data. Recommendation: rsync to ROBS-PC over Tailscale on a daily cron until master-on-PC infrastructure is up.

**Why now**

First. Everything else assumes the Mini is in a known-good state. If services did not load, sleep was not disabled, or backups have nowhere to go, no other work matters until those are fixed.

**How to verify**

All four checks pass. If any fail, debug and resolve before W02.

**Definition of done**

Cutover smoke-test checklist filed in docs/HANDOFF_2026-05-11.md or equivalent, with timestamps showing each verification ran.

**W02  ****Enable pg_stat_statements for query observability**

**Source: **Report 1, Tier 2 (§2.3)    **Effort: **XS (under an hour)    **Risk: **Low — extension is built into Postgres 16, costs nothing at idle

**Blocked by: ***W01 (services running)*

**Files: **

/opt/homebrew/var/postgresql@16/postgresql.conf  (or wherever your postgresql.conf lives on the Mini)

**What to do**

Add shared_preload_libraries = 'pg_stat_statements' to postgresql.conf if not already present.

Restart Postgres: brew services restart postgresql@16 (or via launchd if installed that way).

Connect to each database (mining_guardian and mining_guardian_catalog) and run: CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

Verify with SELECT count(*) FROM pg_stat_statements; — should return a number, not an error.

**Why now**

Second. You cannot tune what you cannot see. Every later optimization in the plan benefits from having this telemetry available — once W03 lands, you will want to know which queries actually got faster, and pg_stat_statements is the cheapest way to measure that. Costs nothing in normal load.

**How to verify**

After 24 hours of normal operation, query SELECT query, calls, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 20;

If it returns the expected slow queries (anything from daily_deep_dive, predictor, fingerprint_builder), the extension is working.

**Definition of done**

Extension enabled in both databases, surviving a Postgres restart, query above returns useful data.

**W03  ****Add Postgres connection pool to GuardianPGDB**

**Source: **Report 1, Tier 2 (§2.1) — highest single-item performance win    **Effort: **M (2-3 days, mostly testing)    **Risk: **Medium — touches every database call site (~30 in core/database_pg.py)

**Blocked by: ***W02 (so you can measure the before/after)*

**Files: **

core/database_pg.py

core/db_targets.py  (may need adjustment if pool is shared)

tests/test_db_targets.py  (extend with pool tests)

**What to do**

Drop psycopg2.pool.ThreadedConnectionPool into GuardianPGDB.__init__ with minconn=2, maxconn=10.

Change _connect to call pool.getconn() instead of psycopg2.connect().

Change connection close paths to call pool.putconn(conn) — make sure exception paths also return the connection.

Audit every cursor usage to ensure connections are returned to the pool, not closed.

Add unit tests covering: pool initialization, concurrent connection checkout, connection-return on success, connection-return on exception.

Roll out to a staging copy of the Mini configuration first if available; otherwise plan a maintenance window.

**Why now**

Third. This is the highest single-item performance win. A typical hourly scan invokes the database hundreds of times; ~5-15ms per fresh connection adds up to roughly 7.5 seconds of pure connection overhead per scan. With pg_stat_statements running from W02, you can verify the improvement quantitatively.

**How to verify**

Compare mean_exec_time in pg_stat_statements before and after; total query time should drop noticeably.

Watch SELECT count(*) FROM pg_stat_activity WHERE datname='mining_guardian'; — should hover at 2-10 rather than spiking to 30+ during a scan.

Tail logs for any 'connection pool exhausted' errors; if they appear, raise maxconn or audit for connection leaks.

**Definition of done**

All tests pass, pg_stat_activity shows controlled connection count, scan latency measurably improved, no pool-exhaustion errors after 48 hours of normal operation.

**W04  ****Tune Postgres for 16GB shared host**

**Source: **Report 1, Tier 2 (§2.3)    **Effort: **S (a few hours, including restart window)    **Risk: **Medium — requires Postgres restart; misconfigured values can degrade performance

**Blocked by: ***W03 (pool in place so connection limit lowering is safe)*

**Files: **

postgresql.conf  (same path as W02)

**What to do**

Set shared_buffers = 1GB (default 128MB).

Set effective_cache_size = 2GB.

Set work_mem = 32MB.

Set maintenance_work_mem = 256MB.

Set max_connections = 50 (you do not need 100+ on single-host install).

Set random_page_cost = 1.1 (SSD).

Set effective_io_concurrency = 200 (SSD).

Restart Postgres in a quiet window. Document the values in deploy/postgresql.conf.template so future Mini installs use them.

**Why now**

Fourth. Defaults assume a generous server. On a 16GB Mini sharing memory with Ollama (5-10GB), Grafana, Prometheus, and nine Python services, defaults under-allocate to Postgres while max_connections wastes slots. Once W03 caps connection demand, lowering max_connections is safe.

**How to verify**

Run SHOW shared_buffers; SHOW effective_cache_size; etc. to confirm values landed.

Watch system memory over a full day of operation: Postgres should use roughly 1-2GB resident, Ollama should still have headroom, no swap pressure.

Check pg_stat_statements before/after: queries hitting cached data should show lower mean_exec_time as more data fits in shared_buffers.

**Definition of done**

Settings applied, surviving a restart, no memory pressure observed for 48 hours, configuration template committed.

**W05  ****Correct ProcessType for always-on services**

**Source: **Report 1, Tier 2 (§2.4)    **Effort: **XS (under an hour)    **Risk: **Low — one-line plist edits, easy to revert

**Blocked by: ***Nothing in this phase*

**Files: **

installer/macos-pkg/resources/launchd/com.miningguardian.scanner.plist

installer/macos-pkg/resources/launchd/com.miningguardian.alerts.plist

installer/macos-pkg/resources/launchd/com.miningguardian.approval-api.plist

installer/macos-pkg/resources/launchd/com.miningguardian.dashboard-api.plist

installer/macos-pkg/resources/launchd/com.miningguardian.slack-listener.plist

installer/macos-pkg/resources/launchd/com.miningguardian.slack-commands.plist

Same files at /Library/LaunchDaemons/ on the running Mini

**What to do**

Change <string>Background</string> to <string>Standard</string> in the six always-on service plists listed above.

Leave the scheduled batch jobs (daily-deep-dive, weekly-training, refinement-chain, etc.) on Background — they should yield to interactive work.

Bootout and bootstrap each service: sudo launchctl bootout system /Library/LaunchDaemons/<plist> followed by sudo launchctl bootstrap system /Library/LaunchDaemons/<plist>.

**Why now**

Fifth. Cheap, mechanical, no risk. Ends the phase with services responding faster to operator interactions and Slack approvals. Easy to revert if any anomaly appears.

**How to verify**

Time a Slack approval round-trip before and after: should be noticeably snappier.

Watch CPU usage on scanner and dashboard-api under load — they should no longer be aggressively throttled.

**Definition of done**

Six plists updated in repo, six running services bootstrapped with new ProcessType, Slack response latency measurably improved.

# **Phase 2 — Closing the Integration Gap (Weeks 2-3)**

| **PHASE 2  ·  ***Weeks 2-3* **Make the catalog data the AI is already collecting actually useful** **Goal: **Turn write-only catalog tables into read-write. This is where the system starts getting smarter, not just faster. |
| --- |

Phase 1 made the system fast and observable. Phase 2 makes it smart. The work happens in two code areas: ai/catalog_context.py for per-scan reads, and ai/train_cohort.py / weekly_train.py for the Sunday training pass. Stay in those files for the whole phase.

**W06  ****Add catalog read for hardware.model_known_issues**

**Source: **Report 2 — highest-leverage missing read    **Effort: **S (one day)    **Risk: **Low — additive change, behind circuit breaker

**Blocked by: ***W03 (connection pool — adding queries to an unpooled DB compounds the problem)*

**Files: **

ai/catalog_context.py  (specifically _fetch_miner_knowledge_pg)

ai/daily_deep_dive.py  (where the prompt context gets composed)

**What to do**

In _fetch_miner_knowledge_pg, add a query to fetch model_known_issues for the miner's model_id, ordered by bobby_experienced DESC, commonality DESC, limited to 10 rows where deleted_at IS NULL AND is_resolved=FALSE.

Format the result into the prompt-context string under a 'Known issues for this model' section.

Make the section optional — if the query returns empty, omit the section header rather than showing 'Known issues: (none).'

Wrap in the existing circuit breaker pattern so a catalog hiccup does not stall scans.

**Why now**

Highest single integration win in the plan. The feedback_loop daemon has been writing into hardware.model_known_issues continuously since C5 went live. The data is there. Adding the read makes every per-miner prompt aware of every restart pattern this model has shown.

**How to verify**

Run ai/daily_deep_dive.py --smoke-test --miner-ip <one IP> and inspect the generated prompt — known_issues section should appear.

Manually insert a test row into hardware.model_known_issues with bobby_experienced=TRUE and re-run the smoke test — the row should appear in the prompt.

Confirm the per-miner prompt token count rose meaningfully (you are now feeding more context to the LLM).

**Definition of done**

Smoke test shows the section in generated prompts. The next live daily deep dive includes the section and the analysis quality is observably more grounded.

**W07  ****Add catalog read for market.war_stories**

**Source: **Report 2 — second highest-leverage missing read    **Effort: **S (under a day, follows W06 pattern)    **Risk: **Low — additive, same pattern as W06

**Blocked by: ***W06 (same code area; finish the pattern there first)*

**Files: **

ai/catalog_context.py

**What to do**

Add a query against market.war_stories using ANY(tagged_model_ids) = miner_model_id OR is_bobby_story=TRUE, ordered by event_date DESC NULLS LAST, limited to 5.

Format under a 'Past operational experience' or 'Lessons from prior operations' section in the prompt context.

Pass the same circuit breaker.

**Why now**

Same logic as W06 but for war_stories. The feedback_loop has been accumulating these from llm_analysis since C5 went live. Adding the read compounds with W06: now the prompt knows the model's known issues AND your specific past handling of them.

**How to verify**

Same as W06 but verify war_stories section appears.

**Definition of done**

War stories section appearing in generated prompts and being meaningfully cited in deep dive output.

**W08  ****Add catalog read for ops.environmental_correlations**

**Source: **Report 2 — third tier read, especially for HVAC integration    **Effort: **S (under a day)    **Risk: **Low — same pattern

**Blocked by: ***W07 (finish the catalog_context.py pattern)*

**Files: **

ai/catalog_context.py

ai/hvac_correlator.py  (review for whether it should also consume this)

**What to do**

Add a query against ops.environmental_correlations filtered by miner_model_id and effective_to IS NULL OR effective_to > NOW().

Format under 'Environmental factors known to affect this model' section.

Optionally extend hvac_correlator.py to use these as priors — if the catalog already says 'this model degrades above ambient X', the correlator does not need to re-derive that pattern from scratch.

**Why now**

Lower leverage than W06/W07 because the table is less frequently populated, but it closes the loop for the HVAC side specifically. Once the per-Mini install includes operator-confirmed environmental thresholds (e.g. from your immersion experience), this table earns its keep.

**How to verify**

Section appears in prompts when correlation data exists for the miner's model.

**Definition of done**

All three planned catalog reads (W06, W07, W08) live in production for at least one daily deep dive cycle.

**W09  ****Pass 2 weekly training reads the catalog**

**Source: **Report 2 — biggest integration gap not in the per-scan path    **Effort: **M (2-3 days, requires careful prompt engineering)    **Risk: **Medium — Pass 2 is the synthesis layer, behavior changes have downstream effects on knowledge.json

**Blocked by: ***W06-W08 (the catalog read patterns are now established)*

**Files: **

ai/train_cohort.py

ai/weekly_train.py

ai/refinement_chain.py  (Pass 2 is invoked via the chain)

**What to do**

Add a 'fleet catalog context' section to the Pass 2 Claude prompt, gathered from the catalog DB rather than just operational data.

Include: failure_patterns aggregated for the cohort's models, top war_stories tagged for those models, environmental_correlations for the cohort's deployment type.

Consider adding cohort-level repair_procedures so Claude can reference 'standard repair steps for this failure pattern.'

Test against the smoke-test path before letting it run in a real Sunday training.

**Why now**

Pass 2 is the synthesis layer where Claude steps back to pattern-match across a week. It is the perfect place for catalog context because cohort-level patterns are exactly what the catalog encodes. Currently Claude reasons about a week of fleet data with zero awareness of what the catalog already knows. This is the single largest unrealized value in the system after the per-scan reads.

**How to verify**

Run ai/weekly_train.py --smoke-test on a known cohort and inspect the prompt.

Compare Pass 2 output before and after: cited reasoning should be more specific ("this matches failure pattern FP-23 which we have seen 4 times") rather than rederived from scratch.

Watch knowledge.json after a real Sunday run — refined_insights should contain entries that explicitly cite catalog facts.

**Definition of done**

First Sunday Pass 2 with catalog context completed, output reviewed, no regression in deep dive quality, knowledge.json shows catalog-grounded reasoning in new insights.

# **Phase 3 — External Intake ****&**** Operator Surfaces (Week 4)**

| **PHASE 3  ·  ***Week 4* **Close the Perplexity gap and make queue states visible** **Goal: **External research flows into the catalog through one Slack command. Operator review surfaces for staging queues are live. |
| --- |

Different code area from Phase 2. This phase is mostly Slack listener, intelligence_report_api, and dual_writer extension work. Mental palette cleanser after two weeks in the AI prompt-builder.

**W10  ****Extend dual_writer with new propose_* functions**

**Source: **Report 2 — Perplexity ingest blockers    **Effort: **S (one day)    **Risk: **Low — additive, idempotent UPSERTs follow existing pattern

**Files: **

intelligence-catalog/db/dual_writer.py

intelligence-catalog/db/tests/test_dual_writer.py

**What to do**

Add propose_firmware_release(family, version, payload, source_tool) — UPSERTs into firmware.firmware_releases.

Add propose_firmware_compatibility(firmware_slug, miner_slug, payload) — UPSERTs into firmware.firmware_compatibility.

Add propose_data_conflict(table, row_id, field, value_a, value_b, source_a_id, source_b_id, payload) — UPSERTs into knowledge.data_conflicts.

Add record_freshness_check(source_slug, sources_checked, found_new, payload) — UPSERTs into knowledge.freshness_log.

All four follow the existing propose_miner_model pattern: idempotent, fail-soft on Postgres unreachable, write to staging where appropriate.

Add unit tests for each, mirroring test_dual_writer existing patterns.

**Why now**

Required for W11 (Slack /intel command) to actually do anything. The Slack handler will call these. Without them, the ingest path has nowhere to land most finding shapes.

**How to verify**

Each propose function has a unit test. Manually invoking each in a Python REPL writes a row into the appropriate catalog table.

**Definition of done**

All four functions live, tested, idempotent verified by re-running the same input twice and confirming no duplicate rows.

**W11  ****Build the Slack /intel command and intake API**

**Source: **Report 2 — Option D, recommended Perplexity ingest path    **Effort: **M (3-4 days including prompt engineering)    **Risk: **Medium — requires reliable structure-extraction prompting

**Blocked by: ***W10 (the propose functions need to exist for /intel to call them)*

**Files: **

api/intelligence_report_api.py  (new endpoint POST /api/catalog/intake)

api/slack_commands.py  (new /intel handler)

ai/structure_extractor.py  (new module — Claude-driven natural-language to structured-finding)

**What to do**

Build POST /api/catalog/intake accepting {event_type, raw_text, source}. Calls structure_extractor to convert raw_text into the appropriate propose_* call. Returns a confirmation payload.

Build the /intel slash command handler. Syntax: /intel <event_type> "<raw_text>". Forwards to the API.

Build structure_extractor with a Claude prompt that takes the raw_text and an event_type hint and returns strict JSON in the dual_writer payload shape.

Add a confirmation card back to Slack with Approve / Reject buttons. Approve flips bobby_verified=TRUE on the staged row. Reject deletes the staged row.

Write the prompt carefully — output must be valid JSON only, no preamble. Test against the four findings from May 9 (the ones in Report 2's mapping table) as a regression suite.

**Why now**

This is the recommended Perplexity ingest solution. Operator pastes Perplexity finding into Slack, Claude structures it, operator reviews and approves, catalog updates with bobby_verified set in one step.

**How to verify**

Paste each of the four May 9 findings (Aggregator, Community Intel, Firmware Tracker, Manufacturer Model) and verify the correct catalog table receives the correct row.

Reject path verified — rejected staging rows are removed.

Approve path verified — bobby_verified flag flips in the actual catalog table.

**Definition of done**

Four real Perplexity findings successfully ingested through /intel. Operator review of the resulting catalog rows confirms data quality.

**W12  ****Morning briefing additions for catalog visibility**

**Source: **Report 1 + Report 2 — catalog freshness, queue states    **Effort: **S (one day)    **Risk: **Low — additive to existing morning briefing

**Blocked by: ***W11 (so catalog_freshness has data to report)*

**Files: **

scripts/morning_briefing.py

Or wherever the 7am morning briefing lives

**What to do**

Add a 'Catalog state' section reporting: count of pending proposals in staging.miner_model_proposals where status='new', count of new entries in knowledge.unknown_fields, last successful catalog-import timestamp, last successful Perplexity-watcher heard-from timestamp per watcher (if W11 added that tracking).

Add a 'Feedback loop' section reporting: rows processed by feedback_loop_daemon in last 24h, broken down by sync_action / sync_llm_analysis / sync_miner_restarts.

Add a 'System health' line reporting last successful run of each scheduled job.

**Why now**

Without these, queues silently fill. Operator visibility into catalog state needs to match the visibility into operational state. The briefing is already the natural daily-report surface — extend it.

**How to verify**

Read the next morning briefing in Slack — new sections appear with sensible numbers.

**Definition of done**

Morning briefing has all three new sections, displaying numbers, observed for at least three consecutive mornings.

**W13  ****Watchdog-of-the-watchdog service**

**Source: **Report 1 — health monitoring of monitoring    **Effort: **S (1-2 days)    **Risk: **Low — new service, no changes to existing code

**Blocked by: ***Phase 1 stable*

**Files: **

monitoring/watchdog.py  (new file)

deploy/com.miningguardian.watchdog.plist  (new launchd plist)

installer/macos-pkg/resources/launchd/com.miningguardian.watchdog.plist  (mirror for installer)

**What to do**

Build a 100-line Python service that runs every 60 seconds: pings /health on each API service, runs SELECT 1 against both Postgres databases, checks that each launchd service has a numeric PID.

On first failure, post to a #mg-alerts Slack channel with details.

On three consecutive failures of the same check, escalate (send a stronger ping, optionally page).

Reset failure counters on success.

Add a launchd plist with KeepAlive: { Crashed: true } so the watchdog itself stays running.

**Why now**

KeepAlive on services handles process crashes. It does not handle stuck-but-running, lost DB connections, or Postgres being down. The watchdog catches what KeepAlive misses. After a month of operation, this is the difference between 'system tells me when something is wrong' and 'I find out from a missing morning briefing.'

**How to verify**

Manually stop a service: watchdog should post within 60 seconds.

Stop and restart Postgres: watchdog should detect both events.

Run for a full week without false positives.

**Definition of done**

Watchdog deployed, alerting verified, no false positives over one week of operation.

# **Phase 4 — Architectural Correctness (Weeks 5-6)**

| **PHASE 4  ·  ***Weeks 5-6* **Restore design intent and clean up shortcuts** **Goal: **Two-Postgres-instance split as originally designed. Knowledge.json discipline. Time zone consistency. Implementation matches architecture. |
| --- |

This phase requires real maintenance windows — Postgres restarts, service reloads, file moves under lock. Schedule for low-activity periods. By this point you have run for a month with the closed loop wired and operator surfaces in place; you know what stable looks like, so disruptive changes are easier to validate.

**W14  ****Split Postgres into two separate instances**

**Source: **Report 3 + operator note May 9 — restoration of original design intent    **Effort: **L (1 week including testing)    **Risk: **High — affects everything; needs a planned maintenance window

**Blocked by: ***W01-W13 stable for at least two weeks*

**Files: **

core/db_targets.py

deploy/postgresql.conf.template  (will need two copies — one per instance)

installer/macos-pkg/scripts/postinstall.sh  (install second Postgres instance)

.env.example  (separate DSNs already exist; will document the split)

**What to do**

Install second Postgres instance on a different port (e.g. 5433). On macOS, this means a separate data directory and a separate launchd plist. brew install postgresql@16 supports running two instances if you create a separate data dir manually.

pg_dump the catalog, drop catalog from the operational instance, restore catalog to the new instance.

Update GUARDIAN_PG_HOST and GUARDIAN_PG_CATALOG_DBNAME — they are already separate variables; just point catalog at the new port.

Apply Phase 1 tuning to the new instance separately. The catalog instance gets less shared_buffers (it is read-heavy at lower volume); the operational instance keeps the bigger allocation.

Update backup scripts to dump both instances separately.

Update installer to provision both instances on fresh installs.

**Why now**

This was the original design. Single-instance was a deployment compromise — explicitly noted by operator on May 9. Splitting reduces blast radius (a corruption in one DB does not take both down), allows independent tuning, and makes the master-on-PC federation model cleaner because each instance can be backed up and synced separately.

**How to verify**

Both instances start and stay running.

Operational queries route to instance 1; catalog queries route to instance 2; no cross-instance queries leak.

Backup scripts produce two separate dump files.

All scheduled jobs run successfully after the split.

**Definition of done**

Two instances running stably for one week. Backups verified. Restore-from-backup test successful for both.

**W15  ****Split daily_deep_analyses out of knowledge.json**

**Source: **Report 1, Tier 2 (§2.5)    **Effort: **S (one day)    **Risk: **Medium — touches the lock pattern; bug here corrupts state

**Files: **

core/file_lock.py

ai/daily_deep_dive.py  (writer of daily_deep_analyses)

ai/train_cohort.py  (reader of daily_deep_analyses)

ai/knowledge_manager.py  (orchestrates merges)

**What to do**

Move the daily_deep_analyses array to its own file knowledge_deep_dives.json with its own flock.

Create locked_deep_dives_update helper analogous to locked_knowledge_update.

Update writers (daily_deep_dive.py) to use the new lock and file.

Update readers (train_cohort.py) to read from the new file.

Tighten retention while you are in there: keep last 7 daily dives and 4 weekly chains.

**Why now**

knowledge.json is 3.57MB; daily_deep_analyses alone is 2.1MB. Splitting drops the hot-path file size by 60%, reduces lock contention dramatically, and tightens retention saves another ~1MB. Hot writers and the daily Pass 1 stop fighting each other.

**How to verify**

After split, knowledge.json should be roughly 1.5MB.

Both files updated correctly during a full daily-deep-dive run.

Pass 2 weekly training successfully reads from the new file.

No 'file not found' errors during the transition (handle the migration cleanly with a one-time copy).

**Definition of done**

Both files in production, hot writers no longer block on the deep-dive lock, file sizes match expectations after a week of operation.

**W16  ****Stop casting timestamps through TO_CHAR**

**Source: **Report 1, Tier 2 (§2.2)    **Effort: **M (2-3 days, mostly searching and testing)    **Risk: **Medium — touches many files; need to verify each query plan

**Files: **

ai/daily_deep_dive.py

ai/predictor.py

ai/fingerprint_builder.py

ai/outcome_checker.py

ai/train_cohort.py

core/database_pg.py  (insert side: pass datetime.now() not isoformat())

**What to do**

Find all queries using TO_CHAR(NOW() - INTERVAL ...) — grep -rn 'TO_CHAR(NOW()' --include='*.py'.

Replace with WHERE scanned_at >= NOW() - INTERVAL '...'.

On the insert side in core/database_pg.py, change datetime.now().isoformat() to datetime.now(timezone.utc) and let psycopg2 handle the typed conversion.

After change, run EXPLAIN on representative queries to confirm index usage. Should see 'Index Scan' on idx_readings_miner instead of 'Seq Scan'.

**Why now**

Schema declares scanned_at as TIMESTAMPTZ but queries route through string comparisons. With small datasets the planner copes; on the eventual 5-10M row table this hurts. Fix it now while query patterns are still being added — once W18-W22 land, even more queries will exist.

**How to verify**

EXPLAIN on representative queries shows index scans, not sequential scans. pg_stat_statements shows mean_exec_time dropping on the hot queries.

**Definition of done**

All TO_CHAR-based comparisons replaced, all inserts using timezone-aware datetimes, query plans verified.

**W17  ****Time zone discipline cleanup**

**Source: **Report 1 — Things you may not have considered    **Effort: **S (one day, finishes what W16 started)    **Risk: **Low — most damage was done before the cleanup; this is hygiene

**Blocked by: ***W16 (don't do these in two passes)*

**Files: **

All Python files using datetime.now() — grep -rn 'datetime.now()' --include='*.py' core/ ai/ api/ scripts/

**What to do**

Replace every datetime.now() with datetime.now(timezone.utc).

Audit any naive datetime arithmetic for timezone-awareness.

Document the convention in docs/CODING_STYLE.md (or equivalent) so future code follows it.

**Why now**

Today the system runs in CDT and assumes CDT everywhere. The minute someone runs the Mini in UTC, ships to a customer in another timezone, or DST math breaks something in March/November, you have hard-to-debug timestamp drift. Schema is already TIMESTAMPTZ-correct; Python side just needs to match.

**How to verify**

Existing tests pass. Spot-check production behavior across a DST boundary (March or November) — no timestamp anomalies.

**Definition of done**

Codebase audit complete, no naive datetime.now() calls remain in core/ai/api/scripts/.

# **Phase 5 — Performance Polish (Weeks 7-8)**

| **PHASE 5  ·  ***Weeks 7-8* **Squeeze remaining wins; future-proof against data growth** **Goal: **Layer 1 of three-layer ceiling reached. Single-site Mining Guardian is at A-grade. |
| --- |

These items are nice-to-have rather than blocking. Do them now while the foundation is fresh. Several get more painful with delay (W21 in particular has a hard deadline).

**W18  ****Pipeline DB I/O against LLM compute in daily deep dive**

**Source: **Report 1, Tier 2 (§2.6)    **Effort: **S (1-2 days)    **Risk: **Low — additive concurrency, fallback to serial if the pipeline fails

**Files: **

ai/daily_deep_dive.py

**What to do**

Wrap the per-miner data-gathering in a concurrent.futures.ThreadPoolExecutor with max_workers=2.

Prefetch (daily_log + 24h trends + hardware + past_analyses + fingerprint) for miner N+1 while the LLM call for miner N is in-flight.

Keep the LLM call itself sequential — Metal cannot run two Qwen inferences at once.

**Why now**

Daily deep dive is currently serial: gather, LLM (2-4 min wait), repeat. During the LLM wait, the database is idle. Pipelining recovers that idle time. With 50 miners at 3 minutes each, baseline is 150 minutes; pipelining cuts roughly 10-15 minutes by getting prompt-build off the critical path.

**How to verify**

Time a full deep dive run before and after. End-to-end wall time should drop noticeably.

**Definition of done**

Wall time reduction observable, no race conditions over a week of nightly runs.

**W19  ****AMS WebSocket persistent connection**

**Source: **Report 1, Tier 2 (§2.7)    **Effort: **M (2-3 days)    **Risk: **Medium — touches the AMS integration, which is critical path

**Files: **

clients/ams_client.py

**What to do**

Refactor _ws_fetch to maintain a singleton WebSocket connection rather than open/close per call.

Implement message-ID-based request/response routing so multiple concurrent calls can share one connection.

Add reconnection logic with exponential backoff if the connection drops.

Keep the existing one-shot pattern as a fallback for first connection or after persistent failures.

**Why now**

Today every page request opens a new TLS handshake (~80-200ms each). Negligible at 1 scan/hour with ~58 miners. At production cadence (multi-site, 30-minute scans, alert-driven scans), it accumulates. Worth doing now while you still remember the AMS WebSocket pattern in detail; harder later.

**How to verify**

Connection count to the AMS server stays at 1 during normal operation. Force a disconnect and verify reconnection happens. No per-page handshake overhead in logs.

**Definition of done**

Singleton connection holding for >24 hours with a real fleet, reconnection tested at least once successfully.

**W20  ****Tune autovacuum for high-churn tables**

**Source: **Report 1 — Things you may not have considered    **Effort: **XS (under an hour)    **Risk: **Low — per-table override, easy to revert

**Files: **

Direct SQL on operational DB

Document the override in migrations/ as a new SQL file

**What to do**

ALTER TABLE miner_readings SET (autovacuum_vacuum_scale_factor = 0.05);

ALTER TABLE log_metrics SET (autovacuum_vacuum_scale_factor = 0.05);

ALTER TABLE chain_readings SET (autovacuum_vacuum_scale_factor = 0.05);

ALTER TABLE pool_readings SET (autovacuum_vacuum_scale_factor = 0.05);

Save the SQL as migrations/008_autovacuum_tuning.sql so it applies on fresh installs.

**Why now**

Default 0.2 scale factor means autovacuum doesn't run until 20% of rows are dead. On a 1M-row table that's 200,000 dead tuples accumulating before cleanup. Bloat hurts query plans because the planner stops trusting its statistics. As your data grows, this matters more.

**How to verify**

Watch pg_stat_user_tables for n_dead_tup counts on the four tables. They should stay proportionally lower than before.

**Definition of done**

Override applied on running DB and committed as migration. n_dead_tup ratios verifiably lower after one week.

**W21  ****Range-partition the timeseries tables**

**Source: **Report 1 — Things you may not have considered    **Effort: **M (2-3 days, includes data migration)    **Risk: **Medium — table restructure on production data

**Files: **

migrations/009_partition_miner_readings.sql  (new)

Same for chain_readings, pool_readings, log_metrics

**What to do**

Convert miner_readings, chain_readings, pool_readings, log_metrics to range-partitioned tables on scanned_at, partitioned by month.

Create partitions for current month + 6 months ahead.

Add a monthly cron that creates next-quarter's partitions.

Migrate existing data into the partitioned structure (CREATE TABLE ... PARTITION OF, INSERT INTO ... SELECT, drop old, rename).

**Why now**

miner_readings will be 5-10M rows within 6 months. Partitioning gives: O(1) old-data drops instead of DELETE WHERE scanned_at <, hot indexes stay small (current month fits in shared_buffers), per-partition VACUUM runs without locking the whole table. Doing this BEFORE the table crosses 5M rows is dramatically easier than after.

**How to verify**

Existing queries continue to work. EXPLAIN on time-windowed queries shows partition pruning. Drop a partition; subsequent queries don't see the dropped data.

**Definition of done**

All four tables partitioned, partition-creation cron in place, existing queries unaffected.

**W22  ****Extend raw_ingestion_log partitions past 2027-Q1**

**Source: **Report 2 — Catalog issue 1, hard deadline    **Effort: **XS (under an hour)    **Risk: **Low — pure schema addition

**Files: **

intelligence-catalog/seed-data/intelligence_catalog_schema_v3_additions.sql  (or new migration)

**What to do**

Either install pg_partman extension and configure it to auto-create partitions on a quarterly schedule.

Or add a quarterly cron that runs CREATE TABLE knowledge.raw_ingestion_log_<YYYY>_q<N> PARTITION OF knowledge.raw_ingestion_log FOR VALUES FROM (...) TO (...);

Recommend pg_partman for cleaner long-term management. The cron approach is a one-line script if pg_partman is not desired.

**Why now**

Existing partitions stop at 2027-Q1. When 2027-Q2 starts, every insert into raw_ingestion_log fails silently with 'no partition found.' This is roughly a year out — but the failure is silent until ingestion stops working. Better to handle now than to debug it on a Monday morning a year from now.

**How to verify**

Partition for 2027-Q2 exists. Insert a row with a 2027-Q2 timestamp succeeds. Query returns it.

**Definition of done**

Either pg_partman installed and configured, or quarterly cron in place and verified for two cycles.

# **Phase 6 — Federation (Months 3-6)**

| **PHASE 6  ·  ***Months 3-6* **Multi-site monthly push/pull/merge cycle** **Goal: **Layer 2 of three-layer ceiling: A+ system. Mac Minis at multiple sites contribute learning; master on operator's PC computes confidence-weighted truth. |
| --- |

Phase 6 is a separate plan. The work is substantial enough that it deserves its own document, written when Phases 1-5 are nearing completion and you have lived with the system long enough to know what federation actually needs in production. The architecture is sketched in Report 2 §'Considerations for the Monthly Federation Model'; the execution plan will follow.

Pre-requisites for starting Phase 6:

- Phases 1-5 stable for at least 30 days.

- Two-Postgres-instance split (W14) verified in production.

- Master DB infrastructure on operator PC chosen and provisioned.

- At least one second site beyond Fort Worth — otherwise federation has nothing to federate.

- iPhone app and PC client work streams clarified — they share federation infrastructure.

# **Working Principles for the Whole Plan**

Patterns that apply across all phases. Re-read these before starting any phase.

### **On commits**

One commit per work item, ideally. Commit message format: 'W## — short description (Phase N)'. Example: 'W03 — add ThreadedConnectionPool to GuardianPGDB (Phase 1)'. This makes the execution plan and the git history line up perfectly. Future debugging benefits enormously from this.

### **On testing**

Every change touches a system that runs 24/7 against real money-making infrastructure. The test discipline that should apply: write the test before the change when feasible, run the existing tests after, smoke-test in dev (the daily_deep_dive --smoke-test, the launchctl bootout/bootstrap cycle, etc) before letting it run in production. Production validation is by observation over hours, not minutes.

### **On rollback**

For each item, know the rollback before starting. For commits, git revert. For Postgres config, the previous postgresql.conf saved as .backup. For schema, an explicit ALTER ... DROP equivalent. For data migrations, a tested restore-from-pg_dump. If you cannot articulate the rollback, you are not ready to start the change.

### **On knowing when to stop a phase**

Each phase has a defined end state. When that end state is observed in production for at least 48 hours with no anomalies, the phase is complete. Resist the urge to slip Phase N+1 work into Phase N just because it 'feels small.' The dependency order exists for a reason.

### **On what to do when something breaks**

First: did the most recent change cause it? git log will tell you. If yes, revert. Investigate later, when the production system is stable again. Second: is anyone unable to mine right now? If yes, fix that first; everything else can wait. Third: file the incident in docs/INCIDENTS_LOG.md or equivalent — what broke, what fixed it, what to do differently next time. The catalog of incidents is itself a knowledge asset over time.

### **On collaboration with future Claude sessions**

When you come back to a fresh chat to work on, say, W11, the most useful opening message is: 'Working on W11 from the Master Execution Plan. Here is the current state of api/intelligence_report_api.py: <paste>. The dual_writer extensions from W10 are complete. Ready to start the /intel command handler.' That gives the next Claude full context in one message and saves enormous time over re-establishing the project.

# **Closing**

This plan is a living document. As work progresses, items will be re-scoped, new items will surface, priorities may shift. The numbering is stable — once a number is assigned, it stays — so even if W08 turns out to be irrelevant, W09 keeps its number. Add new items as W23, W24, etc.

If a major architectural decision changes mid-plan (the federation model evolves, the iPhone app drives a new requirement, a customer site has different needs), come back and amend this document. Or, more practically, write a successor document referencing this one. Future-you will thank present-you for keeping the trail clear.

The work ahead is real but it is the right work. The plan is to follow this sequence, finish what was started, and let the system grow into the architecture that was designed for it. Six phases. Twenty-two items. A path from B+ to A+.

Begin with W01.

*End of plan. Living document — amend as the work progresses. Companion documents: Mining Guardian — Performance **&** Capability Audit (Report 1), Two-Database Deep Dive (Report 2), Overall Assessment **&** Potential (Report 3).*

Page   ·  Prepared May 9, 2026