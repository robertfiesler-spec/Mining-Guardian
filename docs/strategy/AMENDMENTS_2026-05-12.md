# Plan Amendments — 2026-05-12

> **Purpose.** Capture every meaningful delta between the [Master Execution Plan](04_MASTER_EXECUTION_PLAN.md) as written (2026-05-09) and reality as observed since. Keep the original Plan untouched as a historical artifact; treat this file plus [`../EXECUTION_PLAN_STATUS.md`](../EXECUTION_PLAN_STATUS.md) as the working layer.
>
> **Convention.** Each amendment has a stable ID `A##`. When applying an amendment, cite the ID in the commit message. New W-items get W23+; W-numbering never changes once assigned. Sub-items use suffix letters (e.g., `W14a` is a precursor to `W14`).

---

## A01 — W14 moves from Phase 4 to Phase 1.5, and W14a is added as its precursor (and W14b locks the convention)

**Decided:** W14 phase move agreed 2026-05-11 (operator). W14a + W14b added 2026-05-12 after a "what's best for the long term" review.

### Plan as written

W14 ("split Postgres into two separate instances") sits in Phase 4 (Weeks 5-6), labeled L-effort (~1 week). No precursor item, no follow-up convention work.

### Amendment summary

| Item | Where | What it does |
|---|---|---|
| **W14a** *(new)* | Phase 1.5, **before** W14 | Refactor 27 files that bypass `core/db_targets.py` to go through it. Behavior-identical. Adds a cohort guard test that fails CI on any new bypass. |
| **W14** *(moved)* | Phase 1.5, **after** W14a | The topology change. State A → State B. |
| **W14b** *(new)* | Phase 1.5, **after** W14 | Lock the two-target convention in `CLAUDE.md`, `.env.example`, and `installer/macos-pkg/scripts/postinstall.sh` so future writers (humans or AI sessions) follow it by default. |

**Sequence:** W14a → W14 → W14b → (Phase 2 starts).

### What W14 actually is (terminology)

A topology change for the Postgres deployment on the Mac Mini:

| | **State A — today** | **State B — W14 target** |
|---|---|---|
| Containers | 1 Docker container (`mining-guardian-db`) | 2 containers (`mg-operational-db`, `mg-catalog-db`) |
| Port | `127.0.0.1:5432` only | `127.0.0.1:5432` operational, `127.0.0.1:5433` catalog |
| `postgresql.conf` | One, shared | Two, tuned independently |
| Data volume | One Colima volume | Two volumes |
| Memory footprint | One process's `shared_buffers` | Two processes, sized for each workload |
| `max_connections` | One ceiling shared | Two ceilings tuned per side |
| Backup file | Single `pg_dumpall` covers both DBs | One `pg_dump` per instance |
| Crash blast radius | Container crash takes both DBs down | One crash, one DB down |
| Federation readiness | Catalog can't move to master-on-PC without filtering dump | Catalog instance moves as a unit |

State A was a deployment compromise; the original design called for State B (operator note May 9 in Report 1 §1.4 / Report 3).

### Why W14a exists

Code in this repo connects to Postgres one of two ways:

- **Pattern 1** — call `core.db_targets.operational_target()` or `catalog_target()`. The resolver returns the right host/port/dbname for the requested target. Topology-aware.
- **Pattern 2** — read `GUARDIAN_PG_HOST` and `GUARDIAN_PG_PORT` from `os.environ` directly. Topology-blind.

In State A both patterns work — same port for both DBs, only `dbname` differs. In State B, Pattern 2 silently breaks for catalog reads: those files keep hitting port 5432 looking for `mining_guardian_catalog`, which no longer exists there.

**Audit on `main` HEAD `9d2e117`:**

```bash
# Pattern 2 files (need refactor)
grep -rln "GUARDIAN_PG_HOST\|GUARDIAN_PG_PORT" --include='*.py' \
  | grep -v "core/db_targets.py" | grep -v "^tests/"
```

Three categories of result:

**Pure Pattern 1 (2 files — already correct, no work):**
- `intelligence-catalog/db/feedback_loop.py`
- `mg_import_tool/mg_import.py`

**Mixed (3 files — partially migrated during P-018B/C, need finishing):**
- `ai/catalog_context.py`
- `intelligence-catalog/catalog-api/catalog_api.py`
- `intelligence-catalog/db/dual_writer.py`

**Pure Pattern 2 (24 files — full refactor needed):**
- `ai/ai_score.py`, `ai/confidence_scorer.py`, `ai/daily_deep_dive.py`, `ai/fingerprint_builder.py`, `ai/hvac_correlator.py`, `ai/local_llm_analyzer.py`, `ai/predictor.py`, `ai/train_cohort.py`
- `api/ai_dashboard_api.py`, `api/ams_alert_listener.py`, `api/approval_api.py`, `api/dashboard_api.py`, `api/intelligence_report_api.py`, `api/slack_approval_listener.py`, `api/slack_command_handler.py`, `api/system_settings.py`
- `console/system_state.py`
- `core/database_pg.py`, `core/hashrate_evaluation.py`, `core/llm_analyzer.py`, `core/overnight_automation.py`
- `scripts/daily_log_failure_report.py`, `scripts/direct_collect_logs.py`, `scripts/morning_briefing.py`

**Total W14a scope: 27 files** (3 mixed + 24 pure Pattern 2).

These are stragglers from before P-018A/B/C introduced `db_targets.py`. P-018 migrated the highest-leverage call sites but didn't sweep the codebase.

### W14a includes a cohort guard test

In the spirit of `tests/test_p038_timestamptz_vs_text_sql_casts.py` (which guards W16's TO_CHAR cleanup), W14a lands `tests/test_w14a_no_direct_pg_env_reads.py`:

```python
"""W14a cohort guard — every Postgres connector goes through core.db_targets,
not os.environ.get('GUARDIAN_PG_*') directly. Pattern 2 (env-reading) silently
breaks when catalog moves to a separate instance in W14. See A01 in
docs/strategy/AMENDMENTS_2026-05-12.md."""

ALLOWED_BYPASSES = {
    # core/db_targets.py is the ONE place that resolves env vars
    "core/db_targets.py",
    # Tests may inspect env directly
}

def test_no_pattern_2_outside_db_targets():
    offenders = _grep_for_env_reads(exclude=ALLOWED_BYPASSES)
    assert not offenders, (
        "Files reading GUARDIAN_PG_HOST/PORT directly bypass core.db_targets. "
        f"Offenders: {offenders}. "
        "Use operational_target() or catalog_target() instead. "
        "See docs/strategy/AMENDMENTS_2026-05-12.md A01."
    )
```

The test is the convention's teeth. Without it, in 6 months someone (a future Claude session, a contractor, or a sleep-deprived 2am Bobby) adds a quick env-read in a new file, it works fine because the catalog also happens to be on port 5432 *during a transition window*, and the convention quietly decays. With the test, CI catches it on the next PR.

### Why W14b exists (locking the convention)

W14a's test enforces "don't read env vars directly." W14b makes the convention **discoverable** — so the test isn't the only way someone learns the rule.

W14b additions:

1. **`CLAUDE.md`** gets a new section under "Coding Conventions":

   > **Postgres connections.** All Postgres access goes through `core.db_targets.operational_target()` or `catalog_target()`. Never read `GUARDIAN_PG_HOST` or `GUARDIAN_PG_PORT` directly outside `core/db_targets.py` itself — the cohort guard `tests/test_w14a_no_direct_pg_env_reads.py` will fail CI. The operational and catalog DBs may live on different ports (W14 introduced this); the resolver handles that for you.

2. **`.env.example`** gains an explicit comment block above the `GUARDIAN_PG_*` section:

   ```
   # Mining Guardian uses TWO Postgres instances (W14, 2026-05-13ish):
   #   - operational DB on $GUARDIAN_PG_PORT (default 5432)
   #   - catalog DB on $GUARDIAN_PG_CATALOG_PORT (default 5433)
   # Python code MUST go through core.db_targets — do NOT read these vars directly.
   # See docs/strategy/AMENDMENTS_2026-05-12.md A01 for the why.
   ```

3. **`installer/macos-pkg/scripts/lib/install_colima.sh`** docstring at the top documents the two-container assumption.

These three touchpoints are the discoverable surface for future writers. The first place a fresh session reads is `CLAUDE.md` per its own kickoff protocol. The first thing an installer-debugger looks at is `.env.example` and `install_colima.sh`.

### Effort estimates (revised)

| Item | Plan estimate | Revised | Why |
|---|---|---|---|
| **W14a** *(new)* | n/a | M (3-5 days) | 27 files. Each file's refactor is mechanical (~5-10 LOC swap), but 27 of them plus a cohort guard test plus a CI run plus a Mini-side smoke test of each affected service. Cohort guard takes a few hours alone. |
| **W14** | L (~1 week) | M (3-4 days) — **smaller** than Plan estimate | With W14a done, W14 is "spin up second Docker container, `pg_dump`/restore the catalog, change one default in `_resolve_catalog_port`, update installer." The Plan estimated L because it assumed in-place sweep; the sweep is now W14a. |
| **W14b** *(new)* | n/a | XS (under an hour) | Three docstring/`.md` edits. |
| **Total Phase 1.5** | ~1 week (Plan) | **5-9 days** | W14a is the bulk; net is roughly the same total elapsed time but with cleaner rollback and a permanent convention. |

The handoff §4.2 estimated "2 weeks realistic" assuming cleanup happened inside W14. Carving out W14a gets us back closer to the Plan's L estimate while adding the convention-lock W14b.

### Sequencing constraint with other items

| Item | Relation to Phase 1.5 |
|---|---|
| W01 (cutover verification) | Independent. Proceed any time. |
| W02 (pg_stat_statements) | **Best after W14** so it's enabled on both instances with their final tunables. Could be done before, then re-applied. |
| W03 (connection pool in `core/database_pg.py`) | **Order matters.** W03 and W14a both touch `core/database_pg.py`. W14a should land first (refactor to use `db_targets`), then W03 adds the pool to the refactored adapter. Doing them in the other order means the pool gets added against Pattern 2, then has to be retouched in W14a. |
| W04 (Postgres tuning) | **Best after W14**. Tunables differ between operational and catalog; doing it once on State A means re-doing it after the split. |
| W05 (ProcessType) | Independent. Proceed any time. |
| W06-W09 (catalog reads) | **Must wait for W14 complete.** These are new catalog queries; they should land against State B topology directly. |
| W10-W13 (external intake, operator surfaces) | **W11 specifically writes to catalog tables; must wait for W14.** W10, W12, W13 are independent. |

### Revised Phase order

```
Phase 1   — Foundation                        W01, W02, W03, W04, W05
Phase 1.5 — Architectural restoration         W14a (cleanup) → W14 (split) → W14b (convention-lock)
Phase 2   — Closing the integration gap       W06, W07, W08, W09
Phase 3   — External intake & operator surfs  W10, W11, W12, W13
Phase 4   — Architectural correctness         W15, W16 (done), W17
Phase 5   — Performance polish                W18, W19, W20, W21, W22
```

W14 keeps its number per the Plan's stability rule. W14a / W14b are new sibling sub-items.

---

## A02 — W05 scope expands from 6 plists to 9

**Decided:** 2026-05-12, after grep audit.

**Plan as written:** W05 lists exactly 6 plists to flip from `Background` to `Standard`:
`scanner`, `alerts`, `approval-api`, `dashboard-api`, `slack-listener`, `slack-commands`.

**Amendment:** W05 covers **9 plists** — the 6 above plus `console`, `intelligence-report`, and `overnight-automation`.

**Rationale.** All 9 are always-on services with `RunAtLoad=1, KeepAlive=1`, not batch jobs. The 3 the Plan missed:

| Service | What it does | Why Standard |
|---|---|---|
| `console` | Web UI on `127.0.0.1:8787`, operator task panel | Operator-facing; throttled UI is worse than throttled batch |
| `intelligence-report` | Flask API on `localhost:8590`; serves Grafana iframes and `/api/discoveries`; W11's `/intel` lands here | Interactive HTTP |
| `overnight-automation` | Long-running service that auto-executes LOW-RISK actions during 10pm–6am (firmware restart, PDU cycle) per `core/overnight_automation.py` | Time-sensitive autonomous decisions; Background throttling could delay AUTO actions |

If any of the 3 should remain `Background`, drop those lines from the patch — single-line revert per plist.

**Patch ready:** `patches/w05_processtype_standard.patch` covers all 9.

---

## A03 — W03 status refined: half-done, not undone

**Recorded:** 2026-05-12.

**Plan as written:** W03 ("Add Postgres connection pool to GuardianPGDB") implies the work is fully outstanding.

**Reality:** W03 is already half-done.

- `intelligence-catalog/catalog-api/catalog_api.py` already uses `psycopg2.pool.ThreadedConnectionPool` — that side is done.
- `core/database_pg.py` (the operational adapter) is still per-call. Header docstring lines 22–24, 27–29 explicitly say *"conn is checked out per-call (no pool today — simple for correctness)"* and *"Connection pooling (add when we deploy)"*.

Report 1 §2.1 estimates ~500 connections per scan land in the operational path, so the operational adapter is the higher-volume side. The half that's already done (catalog API) is good news but doesn't close the leverage Report 1 was citing.

**Sequencing note.** Per A01, W14a touches `core/database_pg.py` to migrate it to `db_targets`. **W03 should land after W14a**, so the pool gets added to the post-refactor adapter rather than getting redone after the refactor.

---

## A04 — W17 status corrected (prior chat misreported)

**Recorded:** 2026-05-12, after the §5 step 2 grep.

**Prior chat assertion:** W17 was "20-30% done" because PR #180 (the `fmt_dt` helper) touched datetime code.

**Reality:** PR #180 was a *different* datetime fix — it handles `s.get('last_seen', '')[:16]` slicing bugs where Python code assumed datetime values were strings. W17 is the `datetime.now()` → `datetime.now(timezone.utc)` sweep, which is **essentially untouched** (151 naive calls remain in `ai/core/api/scripts/`; 18 tz-aware calls exist as baseline).

Both touch datetime, both are real, but completing one does not close the other.

Verbatim grep output: [`RECONCILIATION_2026-05-12.md`](RECONCILIATION_2026-05-12.md).

---

## A05 — New W-items from 2026-05-11 Grafana stand-up

**Recorded:** 2026-05-12.

The handoff §4.4 surfaced three Grafana follow-ups not in the original Plan. Captured here so they have stable W-numbers and won't get lost.

### W23 — Fix Grafana installer bundle bugs

| Field | Value |
|---|---|
| Effort | XS (under an hour) |
| Risk | Low |
| Phase | Phase 5 or sooner if it gets in the way |

**What to do.** Two files in `installer/macos-pkg/resources/grafana/`:

- `provisioning/dashboards/mining_guardian.yml` — fix the path: `/usr/local/MiningGuardian/grafana/dashboards` → `/Library/Application Support/MiningGuardian/grafana/dashboards`. The README in the same directory documents the correct path; the yaml was never updated.
- `provisioning/datasources/mining_guardian.yml` — fix the user: `user: guardian_app` → `user: mg`. The actual `.env` has `GUARDIAN_PG_USER=mg`.

**Status of repo vs Mini.** The Mini was patched on-disk on 2026-05-11 with `sed` + `.bak`. The repo still has the bugs. Next Mini install from the .pkg would re-introduce them.

### W24 — Grafana password secret management

| Field | Value |
|---|---|
| Effort | S |
| Risk | Medium |
| Phase | Before customer ship |

**Problem.** `brew services` regenerates the LaunchAgent plist on every start, wiping `EnvironmentVariables`. So `${GUARDIAN_PG_PASSWORD}` env-substitution in the datasource yaml doesn't work without inlining the password. The 2026-05-11 workaround inlined the literal 64-char password into the yaml. Acceptable for the operator's PoC Mini; not acceptable for customer ship.

**Options to evaluate (defer the decision to when we get there):**

- Wrapper script that reads `.env` and writes the resolved yaml at service start
- Grafana's own secret store
- Move datasource provisioning out of yaml entirely and use the Grafana provisioning API at install time

### W25 — Grafana panel "No data" — debug or rebuild

| Field | Value |
|---|---|
| Effort | M |
| Risk | Low |
| Phase | When operator wants dashboards working |

**Symptom.** 3 dashboards under "Mining Guardian" folder load but panels render "No data" (green text, not red errors). Grafana log shows `/api/ds/query → status=400 status_source=downstream`. Postgres-side error, likely SQL syntax mismatch between Postgres 16 and the May-era dashboard queries.

**Two diagnostic paths (in order of preference):**

- **Path A (preferred)** — Fix the queries in the existing dashboards. Per operator clarification 2026-05-12 evening: *"i did not know i said rebuild them i just want them working, they already were close to perfect."* The dashboards were close to perfect before the panels broke; the goal is to get them WORKING, not to throw them out. Debug the Postgres-side 400 errors, likely SQL syntax mismatches between Postgres 16 and the May-era queries.
- **Path B (fallback only)** — If Path A reveals the existing dashboards are unrecoverable (e.g., schema drift too severe to fix economically), regenerate from `archive/tmp_scripts_apr08/grafana_brand_dashboards.py`. This is a **fallback**, not a preference. Operator wants the existing dashboards working, not replaced.

**Correction note (2026-05-12 evening):** An earlier version of this amendment (and the docs derived from it) claimed "Operator preference per 2026-05-11: Path B." That was a misinterpretation — the operator did not lock Path B; the operator wants the existing dashboards working. This amendment is corrected. Future-Claude reading the older HANDOFF_2026-05-12_EVENING.md morning section should treat the "Path B preference" line there as obsolete; the live position is what's written here.

---

## A06 — Plan §"Working Principles" gets a new principle: convention enforcement

**Recorded:** 2026-05-12.

The Master Plan's "Working Principles for the Whole Plan" section captures things like "commit per work item," "test discipline," "rollback discipline." Add a sixth:

> **On conventions: enforce them in tests, document them in `CLAUDE.md`.** When a refactor establishes a convention (e.g., "all Postgres connections go through `core.db_targets`" from W14a), land a cohort guard test that fails CI on regressions and add one line to `CLAUDE.md` so future writers — humans or AI — discover the rule before they break it. The test is the convention's teeth; the docs are its discoverability.

Rationale: this is the discipline that produced the existing cohort guards (`tests/test_p038_timestamptz_vs_text_sql_casts.py`, `tests/test_no_retired_host_defaults.py`, `tests/test_p023_no_retired_hosts_in_shipped_payload.py`). Making it explicit in the principles list means it gets applied more consistently to future W-items.

---

## A07 — W05b: feedback-loop-daemon is the 10th always-on service

**Recorded:** 2026-05-12 (after PR #184 merged and was deployed to the Mini).

During the Mini-side W05 deployment, `sudo launchctl list | grep com.miningguardian` surfaced a 10th always-on service we hadn't audited: `com.miningguardian.feedback-loop-daemon`, running as root with PID 80022 (older than the 83xxx range the W05 bootout/bootstrap produced).

**What feedback-loop-daemon is.** The C5 NOTIFY/LISTEN feedback daemon shipped in D-14 PR 4a. Mirrors `deploy/feedback-loop-daemon.service` for VPS parity. Runs `intelligence-catalog/db/feedback_loop_daemon.py` and listens on Postgres `catalog_feedback` channel via LISTEN. Event-driven — idle when the channel is quiet, which is most of the time today since the closed learning loop (W06–W11) isn't fully wired yet.

**State before W05b:** `ProcessType: Background`, NOT in `installer/macos-pkg/resources/launchd/` despite being deployed (manual install, presumably during D-14 work on May 5–9). Logs show healthy lifecycle through three restart cycles 2026-05-08 → 2026-05-09; quiet since 10:59 May 9 because the channel is quiet, not because the daemon is broken.

**Amendment.**

| Item | Change |
|---|---|
| Repo bundle | Add `installer/macos-pkg/resources/launchd/com.miningguardian.feedback-loop-daemon.plist` (didn't exist before this PR) |
| ProcessType | `Background` → `Standard` (matches the W05 rationale for always-on services) |
| `scripts/apply_w05_processtype.sh` | `SERVICES` array grows from 9 to 10; this script reused for the W05b deployment |
| W05 scope | Now covers 10 services. Plan said 6, then A02 said 9; reality is 10 |

**Risk.** Low. Single 1-line change in plist plus 1-line change in script. Same bootout/bootstrap pattern proven on the other 9 services in W05.

**Why the daemon was missing from the installer bundle is still unknown.** D-14 PR 4a should have committed the plist. Worth a `git log -- installer/macos-pkg/resources/launchd/com.miningguardian.feedback-loop-daemon.plist` once after merge to confirm whether this PR is the first time it lands in the repo or whether it was deleted at some point.

---

---

## A08 — New phase order locked, working backward from mid-August customer ship

**Decided:** 2026-05-12, after the catalog design dialogue with operator. Full design in [`05_CATALOG_DESIGN_PLAN_2026-05-12.md`](05_CATALOG_DESIGN_PLAN_2026-05-12.md) §3.

### Plan as written

The Master Plan ([`04_MASTER_EXECUTION_PLAN.md`](04_MASTER_EXECUTION_PLAN.md)) had this order:

- Phase 2 (W06–W09): Closing integration gap — Weeks 2–3
- Phase 3 (W10–W13): External intake & operator surfaces — Week 4
- Phase 4 (W14–W17): Architectural correctness — Weeks 5–6
- Phase 5 (W18–W22): Performance polish — Weeks 7–8
- Phase 6: Federation — Months 3–6

### Amendment summary

Operator-locked ship target: mid-August 2026. Federation cannot wait for "Months 3–6" because customer Minis depend on it from day one. Three new W-items (W26, W27, W30) are required to deliver on the catalog mission stated by operator ("foremost authority of btc miners in the world"). New order:

- ✅ Phase 1.5 (W14a → W14 → W14b) — this week
- **Phase 2 (W10 → W11)** — next 2 weeks — Slack `/intel` lights up daily Perplexity ingest
- **Phase 2b (W06 → W07 → W08 → W09)** — following 2 weeks — AI reads catalog; daily Pass 2 catalog-aware
- **Phase 3 (W26 → W27 → W30)** — June — `updated_at` discipline + field_observed_specs + Layer 2.5 + enrichment CSV extraction
- **Phase 3b (W23/W24/W25 + W12)** — late June — Grafana intelligence dashboard rebuild
- **Phase 4 (W28 + W29)** — July — federation v1 + Pass 2 cadence flag + customer installer two-instance support
- **Phase 5** — first two weeks August — bake / notarization / dry run
- **Phase 6** — post-August — old performance polish (W15, W17, W18–W22) returns

W15 (knowledge.json split) and W17 (tz-aware datetime sweep) move from Phase 4 to post-August because neither blocks customer ship and both are improvements to a working system.

### Why this re-sequencing

The Plan was written without knowing two key operator preferences clarified 2026-05-12:

1. **Daily Pass 2 (not weekly).** Per [`05_CATALOG_DESIGN_PLAN_2026-05-12.md`](05_CATALOG_DESIGN_PLAN_2026-05-12.md) §1.3 (OPERATOR-CADENCE-1), the operator runs the deep dive every day. That multiplies W09's value by ~7 and makes it Tier 1 priority for master.

2. **Federation before customer ship, not after.** Per [`05_CATALOG_DESIGN_PLAN_2026-05-12.md`](05_CATALOG_DESIGN_PLAN_2026-05-12.md) §2, customer Minis pull from master monthly. Cannot ship customer Minis in August without federation v1 already running.

---

## A09 — W11 effort revised M → M-L; two intake patterns; Approve-All UX

**Decided:** 2026-05-12, after reviewing actual Perplexity watcher output format.

### Plan as written

[`04_MASTER_EXECUTION_PLAN.md`](04_MASTER_EXECUTION_PLAN.md) W11: M effort (3–4 days). Single intake pattern: `/intel <event_type> "<raw_text>"`. Single confirmation card.

### Amendment summary

Reality of operator workflow (from chat 2026-05-12 "Q1: I look on the chat daily that they are running out of" + the pasted morning Perplexity output sample):

- Operator reads ONE Perplexity chat per morning that contains output from all 3–4 scheduled watchers
- Most days are "nothing new" days — each watcher reports a freshness check, not a content finding
- A "nothing new" report is itself catalog data and must be recorded via `record_freshness_check`
- The duplicate-digit gotcha is real (`886886 TH/s` instead of `886 TH/s`) and requires explicit preprocessing

Full design in [`05_CATALOG_DESIGN_PLAN_2026-05-12.md`](05_CATALOG_DESIGN_PLAN_2026-05-12.md) §4. Highlights:

- **Two intake patterns:** `/intel paste` (primary, daily) + `/intel <type> "<text>"` (ad-hoc)
- **Approve-All UX:** Slack Block Kit card with separate buttons for freshness checks (bulk approve) vs. content findings (individual review). Keeps daily operator time ~30 seconds.
- **Structure extractor preprocessing:** regex `\b(\d+)\1\b → \1` to collapse duplicate-digit paste artifacts (PERPLEXITY-PASTE-1).
- **W10 grows by one propose function:** `propose_community_intel` for watch-item-type findings (e.g., "treat S23 series specs as rumor unless corroborated"). Original W10 had 4 new functions; now 5.

Effort revised from M (3–4 days) to **M-L (5–7 days)**.

---

## A10 — W30 added: enrichment CSV structured extraction

**Decided:** 2026-05-12, after operator described the "parts section" complaint.

### Plan as written

The Plan did not include any work to extract structured rows from `intelligence-catalog/data/miner_enrichment_master.csv`. The CSV has been read by the Intelligence Report API for display, but never promoted to structured catalog rows.

### Amendment summary

Operator complaint 2026-05-12:

> *"Under parts it should be listing the chip type and number control board types and brands, hashboard types and numbers."*

Root cause: the data exists in `miner_enrichment_master.csv` freeform fields (especially `Distinguishing Features`, `PSU Requirements`) but has never been parsed into the structured `hardware.chips`, `hardware.psu_models`, `hardware.control_boards`, `hardware.hashboards` tables. Today `hardware.chips` has 4 rows but the CSV references 30+ distinct chip models.

Full spec in [`05_CATALOG_DESIGN_PLAN_2026-05-12.md`](05_CATALOG_DESIGN_PLAN_2026-05-12.md) §5 W30. M effort (3–4 days). One-shot importer at `intelligence-catalog/seed-data/extract_structured_specs_from_csv.py`. Targets bring:

- `hardware.chips` from 4 → 30+ rows
- `hardware.psu_models` from 0 → 50+ rows
- `hardware.miner_models.voltage_min/voltage_max` from mostly NULL → 270+/317 populated
- `hardware.miner_models.release_date` from 15% → 90%+ populated

This is the gap that makes the catalog feel empty today. Lands in June per A08 phase order.

---

## How to use this file in commits and chat

When applying any amendment:

```
feat(W14a): refactor 27 Postgres-touching files to use core.db_targets (A01)
test(W14a): cohort guard against direct GUARDIAN_PG_HOST reads (A01)
docs(W14b): document two-target convention in CLAUDE.md (A01, A06)
```

When opening a fresh chat or handing off:

> *Working on W14a per AMENDMENTS A01. The 27-file list is in docs/strategy/AMENDMENTS_2026-05-12.md. Cohort guard test is required per A06. The CLAUDE.md and .env.example edits are W14b and come after W14.*

That single paragraph gives a fresh Claude session everything it needs.
