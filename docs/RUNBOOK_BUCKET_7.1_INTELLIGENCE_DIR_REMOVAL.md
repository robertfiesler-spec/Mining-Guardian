# Bucket 7.1 — `intelligence/` directory removal

**Date:** 2026-04-29
**PR:** Bucket 7.1 (this PR)
**Authority:** `intelligence/DEPRECATED.md` (committed 2026-04-27) + `docs/MG_UNIFIED_TODO_LIST.md` §8.1 (orphan code) + `docs/CATALOG_ORPHAN_TABLES_2026-04-28.md`.
**Originally scheduled:** Mon 2026-05-04 housekeeping PR (per DEPRECATED.md). Pulled forward 5 days because (a) Bucket 6 closed today freeing the install-rebuild critical path, (b) the directory contains the 7-bug unpatched schema duplicates which are an active footgun for the Mac-Mini installer.

## What is being removed (10 files, 1 directory)

| Path | Sha (main, base tree `5865f41a`) | Why |
|---|---|---|
| `intelligence/.env.example` | `eb98c92f` | Replaced by `installer/secrets.env.example` (Thursday rewrite per DEPRECATED.md). |
| `intelligence/DEPRECATED.md` | `08870bd9` | Tombstone removed with the directory it tombstones. |
| `intelligence/README.md` | `e6141617` | Replaced by `docs/VISION.md` + `intelligence-catalog/seed-data/README.md`. |
| `intelligence/database/intelligence_catalog_schema.sql` | `ee400b45` | **Unpatched duplicate** of `intelligence-catalog/seed-data/intelligence_catalog_schema.sql` (still has 7 latent bugs PR #12 fixed in canonical copy). |
| `intelligence/database/intelligence_catalog_schema_v2_additions.sql` | `818a0ec1` | **Unpatched duplicate** of `intelligence-catalog/seed-data/intelligence_catalog_schema_v2_additions.sql`. |
| `intelligence/database/intelligence_catalog_schema_v3_additions.sql` | `e2de2b5f` | **Unpatched duplicate** of `intelligence-catalog/seed-data/intelligence_catalog_schema_v3_additions.sql`. |
| `intelligence/docker-compose.yml` | `8c16d68a` | Mac Mini uses native Postgres, not Docker. |
| `intelligence/docs/intelligence_catalog_design_notes.md` | `b0e9e8ea` | Superseded by `intelligence-catalog/FIELD_INTELLIGENCE_PIPELINE.md`. |
| `intelligence/docs/intelligence_catalog_gap_analysis.md` | `a2b5123a` | Gap analysis findings already absorbed into `docs/CATALOG_ORPHAN_TABLES_2026-04-28.md`. |
| `intelligence/docs/mining_intelligence_catalog_paper.pdf` | `0a99a4e8` | White-paper PDF — moved to `intelligence-catalog/research/` long ago; this was a stale duplicate. |
| `intelligence/docs/schema_inventory.json` | `ccd3aaad` | Stale inventory; `intelligence-catalog/seed-data/intelligence_catalog_schema.sql` is the source of truth. |
| `intelligence/postgres-tuning.conf` | `4c1d5973` | Mac Mini tuning lives in `installer/postgres.conf.template` (Thursday rewrite). |

Directory tree entries `intelligence/`, `intelligence/database/`, and `intelligence/docs/` collapse automatically once their last children are removed.

## Confirmed safe to delete

* **Code refs:** `0` Python/shell/yaml/json files in the repo reference `intelligence/database/`, `intelligence/docker-compose.yml`, `intelligence/postgres-tuning.conf`, or `intelligence/.env.example`. (Verified by `grep -rln 'intelligence/database\|intelligence/docker-compose\|intelligence/postgres-tuning\|intelligence/.env' --include='*.py' --include='*.sh' --include='*.yml' --include='*.yaml' --include='*.toml' --include='*.json'` returning empty.)
* **Doc refs:** `3` retrospective docs reference the old paths (`docs/CATALOG_ORPHAN_TABLES_2026-04-28.md`, `docs/MONDAY_INTELLIGENCE_CATALOG_PLAN.md`, `docs/SESSION_LOG_2026-04-27.md`) — these are historical session/planning documents and intentionally preserved as-written. They will be updated only as part of Bucket 10 (full doc cleanup sweep).
* **Module collision:** `intelligence/` (the deprecated directory) contains **no Python files**, so removal cannot conflict with the launchd reference `python -m intelligence.feedback_loop_daemon`. NOTE: that launchd reference is itself stale — the actual file lives at `intelligence-catalog/db/feedback_loop_daemon.py`. Path mismatch is filed as a follow-up finding (see "Follow-up findings" below); not fixed in this PR to keep scope tight.
* **Disk:** ~250 KB total (most of it the 244-page PDF white-paper duplicate at 0a99a4e8).

## Follow-up findings (NOT fixed in this PR)

1. **Launcher path mismatch.** `installer/macos-pkg/scripts/postinstall.sh` (and the inline launcher in PR #80) references `python -m intelligence.feedback_loop_daemon`, but the actual entry point is `intelligence-catalog/db/feedback_loop_daemon.py`. Bucket 7.x candidate: align the launcher to point at the canonical module (likely `python -m intelligence_catalog.db.feedback_loop_daemon` after a Python package rename, or run-by-path). Tracked in unified TODO append below.
2. **`intelligence-catalog/docker-compose.yml` survives** — Mac Mini moved to native Postgres (no Docker), so this file is also dead. Defer to Bucket 7.x along with `intelligence-catalog/deploy.ps1` (PowerShell — Mac Mini has no Windows path). Audit needed first.

## Verify after merge

```
# 1. Directory gone
test ! -e intelligence/

# 2. No stale-link breakages in runtime code
git grep -E 'intelligence/(database|docker-compose|postgres-tuning|\.env)' -- '*.py' '*.sh' '*.yml' '*.yaml' '*.toml' '*.json' | wc -l
# -> 0

# 3. Canonical schema still present
test -f intelligence-catalog/seed-data/intelligence_catalog_schema.sql
test -f intelligence-catalog/seed-data/intelligence_catalog_schema_v2_additions.sql
test -f intelligence-catalog/seed-data/intelligence_catalog_schema_v3_additions.sql
```

## Reverting (if needed)

```
git revert <merge-commit-sha>
```

The Git Data API tree we built lets the deletion be undone with one revert; no on-disk side effects (the dir was never deployed to any production node — that's exactly the point of the deprecation).
