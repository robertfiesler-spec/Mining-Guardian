# Mining Guardian — Branch Consolidation Plan
**Date:** 2026-04-25 (Saturday evening, post pre-prod sprint)
**Decision deadline:** Before Mac Mini cutover (early May 2026)
**Author:** drafted during bonus sprint, push to audit branch as reference

---

## TL;DR

You have **9 branches** in addition to `main`. After tomorrow's typo rename + CR-4
merge, only **2 branches matter going forward**:
- `pre-prod-audit-2026-04-25` — the audit branch (keep as historical record + tracker for CR-5/6/7)
- A new `release/mac-mini` branch you should create next session, which becomes the integration line for installer + cherry-picked catalog work

The other **7 branches should be killed or salvaged** within the next week:
- 4 are **dead** (3+ weeks old, 0 commits ahead)
- 3 are **divergent reorgs** that all delete the same critical files — they cannot be merged as-is and need slice-by-slice cherry-picking

---

## Branch inventory

| Branch | Ahead | Behind | Last activity | Verdict |
|---|---|---|---|---|
| `main` | (baseline) | — | 5h ago | Production line |
| `hotfix/cr-4-pg-shim-2026-04-25` | 1 | 0 | 45m ago | **MERGE TOMORROW** |
| `pre-prod-audit-2026-04-25` | 42 | 212 | 11m ago | **KEEP** (historical + CR backlog) |
| `feature/intelligence-catalog` | 21 | 212 | 4h ago | **CHERRY-PICK** in slices, do not merge |
| `installer-build` | 3 | 349 | 5d ago | **REBASE FROM MAIN** as `release/mac-mini` |
| `feature/fast-cohort-analysis` | 2 | 120 | 6d ago | **SALVAGE** 2 commits, delete branch |
| `security/hardening-apr21` | 0 | 103 | 4d ago | **DELETE** |
| `feature/ai-learning-enhancements` | 0 | 394 | 3w ago | **DELETE** |
| `realtime-and-observability` | 0 | 342 | 3w ago | **DELETE** |
| `refactor/repo-structure` | 0 | 412 | 3w ago | **DELETE** |

---

## The structural problem

Three branches (`feature/intelligence-catalog`, `feature/fast-cohort-analysis`,
`installer-build`) all share an **older fork point of main**, and they all
delete the same files that `main` HEAD considers active:

### Files all 3 branches delete that main uses
| File | Main HEAD lines | Why this matters |
|---|---|---|
| `core/database_pg.py` | 945 | This is the file CR-4 patches today. Deleting it breaks the production scan loop. |
| `core/database.py` | 1643 | Active SQLite-era module main still references in some paths |
| `clients/ams_client.py` | 974 | The whole AMS integration. Production calls this every scan. |
| `notifiers/slack_notifier.py` | 685 | Production Slack pipeline |
| `api/intelligence_report_api.py` | 1924 | Behind one of the 8 systemd services |
| `api/trends_api.py` | 323 | API endpoint |
| `monitoring/cost_tracker.py` | 440 | Monitoring |

These deletions reflect a **planned restructure** that all three branches assumed
would happen. It didn't — main went a different direction. So merging any of these
branches as-is would delete live, working production code.

### What this means
- **Don't fast-forward merge any of these branches.**
- **Don't `git merge feature/intelligence-catalog into main`.** It would silently
  delete files main needs and break production.
- The good content on these branches must be **cherry-picked or rebuilt** as
  small additive PRs against current main HEAD.

---

## Per-branch action plan

### A. `hotfix/cr-4-pg-shim-2026-04-25` — MERGE TOMORROW

- 1 commit, the CR-4 PG shim patch.
- Already linted, tested, documented.
- **Action:** open PR Sunday after typo rename, merge after smoke test passes.
- **Then delete the branch.**

### B. `pre-prod-audit-2026-04-25` — KEEP

- 42 commits. Deliberately parallel track for pre-prod hardening.
- Most content is in `mg_pre_prod/proposals/` — runbooks, finding docs,
  patcher scripts. None of it conflicts with main.
- 1 commit (9e705f7, the CR-2 hashrate fix on audit-branch line numbers) is
  superseded by tonight's CR-6 patcher targeting main's line numbers.
- **Action:** keep alive indefinitely. As CRs land on main, mark the
  corresponding audit-branch sources as "shipped" in a tracker doc.
- **When it's safe to delete:** once CR-5/6/7 have all landed on main and
  `mg_pre_prod/` is no longer referenced. Probably 2-3 weeks out.

### C. `feature/intelligence-catalog` — CHERRY-PICK IN SLICES

This is the largest divergence: 21 commits, 239 files, +24K/-51K lines.

**What to keep (cherry-pick or rebuild):**

| Commit | What | Keep? | Strategy |
|---|---|---|---|
| db47293 | Bitmain Phase 1 — 24 models | YES | Pure data: `intelligence-catalog/research/bitmain_deep_research_phase1.csv`. Cherry-pick clean. |
| 57ccbfb | Phases 2-4 — 223 more models | YES | Same: 4 CSV files. Cherry-pick. |
| 8b6e66c | enrichment SQL V2 + AH3880 chips_per_board | YES | Two SQL files. Cherry-pick. |
| 1e88f40 | schema_fixes_v1.sql | MAYBE | Verify it still applies cleanly to main's schema state. |
| 0d77ede | catalog_id numbering system | YES | Adds to seed data. Cherry-pick. |
| b61ea49 | fix_and_seed.sql | YES | Cherry-pick. |
| 2433bfe | deploy_schema.sql include paths | YES | Cherry-pick. |
| 7189a44 | deploy.ps1 PowerShell escaping | YES | Cherry-pick. |
| 0a37f94, bdca6e5 | Importer + parsers (Bitmain/MicroBT/Canaan/Auradine/generic/CSV) | YES | 17 files in `intelligence-catalog/importer/`. Pure additions on main (main has no `importer/` subdir). Cherry-pick clean. |
| 0089ed6, e0b5b1a, 5823921, 530456e, e49f45b | mg_import_tool series | MOSTLY YES | Main has its own `mg_import_tool/` (19 files). Diff them. v3.3 resolver + tests are worth keeping. |
| 8059d1b, 36d0656, 1ba973e, 58a7e3e | Password purge | SUPERSEDED | Tonight's CR-7 patcher does this against current main. Skip these commits, use CR-7. |
| f18ad86 | gitignore | YES | Trivial. |
| 71675a5, 58be898, 9afff68, cc829e2 | Doc updates (AI_ROADMAP, SESSION_LOG, README) | SKIP | Main has progressed further on these docs. Audit version is stale. |
| 2d3a7a3 | OpenClaw catalog-bridge | (skipping per Rob) | Already 0 file delta with main. No-op. |
| 530456e | mg_import diagnostic helpers | YES | Cherry-pick. |
| e886720, 7e7c6d8 | AI improvements + operator rule #6 | EVALUATE | Read-and-decide; may be obsoleted by main's AI evolution. |
| e867eeb, d565a27 | Postgres deployment package + session log | EVALUATE | Postgres is already deployed; the package may be redundant. |

**What to discard:**
- Every deletion of `core/database_pg.py`, `core/database.py`, `clients/ams_client.py`,
  `notifiers/slack_notifier.py`, `api/intelligence_report_api.py`,
  `api/trends_api.py`, `monitoring/cost_tracker.py` — these deletions are wrong.
- The 51K lines of removals are mostly stale: old session logs, planning JSON,
  `.bak_apr21` files, REPAIR_LOG churn. Let main keep its current state.

**Action plan:**
1. Next session, create slice PRs in this order (smallest first):
   - PR-A: deep research CSVs (3 commits, pure additions, ~250 model rows)
   - PR-B: importer module (`intelligence-catalog/importer/` — pure additions if main has no equivalent path)
   - PR-C: schema fixes + seed SQL
   - PR-D: mg_import_tool deltas (diff first, only port what's missing)
2. After all slices land on main, **delete `feature/intelligence-catalog`**.
3. The 247 miner models of research data is the highest-value content here.
   Don't lose it.

### D. `installer-build` — REBASE AS `release/mac-mini`

- 3 commits: deployment spec, INSTALLER_PLAN.md (900 lines), branding + Screen 1 mockup.
- 57 new files, but also **deletes the same critical core files** as catalog branch.
- The deletions are stale fork-point assumptions, not intentional.

**Action plan:**
1. Next session, create new branch `release/mac-mini` off current `main`.
2. Cherry-pick the 3 installer commits — but resolve conflicts by KEEPING main's
   `core/`, `clients/`, `api/`, `notifiers/` files and ONLY taking the new
   `installer/` and `branding/` content.
3. Continue building the 11 screens on `release/mac-mini` instead of `installer-build`.
4. **Delete `installer-build`** once cherry-picks land.

This gives you a clean integration branch where:
- Main's current production code is preserved
- The installer plan + branding is preserved
- Future installer work happens against fresh main, not stale main

### E. `feature/fast-cohort-analysis` — SALVAGE 2 COMMITS, DELETE

- 2 commits ahead, 120 behind.
- Commit `ce6d843`: "Add Claude API fallback for Pass 1 and Pass 3" — adds
  `ai/claude_deep_dive.py`, `ai/cohort_analyzer.py`, `ai/fast_analysis.py`,
  `ai/insight_filter.py`, plus `docs/FAST_COHORT_DESIGN.md` and `run_full_chain.sh`.
- Commit `49aa07d`: just a session log doc.

**Action plan:**
1. Read `docs/FAST_COHORT_DESIGN.md` and decide if the cohort analyzer is still
   wanted given main's AI architecture evolution.
2. If yes: cherry-pick only the new files (no deletions of main's core files);
   single PR.
3. If no: just delete the branch.

### F. The 4 dead branches — DELETE

- `feature/ai-learning-enhancements` (0 ahead, 394 behind, 3w stale)
- `realtime-and-observability` (0 ahead, 342 behind, 3w stale)
- `refactor/repo-structure` (0 ahead, 412 behind, 3w stale)
- `security/hardening-apr21` (0 ahead, 103 behind, 4d stale)

These contributed nothing main doesn't already have. They are pure noise.

**Action plan:** delete on the GitHub UI:
```
gh api -X DELETE repos/robertfiesler-spec/Mining-Guardian/git/refs/heads/feature/ai-learning-enhancements
gh api -X DELETE repos/robertfiesler-spec/Mining-Guardian/git/refs/heads/realtime-and-observability
gh api -X DELETE repos/robertfiesler-spec/Mining-Guardian/git/refs/heads/refactor/repo-structure
gh api -X DELETE repos/robertfiesler-spec/Mining-Guardian/git/refs/heads/security/hardening-apr21
```

(Or click "Delete branch" on each in the GitHub UI. They're already merged-equivalent
to nothing useful, so deletion is safe.)

---

## Recommended sequence for next 1-2 weeks

### This weekend (Sunday 2026-04-26)
1. Typo rename per `typo_rename_runbook.md` (8-10 min)
2. Merge `hotfix/cr-4-pg-shim-2026-04-25` to main
3. Run `post_cr4_smoke_test.sh` — confirm green
4. Watch for 30 min, then call it
5. Delete `hotfix/cr-4-pg-shim-2026-04-25` branch

### Monday 2026-04-27
1. Mac Mini cutover (whatever your existing plan is)
2. Delete the 4 dead branches (10 sec)
3. Create `release/mac-mini` from current main

### Tuesday-Thursday next week
1. CR-5 (SQLite-isms) — slice-by-slice. Tier A first (5 dashboard endpoints).
2. CR-6 (hashrate parser) — apply patcher, single PR.
3. CR-7 (password purge) — only after DB password rotation. Multi-step.
4. PR-A: deep research CSVs from feature/intelligence-catalog (cherry-pick)
5. PR-B: importer module (cherry-pick if path is clean)
6. Cherry-pick installer commits onto release/mac-mini
7. Delete `feature/intelligence-catalog` branch

### Friday-Saturday next week
1. Continue installer build on `release/mac-mini`:
   - Get Screens 0 + 1 approved
   - Build Screens 2-4 (Pre-Flight, Site Config, AMS) in real Rich code
2. Salvage decision on `feature/fast-cohort-analysis`

### Following week (Mac Mini arrives)
1. Continue installer screens 5-11
2. Cutover to Mac Mini using the installer

---

## Open questions you'll need to answer

1. **Is `mg_import_tool/` still in active use?** If yes, port the audit branch's
   v3.3 resolver + tests. If you've moved on, skip.
2. **Is the Postgres deployment package on `feature/intelligence-catalog`
   redundant?** (Postgres is already running on the VPS — but is the package
   still useful for the Mac Mini deployment?)
3. **Do you want to keep `feature/fast-cohort-analysis`'s cohort analyzer**
   (Pass 1/3 Claude fallback architecture), or has the AI design moved on?
4. **Schedule for the password rotation** that unblocks CR-7. This is a small
   maintenance window (~5 min) where all 8 services restart — pick a low-traffic
   time and put it on the calendar.

---

## Summary

You're not in trouble — you're in a normal state for a project that's had 4
parallel tracks running. The fix is mechanical: kill the dead branches today,
slice-cherry-pick the catalog branch over the next 2 weeks, rebase the installer,
then keep going.

**Deliverable count after consolidation:**
- 1 production line (main)
- 1 audit branch (historical)
- 1 release branch (mac-mini integration)
- 1 hotfix branch active at a time

That's it. The rest goes away.
