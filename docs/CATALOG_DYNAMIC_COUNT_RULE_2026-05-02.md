# Catalog Dynamic-Count Rule — 2026-05-02

**Owner:** Operator (Rob)
**Recorded:** 2026-05-02
**Source:** Operator quote during PR-B drafting: *"remember the list grows as miners get added so it needs to reflect that on grafana, it is not a static number"*

---

## The rule

The Bitcoin SHA-256 miner catalog (`hardware.miner_models` in the catalog Postgres) is a **living, growing list**. New manufacturers, new generations, new chips, new firmware variants land in this table regularly via `catalog_updater.py --add-from-csv` and the per-PR seed updates. The current count at v1.0.2 build is **320** (313 baseline + 7 Bitaxe in PR #102), but the count is expected to grow.

This means:

### 1. Grafana Intelligence Report miner-dropdown must be SQL-driven

**Forbidden:** A hardcoded miner list embedded in the Grafana dashboard JSON, which has to be edited every time a model is added.

**Required:** A Grafana variable backed by a SQL query, evaluated on every dashboard load:

```sql
SELECT canonical_name
FROM hardware.miner_models
ORDER BY canonical_name;
```

Once that variable feeds the dropdown, the dropdown automatically reflects whatever rows are in `hardware.miner_models` — no Grafana edit ever needed when the catalog grows. This is the only acceptable design.

### 2. The catalog API and Intelligence Report API already follow this rule

`api/intelligence_report_api.py` and `intelligence-catalog/catalog-api/catalog_api.py` already read `hardware.miner_models` at request time. They are correct as-is. The gap is **only** in the Grafana dashboard JSON, which currently encodes a static list.

### 3. Hardcoded counts in docs are fine, but must be framed as point-in-time

When a doc mentions a row count (README, AI_ROADMAP, VISION, CAPABILITIES, runbooks), it must:

- Cite the specific build version (e.g., "320 at v1.0.2 build") — never an unqualified "the catalog has 320 rows."
- Note that the count grows over time.
- Point to `intelligence-catalog/seed-data/seed_miner_models.sql` as the source of truth (its `INSERT INTO hardware.miner_models` count is the canonical seed count).

When the row count changes, the canonical figure to update is the v-tagged build comment, not a scattered set of hardcoded numbers.

### 4. The "313 baseline + 7 Bitaxe in PR #102" provenance must be preserved

Even when the count moves, the provenance line — *the original 313-row C4 baseline plus the 7 Bitaxe rows added in PR #102* — is what tells a future operator how the catalog got to its current size. Do not strip it just to land a search-replace. Add new provenance entries as new contributing PRs land:

```
v1.0.2 catalog = 313 (C4 baseline)
              + 7 (Bitaxe, PR #102)
              + … (future additions, with PR # cited)
              = 320 at v1.0.2 build
```

---

## Verification (do this any time you want to re-confirm the canonical count)

```bash
# Source-of-truth count: INSERT statements into hardware.miner_models in the seed SQL
cd ~/code/Mining-Guardian
grep -c "^INSERT INTO hardware.miner_models" \
  intelligence-catalog/seed-data/seed_miner_models.sql

# Cross-check against the master CSV (data rows, excluding header)
tail -n +2 intelligence-catalog/seed-data/all_bitcoin_sha256_miners.csv | wc -l

# Live-DB count, post-install
psql -U guardian_app -d mining_guardian_catalog \
  -c "SELECT COUNT(*) FROM hardware.miner_models;"
```

All three numbers must match. If they don't, the catalog is in an inconsistent state and the seed must be re-run. As of 2026-05-02 all three return **320**.

---

## Status of the Grafana fix

**Status:** Deferred, not blocked. Tracked on `AI_ROADMAP.md` and `docs/VISION.md` as the Grafana miner-dropdown SQL-driven variable item. Not in the v1.0.2 cutover scope. Will be picked up after the Mac Mini install is verified green and the app project starts.

**Why deferred:** The Mac Mini install (Sunday/Monday 2026-05-04) does not depend on the Grafana variable change. The dashboard works today; it just goes stale every time a new miner lands. We accept that until v1.0.3.

**Forbidden until fixed:** Editing the Grafana dashboard JSON to add hardcoded miner names every time a new model lands. The right answer is the SQL-driven variable; do that one once and never touch it again.
