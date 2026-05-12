# Intelligence Catalog Design Plan — 2026-05-12

> **Purpose.** Capture every architectural decision and work-item commitment made during the 2026-05-12 catalog design dialogue between operator (BigBobby) and Claude. This document is the definitive reference for how the intelligence catalog is supposed to work, who writes to it, who reads from it, how customer Minis fit into it, and what gets built between today and the mid-August 2026 customer ship target.
>
> **Status.** Operator-approved. Frozen as of 2026-05-12 22:30 CDT. Subsequent changes belong in `AMENDMENTS_<date>.md` referencing the relevant section here.
>
> **Companion docs.**
> - [`04_MASTER_EXECUTION_PLAN.md`](04_MASTER_EXECUTION_PLAN.md) — the 22-item W## plan written 2026-05-09. This document amends and re-sequences it via [`AMENDMENTS_2026-05-12.md`](AMENDMENTS_2026-05-12.md) `A07–A12`.
> - [`02_TWO_DATABASE_DEEP_DIVE.md`](02_TWO_DATABASE_DEEP_DIVE.md) — the architectural read of the operational↔catalog interaction. Most assertions in §1–§3 here cite back to it.
> - [`../INTEL_CATALOG_FULL_BRIEF_2026-05-02.md`](../INTEL_CATALOG_FULL_BRIEF_2026-05-02.md) — the comprehensive synthesis of catalog state as of 2026-05-02 (94 tables, ~502 rows, top-10 enrichment gaps).
> - [`../INTELLIGENCE_CATALOG_STATUS.md`](../INTELLIGENCE_CATALOG_STATUS.md) — the P-021 (2026-05-07) two-DB cooperative banner and live update flow.
> - [`../../mg_import_tool/README.md`](../../mg_import_tool/README.md) — the 5,400-line drag-and-drop archive importer that stays on the master and never ships to customers.

---

## 0 · The North Star (operator statement, verbatim)

From operator on 2026-05-12 in this session's design dialogue:

> *"The goal is to make the most comprehensive db on bitcoin only miners on the planet that is getting updated daily with these auto jobs being performed daily. Then using the library as you referenced it as a resource to make our llm and claude analysis so much more accurate. The database is supposed to have 2 sections sort of, manufacture listed specs and real world specs if there is data that has been collected. I want this to be a centerpoint and the foremost authority of btc miners in the world."*

This reframes the catalog from "supporting subsystem" to **product centerpiece**. Mining Guardian is partly a fleet manager and partly the data-collection engine that feeds the master catalog. The catalog ships with customer Minis (read access) and grows through:
1. Daily Perplexity findings (operator-curated)
2. Friend archive imports (mg_import_tool, master-only)
3. Operator's own fleet feedback loop (live today)
4. Monthly two-way sync with customer Minis (starts post-August ship)

Cite this statement as **NORTH-STAR-1** in commit messages when work directly serves the centerpiece goal.

---

## 1 · The locked architecture

### 1.1 Two-section data model

The catalog has two distinct kinds of fact about every miner model:

| Section | Shape | Source | Tables |
|---|---|---|---|
| **Factory specs** | Static single values per model | Manufacturer pages, watchers, manual entry | `hardware.miner_models`, `hardware.chips`, `hardware.psu_models`, `hardware.hashboards`, `hardware.control_boards`, `firmware.firmware_releases` |
| **Real-world specs** | Observed **ranges** per model, possibly per site / cooling-type / firmware-version | `mg_import_tool` archive imports + feedback loop + customer Mini contributions | `ops.field_observed_specs` *(new — see §3.4)*, `market.war_stories`, `ops.failure_patterns`, `hardware.model_known_issues`, `ops.environmental_correlations` |

**Schema is already shaped for this.** `INTEL_CATALOG_FULL_BRIEF_2026-05-02.md` §5 explicitly says: *"Factory specs ≠ field-observed data: `hardware.*` holds factory specs; `market.war_stories` and `ops.failure_patterns` hold field observations. Never conflate."* This plan extends that pattern with a dedicated `ops.field_observed_specs` table for quantitative ranges (hashrate, power, efficiency, temperatures) as distinct from narrative observations (war stories) and pattern matches (failure patterns).

**Operator-locked decision (2026-05-12, Q5):**

> *"Sounds like this is already designed in I would lean towards option b."*

Where "option b" was: *"Two separate views/tabs ('Factory specs' vs 'Field intelligence')"* in Grafana. So the read API exposes both sections distinctly, and the Grafana intelligence dashboard rebuild (see W25) presents them as two named panels.

### 1.2 The four loops

Every byte that enters the master catalog comes through exactly one of these four pathways. Diagram form lives in chat history 2026-05-12 (visualization `catalog_design_locked`).

| Loop | Status today | Target |
|---|---|---|
| **Loop 1 — Perplexity intake** | ❌ Broken. Watchers produce output daily; output lands in operator's Perplexity chat, never reaches the catalog. | Slack `/intel paste` (W11). Operator pastes morning chat; structure extractor identifies findings; freshness checks land via `record_freshness_check`, content findings land via the other propose_* functions with operator Approve/Reject. |
| **Loop 2 — Friend archive imports** | ✅ Working for operational tables. Importer (`mg_import_tool`) accepts CSV/JSON/SQL/XLSX/ZIP/TAR/TGZ/RAR; resolves miner_type via two-tier alias resolver (12,852 + 1,494 rows); writes to `knowledge.field_log_*` and `mg.miners`. **Does NOT currently feed `mining_guardian_catalog`.** | Extend importer with a Layer 2.5 that computes summary stats per archive and writes them to `ops.field_observed_specs` tagged with `site_id` provenance. Friend data enriches catalog real-world ranges (operator answer Q3 — see §1.4 below). |
| **Loop 3 — Operational feedback** | ✅ Working. `feedback_loop_daemon` LISTENs for NOTIFY catalog_feedback, aggregates from `public.action_audit_log` / `llm_analysis` / `miner_restarts` into `ops.failure_patterns` / `market.war_stories` / `hardware.model_known_issues` within ~100ms. | No changes needed for v1. Customer Minis run the same daemon against their own local catalog; their writes flow back to master via monthly pull (Loop 5). |
| **Loop 4 — AI consumers** | ⚠️ Partial. `ai/catalog_context.py` reads only 6 of 95 catalog tables. Daily deep dive (Pass 2) reads zero catalog tables. | W06+W07+W08 add reads of `hardware.model_known_issues`, `market.war_stories`, `ops.environmental_correlations`. W09 adds catalog awareness to daily Pass 2. |

A fifth pathway — Loop 5, the monthly federation cycle — connects customer Minis to the master and is detailed in §2.

### 1.3 Daily Pass 2 is daily, not weekly (operator correction)

The `04_MASTER_EXECUTION_PLAN.md` description of W09 ("Pass 2 weekly training reads the catalog") assumes a Sunday-only cadence. Operator clarification on 2026-05-12:

> *"So I know you do not know this but we have been doing the weekly deep dive everyday, and I will continue to do that for my system. It will not go to a weekly thing until we start putting it on customers' computers. So it is important that it hits because it was a daily thing not weekly."*

**Implication.** W09's value is daily-multiplied (×7 vs. the Plan's assumption), and W09 becomes Tier 1 priority for the operator's master, not "Phase 2 nice-to-have." On customer Minis it falls back to weekly cadence (lower-resource sites, cohort training is less time-sensitive when site is the unit not the world). The script (`ai/refinement_chain.py` invoking Pass 2) needs a config flag `PASS_2_CADENCE = daily | weekly`, defaulting to daily for master and weekly for customer Minis.

Cite this as **OPERATOR-CADENCE-1**.

### 1.4 Friend imports enrich real-world ranges (operator answer Q3)

Operator on 2026-05-12 when asked whether friend archive imports should feed master catalog or stay siloed in operational tables:

> *"I think it would be added to the real world numbers of that particular model so the real world numbers would have ranges and the factory specs would be a static number."*

**Implication.** The mg_import_tool gains a new post-processing step that runs after the existing Layer 2 alias resolution. For each imported archive:

1. Existing Layer 2 already resolves `miner_type` to a `miner_model_id` (or writes to `mg.unresolved_models` for review).
2. **NEW** Layer 2.5 — `aggregate_field_observed_specs()`:
   - For each `miner_model_id` represented in the archive, compute hashrate min/median/max from `knowledge.field_log_power_samples` and `knowledge.field_log_api_stats`
   - Compute power min/median/max similarly
   - Derive efficiency J/TH from the hashrate ÷ power ratio
   - Pull cooling_type from the archive metadata where detectable (Antminer logs sometimes have it; WhatsMiner needs operator hint or default to `air`)
   - Pull firmware_at_observation from the archive header
   - Write one row to `ops.field_observed_specs` tagged with `site_id` and `primary_source_id`
3. The cross-site aggregate ("global real-world range for model X") is then a `GROUP BY miner_model_id` aggregate over all site contributions, which the Grafana dashboard panel queries directly.

This means the same physical Antminer S21 Pro observed at three sites with different cooling produces three rows in `ops.field_observed_specs`; the Grafana panel rolls them up. Cooling type is a critical dimension — an S21 Pro on immersion has a fundamentally different efficiency curve from one on air, so naive averaging across cooling types would lie.

Cite this as **OPERATOR-RANGES-1**.

---

## 2 · Federation — the monthly two-way sync (operator answer Q2)

Operator on 2026-05-12:

> *"The master stays here, every month I pull data from the customer what his intelligence db learned and what his operations db learned, all of those files get added here to the masters then new files with all the new information gets pushed out to the customers."*

This locks **bidirectional monthly sync** with master-on-operator-PC. Diagram in chat history `catalog_design_locked`.

### 2.1 Monthly cycle steps

| Step | What | Who | Frequency |
|---|---|---|---|
| 1 | Pull catalog deltas + operational learnings from each customer Mini | Operator (script) | Monthly, manual trigger |
| 2 | Merge customer pulls into master catalog with conflict resolution | Operator (script) | Monthly, immediately after step 1 |
| 3 | Add operator's own new findings (Perplexity intake, mg_import_tool, own fleet observations from feedback loop) | Already daily via Loops 1-3 | Continuous |
| 4 | Push merged master catalog back to each customer Mini | Operator (script) | Monthly, after step 2 |

**Operator-locked cadence:** Calendar-driven monthly, but **operator-controlled trigger** (not automated cron). Per operator preference — "every month" but kicked off when operator runs the script. This avoids automation failures while operator is away or focused elsewhere.

### 2.2 Conflict resolution policy

When two sites disagree on the same fact (same `miner_model_id`, same field, different values), the merge follows this precedence:

1. **Bobby-verified always wins.** Any row with `verified_by_bobby=TRUE` or `bobby_experienced=TRUE` is immutable to incoming customer data. Schema already supports this — most catalog tables have these columns. Cite [`02_TWO_DATABASE_DEEP_DIVE.md`](02_TWO_DATABASE_DEEP_DIVE.md) §"Bobby's verification is the trump card".
2. **Higher `n_observations` wins.** For real-world ranges in `ops.field_observed_specs`, the row backed by more samples wins. Tie goes to most-recent.
3. **More recent `updated_at` wins.** Falls back when neither bobby_verified nor n_observations breaks the tie.

This policy is implemented in the merge script (see W28).

### 2.3 Schema migration discipline

Per [`02_TWO_DATABASE_DEEP_DIVE.md`](02_TWO_DATABASE_DEEP_DIVE.md) §"Schema evolution across the fleet": when master gains a column, every customer Mini needs that column before next push. The monthly push begins with a schema-migration phase that runs pending `migrations/0NN_*.sql` files committed since the last sync, then proceeds to data sync.

This means **migrations are forever versioned**, and the customer Mini stores its last-applied-migration timestamp so the push script knows what to ship. v1 implementation in W28.

### 2.4 Customer-side review tier (operator decision deferred)

Open question from chat history Q3 of the design dialogue:

> When a customer Mini's feedback loop writes a `war_story` from their fleet, on monthly pull operator either:
> (a) Auto-merge into master with `n_observations += 1` on matching real-world spec
> (b) Review every customer contribution, flag bobby_verified TRUE/FALSE, then merge
> (c) Reject entirely

Operator did not answer this directly before requesting the plan be written. **Default for v1:** option (a) — auto-merge with conflict resolution per §2.2, but record every customer contribution in a `knowledge.customer_contribution_log` table (new — see W28). Operator can review the log after merge and flag/correct anything that smells wrong. Errors are correctable; missed contributions are not.

Cite this as **DEFAULT-MERGE-1**, subject to operator override before W28 implementation.

### 2.5 Operational data does NOT federate

Per the deep dive doc: *"Per-site telemetry (scans, miner_readings, miner_restarts, llm_analysis) is local to each site. It would be wasteful to push 18M+ rows of one site's miner readings to other sites. The right boundary is: catalog federates, operational does not."*

What flows back from customer to master is **only catalog-shaped data** (rows in `mining_guardian_catalog.*`). Raw operational telemetry stays on the customer Mini. The customer's feedback loop daemon has already done the work of distilling telemetry into catalog rows; only those distilled rows migrate.

### 2.6 Customer Minis run two Postgres instances too

Federation requires every customer Mini to have **physically separated operational and catalog databases** so pull/push can move catalog as a unit without entangling operational data. This means W14 (the two-Postgres-instance split landing on master tomorrow, 2026-05-13) **must also ship in the customer .pkg installer for August**. The Plan's W14 already implies this in its "Definition of Done" — `postinstall.sh` provisions both instances on fresh installs. This plan re-asserts that as non-negotiable for August.

---

## 3 · New work items (W23–W29)

Cross-references the existing `04_MASTER_EXECUTION_PLAN.md` W## numbering. The next W-number is W26 (W23, W24, W25 were already added 2026-05-12 morning per `AMENDMENTS_2026-05-12.md` A05 for Grafana work). This plan adds **W26–W29**.

### W26 — `updated_at` discipline across catalog tables

**Source:** [`02_TWO_DATABASE_DEEP_DIVE.md`](02_TWO_DATABASE_DEEP_DIVE.md) §"Operational learnings flowing back to master": *"Most catalog tables already have updated_at; the ones that do not should add it as part of preparing for federation. This is a tiny migration."*

**Effort:** XS (under 2 hours)
**Risk:** Low — pure additive schema change
**Files:**
- `migrations/0NN_catalog_updated_at_columns.sql` *(new)*
- Cohort guard test: `tests/test_w26_all_catalog_tables_have_updated_at.py` *(new)*

**What to do.** Audit every table in `mining_guardian_catalog` for an `updated_at TIMESTAMPTZ` column with a trigger that maintains it. For tables missing it: `ALTER TABLE x ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();` + trigger. The cohort guard test queries `information_schema` and fails if any catalog table lacks the column.

**Why now.** Federation v1 (W28) does delta pulls via `WHERE updated_at > last_sync_ts`. Without consistent `updated_at` discipline, the pull silently misses rows or duplicates them.

**Definition of done.** Every catalog table has `updated_at`. Cohort guard passes. Manual `UPDATE` of any row touches the column.

---

### W27 — `ops.field_observed_specs` table + mg_import_tool Layer 2.5

**Source:** §1.4 of this plan (OPERATOR-RANGES-1).

**Effort:** M (3-5 days)
**Risk:** Medium — touches mg_import_tool which has 178 tests; new aggregation code needs its own tests; new table needs Grafana panel updates
**Files:**
- `migrations/0NN_create_ops_field_observed_specs.sql` *(new)*
- `mg_import_tool/aggregator.py` *(new)* — the Layer 2.5 aggregation logic
- `mg_import_tool/mg_import.py` — call into aggregator from `_do_layer2_postprocessing`
- `mg_import_tool/tests/test_aggregator.py` *(new)*
- Grafana dashboard updates (covered in W25)

**Schema.**

```sql
CREATE TABLE IF NOT EXISTS ops.field_observed_specs (
  id BIGSERIAL PRIMARY KEY,
  miner_model_id UUID NOT NULL REFERENCES hardware.miner_models(id),
  site_id TEXT NOT NULL,  -- 'bobby_master', 'friend_jay', 'customer_3', etc.
  observation_window_start TIMESTAMPTZ NOT NULL,
  observation_window_end TIMESTAMPTZ NOT NULL,
  n_miners_observed INTEGER NOT NULL,
  n_samples BIGINT NOT NULL,
  hashrate_th_min NUMERIC(10,2),
  hashrate_th_p50 NUMERIC(10,2),
  hashrate_th_max NUMERIC(10,2),
  power_w_min INTEGER,
  power_w_p50 INTEGER,
  power_w_max INTEGER,
  efficiency_jth_min NUMERIC(6,3),
  efficiency_jth_p50 NUMERIC(6,3),
  efficiency_jth_max NUMERIC(6,3),
  ambient_temp_avg_c NUMERIC(4,1),
  cooling_type TEXT NOT NULL CHECK (cooling_type IN ('air', 'hydro', 'immersion', 'unknown')),
  firmware_at_observation TEXT,
  notes TEXT,
  primary_source_id UUID REFERENCES knowledge.sources(id),
  bobby_verified BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_field_observed_model_cooling ON ops.field_observed_specs (miner_model_id, cooling_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_field_observed_site ON ops.field_observed_specs (site_id, observation_window_end) WHERE deleted_at IS NULL;
CREATE INDEX idx_field_observed_updated_at ON ops.field_observed_specs (updated_at);  -- for W28 delta pulls
```

**Open dimensions** (operator review needed before implementation):
- Chip temp ranges per board
- Fan RPM curves
- Pool rejection rates
- Restart frequency
- Time-to-first-chip-failure

These likely belong in **sibling tables** (`ops.field_observed_chip_temps`, etc.) keyed similarly. Implementation should add the main `ops.field_observed_specs` first, then siblings as operator confirms which dimensions matter most. Park as **W27-FOLLOWUP**.

**What the aggregator does.** Pseudocode:

```python
def aggregate_field_observed_specs(archive_id, miner_model_id, conn):
    """Run after Layer 2 resolution stamps the archive with miner_model_id."""
    # Fetch all power samples + api stats rows for this archive
    samples = conn.fetch(
        "SELECT pin, hashrate_th, temp_avg_c, firmware FROM knowledge.field_log_power_samples_view "
        "WHERE archive_filename = %s", (archive_id,)
    )
    if len(samples) < 100:
        return  # not enough data to be statistically meaningful
    hashrates = [s.hashrate_th for s in samples if s.hashrate_th]
    powers = [s.pin for s in samples if s.pin]
    # ... compute min/p50/max ...
    row = {
        "miner_model_id": miner_model_id,
        "site_id": detect_site_id(archive_id),  # from archive metadata or operator config
        "observation_window_start": min(s.scanned_at for s in samples),
        "observation_window_end": max(s.scanned_at for s in samples),
        # ...
    }
    conn.execute("INSERT INTO ops.field_observed_specs ... ON CONFLICT DO NOTHING")
```

**Definition of done.** Importing an existing archive that resolves to a `miner_model_id` writes one row to `ops.field_observed_specs`. Re-importing the same archive (SHA-256 dedup) does NOT create a duplicate. Grafana panel shows the new row alongside factory specs.

---

### W28 — Federation v1: pull, merge, push scripts + customer_contribution_log

**Source:** §2 of this plan (operator Q2 answer).

**Effort:** L (1-2 weeks)
**Risk:** High — first end-to-end test must succeed before any customer ship
**Blocked by:** W14 (master + customer both have two-instance topology), W26 (`updated_at` consistency)
**Files:**
- `scripts/federation/pull_from_customer.sh` *(new)*
- `scripts/federation/merge_to_master.py` *(new)*
- `scripts/federation/push_to_customer.sh` *(new)*
- `scripts/federation/run_monthly_sync.sh` *(new — wrapper)*
- `migrations/0NN_knowledge_customer_contribution_log.sql` *(new)*
- `tests/test_federation_merge_policy.py` *(new — verifies conflict resolution)*
- `docs/strategy/W28_PREP.md` *(new — operator-facing runbook)*

**Customer contribution log table.**

```sql
CREATE TABLE IF NOT EXISTS knowledge.customer_contribution_log (
  id BIGSERIAL PRIMARY KEY,
  sync_run_id UUID NOT NULL,
  pulled_from_site_id TEXT NOT NULL,
  pulled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  target_schema TEXT NOT NULL,
  target_table TEXT NOT NULL,
  target_row_id UUID,
  merge_action TEXT NOT NULL CHECK (merge_action IN ('inserted','updated','skipped_bobby_verified','skipped_lower_n_observations','flagged_for_review')),
  conflict_details JSONB,
  bobby_reviewed BOOLEAN NOT NULL DEFAULT FALSE,
  bobby_review_decision TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Every row merged from a customer goes here. The operator can then `SELECT ... WHERE bobby_reviewed = FALSE ORDER BY pulled_at DESC` after sync to spot-check.

**Sync run process.**

1. `pull_from_customer.sh <customer_id>`:
   - SSH/Tailscale to customer Mini
   - `pg_dump` catalog DB from customer to local file `pulls/<customer_id>_<timestamp>.sql`
   - Verify dump checksum + row count sanity
2. `merge_to_master.py`:
   - Apply customer dump to a **staging schema** on master (`staging_pull_<customer_id>`)
   - For each row in staging, apply merge policy (§2.2):
     - Find matching master row by natural key (slug/model_id/etc.)
     - If master row has `bobby_verified=TRUE` → skip, log to `customer_contribution_log` with `merge_action='skipped_bobby_verified'`
     - Else if customer row has higher `n_observations` → update master, log `merge_action='updated'`
     - Else if no master row exists → insert, log `merge_action='inserted'`
     - Drop staging schema after merge
3. `push_to_customer.sh <customer_id>`:
   - Apply any pending `migrations/0NN_*.sql` to customer DB first (schema sync)
   - `pg_dump` master catalog to local file `pushes/<timestamp>.sql`
   - `pg_restore` on customer with `--clean --if-exists` against catalog DB only (operational untouched)

**v1 simplifications** (defer to v2 post-August):
- No automated cadence — operator runs the wrapper script manually
- No parallelism — one customer at a time
- No partial-failure recovery — if merge fails, manual cleanup
- Single conflict-resolution policy (DEFAULT-MERGE-1)

**Definition of done.** End-to-end test on a second machine simulating a customer Mini: full pull + merge + push cycle succeeds, customer_contribution_log shows expected rows, master catalog has new data, customer catalog has master's new findings, operational DBs on both sides are untouched.

---

### W29 — Pass 2 cadence configuration flag

**Source:** §1.3 of this plan (OPERATOR-CADENCE-1).

**Effort:** XS (under 2 hours)
**Risk:** Low — single config switch
**Files:**
- `ai/refinement_chain.py` — read `PASS_2_CADENCE` env var, default `daily`
- `.env.example` — document `PASS_2_CADENCE=daily|weekly` with comment
- `installer/macos-pkg/scripts/postinstall.sh` — set `PASS_2_CADENCE=weekly` in customer .env
- `tests/test_pass_2_cadence_flag.py` *(new)*

**What to do.** Add a config flag the launchd plist consults to decide whether Pass 2 runs daily or weekly. Default on master = `daily` (operator's choice). Default on customer .pkg install = `weekly`. Document the operator's daily-cadence decision so the next person who looks at this doesn't "fix" it back to weekly.

**Definition of done.** Plist references the flag. Master's `.env` has `PASS_2_CADENCE=daily`. Customer .pkg installer writes `PASS_2_CADENCE=weekly`. Test asserts the parsing.

---

### Reordering of existing W## items

`AMENDMENTS_2026-05-12.md` already established Phase 1.5 contains W14a → W14 → W14b. This plan adds Phase ordering after Phase 1.5:

**Old order** (from `04_MASTER_EXECUTION_PLAN.md`):
- Phase 2 (W06-W09): Closing integration gap — Weeks 2-3
- Phase 3 (W10-W13): External intake & operator surfaces — Week 4
- Phase 4 (W14-W17): Architectural correctness — Weeks 5-6
- Phase 5 (W18-W22): Performance polish — Weeks 7-8
- Phase 6: Federation — Months 3-6

**Locked new order** (working backward from mid-August customer ship):
- ✅ Phase 1.5 (W14a → W14 → W14b): **THIS WEEK** — master gets two-instance topology
- **Phase 2 (W10 → W11)**: **Next 2 weeks** — Slack `/intel` lights up daily Perplexity ingest
- **Phase 2b (W06 → W07 → W08 → W09)**: **Following 2 weeks** — AI reads catalog; daily Pass 2 becomes catalog-aware
- **Phase 3 (W26 → W27)**: **June** — `updated_at` discipline + field_observed_specs + Layer 2.5 aggregator
- **Phase 3b (W12 + Grafana W23/W24/W25)**: **Late June** — visibility into catalog state; intelligence dashboard rebuild for two-section view
- **Phase 4 (W28 + W29)**: **July** — Federation v1; customer Mini installer with two-instance topology; Pass 2 cadence flag
- **Phase 5 (final 2 weeks before ship)**: **Early August** — installer testing, notarization, end-to-end customer-Mini dry run, docs
- **Phase 6**: post-August — performance polish from old Phase 5 (W18-W22) and Phase 6 v2 federation hardening

Cite this re-sequencing as **A08** in [`AMENDMENTS_2026-05-12.md`](AMENDMENTS_2026-05-12.md).

---

## 4 · The Slack `/intel` command — full design

This is **W11**, expanded based on the actual Perplexity output format reviewed during the 2026-05-12 design dialogue. Original W11 spec in [`04_MASTER_EXECUTION_PLAN.md`](04_MASTER_EXECUTION_PLAN.md) §W11 was a simpler single-finding shape. Updated spec follows.

### 4.1 Two intake patterns

**Pattern A — `/intel paste` (primary, used daily by operator)**

```
/intel paste
Scheduled task: Intel Catalog — Aggregator Watcher 6:44 AM
No new Bitcoin SHA-256 ASIC miner models found today versus the existing catalog...
[paste continues with all 3-4 watcher reports]
```

The structure extractor (Claude API call, see §4.3) parses the blob, identifies which watcher each section came from, and classifies each finding as either:

- **Freshness check** (watcher ran, nothing new) → `record_freshness_check` write
- **Data conflict** (watcher found two sources disagreeing) → `propose_data_conflict` write
- **New firmware release** → `propose_firmware_release` write
- **New model proposal** → `propose_miner_model` write (existing function)
- **Community intel item** → `propose_community_intel` write *(new propose function — see W10 extension)*

Each finding gets its own row in the Slack confirmation card.

**Pattern B — `/intel <type> "<text>"` (ad-hoc)**

```
/intel firmware "LuxOS now supports MicroBT WhatsMiner M50-series, M60/M60S planned"
```

For findings outside the morning watcher run. Single finding, single confirmation card. Same propose_* targets.

### 4.2 Real-world watcher output shape (from operator 2026-05-12)

Three patterns observed in actual output (operator pasted morning chat 2026-05-12):

**Pattern 1 — "Nothing new" (most common):**
> *"Scheduled task: Intel Catalog — Firmware Tracker 8:01 AM. No genuinely new Bitcoin SHA-256 ASIC miner firmware releases (performance/efficiency/power-mode related) were found since the prior check. Saved the updated run state and findings JSON for the next scheduled run."*

→ Single `record_freshness_check` row: `(source='firmware_tracker_perplexity', sources_checked=6, found_new=FALSE, observed_at=NOW())`

**Pattern 2 — "Found something, but it's noise":**
> *"Potential retailer spec issue noted (not treated as a catalog discrepancy): the CryptoMinerBros A4 Ultra Hydro product page contains conflicting spec blocks—one section states 886 TH/s & 8372 W, while another shows 680 TH/s & 7412 W—suggesting a page/template error rather than a new miner variant."*

→ `propose_data_conflict` row marked `is_resolved=FALSE` and `severity='low'` (template error, not real disagreement) for operator to review.

**Pattern 3 — "State update / watch item":**
> *"State updated for the next run (including an added watch item to treat 'Antminer S23 series' specs as rumor unless corroborated by OEM or reputable mining media)."*

→ `propose_community_intel` row with type='watch_item' for the catalog to remember.

### 4.3 The duplicate-digit gotcha

Operator's morning paste showed: `"886886 TH/s, 83728372 W, 9.4499.449 J/TH"` — paste/OCR artifact, real numbers are 886/8372/9.449. **The structure extractor prompt must include explicit collapse-repeated-digit-pairs logic.** Add a regex preprocessing step before sending to Claude:

```python
import re
# Collapse "886886" → "886", "83728372" → "8372", etc.
# Only when the substring of length N/2 repeats exactly
def dedupe_repeated_numbers(text):
    return re.sub(r'\b(\d+)\1\b', r'\1', text)
```

Cite this as **PERPLEXITY-PASTE-1** since it's a real-world detail that wouldn't be in any spec.

### 4.4 Approve UX (must support "Approve All" for batch-mostly-freshness days)

After the paste, Claude responds in Slack with a card like:

```
Found 3 findings worth catalog write:

📅 Aggregator (6:44 AM)
  ✅ Freshness check: hardware.miner_models — confirmed
     "SealMiner A4 Ultra Hydro" still at 886 TH/s, 8372W, 9.449 J/TH
     [Approve] [Skip]
  ⚠️ Data conflict: CryptoMinerBros page
     Section A: 886 TH/s, 8372W | Section B: 680 TH/s, 7412W
     Likely template error, not a new variant
     [Approve as soft-conflict] [Skip]

📅 Community Intel (7:39 AM)
  ✅ Freshness check: market.forum_posts — confirmed
     "Antminer S23 series" watch flag added for next run
     [Approve]

📅 Firmware Tracker (8:01 AM)
  ✅ Freshness check: firmware.firmware_releases — confirmed
     6 vendor pages checked, no new releases
     [Approve]

[ Approve All Freshness ]   [ Review Each ]   [ Cancel All ]
```

**"Approve All Freshness"** auto-approves only the green ✅ rows. Yellow ⚠️ (data conflicts, new releases) require individual review. This keeps daily operator time at ~30 seconds.

### 4.5 W11 effort revision

Original Plan estimate: M (3-4 days including prompt engineering).
Revised estimate: **M-L (5-7 days)** because:
- Two intake patterns (A and B) instead of one
- "Approve All" batch UX requires Slack Block Kit interactive components
- Structure extractor prompt must handle 4 watcher shapes + the duplicate-digit gotcha
- Regression suite against 5+ days of real operator paste samples

Cite this as **A09** in `AMENDMENTS_2026-05-12.md`.

---

## 5 · Personal items mapping (from operator 2026-05-12)

Operator's enumerated complaints about today's Grafana intelligence dashboard, mapped to W## items in this plan.

| Operator complaint | Root cause | Work item |
|---|---|---|
| *"Intelligence DB has its own grafana page but it was not posting everything"* | Loop 4 read path covers 6 of 95 catalog tables; many panels query empty tables | W06 + W07 + W08 (AI reads) + W25 (Grafana rebuild) |
| *"Fleet section to post if you have any personal data on the particular miner to share and it was never populating"* | `market.war_stories` IS being written by feedback loop but Grafana fleet panel reads from wrong source or queries empty join | W07 (AI reads war_stories; same query pattern feeds Grafana) + W25 panel rebuild against correct source |
| *"Firmware links the program finds every morning should be listed as URLs under the firmware sections"* | Loop 1 broken — Perplexity firmware tracker findings land in `cron_tracking/firmware_tracker/` and get ignored; never reach `firmware.firmware_releases.download_url` | W10 (`propose_firmware_release` includes URL field) + W11 (`/intel paste` writes these via the propose function) |
| *"Under parts it should be listing the chip type and number, control board types and brands, hashboard types and numbers"* | `hardware.chips` has 4 rows (need ~30+); `hardware.control_boards` empty; `hardware.hashboards` has 4 reference rows; the enrichment CSV has this data as freeform text not promoted to structured columns | **NEW W30** — one-shot enrichment-CSV-to-Postgres importer that parses `miner_enrichment_master.csv` freeform fields (`Distinguishing Features`, `PSU Requirements`, etc.) and populates structured rows in `hardware.chips`, `hardware.psu_models`, `hardware.control_boards` |
| *"Foremost authority of btc miners in the world"* | The product mission; serves as decision rule for prioritization | NORTH-STAR-1 (no specific W##, but every W## is evaluated against this) |

### W30 — Enrichment CSV structured extraction

**Effort:** M (3-4 days)
**Risk:** Low — read-only against existing CSV, additive writes to Postgres
**Files:**
- `intelligence-catalog/seed-data/extract_structured_specs_from_csv.py` *(new)*
- Targets: `hardware.chips`, `hardware.psu_models`, `hardware.control_boards`, `hardware.hashboards`, voltage/frequency columns on `hardware.miner_models`

**What to do.** For each row in `miner_enrichment_master.csv`:
1. Parse the `Distinguishing Features` freeform text to extract `chip_model` (regex for BM\d+, AT\d+, KS\d, WM\d patterns), `process_node_nm` (regex for `(\d+)\s*nm`), `chips_per_board`, `boards`
2. Parse `PSU Requirements` to extract PSU model name, output_power_w, input_voltage_range
3. Parse `Voltage Range` to extract voltage_min, voltage_max
4. Parse `Release Date (exact)` to extract a real `DATE` value
5. Write/upsert into structured tables; tag every write with `primary_source_id` pointing to a new `knowledge.sources` row "enrichment_csv_extraction_2026-05" so provenance is clear

**Definition of done.** `hardware.chips` row count goes from 4 to 30+. `hardware.psu_models` populated for at least 50 known PSU types. `hardware.miner_models.voltage_min/voltage_max` populated for 270+ of 317 rows. Grafana parts panel (W25) shows real data.

This is **the gap that makes the catalog feel empty today** — operator's complaint about "parts section should be listing chip type and number..." Solving this in W30 closes that gap directly.

Cite this addition as **A10** in `AMENDMENTS_2026-05-12.md`.

---

## 6 · Locked timeline

Working backward from mid-August 2026 customer ship.

### August 1–15: Bake
- Stability soak (no new W## work)
- Final docs (customer-facing install guide, troubleshooting runbook)
- Apple notarization of `.pkg` (multi-day Apple process — start by Aug 1)
- First customer onboarding kit

### July: Federation + customer installer
- **W28** — federation v1 (pull/merge/push) — first 2 weeks
- **W29** — Pass 2 cadence config — concurrent with W28 (XS)
- **Customer installer two-instance support** — last 2 weeks
- End-to-end dry run on a second physical machine simulating customer Mini

### June: Catalog completeness + visibility
- **W26** — `updated_at` discipline — week 1 (XS, do first)
- **W27** — `ops.field_observed_specs` + mg_import_tool Layer 2.5 — weeks 1-2
- **W30** — enrichment CSV structured extraction — week 2
- **W23, W24, W25** — Grafana intelligence dashboard rebuild (two-section view) — weeks 3-4
- **W12** — morning briefing catalog visibility additions — week 4

### Late May (after W14 lands tomorrow): Plumb the catalog
- **W10** — extend dual_writer.py with propose_* functions — first 2 days
- **W11** — Slack `/intel paste` + `/intel <type>` — next 5-7 days
- **W06 + W07 + W08** — AI reads model_known_issues, war_stories, environmental_correlations — concurrent, 1 day each
- **W09** — daily Pass 2 catalog-aware (master) — 3-4 days

### Tomorrow (2026-05-13)
- W14 — split master Postgres into two instances (operational + catalog)

### Today (done)
- ✅ W14a deployed and live (all 10 services running on refactored code as of 10:22 CDT)
- ✅ This design plan written

---

## 7 · Open questions parked for implementation time

These don't block writing this plan but will surface during W##-by-W## work. Recording so they don't get lost.

### OQ1 — Customer contribution review tier
§2.4 above defaulted to option (a) auto-merge with contribution log. Operator can override before W28 implementation. Decision needed by start of July.

### OQ2 — `ops.field_observed_specs` additional dimensions
§3 W27 lists 5 candidate dimensions (chip temp, fan RPM, pool rejection, restart frequency, time-to-first-chip-failure). Each likely deserves its own sibling table. Operator confirms priority order before W27 starts implementation.

### OQ3 — Cooling type detection from archives
§1.4 / W27 Layer 2.5: Antminer logs sometimes contain cooling_type metadata, WhatsMiner often don't. For unknown cases, defaults to `'air'` — but operator may want a per-archive prompt during mg_import_tool drop-in to confirm. Decide during W27 implementation.

### OQ4 — Customer .pkg pre-seeding
When a customer .pkg installs in August, should it ship with the **current master catalog as initial data** (huge dump bundled in .pkg) or pull the master catalog **after first install** via the federation push script run once?

The push-on-first-install approach is cleaner (smaller .pkg, customer Mini always gets latest at install time) but requires the federation infrastructure to be 100% reliable by August.

Default for v1: **bundle initial catalog in .pkg** as a fallback, then run federation push immediately after install to catch up. Two-belts approach. Decide during W28 prep.

### OQ5 — Old W## items deferred
The original Plan's W15 (split daily_deep_analyses out of knowledge.json), W16 (TO_CHAR cleanup — already done per A04), W17 (tz-aware datetime sweep), W18-W22 (performance polish) move to **Phase 6 / post-August**. None block customer ship, all are improvements to system that's already running. Re-evaluate priority order after August stability soak.

### OQ6 — Perplexity watcher subscription lifecycle
Per [`02_TWO_DATABASE_DEEP_DIVE.md`](02_TWO_DATABASE_DEEP_DIVE.md) §"Why the freshness gap matters": *"If Perplexity has an outage or your subscription lapses, the four scheduled tasks just stop. Mining Guardian has no signal of this."*

Once W11 + W12 land, the morning briefing tells the operator "did we hear from each of the four watchers in the last 36 hours?" That's the signal. But what's the operator response if a watcher goes silent for 72+ hours? Manual Perplexity dashboard check, restart the scheduled task, or escalate? Park as **OQ6** — answer when first watcher-down event happens, not before.

---

## 8 · Reference notes for future-Claude sessions

These pointers tell a fresh Claude session in any future chat where to look to verify or extend this plan. Cite by ID in commit messages and chat.

| Reference | Where it lives | What it answers |
|---|---|---|
| **NORTH-STAR-1** | §0 of this doc | The product mission ("foremost authority of btc miners in the world") — every prioritization decision must trace back to this |
| **OPERATOR-CADENCE-1** | §1.3 | Daily Pass 2 on master, weekly on customer Minis; ratified by operator 2026-05-12 |
| **OPERATOR-RANGES-1** | §1.4 | Friend imports enrich `ops.field_observed_specs` real-world ranges; ratified 2026-05-12 |
| **DEFAULT-MERGE-1** | §2.4 | Auto-merge customer contributions with conflict resolution; can be overridden before W28 |
| **PERPLEXITY-PASTE-1** | §4.3 | Duplicate-digit collapse regex required in structure extractor |
| **A08** | `AMENDMENTS_2026-05-12.md` | New W##-item phase order (W14a → W11 → W06-09 → W26/27/30 → W23-25/12 → W28-29) |
| **A09** | `AMENDMENTS_2026-05-12.md` | W11 effort revised M → M-L with two intake patterns and Approve-All UX |
| **A10** | `AMENDMENTS_2026-05-12.md` | W30 added — enrichment CSV structured extraction |
| **Loop 1** | §1.2 | Perplexity intake — broken today, fixed by W11 |
| **Loop 2** | §1.2 | Friend archive imports — works for operational tables, extended by W27 |
| **Loop 3** | §1.2 | Operational feedback — working today |
| **Loop 4** | §1.2 | AI reads catalog — partial, expanded by W06-09 |
| **Loop 5** | §2 | Monthly federation — built in W28 |

When a future Claude session asks *"why are we doing W27?"* — the answer is *"see §1.4 OPERATOR-RANGES-1 in `05_CATALOG_DESIGN_PLAN_2026-05-12.md`."*

---

## 9 · How to open a fresh session about catalog work

Drop this exact paragraph into the opening message of a new chat:

> *Continuing the Mining Guardian intelligence catalog work. The locked design is at `docs/strategy/05_CATALOG_DESIGN_PLAN_2026-05-12.md`. The execution plan status is at `docs/EXECUTION_PLAN_STATUS.md`. Currently working on W##. The relevant amendment is A## in `docs/strategy/AMENDMENTS_2026-05-12.md`. Companion architectural read is `docs/strategy/02_TWO_DATABASE_DEEP_DIVE.md`. The importer details I'm building against are in `mg_import_tool/README.md`.*

That single paragraph plus the W## you're on gives fresh Claude enough context to be useful in one tool call worth of reading.

---

*End of Catalog Design Plan. Living document — if architecture changes, file an amendment in `AMENDMENTS_<date>.md` referencing the relevant section ID here, do NOT edit this file in place. The frozen snapshot is the value.*
