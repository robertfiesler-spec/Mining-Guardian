# Execution Plan Status

> **Source of truth for W01–W25+ progress against the [Master Execution Plan](strategy/04_MASTER_EXECUTION_PLAN.md).**
> Append-only philosophy: when a status changes, add a row to the History section below the table; do not silently rewrite the table without a corresponding history line.
> Every `[X]` (done) and `[~]` (partial) MUST cite the evidence (commit, grep result, file path) that supports it.
> Companion: [`HANDOFF_2026-05-11_EVENING.md`](HANDOFF_2026-05-11_EVENING.md) (yesterday's handoff), [`strategy/RECONCILIATION_2026-05-12.md`](strategy/RECONCILIATION_2026-05-12.md) (today's grep receipts), [`strategy/AMENDMENTS_2026-05-12.md`](strategy/AMENDMENTS_2026-05-12.md) (plan deltas).

**Last reconciliation:** 2026-05-12 against `main` HEAD `a38b7fc` (PR #190 merge, catalog design plan locked).

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
| W14 | Split Postgres into two separate instances | `[ ]` | TOMORROW (2026-05-13) | Not started. Prep doc at [`strategy/W14_PREP.md`](strategy/W14_PREP.md). W14a (prerequisite) complete. D1–D7 decisions still at defaults. |
| W14b | Lock two-target convention in CLAUDE.md + .env.example + postinstall.sh | `[ ]` | — | Blocked on W14 landing. |

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
| W23 | Fix Grafana installer bundle bugs (yaml path + datasource user) | `[~]` | 2026-05-12 | **Dashboards yml path:** ✅ fixed in this PR (PR forthcoming) — `/usr/local/MiningGuardian/...` → `/Library/Application Support/MiningGuardian/...`. **Datasource user `guardian_app`:** investigation showed both `mg` and `guardian_app` are valid Postgres roles and the deployed datasource works as-is; not a bug, deferred to W14b where we standardize on `mg` across the codebase. **Password inlined in deployed yaml:** real concern but separate scope — deferred to W24 (password secret management). |
| W24 | Grafana password secret management | `[ ]` | — | Password currently inlined in deployed yaml on Mini. Needs proper handling before customer ship. |
| W25 | Grafana panel "No data" — debug or rebuild dashboards | `[ ]` | — | 3 May-era dashboards load but panels return 400 from Postgres-side. Bobby's preference: rebuild the 6 April-era branded dashboards instead. |
| W26 | `updated_at` discipline across catalog tables | `[~]` | 2026-05-12 | **Audit complete.** Query against live catalog shows 89 of 98 tables already have `updated_at`. The 9 missing are intentional append-only event logs (5 partitions of `raw_ingestion_log` plus `field_discovery_log`, `freshness_log`, `bitcoin_network_snapshots`) — all of which already have `created_at` or `ingested_at`. Approach A locked: do NOT add `updated_at` to append-only tables; federation pull uses a small constant mapping instead. Remaining work: ~30 min cohort guard test (no schema migration needed). See `05_CATALOG_DESIGN_PLAN_2026-05-12.md` §3 W26 for details. |
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
- **Tomorrow (2026-05-13)** — Planned: W14 (two-Postgres-instance split on master).
