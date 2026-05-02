# Intelligence Catalog Split-Brain — Fix Plan v1

> **⚠️ SUPERSEDED 2026-05-02 ⚠️**
>
> This plan was written under a **wrong framing**. After reading every catalog doc in the repo, the issue is **not** a routing/split-brain bug. The Mac Mini cutover (D-10/D-11) makes the Mini the canonical Postgres host; the ROBS-PC Docker stack we were debugging is superseded scope. `hardware.miner_models` is **not empty** — it has 317 seeded rows. The real work is **enrichment completeness**: promoting the rich text fields in `unified_miner_index.json` and `miner_enrichment_master.csv` into the empty/sparse Postgres columns (chip types, board types, firmware locations, known issues, voltage ranges, release dates, PSU compat, cooling compat, error codes, failure patterns).
>
> See **`docs/INTEL_CATALOG_FULL_BRIEF_2026-05-02.md`** for the corrected analysis and the top-10 ranked enrichment gaps.
>
> Kept here only for reference / decision history. Do not implement.

---

**Author:** Computer (autonomous agent)
**Date:** 2026-05-02 (Saturday)
**Owner:** Rob Fiesler
**Status:** SUPERSEDED — see banner above
**Branch (when approved):** `fix/intel-catalog-split-brain-D12`
**Locked decisions referenced:** D-12 (Postgres-as-truth, 2026-04-27)
**Mantras to honor:** "late and perfect over early and wrong" · "always over-document" · "one thing at a time" · "stay local, Bitcoin SHA-256 only" · "never call SQLite live"

---

## 1 · One-paragraph summary

The Catalog API on port 8420 is a FastAPI service that serves Bitcoin SHA-256 miner knowledge bundles to local LLMs (Qwen on the Mac Mini, Claude where applicable). It is hard-wired to query 21 PostgreSQL tables across six schemas. Those tables are **empty** in the running `mining-guardian-db` container on ROBS-PC, so every API call returns `"models": [], "knowledge": {}`. Meanwhile, the enrichment pipeline has been writing rich human-curated data to `intelligence-catalog/data/unified_miner_index.json` (288 miner slugs as of today, 583 KB). The API never reads that file. Locked decision **D-12** (2026-04-27) already declared **Postgres-as-truth** — the JSON is supposed to be a debug export, not the source. So the fix is **not** to refactor the API to read JSON; the fix is to **load the JSON's enrichment into Postgres** so the API's existing queries return real data. The seed SQL and the staging-table proposal/promotion machinery are already built (`seed_miner_models.sql`, `dual_writer.py`); they just haven't been run end-to-end against this container.

---

## 2 · Source-line evidence (no hand-waving)

Every claim below has a file and line reference. If any of these is wrong, the fix is wrong, so they are listed first.

### 2.1 The API queries empty Postgres tables

`intelligence-catalog/catalog-api/catalog_api.py` is a 955-line FastAPI app. Line 2 banner: `Catalog API Service — FastAPI on port 8420`.

Confirmed SQL queries against the dead schemas (line numbers from `grep -nE "FROM (hardware|ops|repair|firmware|market|facility)\.|JOIN ..."`):

| Line | Schema.Table | Purpose |
|------|--------------|---------|
| 328 | `hardware.miner_models` | Resolve model_id from slug |
| 343 | `hardware.miner_models` | Fuzzy match by model_name |
| 375 | `ops.failure_patterns` | Known failure modes |
| 384 | `ops.failure_symptoms` | Symptom name lookup |
| 393 | `ops.miner_error_codes` | Vendor error codes |
| 402 | `hardware.model_known_issues` | Per-model gotchas |
| 417 | `firmware.firmware_releases` | Firmware history |
| 424 | `firmware.firmware_compatibility` | Which FW runs on which model |
| 432 | `firmware.firmware_bugs` (by version) | FW bug correlation |
| 438 | `firmware.firmware_bugs` (by model) | FW bug correlation |
| 452 | `ops.operational_thresholds` | Operating limits |
| 459 | `ops.miner_baseline_reference` | Baseline scan reference |
| 466 | `ops.operational_profiles` | Power/perf profiles |
| 472 | `ops.environmental_correlations` | Temp/humidity correlations |
| 485 | `repair.repair_procedures` | Repair playbook |
| 490 | `repair.diagnostic_tools` | Diagnostic tooling |
| 493 | `repair.parts` | Spare parts |
| 503 | `facility.cooling_solutions` | Cooling specs |
| 506 | `facility.container_environment_reference` | Container env limits |
| 518, 889 | `hardware.chips` | Chip lookup |
| 894 | `hardware.psu_models` | PSU lookup |

That is **22 distinct table references across 6 schemas** (memory said "21" — off by one because lines 432 and 438 both hit `firmware.firmware_bugs` with different filters; counted as one table by the audit).

### 2.2 The schemas are declared but the data isn't loaded

`intelligence-catalog/seed-data/intelligence_catalog_schema.sql` declares the 9 schemas:
```
hardware  firmware  ops  market  repair  pool  facility  regulatory  knowledge  staging  seed
```
Plus the staging schema in `staging_schema.sql` for the dual-writer.

`seed_miner_models.sql` (264 KB, 321 INSERT statements) targets:
- `hardware.manufacturers`
- `hardware.miner_models`

So the seed file covers **two tables**. The other 19 referenced tables (`firmware.*`, `ops.*`, `repair.*`, `facility.*`) have no seed data file in the repo today. That's the second half of the split-brain — even if we run the seed perfectly, the API still has to gracefully return empty arrays for unseeded categories instead of 500-ing.

### 2.3 The enrichment data exists and is rich

`intelligence-catalog/data/unified_miner_index.json`:
- 288 top-level miner slugs (verified: `python3 -c "import json; print(len(json.load(open('.../unified_miner_index.json'))))"`)
- Each record has: `display_name`, `manufacturer`, `entity`, `specs{}`, `enrichment{}`
- The `enrichment` block is what the API needs — fields like *Operating Temp Range*, *Humidity Range*, *Voltage Range*, *PSU Requirements*, *Known Issues*, *Sources*. Sample (antminer-r4): see lines 1–30 of any `python3 -c "import json,pprint; pprint.pp(json.load(open('.../unified_miner_index.json'))['antminer-r4'])"` output captured earlier today.

### 2.4 Plumbing for the fix already exists

`intelligence-catalog/db/dual_writer.py` (24 KB, 535 lines) — the **D-12 intake module**:
- `propose_miner_model(slug, payload, source_tool=...)` UPSERTs into `staging.miner_model_proposals`
- `promote_validated_miner_models()` reads validated proposals → inserts into `hardware.miner_models`
- Has a CLI: `python -m intelligence_catalog.db.dual_writer --status / --list-pending / --promote-validated`
- Lines 1–60 of the docstring lock in the contract (D-12, fail-soft, payload_hash uniqueness, etc.)

`intelligence-catalog/seed-data/rebuild_unified_index.py` — keeps the JSON in sync with the seed CSV:
- Lines 14–15 reveal the historic count drift: *"The seed catalog has 313 SHA-256 miner variants (250 model families). The unified_miner_index.json on disk has only 247 family-level entries."*
- Today's actual count is 288 — drift has narrowed, not widened.

### 2.5 The B-9 catalog count drift, demystified

| Source | Count | What it represents |
|--------|-------|--------------------|
| `all_bitcoin_sha256_miners.csv` | 321 lines (320 data rows + header) | Every variant we know exists |
| `seed_miner_models.sql` | 321 INSERT statements | Same list, ready to load |
| `unified_miner_index.json` (today) | 288 slugs | What enrichment has reached |
| `rebuild_unified_index.py` legacy comment | 247 / 313 | Historical — pre-rebuild state |

So **B-9's 313-vs-320 drift is explained**: 320 = unique variants in the master CSV; 313 = an earlier count before late-April additions; 288 = current enrichment coverage. After the fix, all three should converge to 320 with explicit "no enrichment yet" markers for the 32 missing slugs.

### 2.6 Why FastAPI vs Fastify confusion in memory

`intelligence-catalog/catalog-api/catalog_api.py` is **FastAPI** (Python). The `web_app/stack.md` memory referencing **Fastify** (TypeScript) is the **separate web-app/dashboard layer** (top-level `api/` directory in the repo: `dashboard_api.py`, `ai_dashboard_api.py`, etc. — those are Python too, but the memory note about Fastify+TS likely refers to a planned/early dashboard rewrite that isn't part of this fix). Both can be true simultaneously. Today's split-brain bug is **FastAPI + Postgres** in `intelligence-catalog/catalog-api/`.

---

## 3 · Architectural decision — three options, one recommendation

### Option A — **Load JSON into Postgres** (RECOMMENDED ✅)
**What:** Build a one-shot importer that reads `unified_miner_index.json`, runs each record through `dual_writer.propose_miner_model(...)`, then runs `promote_validated_miner_models()` to populate `hardware.miner_models` and `hardware.manufacturers`. Run `seed_miner_models.sql` first so manufacturer rows exist. For the 19 tables we don't have seed data for yet, ensure the API returns `[]` gracefully (defensive code) rather than stack-tracing.

**Pros:**
- Honors locked decision **D-12** (Postgres-as-truth)
- Reuses already-built machinery (`dual_writer.py`, `seed_miner_models.sql`, staging schema)
- The API needs zero changes for the populated tables
- Future enrichment writes go through the same path (consistent contract)
- Postgres gets indexes, joins, ACID — JSON gets none of that

**Cons:**
- Need to write the importer (estimated ~150 LOC)
- Need to add safe-empty fallbacks for the 19 unseeded tables
- Requires the Postgres container to be live during the fix run (it is)

**Risk level:** low — all the hard parts are already built.

### Option B — Refactor API to read JSON
**What:** Replace every `psycopg2` query in `catalog_api.py` with `json.load()` calls against `unified_miner_index.json`.

**Pros:** quick proof-of-life
**Cons:** **Violates D-12.** Locks us out of joins, indexes, and the dual-writer contract. Throws away 24 KB of working dual-writer code. Future enrichment would have to write to a JSON file from cron jobs — fragile.

**Verdict:** rejected on principle, not just effort.

### Option C — Hybrid (read both, prefer Postgres)
**What:** API tries Postgres first; if empty, falls back to JSON.

**Verdict:** rejected — keeps the split-brain alive forever and creates hard-to-debug "which source served this row?" scenarios. Violates "one source of truth."

### Recommendation: **Option A**

---

## 4 · The plan, step by step

> Per "one thing at a time" and "late and perfect over early and wrong," each step has a verification gate. Nothing proceeds until the prior step is green.

### Step 0 · Pre-flight (read-only, no changes)
- 0.1 Confirm Postgres container `mining-guardian-db` is up on ROBS-PC: `docker ps | grep mining-guardian-db` (Rob runs locally; I cannot from sandbox).
- 0.2 Confirm `MG_DB_PASSWORD` is set in the container's `.env`.
- 0.3 Run the existing `verify_catalog_api_coverage.py` to capture **baseline emptiness numbers**: how many rows in each of the 22 tables today. Save to `docs/INTEL_CATALOG_BASELINE_2026-05-02.txt` for the audit trail.
- 0.4 Hit `GET http://localhost:8420/health` and a sample knowledge endpoint; capture the empty response so we have a "before" artifact.

### Step 1 · Branch + scaffolding
- 1.1 Create branch `fix/intel-catalog-split-brain-D12` off `main`.
- 1.2 Create `docs/RELEASE_NOTES_v1.0.2-catalog.md` skeleton.
- 1.3 Create `docs/INTEL_CATALOG_FIX_AUDIT_2026-05-02.md` for the over-documentation trail (every command run, every count, every screenshot).

### Step 2 · Run the existing seed (manufacturers + miner_models)
- 2.1 Run `seed_miner_models.sql` against `mining-guardian-db`: `docker exec -i mining-guardian-db psql -U guardian_admin -d mining_guardian -f /docker-entrypoint-initdb.d/seed_miner_models.sql` (matches the `deploy.ps1:69` command).
- 2.2 Verify row counts:
  - `SELECT COUNT(*) FROM hardware.manufacturers` → expect ~17
  - `SELECT COUNT(*) FROM hardware.miner_models` → expect ~320
- 2.3 If the count is short (because of enum/manufacturer prerequisites), apply the prerequisite enum updates from the SQL file's header (lines 7–18).

### Step 3 · Build the JSON-to-Postgres importer
- 3.1 Create `intelligence-catalog/seed-data/import_enrichment_from_json.py`. It will:
  - Load `unified_miner_index.json`
  - For each slug, call `dual_writer.propose_miner_model(slug, payload, source_tool="initial_enrichment_load")`
  - Print a per-slug status line; suppress duplicates; collect errors
  - End with: total proposed, total skipped (already pending/validated), total errors
- 3.2 Add a `--dry-run` flag (no-op if pre-existing in dual_writer; otherwise wrap each call).
- 3.3 Add unit tests in `tests/intelligence_catalog/test_import_enrichment.py` — minimum: dict-shape validation, slug normalization, dry-run honored.

### Step 4 · Promote and verify
- 4.1 Run `python -m intelligence_catalog.db.dual_writer --list-pending` — expect 288 pending.
- 4.2 Eyeball-check 10 random pending rows for sanity (slug, manufacturer, hashrate range).
- 4.3 Mark them validated (script TBD — likely a `--validate-all-pending` flag we add to `dual_writer.py`, or a one-off SQL `UPDATE staging.miner_model_proposals SET status='validated'`).
- 4.4 Run `python -m intelligence_catalog.db.dual_writer --promote-validated` — expect "promoted N rows."
- 4.5 Re-run `verify_catalog_api_coverage.py` — `hardware.miner_models` should now have ~320 rows with enrichment columns populated. Save the new numbers to the audit doc.

### Step 5 · Defensive fallback for the 19 still-empty tables
- 5.1 In `catalog_api.py`, wrap each query block in a defensive helper that returns `[]` on `UndefinedTable`, `OperationalError`, or empty result, with a structured log line: `"category=ops table=ops.failure_patterns coverage=0%"`.
- 5.2 Add a `coverage_report` field to the API's debug endpoint so the customer-facing reality is observable.
- 5.3 Write a follow-up backlog item B-15 to seed the remaining 19 tables (out of scope for this PR).

### Step 6 · End-to-end smoke
- 6.1 `curl http://localhost:8420/health` → `{"status":"ok"}`
- 6.2 `curl http://localhost:8420/knowledge/antminer-s19xp` → expect populated `model{}`, `enrichment{}`, empty arrays for ops/repair/firmware (with coverage notes)
- 6.3 Capture before/after side-by-side in audit doc.

### Step 7 · PR + handoff
- 7.1 Update `docs/MG_UNIFIED_TODO_LIST.md` Section 17 to flip catalog rows from 🔴 OPEN to ✅ DONE.
- 7.2 Bump version to `1.0.2` (catalog hotfix).
- 7.3 Open PR titled `fix(catalog): load enrichment into Postgres per D-12 (closes intel-catalog split-brain)` referencing this plan doc.
- 7.4 Provide Rob with the exact command sequence to run against `mining-guardian-db` post-merge.

---

## 5 · What is explicitly out of scope (and tracked)

| ID | Item | Why deferred |
|----|------|--------------|
| B-15 (new) | Seed the 19 remaining tables (ops.*, repair.*, firmware.*, facility.*) | Each needs its own data sourcing pass; one thing at a time |
| B-1..B-10, B-14 | Installer UX backlog | Already deferred to next sprint |
| Web-app dashboard rewrite | Fastify+TS (per stack memory) | Separate stack, separate sprint |
| `pool.*` and `regulatory.*` schemas | Not currently queried by API | No ROI yet |
| SQLite anything | "Never call SQLite live" — not touching it | Per Rob's standing order |

---

## 6 · Risks and mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Postgres container not running on ROBS-PC | Med | Step 0 pre-flight catches it; Rob restarts before continuing |
| Enum prerequisites in seed_miner_models.sql header missed | Med | Step 2.3 explicitly applies them |
| `dual_writer.propose_miner_model` rejects payloads with extra keys (specs, entity) | Low | Stage 3 unit tests; mitigation = strip to allowed keys before propose |
| Promote step UPSERT collisions | Low | Existing payload_hash unique index handles it |
| API still returns empties for ops/repair/firmware | **Certain** — by design | Step 5 defensive fallback + B-15 follow-up |
| 320 vs 288 gap (32 slugs in CSV but not in JSON) | Med | Run `rebuild_unified_index.py` first to close the gap before importing |

---

## 7 · Verification matrix (what "done" looks like)

| Check | Expected | Source |
|-------|----------|--------|
| `SELECT COUNT(*) FROM hardware.miner_models` | ≥ 288, ideally 320 | psql |
| `SELECT COUNT(*) FROM hardware.manufacturers` | ≥ 17 | psql |
| `GET /knowledge/antminer-s19xp` returns non-empty `model` and `enrichment` | yes | curl |
| `GET /coverage` reports 100% on hardware, 0% on ops/repair/firmware | yes | curl |
| `verify_catalog_api_coverage.py` passes its existing assertions | yes | pytest |
| Qwen prompt injection returns real specs for "what's the temp range on an S19 XP" | yes | live Qwen test on the Mini |
| `MG_UNIFIED_TODO_LIST.md` shows 🔴→✅ for catalog rows | yes | git diff |

---

## 8 · Open questions for Rob (no work proceeds until answered)

1. **Run venue:** `mining-guardian-db` lives on ROBS-PC (Windows). Should I prepare commands you run there, or do you want to migrate the container to the Mac Mini first (per the LIVING_CATALOG.md 2026-04-30 cutover note)? The fix works either way; this is a "where" question, not a "what" question.

2. **Validation policy:** Step 4.3 needs to mark 288 staging rows as validated. Two options:
   - 4.3a Auto-validate everything from the initial bulk import (fastest)
   - 4.3b Eyeball each one in batches of 25 (safer, slower) — your "late and perfect" preference might want this
   I default to 4.3a with a clearly logged "initial_enrichment_load auto-validated" reason; if you want 4.3b say so.

3. **Live Qwen test:** verification matrix line 6 needs the Mini awake + Ollama running. Do you want me to leave that as a separate manual step in the runbook, or is it a hard gate before merge?

4. **Versioning:** I'm proposing v1.0.2 for the catalog hotfix. If you'd rather call this v1.1.0 (because it's a bigger architectural fix than B-11/12/13), say so — naming only.

---

## 9 · Estimated effort

| Phase | Effort | Notes |
|-------|--------|-------|
| Plan approval | depends on Rob | This document |
| Step 0–2 (run existing seed) | ~30 min Rob's hands-on time | Most of it is `docker exec` + verifying counts |
| Step 3 (write importer + tests) | ~2 hours agent work | Then handed to Rob to run |
| Step 4 (promote) | ~15 min Rob's hands-on | After importer green |
| Step 5 (defensive fallback) | ~1 hour agent work | Pure Python in `catalog_api.py` |
| Step 6–7 (smoke + PR) | ~30 min combined | |
| **Total elapsed** | **~half a day** | Spread over a focused session |

---

## 10 · Appendix — Files I will touch

**Create:**
- `intelligence-catalog/seed-data/import_enrichment_from_json.py`
- `tests/intelligence_catalog/test_import_enrichment.py`
- `docs/RELEASE_NOTES_v1.0.2-catalog.md`
- `docs/INTEL_CATALOG_FIX_AUDIT_2026-05-02.md`
- `docs/INTEL_CATALOG_BASELINE_2026-05-02.txt` (pre-fix snapshot)

**Modify:**
- `intelligence-catalog/catalog-api/catalog_api.py` (Step 5 defensive helpers + `/coverage` endpoint)
- `intelligence-catalog/db/dual_writer.py` (add `--validate-all-pending` flag if Rob picks 4.3a)
- `pyproject.toml` (version bump)
- `docs/MG_UNIFIED_TODO_LIST.md` (Section 17 status flips, new B-15 entry)
- `docs/INSTALLER_UX_BACKLOG_2026-05-01.md` (cross-link B-9 closure)

**Do not touch (out of scope):**
- Anything under `installer/`, `scripts/setup.sh`, `core/`, `api/dashboard_api.py`, the SQLite archive, or the Fleet auto-discovery code.

---

*End of plan v1. Awaiting Rob's go/no-go.*
