# Bucket 10 — Full Repo Documentation Cleanup Audit

**Date:** 2026-04-29
**Author:** Mining Guardian agent (autonomous run)
**Status:** AUDIT + PLAN ONLY — no archives/deletes have happened yet
**Doctrine:** "rather be late and perfect than early and wrong" + "always comprehensive, always over-document"

---

## 0. Why this audit exists

Mining Guardian's `docs/` directory and repo root carry **104 Markdown files** as of main HEAD `7601b758` (post PR #59 + PR #79 merges). Roughly half of those are **dated session logs, handoffs, and one-off resume points** from the late-March / early-April push toward the Mac-Mini era. The repo has shipped past most of them — Bucket 6 closed today, Bucket 7 closed today, the PKG installer rewrite landed last week, the catalog schema is on the VPS — and the doc graveyard is now the single biggest source of "what is real?" friction whenever a new session starts.

This audit:

1. Inventories every `*.md` at `./` and in `./docs/`
2. Counts incoming references for each file (other `.md`/`.py`/`.sh`/`.yml`/`.html`/`.txt` files mentioning it by basename)
3. Tiers the inventory into Archive-Safe / Archive-After-Citation-Update / Keep
4. Proposes a **two-PR execution plan** (this audit doc, then a follow-up move/cite-update PR)

**No file has been moved, deleted, or rewritten yet.** This document is the "spec" Bucket 10 will execute against, after Bobby reviews the tiering.

---

## 1. Method

Reference counting was performed on a fresh clone of `main` at SHA `7601b758` using a simple basename grep across `*.md`, `*.py`, `*.sh`, `*.yml`, `*.yaml`, `*.html`, `*.txt`. Self-references were excluded; the `.git` directory was excluded. The script lives at `/tmp/mg_audit/refcount.sh` (not committed — it's a one-shot audit tool, not part of the repo).

**Caveats / known limitations:**

- The script matches the **exact basename** only. Wildcard references like ``docs/PERPLEXITY_PROMPT_*.md`` in `CLAUDE.md` are **not** counted. Two files (V1 + V2 of the catalog Perplexity prompt) sit in Tier A by exact-match count but are technically referenced via wildcard in `CLAUDE.md`.
- The script does not parse Markdown link syntax — a malformed link still counts as a reference if the basename appears anywhere in the file.
- "Reference count" is a **proxy** for importance, not a guarantee. Living-doc status was verified by spot-checking each Tier-A file before moving it into the archive list.

---

## 2. Inventory summary

| Location | `*.md` count |
|---|---|
| Repo root | 8 |
| `docs/` | 96 |
| **Total** | **104** |

### 2.1. Reference-count distribution

| Refs | File count |
|---|---|
| 0 | 15 |
| 1 | 20 |
| 2 | 13 |
| 3 | 14 |
| 4 | 11 |
| 5 | 9 |
| 6 | 2 |
| 7 | 7 |
| 8 | 3 |
| 9 | 3 |
| 11 | 1 (`docs/CRON_SCHEDULE.md`) |
| 12 | 1 (`docs/DECISIONS.md`) |
| 14 | 1 (`AI_ROADMAP.md`) |
| 16 | 1 (`docs/VISION.md`) |
| 18 | 1 (`REPAIR_LOG.md`) |
| 33 | 1 (`README.md`) |
| 39 | 1 (`CLAUDE.md`) |

**Top 5 most-referenced docs (the load-bearing ones — never touch):** `CLAUDE.md` (39), `README.md` (33), `REPAIR_LOG.md` (18), `docs/VISION.md` (16), `AI_ROADMAP.md` (14).

---

## 3. Tier A — Archive immediately (15 files, ~83 KB total)

These have **zero incoming references** anywhere in the repo. They are dated session logs, superseded prompt drafts, or one-off "ready to apply" notes whose work was either applied (and the note never updated) or quietly dropped.

| Path | Size | Date / kind | Why archive |
|---|---|---|---|
| `SESSION_COMPLETE.md` (root) | 4.0 KB | 2026-04-15 session log | One-off final-day summary, superseded by every later SESSION_LOG_* |
| `docs/DG1_FIX_READY_TO_APPLY.md` | 0.2 KB | 2026-04-13 | "DG-1" not mentioned in `MG_UNIFIED_TODO_LIST.md` or `DECISIONS.md`; either applied silently or dropped |
| `docs/PERPLEXITY_PROMPT_MINING_INTELLIGENCE_CATALOG.md` | 7.5 KB | early draft | **Superseded by V2** in same dir (V2 is the comprehensive version) |
| `docs/PERPLEXITY_PROMPT_MINING_INTELLIGENCE_CATALOG_V2.md` | 17.4 KB | comprehensive prompt | Catalog schema research artifact — research is done, schema is deployed (PR #68); now historical |
| `docs/RESUME_HERE_2026_04_08.md` | 5.6 KB | 2026-04-08 morning | Superseded by `RESUME_HERE_2026_04_08_EVENING.md` (same day) |
| `docs/SESSION_LOG_2026-04-10-afternoon.md` | 4.5 KB | session log | dated |
| `docs/SESSION_LOG_2026-04-10-late-night.md` | 4.5 KB | session log | dated |
| `docs/SESSION_LOG_2026-04-10.md` | 3.9 KB | session log | dated |
| `docs/SESSION_LOG_2026-04-12.md` | 7.2 KB | session log | dated |
| `docs/SESSION_LOG_2026-04-13.md` | 5.1 KB | session log | dated; April-13 work captured in `SESSION_2026-04-13_S21_TEST_AND_FIXES.md` (Tier B) |
| `docs/SESSION_LOG_2026-04-17.md` | 3.5 KB | session log | dated |
| `docs/SESSION_LOG_2026-04-18.md` | 3.4 KB | session log | dated |
| `docs/SESSION_LOG_2026-04-21.md` | 3.6 KB | session log | dated |
| `docs/SESSION_LOG_2026-04-26.md` | 10.3 KB | session log | dated; superseded by 04-27 / 04-28 / 04-29 |
| `docs/SESSION_SUMMARY_2026-04-13-afternoon.md` | 0.5 KB | 2026-04-13 afternoon | dated, redundant with `SESSION_2026-04-13_S21_TEST_AND_FIXES.md` |

**Action:** `git mv` each file to `docs/_archive/2026-04/` (new dir). Add `docs/_archive/README.md` explaining the archive. **No citation updates required** because these have zero incoming references (after we exclude their own self-references and the wildcard glob in `CLAUDE.md`).

**Wildcard-glob caveat:** The `CLAUDE.md` "Tracked artifacts" table at L322 references `docs/PERPLEXITY_PROMPT_MINING_INTELLIGENCE_CATALOG*.md`. After the V1+V2 archive, that table row should be updated to point at the new archive path, OR removed entirely. Recommend **remove** — the catalog schema research is finished and the file no longer needs a tracker entry.

---

## 4. Tier B — Archive after citation update (33 files)

These have 1 or 2 incoming references. In nearly every case, the only thing referencing them is **`CLAUDE.md`'s** "Tracked artifacts" / "Doc index" tables, which need updating regardless. Archiving these requires:

1. Update the citation(s) in the referencing file
2. Move the file to `docs/_archive/2026-04/`
3. (If `CLAUDE.md` is the only referencer and the entry is just an index row) consider deleting the row instead of pointing it at the archive

### 4.1. Tier B-1 (single reference — 20 files)

| Path | Size | Referenced by | Treatment |
|---|---|---|---|
| `AUDIT_SUMMARY_2026-04-13.md` (root) | 6.7 KB | `CLAUDE.md` | drop CLAUDE row, archive |
| `docs/AI_DATA_AUDIT_2026-04-10.md` | 9.5 KB | `CLAUDE.md` | drop CLAUDE row, archive |
| `docs/BIXBIT_DIRECT_API.md` | 8.4 KB | `CLAUDE.md` | **PROBABLY KEEP** — vendor API doc, not a session artifact. Verify before archiving. |
| `docs/COMPLETE_AI_AUDIT_2026-04-10.md` | 11.2 KB | `CLAUDE.md` | superseded by V2 (same dir); drop CLAUDE row, archive |
| `docs/COMPLETE_AI_AUDIT_V2_2026-04-10.md` | 17.3 KB | `CLAUDE.md` | dated audit; the V2 supersedes V1 but neither is now active. Archive both |
| `docs/CONFIDENCE_SCORING.md` | 6.8 KB | `CLAUDE.md` | **PROBABLY KEEP** — design doc for confidence pipeline, possibly still active. Verify. |
| `docs/CONTAINER_SENSOR_REFERENCE.md` | 6.6 KB | `CLAUDE.md` | **PROBABLY KEEP** — vendor reference, sister of `CONTAINER_MONITORING.md` (Tier C). Verify. |
| `docs/HANDOFF_2026_04_09_MIDMORNING.md` | 20.5 KB | `LATENT_BUGS.md` | dated handoff; update LATENT_BUGS citation, archive |
| `docs/OVERNIGHT_TEST_STATUS_2026-04-13.md` | 3.2 KB | `CLAUDE.md` | dated test status; drop CLAUDE row, archive |
| `docs/POSTGRES_MIGRATION_STATUS_2026-04-23.md` | 6.6 KB | `POSTGRES_MIGRATION_STATUS_2026-04-24.md` | direct successor doc references it for diff; update next-day's citation + archive 23 |
| `docs/POSTGRES_STAGING_STATE_2026-04-23.md` | 5.9 KB | `CLAUDE.md` | dated staging snapshot; drop CLAUDE row, archive |
| `docs/PROFILE_MAP_QUESTIONS.md` | 5.0 KB | `CLAUDE.md` | **VERIFY** — questions doc, might still be open work |
| `docs/REMAINING_WORK_2026-04-28.md` | 12.0 KB | `LATENT_BUGS.md` | dated; superseded by today's progress. Update LATENT_BUGS, archive |
| `docs/RESUME_HERE_2026_04_08_0840.md` | 6.8 KB | `RESUME_HERE_2026_04_08_EVENING.md` | direct successor; update EVENING citation, archive 0840 |
| `docs/SESSION_2026-04-13_S21_TEST_AND_FIXES.md` | 6.7 KB | `LATENT_BUGS.md` | dated session log; update LATENT_BUGS, archive |
| `docs/SESSION_COMPLETE_2026-04-13.md` | 4.5 KB | `OVERNIGHT_TEST_STATUS_2026-04-13.md` | both dated; will be archived together |
| `docs/SESSION_LOG_2026-04-16.md` | 5.5 KB | `LATENT_BUGS.md` | dated session log; update LATENT_BUGS, archive |
| `docs/SESSION_REPORT_2026-04-23.md` | 7.5 KB | `NEXT_SESSION.md` | NEXT_SESSION.md is a **superseded** doc (Tier C kept for audit) — citation can stay with archive prefix. Archive |
| `docs/SLACK_BRANDING_CHECKLIST.md` | 2.1 KB | `CLAUDE.md` | **VERIFY** — Slack branding may still be open scope (Bucket 9 area) |
| `docs/WHATSMINER_API.md` | 9.3 KB | `CLAUDE.md` | **PROBABLY KEEP** — vendor API doc, sister of AURADINE/AMS/BIXBIT. Verify. |

**5 of 20 flagged for verify-first** — vendor API/reference docs and design docs that look like living material despite low ref count. Bobby should review those 5 before archiving (BIXBIT_DIRECT_API, CONFIDENCE_SCORING, CONTAINER_SENSOR_REFERENCE, PROFILE_MAP_QUESTIONS, SLACK_BRANDING_CHECKLIST, WHATSMINER_API).

### 4.2. Tier B-2 (two references — 13 files)

| Path | Size | Referenced by | Treatment |
|---|---|---|---|
| `docs/AMS_API.md` | 8.6 KB | CLAUDE.md, AMS_INTEGRATION.md | **KEEP** — vendor API used by AMS_INTEGRATION |
| `docs/GRAFANA_PROMETHEUS_PLAN.md` | 6.1 KB | CLAUDE.md, REPAIR_LOG.md | **KEEP** — referenced by living REPAIR_LOG |
| `docs/HOW_TO_UPLOAD_LOGS_TO_CLAUDE.md` | 6.3 KB | CLAUDE.md, DEMO_DAY_HANDOFF_2026_04_08.md | **VERIFY** — uploader workflow may still be active |
| `docs/OUTSIDE_INIT_DB_AUDIT_2026-04-23.md` | 5.7 KB | CLAUDE.md, POSTGRES_STAGING_STATE_2026-04-23.md | both companions are dated; archive together |
| `docs/POSTGRES_MIGRATION_PLAN_2026-04-23.md` | 14.1 KB | CLAUDE.md, POSTGRES_MIGRATION_STATUS_2026-04-24.md | dated plan; update STATUS-04-24 citation, archive |
| `docs/POSTGRES_MIGRATION_STATUS_2026-04-24.md` | 10.9 KB | CLAUDE.md, SESSION_LOG_2026-04-24.md | most recent migration status — **KEEP** until next status snapshot supersedes it |
| `docs/REFINED_INSIGHTS_DESIGN.md` | 7.9 KB | CLAUDE.md, `ai/insight_manager.py` | **KEEP** — referenced from Python code |
| `docs/RUNBOOK_2026-04-27_afternoon.md` | 9.4 KB | CLAUDE.md, SESSION_LOG_2026-04-27.md | dated runbook; SESSION_LOG_2026-04-27 still high-ref. Defer archive until 04-27 log archives |
| `docs/RUNBOOK_2026-04-28_pkg_build.md` | 13.2 KB | RELEASE_NOTES_v1.0.0.md, RUNBOOK_DISTRIBUTION_v1.0.0.md | **KEEP** — referenced by living release docs |
| `docs/RUNBOOK_DISTRIBUTION_v1.0.0.md` | 11.3 KB | MG_UNIFIED_TODO_LIST.md, RUNBOOK_PKG_REBUILD.md | **KEEP** — current installer doc |
| `docs/RUNBOOK_PKG_REBUILD.md` | 16.0 KB | MG_UNIFIED_TODO_LIST.md, SESSION_LOG_2026-04-29.md | **KEEP** — listed in shared assets, current rebuild runbook |
| `docs/SESSION_LOG_2026-04-22.md` | 9.0 KB | AI_ROADMAP.md, SESSION_HANDOFF_2026-04-24.md | dated session log; both referencers are living. Update both citations, archive |
| `docs/WAREHOUSE_MECHANICAL.md` | 0.9 KB | CLAUDE.md, SESSION_LOG_2026-04-13.md | tiny stub; SESSION_LOG_2026-04-13 will be archived. **VERIFY** if domain content still wanted |

**Net Tier B-2 archive candidates:** OUTSIDE_INIT_DB_AUDIT_2026-04-23, POSTGRES_MIGRATION_PLAN_2026-04-23, SESSION_LOG_2026-04-22 (3 of 13). The other 10 are KEEP or VERIFY.

---

## 5. Tier C — Keep (56 files)

Everything with **3+ incoming references**, plus everything explicitly load-bearing. Highlights:

| File | Refs | Why keep |
|---|---|---|
| `CLAUDE.md` | 39 | Primary agent config — never touch |
| `README.md` | 33 | Repo entry point |
| `REPAIR_LOG.md` | 18 | Living repair history |
| `docs/VISION.md` | 16 | North-star doc |
| `AI_ROADMAP.md` | 14 | Forward plan |
| `docs/DECISIONS.md` | 12 | ADR ledger |
| `docs/CRON_SCHEDULE.md` | 11 | Cron source of truth |
| `NEXT_SESSION.md` | 9 | **SUPERSEDED but explicitly kept for audit trail** — banner in file says so |
| `docs/DAILY_LOG_CAPTURE_VISION.md` | 9 | Living vision |
| `docs/SECURITY.md` | 9 | Security policy / threat model |
| `docs/MG_UNIFIED_TODO_LIST.md` | 8 | The TODO source of truth |
| `docs/OPEN_LOG_UPLOADER_VISION.md` | 8 | Living vision |
| `docs/SESSION_LOG_2026-04-27.md` | 8 | Most recent comprehensive session log before today |
| `DEPLOYMENT_CHECKLIST.md` (root) | 7 | **Just merged via PR #79 (Bucket 6f)** — Mac-Mini era |
| `docs/SESSION_HANDOFF_2026-04-24.md` | 7 | Recent handoff still cited |
| `docs/DB_STATE_2026-04-23.md` | 7 | Latest DB snapshot |
| `docs/LATENT_BUGS.md` | 7 | Living bug tracker |
| `docs/OPERATOR_RULES.md` | 7 | Operator playbook |
| `docs/CLOUDFLARE_MIGRATION.md` | 7 | Living migration guide |
| `docs/DAILY_DEEP_DIVE_DESIGN.md` | 7 | Living design |

Plus all vendor/API docs (AURADINE, AMS, BIXBIT modulo verify), HVAC/container monitoring, MAC_MINI_DEPLOYMENT_RUNBOOK, INTELLIGENCE_CATALOG_STATUS, etc.

Full Tier-C list is just "everything not in Tier A or Tier B-archive-bucket" — 56 files total.

---

## 6. Special considerations

### 6.1. `NEXT_SESSION.md` (root)

Has 9 incoming references and a `> # ⚠️ SUPERSEDED — DO NOT ACT ON THIS DOCUMENT` banner. Per "comprehensive + over-document always" doctrine, the file is **kept** as a historical record. The banner is sufficient defense against accidental action; archiving it would break 9 callers. **Decision: KEEP, no change.**

### 6.2. `docs/SESSION_LOG_2026-04-29.md` (today)

Created in PR #59 (merged earlier today). 3 references at audit time, will accumulate more as today's work progresses. **KEEP — it's the active session log.**

### 6.3. `docs/MG_UNIFIED_TODO_LIST.md` rule

The convention is: every fix PR flips its row in this file in the same commit. Bucket 10's eventual archive PR must do the same — flip "Bucket 10" from 🔴 OPEN to ✅ DONE in the move commit.

### 6.4. Wildcard-glob references in `CLAUDE.md`

`CLAUDE.md` line 322 references `docs/PERPLEXITY_PROMPT_MINING_INTELLIGENCE_CATALOG*.md` — exact-match grep does not detect this. After Tier A archive, that row should either be:

- Removed entirely (recommended; catalog schema research is done)
- OR repointed at `docs/_archive/2026-04/PERPLEXITY_PROMPT_MINING_INTELLIGENCE_CATALOG*.md`

Other wildcard references in `CLAUDE.md` should be sanity-checked the same way before the archive PR ships.

---

## 7. Execution plan

### Phase 1 (this PR — #85, audit/plan only)

- [x] Inventory 104 files
- [x] Reference-count every file
- [x] Tier into A / B / C
- [x] Flag verify-first cases
- [x] Write this planning doc
- [ ] Open PR with this doc + flip Bucket 10 row in `MG_UNIFIED_TODO_LIST.md` from 🔴 OPEN → 🟡 PLAN APPROVED PENDING (or similar in-progress marker)

### Phase 2 (follow-up PR — once Bobby reviews tiering)

- Resolve the 5 Tier B-1 verify-first cases (BIXBIT_DIRECT_API, CONFIDENCE_SCORING, CONTAINER_SENSOR_REFERENCE, PROFILE_MAP_QUESTIONS, SLACK_BRANDING_CHECKLIST, WHATSMINER_API) → Bobby decides keep or archive
- Resolve the 2 Tier B-2 verify-first cases (HOW_TO_UPLOAD_LOGS_TO_CLAUDE, WAREHOUSE_MECHANICAL)
- Create `docs/_archive/2026-04/` with `README.md` index
- `git mv` Tier A files (15) — no citation updates needed
- `git mv` confirmed Tier B archive candidates + update each referencing citation in the same commit
- Drop dead `CLAUDE.md` "Tracked artifacts" rows for archived files
- Verify `MG_UNIFIED_TODO_LIST.md` Bucket 10 flip → ✅ DONE
- Total: ~15 Tier-A + ~10–15 Tier-B = **~25–30 files moved**, **~15–20 citations updated**

### Phase 3 (deferred — not part of Bucket 10)

- Larger directory restructure (e.g. `docs/runbooks/`, `docs/sessions/`, `docs/architecture/`, `docs/vendor-apis/`) is out of scope. Bucket 10 only **archives the dead and superseded** — it does not reorganize the living docs.

---

## 8. What this audit explicitly does NOT do

- Does not delete any file. Archive = `git mv` to `docs/_archive/2026-04/`. Files remain in repo history and on disk.
- Does not touch the top 15 most-referenced docs.
- Does not move active session/runbook material from this week (`SESSION_LOG_2026-04-27`, `_2026-04-28`, `_2026-04-29`, `RUNBOOK_PKG_REBUILD`, `RUNBOOK_DISTRIBUTION_v1.0.0`, `RUNBOOK_2026-04-28_pkg_build`).
- Does not modify any non-doc file (no `.py`, no `.sh`, no `migrations/`, no `installer/`).
- Does not change any active TODO except flipping the Bucket 10 row.

---

## 9. Open questions for Bobby

1. **Verify-first list (8 files):** BIXBIT_DIRECT_API, CONFIDENCE_SCORING, CONTAINER_SENSOR_REFERENCE, PROFILE_MAP_QUESTIONS, SLACK_BRANDING_CHECKLIST, WHATSMINER_API, HOW_TO_UPLOAD_LOGS_TO_CLAUDE, WAREHOUSE_MECHANICAL. Each looks like potentially-living material despite low refcount. Keep or archive?
2. **Wildcard `CLAUDE.md` row for catalog Perplexity prompts:** drop the row entirely, or repoint at archive?
3. **Archive directory naming:** `docs/_archive/2026-04/` (chronological) vs `docs/_archive/by-topic/` (categorical) vs `docs/sessions/archive/2026-04/` (by-content-type). Recommend `docs/_archive/2026-04/` — simplest, single-pass.

---

## 10. Sign-off

**Files audited:** 104
**Tier A (archive immediately):** 15 (~83 KB)
**Tier B (archive after citation update):** 33 candidates → ~13 confirmed safe, 8 flagged verify-first, 12 KEEP
**Tier C (keep):** 56
**Net moves expected:** ~25–30 files
**Net citation updates expected:** ~15–20 lines across `CLAUDE.md`, `LATENT_BUGS.md`, `RESUME_HERE_2026_04_08_EVENING.md`, `POSTGRES_MIGRATION_STATUS_2026-04-24.md`, `AI_ROADMAP.md`, `SESSION_HANDOFF_2026-04-24.md`

This audit is the spec. The next PR (#86 or whatever number is open at that point) executes against it after Bobby resolves §9.
