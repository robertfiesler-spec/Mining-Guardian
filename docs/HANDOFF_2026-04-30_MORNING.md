# Mining Guardian — Morning Handoff for Install Day

**For:** Computer (tomorrow morning's session) and Rob
**Written:** 2026-04-29 evening
**Install date:** 2026-04-30 (today, when you're reading this)
**Tag:** `v1.0.0-install-ready` @ `775b65308ab99fac16841eec6f27f65df3d3fd2d`

---

## TL;DR — Read This First

**Status: GREEN. Repo is frozen, tested, and install-ready. There is nothing left to fix in the codebase.** Your job today is to follow the runbook, run the installer on the Mac Mini, and verify success — not to write more code.

Rob's standing rules still apply: step-by-step, no slop, "rather be late and perfect than early and wrong", over-document, defer to recommendations on minor decisions, never call SQLite "live", Bitcoin SHA-256 miners only, never "scrape/crawl".

---

## Single Source of Truth — Read These In Order

1. **This file** — orientation
2. **`docs/RUNBOOK_INSTALL_DAY_2026-04-30.md`** — the actual install procedure (9 sections + 2 appendices)
3. **`scripts/preflight_install_day.sh`** — read-only Mac Mini health check, run before installer
4. **`docs/MG_UNIFIED_TODO_LIST.md`** — full project history if you need the why behind any decision

---

## Where Things Stand at v1.0.0-install-ready

### Repo health (re-verified evening of 2026-04-29)

| Check | Status |
|---|---|
| main HEAD | `775b653` — `docs: Install-day unbox runbook + pyflakes residual log (#96)` |
| Tag `v1.0.0-install-ready` | Points at `775b653` ✓ |
| Open PRs | **0** |
| Remote branches | **4** (main + 3 retained: `feature/fast-cohort-analysis`, `feature/intelligence-catalog`, `pre-prod-audit-2026-04-25`) |
| Tests | **394 passed, 65 skipped (DB-required), 0 failed** |
| B-6 typo lint | **clean** (62/62 allow-listed) |
| `debug=True` in code | **0** |
| Unguarded `0.0.0.0` binds | **0** (5 occurrences are loopback-default with env-var opt-in + WARN log) |
| `eval`/`exec` calls | **0** |
| Hardcoded secrets / committed `.env` / private keys | **0** |
| Migrations enumerated by `setup.sh` | **5/5** (001, 003, 004_drop_dead_stubs, 004_system_settings, 005) |
| launchd plists valid | **9/9** (8 in installer + 1 deploy/) |
| Pyflakes residual | 253 cosmetic warnings (unused imports/locals/f-strings) — logged in `docs/PYFLAKES_RESIDUAL_2026-04-29.txt`, **deferred post-install** |

### Install cascade summary (this project segment)

**25 PRs merged on install-day-eve** — full list:

- **#61–67** — Security cluster
- **#68** — Bucket 3.2 runbook
- **#69, #75, #77, #78, #84** — 5 conflicting PRs rebased and merged
- **#70** — Reality-check
- **#71** — Code/runtime
- **#72** — B-6 typo lint allow-list
- **#73** — Bucket 5.7 runbook
- **#74, #76, #80** — Bucket 6 installer (clean)
- **#81–83** — Bucket 7 cleanup
- **#91** — Doc sweep (foundation for all rebases)
- **#92** — Fix B-8: 3 silent NameError bugs (missing `Tuple`, `os`, `requests` imports)
- **#93** — Stale-branch triage (19 deleted, 3 retained)
- **#94** — Test fix-up: `insert_raw_json` signature drift
- **#95** — `setup.sh` migration loop fix (dual-004 collision + apply 005)
- **#96** — Install-day unbox runbook + pyflakes residual log

---

## Carry-Forward (Deliberately Deferred per "Rather Late and Perfect")

These are **NOT** install-day blockers. Do not touch them today unless install fails and one of them is the cause.

| Item | Where | When |
|---|---|---|
| **B-7** live migrations 002_layer2 + staging | VPS-side per `docs/RUNBOOK_BUCKET_5.7_COMMIT_LIVE_MIGRATIONS.md` | Post-install, on VPS |
| **253 cosmetic pyflakes** warnings | `docs/PYFLAKES_RESIDUAL_2026-04-29.txt` | Post-install cleanup sweep |
| **3 retained branches** for audit | `feature/fast-cohort-analysis`, `feature/intelligence-catalog`, `pre-prod-audit-2026-04-25` | Post-install audit |
| `api/intelligence_report_api.py:528` docstring "LIVE operational data" wording | Wording-only nit | Post-install |
| `core/database.py:578,782` SQLite ATTACH comments | SQLite-retirement bucket | Post-install |

**Discovered tonight, not blocking:** Two extra tags appeared in remote during fetch (`archive/installer-build-20260428` and `v1.0.0-978ff61126ea`). Almost certainly from CI/build pipelines. Do not delete.

---

## Today's Plan (Recommended Order)

### Step 1 — Wake-up sanity check (5 min, in this conversation)

When Rob arrives this morning, the first action is to confirm nothing changed overnight. Run this:

```bash
cd /home/user/workspace/mg-repo
git fetch --all --tags --prune
git log --oneline -3                  # expect 775b653 at top
git rev-list -n 1 v1.0.0-install-ready  # expect 775b65308ab99fac16841eec6f27f65df3d3fd2d
gh pr list --repo robertfiesler-spec/Mining-Guardian --state open  # expect empty
bash scripts/lint_mining_gaurdian_typo.sh  # expect "B-6 lint: clean"
python -m pytest tests/ mg_import_tool/tests/ intelligence-catalog/db/tests/ intelligence-catalog/watchers/tests/ -q --tb=no  # expect 394 passed
```

If any of those return unexpected output → **STOP** and investigate before touching the Mac Mini. Use `gh pr list --state all` to see if anything was merged overnight.

### Step 2 — On the Mac Mini, run preflight (5 min)

Once Rob is at the Mac Mini, before doing anything else:

```bash
cd ~/Documents/GitHub/Mining-Guardian   # or wherever the repo lives
git fetch --all --tags
git checkout v1.0.0-install-ready
bash scripts/preflight_install_day.sh
```

Exit codes:
- **0 (ALL GREEN)** — proceed to Step 3
- **2 (PROCEED WITH CAUTION)** — review warnings together, decide
- **1 (BLOCKED)** — fix failure(s) before running installer; do not skip

The script is **read-only** — it makes no system changes. It checks: macOS version, arch, free disk, network, Xcode CLT, brew, git, psql, python3, .pkg sha256 + signature + notarization, postgres reachability, repo HEAD, tag presence, NTP drift.

### Step 3 — Run the installer (per RUNBOOK)

Follow `docs/RUNBOOK_INSTALL_DAY_2026-04-30.md` section by section. Do not skip ahead. The runbook covers:

1. Preflight (now done by script)
2. Unbox / first-boot
3. Network setup
4. Postgres install
5. Run `MiningGuardian-1.0.0-0f849bd217cc.pkg`
6. Smoke tests
7. Verify scheduled jobs (launchd)
8. Sign-off
9. Troubleshooting

Plus appendices for credentials reference and rollback.

### Step 4 — Sign-off

When the runbook's sign-off section passes, tag the install completion (Rob can decide on the tag name when we get there) and update `docs/MG_UNIFIED_TODO_LIST.md` install row from in-progress to done.

---

## Key Facts Computer Needs (in case context is fresh)

- **Repo:** `robertfiesler-spec/Mining-Guardian`
- **Local clone:** `/home/user/workspace/mg-repo/` on `main`
- **Git identity for commits:** `Computer <computer@perplexity.ai>`
- **GitHub access:** `gh` CLI with `api_credentials=["github"]`. Never use browser_task for GitHub.
- **Use Git Data API** for files >100KB.
- **PR merge pattern:** `gh pr merge $N --repo robertfiesler-spec/Mining-Guardian --squash --delete-branch`
- **Wait ~25s after force-push** for GitHub mergeability/CI to recompute
- **Non-interactive rebase:** `GIT_EDITOR=true git rebase --continue`

### Credentials reference (also in runbook appendix)

- **Catalog DB:** Postgres 16, db `mining_guardian`, user `guardian_app`, port 5432
- **MG_DB_PASSWORD:** `tX-fhG#iJdm{V?>uuZ35G-Y)O5<UeN=5`
- **Grafana password:** `002300rfNEW`
- **Apple Dev:** robfiesler25@gmail.com / Team ID `ARJZ5FYU94` / Notarization Key `FPZJ87B3QF` / Issuer `f53661a7-931a-4976-8f8e-82353256931a`
- **Shipped .pkg:** `MiningGuardian-1.0.0-0f849bd217cc.pkg` sha256 `1e65fe7827ffba2c8cd4daa0c2a42218bb156798521278fd0e567b0cef53a646`

### Convention reminders

- **Every fix PR flips MG_UNIFIED_TODO_LIST.md row** from 🔴 OPEN to ✅ DONE in the same commit
- **B-6 lint runs after every doc edit** as canary — `bash scripts/lint_mining_gaurdian_typo.sh`
- **Combine-don't-pick** for status-flip conflicts on MG_UNIFIED_TODO_LIST.md
- **Glob `[0-9][0-9][0-9]_*.sql`** for migration loops — handles missing slots, dual-prefix collisions, future migrations
- **Test mocks must be updated** when production signatures change

---

## Shared Asset Names (use same name to update version history)

`mg_diag_script`, `mg_locate_script`, `mg_import_v34`, `mg_audit_findings`, `mg_unified_gap_list`, `mg_cutover_checklist`, `mg_unified_todo`, `mg_brochure`, `mg_program_instructions`, `mg_setup_manual`, `mg_installer_screen_welcome`, `mg_installer_screen_preflight`, `mg_installer_screen_installing`, `mg_installer_screen_done`, `mg_study_note_2026-04-29`, `mg_runbook_pkg_rebuild`, `mg_study_note_2026-04-30`, `mg_full_scope_2026-04-29`, `mg_documents_cleanup_log_2026-04-29`, `mg_documents_inventory_2026-04-29`

For today's session, expect new shared assets: `mg_handoff_2026-04-30`, `mg_preflight_script`, `mg_install_complete_*` (after install lands).

---

## What Computer Did Tonight (2026-04-29 evening, after v1.0.0-install-ready was tagged)

1. **Re-verified repo health** — main, tag, branches, PRs, B-6 lint all match expected
2. **Re-ran full test suite** — 394 passed, 65 skipped, 0 failed — same as last night
3. **Dry-ran setup.sh migration glob** — confirmed all 5 migrations enumerate (001, 003, 004×2, 005) and 002 absence is reported correctly
4. **Re-validated all 9 launchd plists** via plistlib — all have valid Label + ProgramArguments
5. **Confirmed pkg sha256 + filename** are documented in two places (runbook + unified todo) so Mac-Mini-side verification is unambiguous
6. **Re-ran final security sweep** — 0 debug=True, 0 unguarded binds, 0 eval/exec, 0 secrets, 0 .env, 0 keys
7. **Wrote `scripts/preflight_install_day.sh`** — 8-section read-only Mac Mini health check (this file)
8. **Wrote this handoff document**

Nothing was committed or pushed. Tag is unchanged. Repo state at `775b653` is identical to when Rob signed off last night, plus one local-only preflight script + handoff doc that will be committed in the morning if Rob approves.

---

## First-Move Recipe for Tomorrow's Computer Session

When the morning session opens, do this in order:

1. Read this file (`docs/HANDOFF_2026-04-30_MORNING.md`) **before anything else**
2. Run the wake-up sanity check (Step 1 above) — confirm nothing changed overnight
3. Greet Rob with status: "Repo still green. Preflight script and handoff are local-only — want me to commit them as your first PR of the day, or hold them until after install?"
4. If Rob approves committing the prep work: open PR for `scripts/preflight_install_day.sh` + `docs/HANDOFF_2026-04-30_MORNING.md` on a branch like `docs/install-day-prep-2026-04-30`
5. Once Rob is at the Mac Mini, walk through the runbook section by section. **One thing at a time.**

**Default behaviors** (per Rob's autonomy rule "defer to your recommendation"):

- Commit prep work as the day's first PR — yes
- Tag install-completion when sign-off passes — yes (suggest `v1.0.0-installed-mac-mini` or similar; let Rob pick name)
- Touch carry-forward items today — **no, not unless install requires it**
- Open new bugs found during install — yes, log in `docs/LATENT_BUGS.md` as B-9, B-10, etc.

---

## End-of-Day Definition of Done

Today succeeds when:

1. Mac Mini boots Mining Guardian without errors
2. All 9 launchd jobs are loaded and the next-scheduled run completes successfully
3. Catalog DB has all 5 migrations applied and seed data loaded
4. Smoke tests in runbook section 6 pass
5. Sign-off section in runbook is complete with timestamps
6. `docs/MG_UNIFIED_TODO_LIST.md` install row is flipped to DONE
7. Either a successful-install tag is pushed, or Rob explicitly defers tagging

Anything beyond that is a bonus, not a requirement.

---

**End of handoff. See you in the morning.**
