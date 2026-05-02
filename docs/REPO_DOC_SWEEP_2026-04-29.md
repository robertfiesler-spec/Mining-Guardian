# Repo Doc Sweep — 2026-04-29

**Branch:** `docs/repo-full-doc-sweep-2026-04-29`  
**Base:** `main` @ `3ea5e72f` (post-PR #90 squash)  
**Author:** Bobby + assistant pair-programming session  
**Purpose:** Final doc cleanup before Mac Mini install (tomorrow morning, 2026-04-30).

## Why this exists

Bobby flagged that several repo docs still reference SQLite (Phase 1 era), the deprecated `intelligence/` directory (Bucket 7.1), the OpenClaw integration (Bucket 4), and old VPS deployment paths — all work that completed weeks ago. The Bucket 10 audit (PR #85) cataloged docs into A/B/C tiers but didn't actually rewrite the stale content. This sweep does the rewrites.

Goal: by end of today, every `.md` file in the repo is either accurate-as-of-today, archived to `docs/archive/2026-04/`, or deleted. No stale references to SQLite, OpenClaw, `intelligence/`, or VPS-only paths remain in active docs.

## Inventory

Total `.md` files in repo: **242** (excluding `.git/`).

Stale-term breakdown across all docs (post-PR #90):

| Stale term | Hit count (files) |
|------------|-------------------|
| `sqlite` (case-insensitive) | 39 |
| `intelligence/` (deprecated dir path) | 11 |
| `openclaw` | 37 |
| VPS / Debian / `srv1549463` | 48 |
| 🔴 OPEN / TODO: / FIXME / XXX | 10 |
| Phase 1 / Phase 1A / Phase 1B | 3 |

## Decision matrix

| Action | Count | What happens |
|--------|-------|--------------|
| **DELETE** | 24 | `git rm` — entire `intelligence/` dir (Bucket 7.1, never merged), entire `deploy/openclaw-skills/` dir (Bucket 4, never merged), 5 root-level one-shot resume notes. Git history retains them. Also patches `installer/macos-pkg/scripts/build_pkg.sh` to drop the deprecated `intelligence/***` rsync include. |
| **ARCHIVE** | 36 | `git mv` to `docs/archive/2026-04/`. Stay searchable, out of active docs. |
| **REWRITE** | 4 | Full content rewrite — root-level high-visibility files. |
| **UPDATE** | 49 | Surgical edits — strip stale terms, keep doc structure. |
| **KEEP** | 134 | Already current or tooling files \w no stale content. |

## Execution sequence (single PR, multiple commits)

1. **Commit 1 (THIS commit):** Audit doc + inventory CSVs landed first as the record.
2. **Commit 2:** DELETE — 24 files: entire `intelligence/` directory (12 files), entire `deploy/openclaw-skills/` directory (7 files), 5 root-level one-shot notes (`NEXT_SESSION.md`, 3× `RESUME_HERE_*`, `MORNING_KICKOFF_PROMPT.md`). Also: 1-line patch to `installer/macos-pkg/scripts/build_pkg.sh` (`intelligence/***` → `intelligence-catalog/***`). `intelligence-catalog/` is LIVE CODE (catalog API, watchers, 320 miner seed CSV) and is preserved.
3. **Commit 3:** ARCHIVE — 36 files moved to `docs/archive/2026-04/`.
4. **Commit 4–7:** REWRITE — 4 root-level files, one commit each (`README.md`, `CLAUDE.md`, `AI_ROADMAP.md`, `DEPLOYMENT_CHECKLIST.md`).
5. **Commit 8–11:** UPDATE — 49 files batched by theme:
   - Commit 8: SQLite removal across all `docs/`.
   - Commit 9: OpenClaw removal across all `docs/`.
   - Commit 10: `intelligence/` reference rewrites across all `docs/`.
   - Commit 11: VPS path rewrites where Mac Mini is the target deployment.
6. **Commit 12:** Final grep verification — zero stale terms in active (non-archive) `.md` files. If any survived, fix them in this commit.
7. **Commit 13:** Session log update + study note.

Open one PR at the end — `docs(repo): full doc sweep — strip SQLite/OpenClaw/intelligence/ refs, archive 36 historical, delete 19 deprecated`.

## Tier 1 — DELETE (19 files)

These files are permanently removed from the working tree. Git history retains them.

| File | Stale hits | Rationale |
|------|------------|-----------|
| `docs/RESUME_HERE_2026_04_08_EVENING.md` | 72 | One-shot resume/kickoff prompts from April 8 sessions |
| `docs/RESUME_HERE_2026_04_08_0840.md` | 22 | One-shot resume/kickoff prompts from April 8 sessions |
| `docs/RESUME_HERE_2026_04_08.md` | 15 | One-shot resume/kickoff prompts from April 8 sessions |
| `NEXT_SESSION.md` | 14 | One-shot resume note from old session |
| `intelligence/README.md` | 13 | Deprecated tree (Bucket 7.1) — never executed PR cleanup |
| `intelligence/docs/intelligence_catalog_design_notes.md` | 6 | Deprecated tree (Bucket 7.1) — never executed PR cleanup |
| `intelligence-catalog/FIELD_INTELLIGENCE_PIPELINE.md` | 5 | Deprecated tree (Bucket 7.1) — never executed PR cleanup |
| `docs/MORNING_KICKOFF_PROMPT.md` | 4 | One-shot resume/kickoff prompts from April 8 sessions |
| `intelligence/DEPRECATED.md` | 4 | Deprecated tree (Bucket 7.1) — never executed PR cleanup |
| `deploy/openclaw-skills/guardian-db/SKILL.md` | 1 | OpenClaw removed in Bucket 4 — leftover skill files |
| `intelligence-catalog/LIVING_CATALOG.md` | 1 | Deprecated tree (Bucket 7.1) — never executed PR cleanup |
| `intelligence-catalog/research/MINER_CATALOG_RESEARCH_NOTES.md` | 1 | Deprecated tree (Bucket 7.1) — never executed PR cleanup |
| `deploy/openclaw-skills/guardian-db/references/schema.md` | 0 | OpenClaw removed in Bucket 4 — leftover skill files |
| `intelligence-catalog/research/asicminervalue_all_sha256.md` | 0 | Deprecated tree (Bucket 7.1) — never executed PR cleanup |
| `intelligence-catalog/research/bitmain_all_variants.md` | 0 | Deprecated tree (Bucket 7.1) — never executed PR cleanup |
| `intelligence-catalog/research/canaan_all_variants.md` | 0 | Deprecated tree (Bucket 7.1) — never executed PR cleanup |
| `intelligence-catalog/research/microbt_all_variants.md` | 0 | Deprecated tree (Bucket 7.1) — never executed PR cleanup |
| `intelligence-catalog/seed-data/README.md` | 0 | Deprecated tree (Bucket 7.1) — never executed PR cleanup |
| `intelligence/docs/intelligence_catalog_gap_analysis.md` | 0 | Deprecated tree (Bucket 7.1) — never executed PR cleanup |

## Tier 2 — ARCHIVE (36 files)

Moved verbatim to `docs/archive/2026-04/<original-filename>`. No content edits.

| File | Stale hits | Rationale |
|------|------------|-----------|
| `docs/HANDOFF_2026_04_09_MIDMORNING.md` | 95 | Historical session log — move to docs/archive/2026-04/ |
| `REPAIR_LOG.md` | 46 | Root-level historical — archive per user decision |
| `docs/DB_STATE_2026-04-23.md` | 37 | Postgres migration complete — point-in-time doc |
| `docs/SESSION_HANDOFF_2026-04-24.md` | 37 | Historical session log — move to docs/archive/2026-04/ |
| `docs/POSTGRES_MIGRATION_PLAN_2026-04-23.md` | 26 | Postgres migration complete — point-in-time doc |
| `docs/POSTGRES_MIGRATION_STATUS_2026-04-24.md` | 18 | Postgres migration complete — point-in-time doc |
| `docs/SESSION_LOG_2026-04-24.md` | 18 | Historical session log — move to docs/archive/2026-04/ |
| `docs/SESSION_LOG_2026-04-27.md` | 16 | Historical session log — move to docs/archive/2026-04/ |
| `docs/POSTGRES_STAGING_STATE_2026-04-23.md` | 13 | Postgres migration complete — point-in-time doc |
| `docs/SESSION_REPORT_2026-04-23.md` | 10 | Historical session log — move to docs/archive/2026-04/ |
| `docs/SESSION_LOG_2026-04-09.md` | 9 | Historical session log — move to docs/archive/2026-04/ |
| `docs/SESSION_LOG_2026-04-26.md` | 9 | Historical session log — move to docs/archive/2026-04/ |
| `docs/SESSION_LOG_2026-04-22.md` | 8 | Historical session log — move to docs/archive/2026-04/ |
| `SESSION_COMPLETE.md` | 7 | Root-level historical — archive per user decision |
| `docs/DB_STATE_2026-04-22.md` | 7 | Postgres migration complete — point-in-time doc |
| `docs/POSTGRES_MIGRATION_STATUS_2026-04-23.md` | 7 | Postgres migration complete — point-in-time doc |
| `docs/SESSION_NOTE_2026-04-29_grafana_dropdown.md` | 5 | Historical session log — move to docs/archive/2026-04/ |
| `docs/OUTSIDE_INIT_DB_AUDIT_2026-04-23.md` | 4 | Postgres migration complete — point-in-time doc |
| `docs/SESSION_LOG_2026-04-28.md` | 4 | Historical session log — move to docs/archive/2026-04/ |
| `docs/SESSION_NOTE_2026-04-29_operator_schedules.md` | 4 | Historical session log — move to docs/archive/2026-04/ |
| `docs/SESSION_LOG_2026-04-13.md` | 3 | Historical session log — move to docs/archive/2026-04/ |
| `AUDIT_SUMMARY_2026-04-13.md` | 2 | Point-in-time April 13 status |
| `docs/SESSION_COMPLETE_2026-04-13.md` | 2 | Historical session log — move to docs/archive/2026-04/ |
| `docs/SESSION_LOG_2026-04-10-late-night.md` | 2 | Historical session log — move to docs/archive/2026-04/ |
| `docs/SESSION_LOG_2026-04-10.md` | 2 | Historical session log — move to docs/archive/2026-04/ |
| `docs/SESSION_LOG_2026-04-21.md` | 2 | Historical session log — move to docs/archive/2026-04/ |
| `docs/CORE_DATABASE_AUDIT_2026-04-23.md` | 1 | Postgres migration complete — point-in-time doc |
| `docs/SESSION_LOG_2026-04-10-afternoon.md` | 1 | Historical session log — move to docs/archive/2026-04/ |
| `docs/SESSION_LOG_2026-04-29.md` | 1 | Historical session log — move to docs/archive/2026-04/ |
| `docs/SESSION_NOTE_2026-04-29_web_gui_mode_selector.md` | 1 | Historical session log — move to docs/archive/2026-04/ |
| `docs/SESSION_SUMMARY_2026-04-13-afternoon.md` | 1 | Historical session log — move to docs/archive/2026-04/ |
| `docs/OVERNIGHT_TEST_STATUS_2026-04-13.md` | 0 | Point-in-time April 13 status |
| `docs/SESSION_LOG_2026-04-12.md` | 0 | Historical session log — move to docs/archive/2026-04/ |
| `docs/SESSION_LOG_2026-04-16.md` | 0 | Historical session log — move to docs/archive/2026-04/ |
| `docs/SESSION_LOG_2026-04-17.md` | 0 | Historical session log — move to docs/archive/2026-04/ |
| `docs/SESSION_LOG_2026-04-18.md` | 0 | Historical session log — move to docs/archive/2026-04/ |

## Tier 3 — REWRITE (4 files)

Full rewrite. Old content checked into archive at `docs/archive/2026-04/<filename>.pre-sweep.md` first if it has historical value.

| File | Stale hits | Rationale |
|------|------------|-----------|
| `CLAUDE.md` | 50 | Claude Code agent instructions — must be current |
| `AI_ROADMAP.md` | 49 | Forward-looking roadmap — strip SQLite/OpenClaw |
| `README.md` | 35 | Top of repo — must reflect 2026-04-29 architecture |
| `DEPLOYMENT_CHECKLIST.md` | 27 | Customer-facing — final pass for Mac Mini install |

## Tier 4 — UPDATE (49 files)

Surgical edits only. Remove stale terms, fix references, keep document structure intact.

| File | Stale hits | Rationale |
|------|------------|-----------|
| `docs/MG_UNIFIED_TODO_LIST.md` | 62 | Docs file with 62 stale hits (sqlite=2, intel/=0, openclaw=23, vps=9) |
| `docs/VISION.md` | 24 | Docs file with 24 stale hits (sqlite=1, intel/=2, openclaw=18, vps=2) |
| `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md` | 23 | Docs file with 23 stale hits (sqlite=2, intel/=0, openclaw=1, vps=19) |
| `docs/CAPABILITIES.md` | 14 | Docs file with 14 stale hits (sqlite=0, intel/=0, openclaw=9, vps=5) |
| `docs/CLOUDFLARE_MIGRATION.md` | 14 | Docs file with 14 stale hits (sqlite=0, intel/=0, openclaw=8, vps=6) |
| `docs/CATALOG_ORPHAN_TABLES_2026-04-28.md` | 12 | Docs file with 12 stale hits (sqlite=0, intel/=9, openclaw=2, vps=1) |
| `docs/GRAFANA_PROMETHEUS_PLAN.md` | 11 | Docs file with 11 stale hits (sqlite=3, intel/=0, openclaw=0, vps=8) |
| `docs/MONDAY_INTELLIGENCE_CATALOG_PLAN.md` | 11 | Docs file with 11 stale hits (sqlite=0, intel/=5, openclaw=0, vps=5) |
| `docs/ROADMAP_TO_MAC_MINI_2026-05-05.md` | 11 | Docs file with 11 stale hits (sqlite=1, intel/=0, openclaw=6, vps=3) |
| `docs/DEMO_DAY_HANDOFF_2026_04_08.md` | 8 | Docs file with 8 stale hits (sqlite=0, intel/=0, openclaw=0, vps=7) |
| `.claude/commands/wrap-up.md` | 6 | .claude tooling with 6 stale hits |
| `docs/INTELLIGENCE_CATALOG_STATUS.md` | 6 | Docs file with 6 stale hits (sqlite=0, intel/=2, openclaw=0, vps=3) |
| `docs/LATENT_BUGS.md` | 6 | Docs file with 6 stale hits (sqlite=0, intel/=0, openclaw=0, vps=6) |
| `docs/CORS_LOCKDOWN_PLAN.md` | 5 | Docs file with 5 stale hits (sqlite=0, intel/=0, openclaw=4, vps=1) |
| `docs/DECISIONS.md` | 5 | Docs file with 5 stale hits (sqlite=3, intel/=0, openclaw=1, vps=0) |
| `docs/HVAC_SYSTEMS.md` | 5 | Docs file with 5 stale hits (sqlite=0, intel/=0, openclaw=0, vps=5) |
| `docs/BUCKET_10_REPO_DOCS_AUDIT_2026-04-29.md` | 4 | Docs file with 4 stale hits (sqlite=0, intel/=0, openclaw=0, vps=1) |
| `docs/HOW_TO_UPLOAD_LOGS_TO_CLAUDE.md` | 4 | Docs file with 4 stale hits (sqlite=0, intel/=0, openclaw=0, vps=3) |
| `.claude/commands/create-plan.md` | 3 | .claude tooling with 3 stale hits |
| `docs/CRON_RECONCILIATION.md` | 3 | Docs file with 3 stale hits (sqlite=0, intel/=0, openclaw=0, vps=3) |
| `docs/DAILY_DEEP_DIVE_DESIGN.md` | 3 | Docs file with 3 stale hits (sqlite=0, intel/=0, openclaw=0, vps=3) |
| `docs/OPERATOR_SCHEDULES.md` | 3 | Docs file with 3 stale hits (sqlite=0, intel/=0, openclaw=0, vps=3) |
| `docs/SESSION_2026-04-13_S21_TEST_AND_FIXES.md` | 3 | Docs file with 3 stale hits (sqlite=0, intel/=0, openclaw=0, vps=2) |
| `docs/TESTING.md` | 3 | Docs file with 3 stale hits (sqlite=2, intel/=0, openclaw=1, vps=0) |
| `.claude/agents/orchestrator.md` | 2 | .claude tooling with 2 stale hits |
| `.claude/commands/next.md` | 2 | .claude tooling with 2 stale hits |
| `.claude/commands/plan.md` | 2 | .claude tooling with 2 stale hits |
| `.claude/hooks/README.md` | 2 | .claude tooling with 2 stale hits |
| `docs/CONTAINER_MONITORING.md` | 2 | Docs file with 2 stale hits (sqlite=0, intel/=0, openclaw=2, vps=0) |
| `docs/CRON_SCHEDULE.md` | 2 | Docs file with 2 stale hits (sqlite=0, intel/=0, openclaw=0, vps=2) |
| `docs/LOG_COLLECTION_ARCHITECTURE.md` | 2 | Docs file with 2 stale hits (sqlite=0, intel/=0, openclaw=0, vps=2) |
| `docs/PERPLEXITY_PROMPT_MINING_INTELLIGENCE_CATALOG.md` | 2 | Docs file with 2 stale hits (sqlite=1, intel/=0, openclaw=0, vps=1) |
| `docs/REMAINING_WORK_2026-04-28.md` | 2 | Docs file with 2 stale hits (sqlite=0, intel/=0, openclaw=0, vps=2) |
| `docs/WEB_GUI_OPERATOR_CONSOLE.md` | 2 | Docs file with 2 stale hits (sqlite=0, intel/=0, openclaw=0, vps=2) |
| `installer/macos-pkg/README.md` | 2 | 2 stale hits |
| `mg_import_tool/README.md` | 2 | 2 stale hits |
| `.claude/WORKFLOW.md` | 1 | .claude tooling with 1 stale hits |
| `.claude/agents/architect.md` | 1 | .claude tooling with 1 stale hits |
| `.claude/agents/security-reviewer.md` | 1 | .claude tooling with 1 stale hits |
| `.claude/commands/init.md` | 1 | .claude tooling with 1 stale hits |
| `.claude/commands/security-check.md` | 1 | .claude tooling with 1 stale hits |
| `.claude/commands/verify-visual.md` | 1 | .claude tooling with 1 stale hits |
| `.claude/rules/suggest-commands.md` | 1 | .claude tooling with 1 stale hits |
| `docs/API_REFERENCE.md` | 1 | Docs file with 1 stale hits (sqlite=0, intel/=0, openclaw=1, vps=0) |
| `docs/BIXBIT_DIRECT_API.md` | 1 | Docs file with 1 stale hits (sqlite=0, intel/=0, openclaw=0, vps=0) |
| `docs/OPEN_LOG_UPLOADER_VISION.md` | 1 | Docs file with 1 stale hits (sqlite=0, intel/=0, openclaw=0, vps=0) |
| `docs/PERPLEXITY_PROMPT_MINING_INTELLIGENCE_CATALOG_V2.md` | 1 | Docs file with 1 stale hits (sqlite=1, intel/=0, openclaw=0, vps=0) |
| `docs/REPAIR.md` | 1 | Docs file with 1 stale hits (sqlite=0, intel/=0, openclaw=0, vps=1) |
| `docs/RUNBOOK_BUCKET_3_RECONCILIATION_2026-04-29.md` | 1 | Docs file with 1 stale hits (sqlite=0, intel/=0, openclaw=0, vps=0) |

## KEEP files (134)

Listed in the inventory CSV. Most are `.claude/` tooling files (commands/agents/rules/skills) and current 2026-04-29 docs. Will be re-grepped in Commit 12 to verify zero stale terms remain.

## Out-of-scope (deferred until after doc sweep)

- Triage of 23 open PRs and 43 stale origin branches.
- Final security sweep (secrets, hardcoded creds, debug=True, 0.0.0.0 binds).
- Code cleanup (dead imports, unused files, TODO/FIXME audit).
- Test pass on current main.
- Final preflight + `v1.0.0-install-ready` tag.
- Grafana 320-miner dropdown fix.

All deferred per Bobby's directive: "when the documents are done we will continue with the polishing."
