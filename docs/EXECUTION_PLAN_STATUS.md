# Execution Plan Status

> **Source of truth for W01–W25+ progress against the [Master Execution Plan](strategy/04_MASTER_EXECUTION_PLAN.md).**
> Append-only philosophy: when a status changes, add a row to the History section below the table; do not silently rewrite the table without a corresponding history line.
> Every `[X]` (done) and `[~]` (partial) MUST cite the evidence (commit, grep result, file path) that supports it.
> Companion: [`HANDOFF_2026-05-11_EVENING.md`](HANDOFF_2026-05-11_EVENING.md) (yesterday's handoff), [`strategy/RECONCILIATION_2026-05-12.md`](strategy/RECONCILIATION_2026-05-12.md) (today's grep receipts), [`strategy/AMENDMENTS_2026-05-12.md`](strategy/AMENDMENTS_2026-05-12.md) (plan deltas).

**Last reconciliation:** 2026-05-13 evening against `main` HEAD `5cf154f` (PR #211 merge, W26a Intelligence Catalog dashboard works on Grafana 13).

---

## Legend

| Mark | Meaning |
|---|---|
| `[X]` | Done — verified against repo and/or live system |
| `[~]` | Partial — some sub-tasks complete, others outstanding |
| `[ ]` | Not started |
| `[?]` | Status unverified — needs check |
| `[-]` | Deferred / superseded / out of scope |

---

## Phase 1 — Foundation

| ID | Title | Status | When | Evidence |
|---|---|---|---|---|
| W01 | Verify cutover succeeded | `[~]` | 2026-05-11 | 9 launchd services verified loaded (handoff §2.2 + 2.3); scanner running with `--loop` recurrence; `.env` wired with Anthropic key. **Pending:** `pmset -a sleep 0 disksleep 0` (script prepped at `/scripts/disable_sleep.sh`); backup destination decision (Report 1 §1.4 still open). |
| W02 | `pg_stat_statements` for query observability | `[ ]` | — | Grep of repo for `pg_stat_statements` and `shared_preload_libraries`: **0 hits** in any tracked file. Not started. |
| W03 | `psycopg2.pool.ThreadedConnectionPool` in `GuardianPGDB` | `[~]` | — | `intelligence-catalog/catalog-api/catalog_api.py` **already uses** `ThreadedConnectionPool` — that side is done. But `core/database_pg.py` header docstring (lines 22–24, 27–29) still says *"conn is checked out per-call (no pool today — simple for correctness)"* and *"Connection pooling (add when we deploy)"*. Operational adapter pool is not done. This is the higher-call-volume side; Report 1 §2.1 estimates ~500 calls/scan come through here. |
| W04 | Postgres tuning for 16GB shared host | `[ ]` | — | Not started. `deploy/postgresql.conf.template` does not yet exist. |
| W05 | `ProcessType: Background` → `Standard` on always-on services | `[X]` | 2026-05-12 | PR #184 merged + applied to Mini. Re-scoped: **10 services** (not 6, not 9) per AMENDMENT A07 — added `com.miningguardian.feedback-loop-daemon` via PR #185. All 10 services bootstrapped to `Standard`, verified by `sudo launchctl list \| grep com.miningguardian` returning numeric PIDs across the cohort. |

## Phase 1.5 — Architectural restoration (moved from Phase 4 per 2026-05-11 decision)

| ID | Title | Status | When | Evidence |
|---|---|---|---|---|
| W14a | Refactor 27 files bypassing `core/db_targets.py` | `[X]` | 2026-05-12 | PRs #186 (initial 27-file refactor) + #187 (import-order hotfix on 7 entry-point files) + #188 (import-order sweep on 5 latent siblings) + #189 (self-contained sys.path Path X on all 12 files). All 4 PRs merged to `main`. Deployed to Mini via surgical scp + bootout/bootstrap; all 10 services healthy on W14a code as of 2026-05-12 10:22 CDT. 37+ minute soak with zero ModuleNotFoundError. Cohort guard test `tests/test_w14a_no_direct_pg_env_reads.py` passes on `main`. |
| W14 | Split Postgres into two separate instances | `[X]` | 2026-05-13 | Executed live against Mini 06:48-07:10 CDT following [`strategy/W14_PREP.md`](strategy/W14_PREP.md) steps 0-8. Two containers live: `mining-guardian-db` (port 5432, `mining_guardian` only, 100 MB) and `mg-catalog-db` (port 5433, `mining_guardian_catalog` only, 17 MB). Pre-W14 backup → restore → row-count match (324/17/6/22/0) → `.env` + `db_targets.py` deploy → bootout/bootstrap 10 always-on services → smoke gate (3 sub-checks, including end-to-end `daily_deep_dive --dry-run` resolving 72 miners with correct model lookups) → `DROP DATABASE` on old → reload 12 scheduled. All 10 always-on services held same PIDs (66707-66788) through Step 7. Post-mortem: see [`strategy/W14_POSTMORTEM_2026-05-13.md`](strategy/W14_POSTMORTEM_2026-05-13.md) for the Step 2 password-quoting bug caught by Step 6 smoke gate and fixed by `ALTER USER`. Rollback artifacts retained on Mini: `pre-w14-*-20260512-121154.dump`, `.env.pre-w14-20260513`, `core/db_targets.py.pre-w14-20260513`. |
| W14b | Lock two-target convention in CLAUDE.md + .env.example + postinstall.sh | `[X]` | 2026-05-13 | Convention block landed in CLAUDE.md `## Coding Conventions` (PR #203). Two binding rules: (1) all Postgres access through `core.db_targets`, enforced by `tests/test_w14a_no_direct_pg_env_reads.py`; (2) `.env` values sourced via `xargs` (strips quotes) before downstream use, enforced by `tests/test_w14_password_quote_consistency.py`. `.env.example` rewritten with two-instance topology + quote-handling note. `installer/macos-pkg/scripts/lib/install_colima.sh` header documents two-container provisioning + the password-injection patterns. The full installer code changes (postinstall.sh provisioning of the second container) ship with W14 Step 10. |

## Phase 2 — Closing the integration gap

| ID | Title | Status | When | Evidence |
|---|---|---|---|---|
| W06 | Catalog read for `hardware.model_known_issues` | `[ ]` | — | Blocked on W03 + W14. |
| W07 | Catalog read for `market.war_stories` | `[ ]` | — | Blocked on W06. |
| W08 | Catalog read for `ops.environmental_correlations` | `[ ]` | — | Blocked on W07. |
| W09 | Pass 2 weekly training reads the catalog | `[ ]` | — | Blocked on W06–W08. |

## Phase 3 — External intake & operator surfaces

| ID | Title | Status | When | Evidence |
|---|---|---|---|---|
| W10 | Extend `dual_writer` with 4 new `propose_*` functions | `[ ]` | — | Not started. |
| W11 | Slack `/intel` command + intake API | `[ ]` | — | Blocked on W10 + W14. |
| W12 | Morning briefing — catalog visibility additions | `[ ]` | — | Not started. |
| W13 | Watchdog-of-the-watchdog service | `[ ]` | — | Not started. |

## Phase 4 — Architectural correctness (W14 moved out → Phase 1.5)

| ID | Title | Status | When | Evidence |
|---|---|---|---|---|
| W15 | Split `daily_deep_analyses` out of `knowledge.json` | `[ ]` | — | `knowledge_backup.json` (3.74 MB) confirmed at repo root; 6 production files reference `daily_deep_analyses` (`ai/train_cohort.py`, `daily_deep_dive.py`, `refinement_chain.py`, `knowledge_manager.py`, `comprehensive_audit.py`, `api/dashboard_api.py`). |
| W16 | Stop casting timestamps through `TO_CHAR` | `[X]` | 2026-05-11 | PR #178 (commit in P-038 cohort). Reconciliation grep `TO_CHAR(NOW(` in `ai/ core/ api/ scripts/` returns **0 hits**. The 7 hits in `tests/test_p038_timestamptz_vs_text_sql_casts.py` are intentional regression-guard pattern strings. See [`strategy/RECONCILIATION_2026-05-12.md`](strategy/RECONCILIATION_2026-05-12.md). |
| W17 | `datetime.now()` → `datetime.now(timezone.utc)` everywhere | `[ ]` | — | Reconciliation grep: **151** `datetime.now()` empty-parens calls in `ai/core/api/scripts/`. 18 calls already use `datetime.now(timezone...)` form — useful baseline. Plan §W17 effort estimate (S) is roughly correct: it's a sweep across many files, not deep work. |

## Phase 5 — Performance polish

| ID | Title | Status | When | Evidence |
|---|---|---|---|---|
| W18 | Pipeline DB I/O against LLM compute in daily deep dive | `[ ]` | — | Not started. |
| W19 | AMS WebSocket persistent connection | `[ ]` | — | Not started. |
| W20 | Autovacuum tuning for high-churn tables | `[ ]` | — | Not started. |
| W21 | Range-partition the timeseries tables | `[ ]` | — | Not started. |
| W22 | Extend `raw_ingestion_log` partitions past 2027-Q1 | `[ ]` | — | Hard deadline: 2027-Q2. Not started. |

## Phase 6 — Federation

| ID | Title | Status | When | Evidence |
|---|---|---|---|---|
| (separate plan, months 3–6) | — | `[-]` | — | Out of scope until Phases 1–5 stable for 30+ days. |

## New W-items (not in the original plan)

These were surfaced by the 2026-05-11 evening Grafana stand-up, the 2026-05-12 reconciliation pass, and the 2026-05-12 catalog design dialogue. Captured here so they're not lost. Full rationale in [`strategy/AMENDMENTS_2026-05-12.md`](strategy/AMENDMENTS_2026-05-12.md) and [`strategy/05_CATALOG_DESIGN_PLAN_2026-05-12.md`](strategy/05_CATALOG_DESIGN_PLAN_2026-05-12.md).

| ID | Title | Status | When | Evidence |
|---|---|---|---|---|
| W23 | Fix Grafana installer bundle bugs (yaml path + datasource user) | `[X]` | 2026-05-13 | **Dashboards yml path:** fixed in PR #193 — `/usr/local/MiningGuardian/...` → `/Library/Application Support/MiningGuardian/...`. **Datasource user:** `mg` is now canonical via W14b convention lock (PR #203); `guardian_app` references in codebase are stylistic-only, tracked as W14b follow-on. **Password inlined in deployed yaml:** addressed for repo via env-var form in PR #211 W26a; Mini's deployed yaml still has the password inlined, deferred to W24 (proper secret management). |
| W24 | Grafana password secret management | `[ ]` | — | Password currently inlined in deployed yaml on Mini. Needs proper handling before customer ship. Couples with Postgres password rotation (also open). |
| W25 | Grafana panel "No data" — debug + restore dashboards on Mini | `[X]` | 2026-05-13 | **Three landings closed this together.** PR #209 made dashboard_api host/port env-configurable (was hardcoded 127.0.0.1, breaking Tailscale iframe access). PR #210 (W25b) fixed `/fleet/board_stats` SQLite-isms → Postgres-strict via `DISTINCT ON (ip)` + outer `GROUP BY m.model`. 9 VPS-restored dashboards now load + populate on Mini at `http://100.69.66.32:3000`. Cohort guards: 7 tests for the bind config (`tests/test_w25_dashboard_api_bind_config.py`) + 5 tests for the GROUP BY fix (`tests/test_w25b_dashboard_api_postgres_strict_group_by.py`). |
| W25b | `/fleet/board_stats` SQLite → Postgres GROUP BY | `[X]` | 2026-05-13 | PR #210. SQLite-era subqueries grouped only by `ip` while selecting `model`; Postgres 16 strictly rejected. Fix uses `DISTINCT ON (ip)` in subqueries (preserves one-row-per-ip intent) + `m.model` added to outer GROUP BY + `HAVING SUM(c.hw_errors) > 0` for alias-free clarity. Live-Mini verified: 127.0.0.1 HTTP 200 70ms, 100.69.66.32 HTTP 200 31ms. |
| W26 | `updated_at` discipline across catalog tables | `[X]` | 2026-05-12 | **Audit complete + cohort guard test landed.** Audit query against live catalog showed 89 of 98 tables already have `updated_at`. The 9 missing are intentional append-only event logs (5 partitions of `raw_ingestion_log` plus `field_discovery_log`, `freshness_log`, `bitcoin_network_snapshots`) — all of which already have `created_at` or `ingested_at`. Approach A locked: do NOT add `updated_at` to append-only tables; federation pull uses a small constant mapping instead. Cohort guard test at `tests/test_w26_catalog_timestamp_columns.py` verifies the contract holds against live catalog (3 tests, all passing 2026-05-12 evening; correctly fails when manifest is wrong, verified by removing a table and watching the test error). See `05_CATALOG_DESIGN_PLAN_2026-05-12.md` §3 W26 for details. |
| W26a | Intelligence Catalog dashboard works on Grafana 13 | `[X]` | 2026-05-13 | PR #211. Three distinct breakage modes fixed: (1) markdown panel literal `\n` escape sequences → real newlines; (2) Grafana 12.2+ bug #112418 workaround — `database:` duplicated into `jsonData:` block in `mining_guardian.yml` for all 3 Postgres datasources; (3) dashboard `schemaVersion` 16 → 39 + datasource UID pushed onto every SQL target. Live-Mini after deploy + Grafana restart: all 5 panels populate (10 schemas, 98 tables, full firmware listing, formatted documentation). Yaml hardening: env-var form `${GUARDIAN_PG_PASSWORD}` preserved in repo despite Mini's deployed yaml having password inlined; password rotation tracked separately. Cohort guard: 6 tests (`tests/test_w26a_catalog_dashboard_grafana13_compat.py`) including Failure Mode 9 sibling sweep. |
| W26b | Installer dashboard catch-up — mirror 8 VPS-restored dashboards into repo | `[ ]` | — | **Queued for 2026-05-14.** Mini runs 9 dashboards; repo installer ships only 4 (3 May-2 + W26a's catalog). 8 missing dashboards (`mining_guardian_*.json` from VPS restore) live only on Mini filesystem. **Decision (locked 2026-05-13 evening):** ship as-is in `installer/macos-pkg/resources/grafana/dashboards/reference-mini/` to clearly label as Mini-specific (5 of 8 contain hardcoded `100.69.66.32` references). Defer IP-templating to a future W item. Runbook: [`strategy/W26b_PREP.md`](strategy/W26b_PREP.md). |
| W27 | `ops.field_observed_specs` table + mg_import_tool Layer 2.5 aggregator | `[ ]` | — | Friend archive imports enrich real-world ranges with site_id provenance (OPERATOR-RANGES-1). M effort. See `05_CATALOG_DESIGN_PLAN` §3 W27 + §1.4. |
| W28 | Federation v1: pull/merge/push scripts + customer_contribution_log | `[ ]` | — | Required for August customer ship. L effort. See `05_CATALOG_DESIGN_PLAN` §2 + §3 W28. |
| W29 | Pass 2 cadence config flag | `[ ]` | — | Daily on master, weekly on customer Minis (OPERATOR-CADENCE-1). XS effort. See `05_CATALOG_DESIGN_PLAN` §1.3 + §3 W29. |
| W30 | Enrichment CSV structured extraction | `[ ]` | — | Populate `hardware.chips` (4 → 30+ rows), `hardware.psu_models`, voltage/frequency columns, release dates from existing CSV freeform fields. Closes the "parts section" gap. M effort. See `05_CATALOG_DESIGN_PLAN` §5 W30. |

---

## Reconciliation receipts (2026-05-12)

The §5 step 2 greps from yesterday's handoff, run against `main` HEAD `9d2e117`. **Trust these over any chat assertion** — if a future Claude session disagrees, re-run them, don't argue from memory.

```bash
# W16 — should be 0 in production paths
grep -rn 'TO_CHAR(NOW(' ai/ core/ api/ scripts/ --include='*.py' | wc -l
# Result: 0    ✓

# W17 — should be ~151
grep -rnE 'datetime\.now\(\)' ai/ core/ api/ scripts/ --include='*.py' | wc -l
# Result: 151  ✓

# W05 — should show Background for all always-on services
for f in installer/macos-pkg/resources/launchd/com.miningguardian.*.plist; do
  name=$(basename "$f" .plist | sed 's/com.miningguardian.//')
  pt=$(grep -A1 '<key>ProcessType</key>' "$f" | tail -1 | tr -d '[:space:]')
  echo "  $name : $pt"
done
# Result: 9 services, all <string>Background</string>
```

Full receipts: [`strategy/RECONCILIATION_2026-05-12.md`](strategy/RECONCILIATION_2026-05-12.md).

---

## History

- **2026-05-09** — Plan created (W01–W22). Source: strategy reports 1–4 prepared by external reader.
- **2026-05-11 (evening)** — Cohort P-038 (7 PRs + 1 bonus) merged. W16 closed. W01 substantially complete on cutover side. W14 moved from Phase 4 to Phase 1.5 by operator decision.
- **2026-05-11 (evening)** — Grafana 13.0.1 stood up via Homebrew on Mini. 3 bundle bugs surfaced → W23/W24/W25 added.
- **2026-05-12 (morning)** — First formal reconciliation pass. W16/W17 status verified against `main` HEAD `9d2e117`. W03 status refined: catalog API side already pooled; operational adapter side still per-call. W05 scope verified at 9 plists (not 6 as Plan §W05 says). This file created as single source of truth.
- **2026-05-12 (morning)** — W05 + W05b merged + deployed (PRs #184, #185). 10 launchd services (not 6, not 9) now `ProcessType=Standard` on Mini. AMENDMENT A07.
- **2026-05-12 (mid-day)** — W14a complete. PRs #186 → #187 → #188 → #189 merged. 27 files routed through `core.db_targets`, 12 files received self-contained sys.path with install root. Surgical redeploy to Mini at 10:22 CDT; all 10 services healthy on W14a code with 37+ minute clean soak. Cohort guard test passing.
- **2026-05-12 (afternoon)** — Catalog design plan locked from operator/Claude dialogue. PR #190 merged. New doc at `strategy/05_CATALOG_DESIGN_PLAN_2026-05-12.md` (623 lines). New work items W26–W30 added. New AMENDMENTS A08/A09/A10. Phase order re-sequenced working backward from mid-August 2026 customer ship target.
- **2026-05-12 (evening)** — W01 (pmset portion) closed; May 11 Anthropic API key rotated and slack-commands restarted (PID 28448); D1-D7 all locked at defaults; Step 0 pre-W14 backup created and verified on Mini (24 MB operational + 596 KB catalog dumps, all 8 row counts match baseline). W23 partial fix — dashboards yml path bug closed; datasource user / password inlining deferred to W14b and W24 respectively.
- **2026-05-12 (evening, late)** — W26 audit complete. Query against live catalog: 89 of 98 tables already have `updated_at`; the 9 missing are all append-only event logs with existing `created_at`/`ingested_at` columns. Approach A locked (no schema migration; federation pull uses constant mapping). W26 status moved [ ] → [~] partial; remaining work reduced from "under 2h" to "under 30 min cohort guard test". Design plan §3 W26 updated with audit results and locked decision.
- **2026-05-12 (evening, latest)** — W14 Step 4 code pre-staged in `core/db_targets.py` (PR #197 merged). Backward-compatible by design: pre-W14 with catalog env vars unset, behavior is byte-identical to current; post-W14 with env vars set, catalog routes to port 5433 automatically. Smoke-tested on laptop (Python 3.14) and Mini (Python 3.12.7). Tomorrow's W14 Step 4 reduced from "edit Python + add env vars + restart services" to "scp file + add env vars + restart services." W26 cohort guard test landed at `tests/test_w26_catalog_timestamp_columns.py`; 3 tests all pass against live Mini catalog. W26 status moved [~] → [X] DONE.
- **Tomorrow (2026-05-13)** — ~~Planned: W14~~ → see entries below.
- **2026-05-13 (morning, 06:48-07:10 CDT)** — **W14 executed and closed.** Two-Postgres-instance split landed live on the Mini. Sequence (per [`strategy/W14_PREP.md`](strategy/W14_PREP.md)): Step 1 unloaded 12 scheduled launchd jobs (10 always-on kept running through the entire window) → Step 2 spun up `mg-catalog-db` (postgres:16-bookworm, port 5433, bind-mounted `/Library/Application Support/MiningGuardian/pgdata-catalog`) → Step 3 dropped empty bootstrap DB, restored from `pre-w14-catalog-20260512-121154.dump` via `pg_restore`, row counts matched baseline exactly (324/17/6/22/0) → Step 4 backed up live `db_targets.py` + `.env`, scp'd new resolver code from laptop, appended `GUARDIAN_PG_CATALOG_HOST=127.0.0.1` and `GUARDIAN_PG_CATALOG_PORT=5433` to `.env` → Step 5 bootout/bootstrap of all 10 always-on services (including `feedback-loop-daemon`, the 10th from A07), all came back on fresh PIDs in cluster 66707-66788 → Step 6 smoke gate (3 sub-checks): fresh Python resolver verified, `ai.catalog_context.get_catalog_context()` returned valid result for ANTMINER S19j Pro, `daily_deep_dive --dry-run` enumerated 72 online miners with correct model lookups → Step 7 `DROP DATABASE mining_guardian_catalog` on `mining-guardian-db` → Step 8 reload 12 scheduled jobs (back to 22 total). **Bug found and fixed mid-flight (see post-mortem doc):** Step 6 smoke caught a password-authentication failure on 5433 — root cause was `cut -d= -f2-` in my Step 2 `docker run` preserving literal single quotes around the password from `.env`, leaving the new container's `mg` role with a 66-char quoted password while applications send the 64-char unquoted value. Fixed by `ALTER USER mg WITH PASSWORD '<unquoted>'` inside the container. Smoke gate did its job: bug surfaced in 6a before any irreversible step. Post-W14 verification: `daily_deep_dive --dry-run` clean on the new topology, all 10 always-on services held PIDs through Step 7's drop. New entries in execution status: W14 `[X]`, W14b cleared to start, post-mortem doc added at `strategy/W14_POSTMORTEM_2026-05-13.md`.
- **2026-05-13 (late morning)** — **W14b convention lock landed** (PR #203). `CLAUDE.md` `## Coding Conventions` section added with two binding rules (Postgres access via `core.db_targets`, `.env` quote-stripping via `xargs`); both reference cohort guard tests. `.env.example` rewritten with two-instance topology + `GUARDIAN_PG_CATALOG_HOST=127.0.0.1`/`PORT=5433` defaults + quote-handling note. `installer/macos-pkg/scripts/lib/install_colima.sh` head docstring now documents the two-container provisioning requirement + the `--env-file` password-injection rule from the post-mortem. The actual `postinstall.sh` provisioning code change ships with W14 Step 10. **Cohort guard test #2 (`tests/test_w14_password_quote_consistency.py`)** also landed earlier (PR #202): verified-by-negation by temporarily re-injecting the W14 password bug on `mg-catalog-db`; test failed cleanly on catalog target with diagnostic pointing to the post-mortem doc, passed on operational; restored password, both back to PASS. **Scheduled-job verification on the new topology:** triggered `operator-review` (natural fire at 08:00 — exit 0), `morning_briefing` (manual via launcher — exit 0, Slack posted), `log_failure_report` (manual — exit 0). Pre-existing bugs surfaced in `db_maintenance.sh` (Colima socket path resolution under launchd context), `catalog_import` permissions, and stale `daily_deep_dive` last-run-date tracking; tracked separately, not in W14 scope.
- **2026-05-13 (afternoon, P-038 v2)** — **P-038 cohort got a second pass** when Grafana panel inspection during W25 setup surfaced surviving timestamp-slicing bugs. PR #206 fixed 19 timestamptz `[:N]` slice sites in production code (`api/dashboard_api.py`, `api/ai_dashboard_api.py`, intel-report renderers) where `datetime` objects from Postgres were being sliced like strings, producing TypeError at render time. PR #207 followed up with 14 HTML-rendering `[:19]` sites converted to `fmt_dt(...)` from `core.tz_utils` for type consistency. Cohort guard test now: 4 tests, all pass. PR #208 then deleted the `archive/` (legacy SQLite-era code, ~50 files) and `fixes/` (one-shot migration scripts, ~41 files) directories — 91 files, -15,898 LOC. Verified via static analysis that no current code path imports from either dir.
- **2026-05-13 (afternoon, Grafana restoration)** — **W25 + W25b + W26a landed back-to-back to bring the Mini's Grafana to a fully-working state.** PR #209 (W25) made dashboard_api `host`/`port` env-configurable via `MG_DASHBOARD_HOST`/`MG_DASHBOARD_PORT` (defaults `0.0.0.0:8585`); was hardcoded to `127.0.0.1`, blocking Tailscale iframe rendering. PR #210 (W25b) fixed `/fleet/board_stats` SQLite-era SQL that Postgres 16 strictly rejected — `DISTINCT ON (ip)` in subqueries + `m.model` added to outer GROUP BY. PR #211 (W26a) fixed the Intelligence Catalog dashboard's three distinct breakage modes (literal `\n` in markdown, Grafana 12.2+ bug #112418 datasource workaround via `jsonData.database` duplication, dashboard schemaVersion 16→39 + target-level datasource UID pin). Live-Mini after Grafana restart: all 5 catalog panels populate (10 schemas, 98 tables, firmware listing, formatted markdown documentation). W25/W25b/W26a all closed, W23 closed retrospectively (yaml path fixed in PR #193, user standardized in W14b). Mini now runs 9 dashboards total: 1 in repo's installer + 8 VPS-restored only on Mini → **W26b queued** to close that drift by mirroring the 8 into the repo.
- **2026-05-13 (mid-morning)** — **W14 Step 9 (D6) landed.** New backup pipeline: `scripts/backup_operational.sh` + `scripts/backup_catalog.sh` + `scripts/daily_backup.sh` (wrapper) + new launchd plist `com.miningguardian.scheduled.daily-backup.plist` scheduled for 02:00 CDT (operator-tunable, deferred per upcoming cron-schedule rearrangement). Each per-instance script: pre-flight checks container is up, `pg_dump -Fc` from inside the container (no plaintext password on the wire), verify dump with `pg_restore --list`, apply retention (default 7 most recent dumps, env-tunable via `MG_BACKUP_RETAIN_COUNT`, pre-W14 dumps deliberately not matched by the prune pattern so they remain). Wrapper runs both, returns non-zero if either fails. Three legacy VPS-era scripts (`backup_db.sh`, `backup_mining_guardian.sh`, original `daily_backup.sh`) — all referencing decommissioned `/root/Mining-Guardian` and SQLite `guardian.db` — renamed to `*.legacy-vps-decommissioned` so the breadcrumb is preserved without execution-path interference. **Solved a pre-existing bug as part of Step 9:** Colima socket path under launchd context. Setting `DOCKER_HOST="unix:///Users/miningguardian/.colima/default/docker.sock"` explicitly in the backup scripts bypasses the broken default-context resolution that's been failing `db_maintenance.sh` for days. Smoke verified end-to-end via `sudo /bin/bash scheduled_job_launcher.sh scripts/daily_backup.sh daily_backup` → exit 0, both dumps written + verified, 2-second wall time. Same fix should be applied to `db_maintenance.sh` in the post-W14 cleanup PR. Backup files live at `/Library/Application Support/MiningGuardian/backups/{operational,catalog}-YYYYMMDD-HHMMSS.dump`.
