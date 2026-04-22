# Field Intelligence Pipeline

**Status:** Layer 2 SHIPPED 2026-04-22 — v3.3 tool live, 14,178 rows persisted from first real archive
**Owner:** Rob Fiesler
**Mission:** "Ring the neck of all this data" — capture, link, and learn from every data point
in every archive from the known mainstream fleet. Zero data loss. Zero orphans. Every day
the database gets smarter.

> **Update 2026-04-22:** This document was originally written as a forward-looking design. As of
> April 22 the Layer 1 + Layer 2 foundation is **live in Postgres** (317 SHA-256 models,
> 12,852 Tier-1 aliases, 1,494 Tier-2 family aliases). The `mg_import_tool` v3.3 ships the
> streaming loader, resolver, raw-JSON capture, and identity extraction. Layers 3-6 remain
> as specified. Minor schema corrections are called out inline with **[SHIPPED]** markers.

---

## Organizing Principle: Spec vs Observed

Every performance dimension in the catalog has two parallel representations:

- `spec_*` — what the vendor says
- `observed_*` — what the fleet actually does (p50, p95, sample size)

The Mining Guardian UI renders both side by side with a delta badge. This is THE feature.
Everything else in the pipeline exists to feed this comparison accurately.

Sample-size confidence tiers:

- **n=1-2:** observed shown with "⚠ preliminary" badge
- **n=3-9:** observed shown with "limited sample" badge
- **n=10+:** observed shown as authoritative, bold, with 95% CI

---

## Where the Data Lives (as of 2026-04-22)

Mining Guardian spans **two database engines** by design:

### Postgres — `mining_guardian` (Docker, `mining-guardian-db` container)
Catalog + field intelligence. Strict schemas, FKs, schema evolution tracked via numbered migrations.

| Schema | Purpose |
|---|---|
| `hardware` | canonical catalog — `miner_models` (317 SHA-256 rows), `model_aliases` (Tier-1) |
| `mg` | linking + operational — `model_family_aliases`, `unresolved_models`, `import_runs`, `unknown_fields`, `field_promotion_queue` |
| `knowledge` | raw field extract — `field_log_*` tables |
| `firmware`, `facility`, `ops` | domain-specific catalog/operational tables |

### SQLite — 4-DB split under `/databases/` (Phase 1, 2026-04-22)
Live miner telemetry, routed by `core/database_router.py`. **This is transitional** —
Phase 2 (tomorrow) migrates these to Postgres.

| File | Role | Size |
|---|---|---|
| `operational.db` | hot reads — scans, miner_hardware, approvals, maintenance windows | 1.5 MB |
| `timeseries.db` | append-only — miner/chain/pool/chip/hvac/weather readings | 5.4 GB |
| `ai_knowledge.db` | learning brain — llm_analysis, baselines, tracking | 5.2 MB |
| `audit.db` | paper trail — action audit, miner_logs, ams_notifications | 1006 MB |

The router has no knowledge of Postgres — catalog/field-log work always goes through
psycopg in the import tool. Phase 2 will unify on Postgres and update the router to a
pg connection-pool pattern.

---

## The 6-Layer Pipeline

```
┌────────────────────────────────────────────────────────────┐
│ LAYER 6: Intake Review       → parse warnings dashboard    │
├────────────────────────────────────────────────────────────┤
│ LAYER 5: Enrichment Proposals → auto-correction queue      │
├────────────────────────────────────────────────────────────┤
│ LAYER 4: Field Stats Rollup   → observed_* columns updated │
├────────────────────────────────────────────────────────────┤
│ LAYER 3: Physical Miner Dedup → mg.miners keyed by MAC     │
├────────────────────────────────────────────────────────────┤
│ LAYER 2: Model Identification → two-tier resolver          │ ← SHIPPED 2026-04-22
├────────────────────────────────────────────────────────────┤
│ LAYER 1: Raw Extraction       → knowledge.field_log_*      │ ← SHIPPED (v2 + v3 raw JSON)
└────────────────────────────────────────────────────────────┘
```

Build order:
- **Layers 1-2:** SHIPPED. v3.3 import tool ships both.
- **Layers 3-6:** next, incrementally post-audit.
- **Learning loops A-D** layered on top once Layers 3-4 have data.

---

## Layer 1: Raw Extraction [SHIPPED v2, extended in v3]

Extracts `.tgz` / `.tar` / `.rar` archives of two known shapes (WhatsMiner + Antminer) into
8 tables under `knowledge.field_log_*`. API keys redacted, device IDs preserved.

### v3 extensions

**`knowledge.field_log_raw_json`** — every parsed blob, even unknown fields.

```sql
CREATE TABLE knowledge.field_log_raw_json (
    id              BIGSERIAL PRIMARY KEY,
    archive_id      BIGINT NOT NULL REFERENCES knowledge.field_log_imports(id),
    source_file     TEXT NOT NULL,
    raw_payload     JSONB NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON knowledge.field_log_raw_json (archive_id);
CREATE INDEX ON knowledge.field_log_raw_json USING GIN (raw_payload);
```

Captured once per source file per archive (deduped on `(archive_id, source_file)`).

**`knowledge.field_log_miner_identity`** — emits one identity row per boot session,
carrying the resolved `catalog_slug`, raw strings, and confidence. Populated by v3.2+.

**Why:** Every field, every value, always captured — even if we don't have a typed column
for it yet. This is the insurance policy that makes schema evolution safe: when we promote
a new field to a real column later, the backfill reads from here.

---

## Layer 2: Model Identification [SHIPPED 2026-04-22]

### Problem
Raw logs carry strings like `M31S+_V100`, `Antminer_S19`, or control-board-version strings
like `V70`. The catalog uses slugs like `whatsminer-m31s-plus-v100` and `antminer-s19`.
Until today, every archive landed in the DB but was disconnected from the catalog.

### Solution — Two-Tier Resolver

We ship **two alias tables** instead of one, because the raw-string space has an
irreducible ambiguity: many WhatsMiner V-codes map to a **family** rather than a
single model, and the correct variant depends on the observed hashrate.

#### Tier 1: `hardware.model_aliases` — unambiguous 1:1

```sql
CREATE TABLE hardware.model_aliases (
    id                  BIGSERIAL PRIMARY KEY,
    model_id            UUID NOT NULL REFERENCES hardware.miner_models(id),
    alias_normalized    TEXT NOT NULL,
    source_field        TEXT NOT NULL,
    confidence          NUMERIC(3,2) NOT NULL,
    match_type          TEXT NOT NULL,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          TEXT,
    UNIQUE (alias_normalized)
);
CREATE INDEX ON hardware.model_aliases (model_id);
```

**Pre-seeded with 12,852 rows** covering:
- canonical slug forms
- parenthetical-qualified names (`Antminer S19 (Hydro)`)
- all 15 V-code variants (V10, V20, V30, V40, V50, V60, V70, V80, V90, V100, VE30,
  VE50, VE80, VK10, VK30) for every applicable WhatsMiner and Antminer family
- underscore/hyphen/space permutations
- retailer SKU variants

Unique on `alias_normalized` — a Tier-1 hit is **instant, exact, authoritative**.

#### Tier 2: `mg.model_family_aliases` — ambiguous, resolved by hashrate

```sql
CREATE TABLE mg.model_family_aliases (
    id                  BIGSERIAL PRIMARY KEY,
    alias_normalized    TEXT NOT NULL UNIQUE,
    candidate_model_ids UUID[] NOT NULL,          -- all variants in family
    candidate_hashrates_ths NUMERIC[] NOT NULL,   -- aligned with candidates
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Pre-seeded with 1,494 rows.** Contains family strings like `whatsminer-m30s` that
resolve to multiple catalog entries differentiated by hashrate bin (e.g., 86 / 88 / 90 /
94 / 100 TH/s variants). Resolver picks **nearest hashrate bin, no tolerance** — ties
break to the lower-rated bin (observed-under-spec is more common than over-spec).

#### Fallback: `mg.unresolved_models`

```sql
CREATE TABLE mg.unresolved_models (
    id                  BIGSERIAL PRIMARY KEY,
    raw_string          TEXT NOT NULL,
    source_field        TEXT NOT NULL,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    occurrence_count    INT NOT NULL DEFAULT 1,
    sample_archive_ids  BIGINT[] NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending',
    resolved_to_model_id UUID REFERENCES hardware.miner_models(id),
    resolved_at         TIMESTAMPTZ,
    resolved_by         TEXT,
    UNIQUE (raw_string, source_field)
);
```

If no hashrate is available (or the aliased candidates can't be disambiguated), the
string lands here for manual GUI triage — we never guess.

### Resolver Pipeline (`clients/resolver.py`, 445 lines)

5-step pipeline, first match wins:

1. **Normalize** the raw string (preserve trailing `+`/`++`, lowercase, squash separators)
2. **Tier-1 exact** lookup on `alias_normalized`
3. **Tier-2 family** lookup + hashrate bin resolution (nearest, no-tolerance, ties-low)
4. **V-code introspection** on `control_board_version` (V-codes often land in CBV, not
   miner_type)
5. **Fallback** to `mg.unresolved_models` with sample archive id

Every import of a given `miner_type`+`control_board_version` pair runs through the
resolver once and stamps the resulting `model_id` + `confidence` + `match_type` onto
every emitted field-log row for that archive.

### Import Run Tracking: `mg.import_runs`

```sql
CREATE TABLE mg.import_runs (
    id                  BIGSERIAL PRIMARY KEY,
    archive_filename    TEXT NOT NULL,
    archive_sha256      TEXT,
    status              TEXT NOT NULL,            -- ok | failed | partial | skipped
    rows_persisted      BIGINT NOT NULL DEFAULT 0,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at         TIMESTAMPTZ,
    error_message       TEXT,
    error_traceback     TEXT
);
```

Used by the v3.3 SSE streaming endpoint for live progress and by
`/api/resolver-summary` for coverage reporting.

### Result from First Real Run (2026-04-22)

Single archive: `Antminer_S19_2024-06-27_2024-06-29.tar` (v2-killer, 14k autotune events)

- Parse time: **0.45s**
- Rows persisted: **14,178**
- Resolver status: **ok**
- `mg.unresolved_models`: **0** after run

---

## Unknown Field Surveillance

**`mg.unknown_fields`**

```sql
CREATE TABLE mg.unknown_fields (
    id                  BIGSERIAL PRIMARY KEY,
    field_key           TEXT NOT NULL,
    source_file_pattern TEXT,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    first_archive_id    BIGINT REFERENCES knowledge.field_log_imports(id),
    occurrence_count    INT NOT NULL DEFAULT 1,
    distinct_models_seen INT NOT NULL DEFAULT 1,
    sample_values       JSONB,
    value_type_guess    TEXT,
    status              TEXT NOT NULL DEFAULT 'observed',
    UNIQUE (field_key, source_file_pattern)
);
```

**`mg.field_promotion_queue`**

```sql
CREATE TABLE mg.field_promotion_queue (
    id                      BIGSERIAL PRIMARY KEY,
    unknown_field_id        BIGINT NOT NULL REFERENCES mg.unknown_fields(id),
    proposed_column_name    TEXT NOT NULL,
    proposed_data_type      TEXT NOT NULL,
    proposed_target_table   TEXT NOT NULL,
    auto_generated_sql      TEXT,
    status                  TEXT NOT NULL DEFAULT 'pending',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_by             TEXT,
    approved_at             TIMESTAMPTZ,
    applied_at              TIMESTAMPTZ
);
```

**Promotion thresholds** (aligned with spec-vs-observed confidence tiers):

- `occurrence_count ≥ 2` AND seen in `≥ 1` model → status = `proposed`
- `occurrence_count ≥ 5` AND seen in `≥ 2` distinct models → auto-generate promotion SQL, queue for approval

Because every field value is already in `field_log_raw_json`, promotion is a
non-destructive ALTER TABLE + backfill.

---

## v3.3 Import Tool — API Surface

Flask app (`:5050`), streams via Server-Sent Events.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/import-files-stream` | POST | SSE batch import, per-archive error isolation, sha256 dedup |
| `/api/resolver-summary` | GET | Tier-1 / Tier-2 / unresolved counts, coverage % |
| `/api/unresolved-sample?limit=N` | GET | Peek unresolved queue (default 50) |
| `/api/cancel-batch` | POST | Cooperative mid-batch cancel |

**SSE event stream:** `batch_started`, `archive_started`, `archive_parsed`,
`archive_persisted`, `resolver_stats_updated`, `archive_completed`, `archive_skipped`,
`batch_completed`.

277 tests passing. `v3.3` zip shipped 2026-04-22 evening; deploys tomorrow via
`TOMORROW_DEPLOY_STEPS.md`.

---

## Layer 3: Physical Miner Dedup (POST-AUDIT)

**`mg.miners`**

```sql
CREATE TABLE mg.miners (
    mac_address     TEXT PRIMARY KEY,
    first_seen_at   TIMESTAMPTZ NOT NULL,
    last_seen_at    TIMESTAMPTZ NOT NULL,
    model_id        UUID REFERENCES hardware.miner_models(id),
    archive_count   INT NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active',
                            -- active | dormant | retired | rma
    identity_hash   TEXT,
    notes           TEXT
);

CREATE TABLE mg.miner_archives (
    miner_mac       TEXT NOT NULL REFERENCES mg.miners(mac_address),
    archive_id      BIGINT NOT NULL REFERENCES knowledge.field_log_imports(id),
    observed_at     TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (miner_mac, archive_id)
);
```

MAC as primary key because: stable across reboots, present in every archive, matches
operational reality. Secondary `identity_hash` (from chip serials) handles mainboard
swap edge case.

---

## Layer 4: Field Stats Rollup (POST-AUDIT)

**`mg.catalog_field_stats`** — the observed half of spec-vs-observed.

```sql
CREATE TABLE mg.catalog_field_stats (
    model_id        UUID PRIMARY KEY REFERENCES hardware.miner_models(id),

    -- Hashrate
    observed_hashrate_ths_p50    NUMERIC,
    observed_hashrate_ths_p95    NUMERIC,
    observed_hashrate_ths_mean   NUMERIC,
    observed_hashrate_ths_stddev NUMERIC,

    -- Power
    observed_power_w_p50         NUMERIC,
    observed_power_w_p95         NUMERIC,

    -- Efficiency (derived)
    observed_efficiency_jth_p50  NUMERIC,
    observed_efficiency_jth_p95  NUMERIC,

    -- Temps
    observed_temp_c_p50          NUMERIC,
    observed_temp_c_p95          NUMERIC,

    -- Reliability
    observed_mean_lifetime_hours NUMERIC,
    observed_pool_fail_rate_pct  NUMERIC,

    -- Distributions (JSONB)
    top_error_patterns           JSONB,
    firmware_distribution        JSONB,
    pool_distribution            JSONB,

    -- Sampling metadata
    sample_size_archives         INT,
    sample_size_miners           INT,
    confidence_tier              TEXT,
    computed_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Refresh cadence:** event-driven — recompute for a given `model_id` whenever a new
archive for that model is imported AND it has been >24h since last recompute.

---

## Layer 5: Enrichment Proposals (POST-AUDIT)

**`mg.enrichment_proposals`**

```sql
CREATE TABLE mg.enrichment_proposals (
    id              BIGSERIAL PRIMARY KEY,
    proposal_type   TEXT NOT NULL,
        -- spec_correction | new_alias | new_model |
        -- firmware_observation | pool_observation
    target_model_id UUID REFERENCES hardware.miner_models(id),
    field_name      TEXT,
    current_value   TEXT,
    proposed_value  TEXT,
    evidence        JSONB NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    proposed_by     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_by     TEXT,
    reviewed_at     TIMESTAMPTZ
);
```

Auto-generated when Layer 4 detects spec-vs-observed drift > threshold with n ≥ 10 miners
and persistence ≥ 7 days. User approves in GUI → `hardware.miner_models` updated, audit
trail preserved.

---

## Layer 6: Intake Review (POST-AUDIT)

Dashboard showing archives with parse warnings — missing MAC, truncated logs, unknown
chip IDs, unresolved model strings. Not blocking, just visibility. `/api/resolver-summary`
and `/api/unresolved-sample` are the v3.3 data sources for this dashboard.

---

## Dormant Miner Surveillance

**`mg.dormant_miners`**

```sql
CREATE TABLE mg.dormant_miners (
    id              BIGSERIAL PRIMARY KEY,
    miner_mac       TEXT NOT NULL,
    last_archive_id BIGINT REFERENCES knowledge.field_log_imports(id),
    last_seen_at    TIMESTAMPTZ NOT NULL,
    days_dormant    INT NOT NULL,
    surfaced_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status          TEXT NOT NULL DEFAULT 'awaiting_review',
    rma_record_id   BIGINT REFERENCES mg.rma_records(id),
    resolution      TEXT,
    resolved_at     TIMESTAMPTZ,
    resolved_by     TEXT
);
```

**Detection rule:** MAC not seen in any new archive for 30+ days AND was active in ≥ 3
prior archives → auto-surfaced to "Missing in Action" queue. 5-question popup feeds the
RMA record.

---

## RMA / Failure Record Form

**`mg.rma_records`**

```sql
CREATE TABLE mg.rma_records (
    id              BIGSERIAL PRIMARY KEY,
    miner_mac       TEXT,
    miner_serial    TEXT,
    model_id        UUID REFERENCES hardware.miner_models(id),
    pulled_date     DATE NOT NULL,
    failure_reason  TEXT NOT NULL,
        -- psu_failure | hashboard_failure | control_board |
        -- fan_failure | network | overheat | unknown | other
    failure_reason_detail TEXT,
    replaced_with_mac TEXT,
    replaced_with_serial TEXT,
    tech_notes      TEXT,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (miner_mac IS NOT NULL OR miner_serial IS NOT NULL)
);
```

GUI form + CSV import hook. Weekly import cadence.

**Why this matters:** Turns Loop D from blind clustering into labeled supervised
classification. Failure signatures get named ("PSU brownout", "chip degradation", etc.)
and Mining Guardian can issue *named* warnings with 3-5 days lead time.

---

## Pool Normalization

**`mg.pools`**

```sql
CREATE TABLE mg.pools (
    id              BIGSERIAL PRIMARY KEY,
    pool_name       TEXT NOT NULL,
    region          TEXT,
    url             TEXT NOT NULL,
    port            INT,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (url)
);
```

`knowledge.field_log_pools` gets FK to `mg.pools.id`. Enables aggregation across the
fleet: pool disconnect rate by pool_name, regional latency patterns, etc.

---

## Learning Loops (post-audit)

Built on top of Layers 3-4. Schema foundation lives in v3 so nothing is lost.

### Loop A — Spec Drift Detection (reactive)
Nightly diff of `spec_*` vs `observed_*` with n ≥ 10 miners, two-sample t-test, drift
persistent 7+ days → emits `enrichment_proposals` rows.

### Loop B — Pattern Mining (predictive)
`mg.learned_patterns` table. Association rule mining on events + power samples + autotune.
Learns correlations like "voltage <12.80V on S19 → ZeroHashrate within 6h, 73% conf,
n=1247". Patterns with confidence >60% and support >50 feed Mining Guardian's alerting.

### Loop C — Anomaly Detection (continuous)
`mg.model_baselines` per `model_id` (rolling distributions). Each new archive compared
to baseline, z-score >3σ flags `mg.anomaly_events`. Event-driven rebaseline (only when
new data for that model arrives and >7 days since last recompute).

### Loop D — Failure Signature Library (diagnostic)
`mg.failure_signatures` table. When a miner goes dormant or emits hashboard_failure event,
back-trace 7 days of telemetry, store as JSONB signature. After 50+ signatures, k-means
cluster them. With RMA form labels, clusters get names.

---

## Execution Plan

| # | Task | Who | Status |
|---|---|---|---|
| 1 | Design doc (this file) | me | DONE |
| 2 | Kill runaway v2 import process | user | DONE |
| 3 | Pre-seed `hardware.model_aliases` + `mg.model_family_aliases` | me | DONE (12,852 + 1,494) |
| 4 | Build v3.1: Layer 2 + raw JSON + streaming fix + two-tier resolver | subagent | DONE |
| 5 | Build v3.2: identity extraction fix + raw JSON per-file capture | subagent | DONE |
| 6 | Build v3.3: SSE streaming + per-archive error isolation + resolver summary + sha256 dedup + cancel-batch | subagent | DONE |
| 7 | Ship v3.3 zip | me | DONE |
| 8 | Single-archive diagnostic run (Antminer S19 v2-killer) | user | DONE — 14,178 rows |
| 9 | Tomorrow: 83-archive mass import via SSE | user | PENDING |
| 10 | Verify ≥95% auto-match, resolve remainder | user + me | PENDING |
| 11 | SQLite → Postgres Phase 2 migration | user + me | PENDING (tomorrow) |
| 12 | Unified view over `ops.log_*` + `knowledge.field_log_*` | me | PENDING |
| 13 | Deprecate `ops.log_*` after parity verified | me | PENDING |
| 14+ | Layers 3-6 + Learning Loops A-D | later | scheduled post-audit |

---

## Design Decisions Locked

1. **MAC as physical miner primary key**, with secondary `identity_hash` from chip
   serials to catch mainboard swap rate.
2. **Two-tier alias architecture** — Tier 1 for unambiguous, Tier 2 for hashrate-disambiguated
   families. Both fully audit-trailed.
3. **V-codes checked in both `miner_type` AND `control_board_version`** — field origin
   varies by vendor/firmware.
4. **Unified view, then deprecate `ops.log_*`** — re-import replays the source data,
   migration is redundant.
5. **Field stats recompute event-driven**, not scheduled — matches bursty archive velocity.
6. **Unresolved models manual GUI triage**, not LLM auto-resolver — mainstream fleet
   means tiny queue.
7. **New tables split between `hardware.` (catalog-reference) and `mg.` (operational linking)** —
   Tier-1 alias table sits in `hardware` because it's a pure catalog-shape mapping; everything
   stateful (import runs, unresolved queue, promotion queue, RMA, pools) lives in `mg`.
8. **Side-by-side spec vs observed always** — no toggling, no hiding.
9. **Confidence tiers on observed data:** n=1-2 preliminary, n=3-9 limited, n=10+
   authoritative.
10. **Unknown field promotion threshold:** n=2 proposed, n=5 + 2 distinct models
    auto-queues column promotion.
11. **Pools treated as separate dimensions** (name + region + port) — each miner on a
    different pool by operator design.
12. **Ties in Tier-2 hashrate bins break to the lower-rated variant** — observed-under-spec
    is more common than over-spec.
13. **Normalizer preserves trailing `+` / `++`** — these are real variant discriminators.

---

## Non-Goals (explicitly out of scope)

- HVAC / ambient temperature data — not available (in field logs; AMS data separate)
- Electricity cost per miner — not available
- Heat output / facility-level metrics — not available
- Multi-site / per-container dimensions — single logical fleet
- Exotic / non-mainstream hardware parsers — fleet is mainstream only
- BTC price tracking — tracked separately, joined by timestamp at query time

---

## Future Data Sources (anticipated)

User expects more data dumps over the next 6 months from other sources. The pipeline
is explicitly designed so that:

- New archive formats land in `knowledge.field_log_raw_json` even if not yet parsed
- Unknown fields surface in `mg.unknown_fields` automatically
- Two-tier alias table absorbs new model strings as they appear
- Every addition strengthens the learning loops

This is the "Ring The Neck" property: no matter what comes in, nothing is lost.

---

## Revision History

| Date | Change |
|---|---|
| 2026-04-22 (initial) | Design doc locked — single-tier alias table, 238-model target |
| 2026-04-22 (evening) | **SHIPPED** — two-tier resolver, 317 models, 12,852 Tier-1 + 1,494 Tier-2, v3.3 import tool live. Corrected schema references (`catalog.miner_models` → `hardware.miner_models`). Added Phase 1 DB split context. Added v3.3 API surface. Updated Execution Plan with Phase 2 SQLite→Postgres migration. |
