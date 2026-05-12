# HANDOFF — 2026-05-12 (Tuesday evening)

> **For the next session.** Drop this file into the first message of the new chat. The state of the world is in this file plus the artifacts it points at. No re-uploading of strategic docs needed — they're now in the repo under `docs/strategy/`.

---

## 0. The TL;DR

Today was a **planning and prep session**, not an execution session. The big artifacts:

1. **The 4 strategic docs are now in the repo** under `docs/strategy/` as committed Markdown — no more uploading them every chat. Plus a `README.md` index that tells future sessions which doc answers which question.
2. **`docs/EXECUTION_PLAN_STATUS.md` is the new single source of truth** for W-item progress. Every status assertion cites verifiable evidence (grep, commit, file path).
3. **The §5 step 2 reconciliation greps ran for real** against `main` HEAD `9d2e117`. Captured in `docs/strategy/RECONCILIATION_2026-05-12.md` as receipts. The handoff's prior-chat self-correction on W16/W17 is confirmed accurate: W16 done, W17 untouched (151 naive `datetime.now()` calls remain).
4. **W14 prep doc is written** at `docs/strategy/W14_PREP.md` — operational plan for the two-Postgres split with rollbacks, decision matrix (D1-D7), and the cohort guard test.
5. **W05 PR patch is ready** at `patches/w05_processtype_standard.patch` — flips ProcessType on 9 plists (not 6 as the Plan said). The expanded scope is documented in `docs/strategy/AMENDMENTS_2026-05-12.md` §A02.
6. **Three small bash scripts staged**: `scripts/disable_sleep.sh` (W01 pmset), `scripts/apply_w05_processtype.sh` (Mini-side bootout/bootstrap), `scripts/run_reconciliation_greps.sh` (re-run the reconciliation any time).

**Key decision today (operator):** W14 split is real architectural restoration (State A → State B). The Plan put it in Phase 4; we moved it to Phase 1.5 yesterday. Today we added **W14a** (Phase 0 cleanup of 27 files that bypass `core/db_targets.py`) and **W14b** (lock the convention in CLAUDE.md + .env.example after the topology change lands). The principle: *the code convention is the durable artifact, not the topology change.*

---

## 1. What's in the bundle to apply tomorrow

These artifacts are staged in `/home/claude/output/` in this session's sandbox. Bobby applies them on the laptop, commits, pushes.

```
docs/
├── EXECUTION_PLAN_STATUS.md                  # NEW — single source of truth
├── HANDOFF_2026-05-12_EVENING.md             # NEW — this file
└── strategy/
    ├── README.md                              # NEW — directory index
    ├── 01_PERFORMANCE_AUDIT.md                # NEW — was Mining_Guardian_Performance_Audit.docx
    ├── 02_TWO_DATABASE_DEEP_DIVE.md           # NEW — was Mining_Guardian_Two_Database_Deep_Dive.docx
    ├── 03_OVERALL_ASSESSMENT.md               # NEW — was Mining_Guardian_Overall_Assessment.docx
    ├── 04_MASTER_EXECUTION_PLAN.md            # NEW — was Mining_Guardian_Master_Execution_Plan.docx
    ├── AMENDMENTS_2026-05-12.md               # NEW — all plan deltas (A01-A06)
    ├── RECONCILIATION_2026-05-12.md           # NEW — grep receipts
    └── W14_PREP.md                            # NEW — two-Postgres-split plan

scripts/
├── disable_sleep.sh                           # NEW — W01 pmset
├── apply_w05_processtype.sh                   # NEW — Mini-side W05 service reload
└── run_reconciliation_greps.sh                # NEW — re-runnable reconciliation

patches/
└── w05_processtype_standard.patch             # NEW — git apply this, then commit + push
```

Suggested commit sequence:

```bash
cd /Users/BigBobby/Documents/GitHub/Mining-Guardian
git checkout -b docs/strategic-planning-suite-2026-05-12

# Drop the docs/ and strategy/ files in place, then:
mkdir -p docs/strategy scripts patches
# (copy files from the sandbox bundle)

git add docs/ scripts/ patches/
git commit -m "docs(strategy): add planning suite + reconciliation receipts

- Commit the 4 strategic docs (Report 1-3 audits + Master Execution Plan)
- Add EXECUTION_PLAN_STATUS.md as the single source of truth
- Add AMENDMENTS_2026-05-12.md capturing all plan deltas since 2026-05-09
- Add RECONCILIATION_2026-05-12.md with §5 step 2 grep receipts
- Add W14_PREP.md for the two-Postgres-instance split
- Add disable_sleep.sh, apply_w05_processtype.sh, run_reconciliation_greps.sh
- Add w05_processtype_standard.patch ready for git apply

Establishes docs/strategy/ as the long-term home for planning artifacts.
Future sessions read this directory plus EXECUTION_PLAN_STATUS.md to
get oriented in under 5 minutes."

git push -u origin docs/strategic-planning-suite-2026-05-12
# Open PR from web UI, merge fast (no risk — docs and patches, no code paths affected)
```

The patch file (`patches/w05_processtype_standard.patch`) is committed but NOT applied yet. Applying it is a separate W05 PR.

---

## 2. Plan amendments captured today

All in [`docs/strategy/AMENDMENTS_2026-05-12.md`](docs/strategy/AMENDMENTS_2026-05-12.md):

| ID | Summary |
|---|---|
| **A01** | W14 sequencing: W14a (cleanup, 27 files) → W14 (split) → W14b (convention lock). All three in Phase 1.5. The "what's best for the long term" answer to last night's "Option A vs Option B" question. |
| **A02** | W05 scope expands from 6 plists to 9 (add `console`, `intelligence-report`, `overnight-automation`) — all 3 are service-shaped per inspection |
| **A03** | W03 status refined: catalog API side already pooled, operational adapter still per-call. Half-done, not undone. |
| **A04** | W17 status corrected: PR #180 was a different datetime fix, not the tz-aware sweep. W17 essentially untouched. |
| **A05** | New W-items W23 / W24 / W25 from 2026-05-11 Grafana stand-up |
| **A06** | New "Working Principle": conventions get enforced in cohort guard tests AND documented in CLAUDE.md. Generalizes the discipline that produced PR #178's regression test. |

Cite by ID in commit messages.

---

## 3. Reconciliation findings (the receipts)

Run against `main` HEAD `9d2e117` (PR #182 merge, P-038 cohort closed) on 2026-05-12. Full output in [`docs/strategy/RECONCILIATION_2026-05-12.md`](docs/strategy/RECONCILIATION_2026-05-12.md).

| Check | Expected | Actual | Verdict |
|---|---|---|---|
| W16 — `TO_CHAR(NOW(` in `ai/core/api/scripts/` | 0 | 0 | ✅ Done |
| W16 — Same pattern in `tests/` (regression guards) | 7 | 7 | ✅ Guards intact |
| W17 — naive `datetime.now()` in `ai/core/api/scripts/` | ~151 | 151 | ⚠️ Not started |
| W17 — tz-aware `datetime.now(timezone…)` baseline | — | 18 | (info only) |
| W05 — `Background` plists in `installer/macos-pkg/resources/launchd/` | 9 | 9 | ⚠️ Not started, scope is 9 not 6 |
| W03 — `ThreadedConnectionPool` usage in repo | — | 1 file (catalog API) | ⚠️ Half-done; operational adapter outstanding |
| W02 — `pg_stat_statements` references in repo | 0 | 0 | ⚠️ Not started |

**Surprise during the audit:** 27 files (not 17 as the prior chat estimated) bypass `core/db_targets.py` and read `GUARDIAN_PG_HOST/PORT` directly. The proper categorization:
- 2 files use Pattern 1 cleanly (good)
- 3 files are mixed (partially migrated during P-018B/C)
- 24 files are pure Pattern 2 (need full refactor)

Authoritative list in [`AMENDMENTS_2026-05-12.md`](docs/strategy/AMENDMENTS_2026-05-12.md) §A01.

---

## 4. Where the plan stands going forward

Updated phase order per A01:

| Phase | Items | Status |
|---|---|---|
| Phase 1 — Foundation | W01, W02, W03, W04, W05 | W01 ~50% (cutover side done; pmset + backup decision pending). W05 PR ready. W02/W03/W04 best after Phase 1.5. |
| **Phase 1.5 — Architectural restoration** | **W14a → W14 → W14b** | All 3 new today. Start with W14a. |
| Phase 2 — Closing the integration gap | W06, W07, W08, W09 | Blocked on Phase 1.5. |
| Phase 3 — External intake & operator surfaces | W10, W11, W12, W13 | W11 blocked on Phase 1.5. |
| Phase 4 — Architectural correctness | W15, W16 (✅), W17 | |
| Phase 5 — Performance polish | W18, W19, W20, W21, W22 | |

What can start tomorrow (Wednesday) without blocking on anything else:

1. **Commit the strategic-docs PR** (the bundle above). XS effort, zero risk.
2. **Apply the W05 patch** as its own PR. XS effort. Includes:
   - `git apply patches/w05_processtype_standard.patch`
   - scp the 9 changed plists to the Mini
   - Run `scripts/apply_w05_processtype.sh` on the Mini
3. **Run `scripts/disable_sleep.sh`** on the Mini. Closes the pmset half of W01.
4. **Start W14a** — the 27-file refactor. 3-5 days. M-effort. See `docs/strategy/W14_PREP.md` for the file list and order.

If only 30 min tomorrow → just (1). One git push, zero risk, persistent value.

---

## 5. Open items, parked / to-do (carried over from 2026-05-11)

### 5.1 Security
- 🔐 **Rotate the May 11 Anthropic "mini" API key.** Pasted in the prior chat as `sk-ant-api03-CFvQ5RI_…`. Bobby agreed to rotate later. Steps: delete the existing key in https://console.anthropic.com/settings/keys, create a new one (same name "mini"), `nano /Library/Application\ Support/MiningGuardian/.env` to swap. Don't paste the new value in chat.

### 5.2 Grafana (W23 / W24 / W25 in AMENDMENTS A05)
- Bundle bugs in repo (W23): yaml path + datasource user
- Password secret management (W24): inlined password in deployed yaml acceptable for PoC, not for ship
- Dashboard panel "No data" (W25): Bobby's pref is Path B — rebuild the 6 April-era branded dashboards

### 5.3 Mini repo checkout
- `~miningguardian/code/Mining-Guardian/` was at `084dcba` per yesterday's handoff. Has it been pulled since?

### 5.4 W01 backup destination
- Still undecided. Three options: rsync to ROBS-PC over Tailscale (recommended), external USB drive, Time Machine to a NAS. Pre-Phase-1.5 decision.

### 5.5 PyYAML on Mini
- Installed via `pip3 install --user pyyaml` (6.0.3). Lives in user site-packages. Not blocking.

### 5.6 Customer-facing installer UI (P-040)
- Deferred, ~half day, blocked on first-customer-ship timing (≥1 month).

### 5.7 .pkg rebuild
- Would bundle today's 7 PRs + Grafana provisioning + Homebrew setup steps + the W14 two-container provisioning once W14 lands. Apple notarization required. Critical before first customer ship.

---

## 6. New decisions on the table (Phase 1.5 entry)

Before W14 starts, the operator answers D1-D7 from [`W14_PREP.md`](docs/strategy/W14_PREP.md). Defaults exist for each. None are needed for W14a (the cleanup) to begin.

Summary:
- **D1:** Rename `mining-guardian-db` → `mg-operational-db`? Default keep.
- **D2:** Same password for both instances? Default yes.
- **D3:** Same data dir parent? Default yes.
- **D4:** Catalog `shared_buffers`? Default 512MB.
- **D5:** W02/W04 tuning before or after split? Default after.
- **D6:** One backup script or two? Default two with a wrapper.
- **D7:** First customer .pkg include two-container provisioning? Default yes.

---

## 7. What you'll see in production tomorrow

- 🕗 **8 AM CDT** — daily log pull (no change)
- 🕔 **5 PM CDT** — `daily_deep_dive` runs (working since 2026-05-11 fixes)
- 🌙 **3:30 AM CDT** — `db_maintenance` exits 0 with full report (working since PR #182)
- 🌐 **Anytime** — Grafana at `http://100.69.66.32:3000` over Tailscale; panels still "No data" until W25

If the W05 PR lands tomorrow and gets applied, you'll see noticeably snappier Slack approval round-trips. Otherwise unchanged.

---

## 8. Memory notes added today

None directly. The handoff + the committed `docs/strategy/` files do the carrying-forward work.

Conventions reinforced in `AMENDMENTS_2026-05-12.md` §A06 — cohort guard tests + `CLAUDE.md` updates for any new convention. Worth applying to existing work too if you find places where it would have caught a regression.

---

## 9. How to open the next chat

> *Continuing from 2026-05-12 evening. The handoff is at `docs/HANDOFF_2026-05-12_EVENING.md`. The strategic docs and amendments are committed under `docs/strategy/`. The status file is `docs/EXECUTION_PLAN_STATUS.md`. Goal of this session: <pick one — commit the strategic-docs PR, apply W05, or begin W14a per W14_PREP.md>.*

Single paragraph. Five-minute orientation.

---

## 10. Honest reactions (for context if questioned)

**Things that went well today.** The §5 reconciliation produced unambiguous numbers. The strategic docs being already Markdown (not actual .docx) was a happy surprise that saved 2 hours. Catching that the 17-file estimate was actually 27 — and that 3 of those are mixed-pattern stragglers from P-018B/C — happened *because* the grep got re-run from scratch, not because the prior chat claim was trusted. That's the §5 lesson in action.

**Things I'd adjust about the Plan.**
- The Plan's W05 listing of 6 plists is incomplete. Real count: 9.
- The Plan's W14 effort estimate (L) is correct *if and only if* the 27-file cleanup is carved out as W14a. Without that, the handoff's "2 weeks" estimate is more honest.
- The Plan has zero items for operator-facing dashboards. W23/W24/W25 fill that gap. Whether dashboards are out of scope is a defensible choice but should be explicit.
- The cohort guard test pattern (W14a includes one) generalizes — A06 amends the Plan's "Working Principles" to call this out. Likely applies retroactively to W17 as well (a cohort guard against `datetime\.now\(\)` outside `core/dt_format.py` would prevent W17 regressions for the next 5 years).

**What I think is at risk.**
- W14a is mechanical but boring. 27 files of repetitive refactor is the kind of work where attention slips on file #18 and a bug lands. Recommend reviewing in small batches (e.g., 5 files per review pass) rather than one giant PR review.
- The cohort guard test pattern only works if CI is reliably run. Worth verifying that CI is green on the strategic-docs PR (which has no code changes) before relying on CI for W14a's test.
- The pmset and W05 changes are reversible. The W14 step 7 (DROP DATABASE on the old catalog) is not, without the pre-w14 backup. The W14_PREP §Step 0 emphasizes this; please don't skip the verify-the-backup-restore step.

---

*End of handoff (morning planning section). Prepared 2026-05-12 morning, Tuesday. Companion artifacts in `docs/strategy/`, `scripts/`, and `patches/`. Living document — see EVENING UPDATE below for what actually happened during execution.*

---

# EVENING UPDATE — What actually happened 2026-05-12

> **Appended 2026-05-12 ~14:30 CDT** at the end of an unexpectedly large execution day. The morning sections above remain as the record of what was *planned*. This section is the record of what was *done*. Read both for the full picture; the divergence is itself useful data.
>
> **TL;DR of the divergence:** Morning predicted "if only 30 min tomorrow → just commit the strategic-docs PR." Reality: 10 PRs merged, W05+W14a both deployed to Mini, key rotated, pre-W14 backup verified, W26 audit complete, D1-D7 all locked. Today turned into one of the more substantial execution days.

---

## E0. The actual TL;DR

Today was not the planning-and-prep session the morning handoff predicted. It became a heavy execution day across two clean cohorts:

**Morning cohort (8:00–10:22 CDT):** W05 + W14a — 6 PRs merged, full deploy to Mini, 37+ min clean soak.

**Afternoon cohort (~10:30 CDT onward):** Catalog architectural design dialogue locked the centerpiece vision; then 4 more PRs landed (status file update, D1-D7 lock, W23 Grafana path fix, W26 audit results).

**End-of-day production state on Mini:** 10 launchd services running on W14a-refactored code with new Anthropic API key and `ProcessType=Standard`. Pre-W14 backup files exist on disk (24 MB operational + 596 KB catalog), both verified by restore-to-scratch. pmset sleep disabled. Ready for W14 execution tomorrow.

**Main HEAD at end of day:** `81b258e` (PR #194 merge). PR #195 (tomorrow morning handoff) and PR #196 (this update) bring it to `~81b258e+2`.

---

## E1. The 10 PRs merged today

In order:

| # | PR | What | Outcome |
|---|---|---|---|
| 1 | #184 | `chore(launchd): W05 ProcessType=Standard on 9 services` | Merged + deployed; verified by `sudo launchctl list` returning numeric PIDs |
| 2 | #185 | `chore(launchd): W05b feedback-loop-daemon (10th service, A07)` | Discovered during PR #184 deploy — A07 expanded W05 scope from 6→9→10 |
| 3 | #186 | `refactor(W14a): 27 files routed through core.db_targets` | Merged; immediately crashed 3 services on Mini due to import-order bug |
| 4 | #187 | `fix(W14a): import-order hotfix on 7 entry-point files` | First repair attempt — fixed the 3 crashing, exposed 5 latent siblings |
| 5 | #188 | `fix(W14a): import-order sweep on 5 latent siblings` | Second repair — same bug class, different files |
| 6 | #189 | `fix(W14a): self-contained sys.path with install root / Path X (12 files)` | Final clean version — each affected file adds install root to sys.path FIRST, then imports work regardless of caller context |
| 7 | #190 | `docs(strategy): catalog design plan locked from 2026-05-12 dialogue` | 623-line architectural design doc from operator dialogue; adds AMENDMENTS A07-A10, work items W26-W30 |
| 8 | #191 | `docs(status): update EXECUTION_PLAN_STATUS with today's progress` | W05 [X], W14a [X], W14 tagged TOMORROW, W14b added, W26-W30 added |
| 9 | #192 | `docs(W14_PREP): lock D1-D7 at defaults; add pre-W14 status section` | All 7 W14 decisions locked at defaults; pre-W14 status section documents what's complete going into tomorrow |
| 10 | #193 | `fix(W23): Grafana dashboards yml path matches deployed Mini` | Single yml file: `/usr/local/MiningGuardian/...` → `/Library/Application Support/MiningGuardian/...`. W23 marked [~] partial. |
| 11 | #194 | `docs(W26): audit results lock Approach A — no schema migration needed` | Live catalog query showed 89/98 tables already have `updated_at`; the 9 missing are intentional append-only logs. W26 scope reduced from "under 2h" to "under 30 min". |

(Plus PR #195 — the tomorrow-morning handoff doc — and PR #196 — this update — also landed.)

### What broke + recovered: the W14a import-order chain (PRs #186 → #187 → #188 → #189)

PR #186 deployed the 27-file refactor to the Mini and immediately crashed 3 services with `ModuleNotFoundError: No module named 'core'`. Investigation revealed the refactored files placed `from core.db_targets import ...` BEFORE their sys.path manipulation block. On the Mini, the install root `/Library/Application Support/MiningGuardian/` is not automatically on the Python path; without sys.path setup running first, the `core` import fails.

Three successive fixes were needed:

1. **#187 (hotfix):** 7 entry-point files that were actively crashing
2. **#188 (sweep):** 5 latent siblings — same bug class but not yet triggered because their launchd services hadn't reloaded
3. **#189 (Path X — the clean version):** All 12 affected files now start with a self-contained sys.path block that adds the install root FIRST. Works regardless of whether the caller is `launchctl bootstrap` (no implicit path) or `python -m core.X` (which puts install root on sys.path naturally).

The 12 files that received Path X:
- api/ams_alert_listener, api/approval_api, api/dashboard_api, api/intelligence_report_api, api/slack_approval_listener, api/slack_command_handler, api/ai_dashboard_api
- core/overnight_automation
- ai/confidence_scorer, ai/fingerprint_builder, ai/hvac_correlator, ai/train_cohort

**Why three PRs not one:** Failure Mode 9 (in CLAUDE.md) says sibling sweeps in one PR are OK *if same bug class*. In retrospect #188 + #189 could have been combined (both "import-order discipline"), but the separation made the deploy safer — each PR was independently verifiable on the Mini before continuing.

**Final deploy verification (post-#189):** All 10 services bootstrapped with these PIDs:
- scanner 14597, alerts 14801, approval-api 14908, console 15000, dashboard-api 15090, feedback-loop-daemon 15178, intelligence-report 15337, overnight-automation 15426, slack-commands 15514, slack-listener 15580

37+ minute clean soak with zero errors.

---

## E2. The W14 D1-D7 decisions all locked at defaults

Morning §6 listed D1-D7 as open. Evening status: **ALL 7 LOCKED AT DEFAULTS** by operator confirmation. Permanent in [`docs/strategy/W14_PREP.md`](strategy/W14_PREP.md) via PR #192.

| ID | Locked value | Why |
|---|---|---|
| **D1** | KEEP `mining-guardian-db` container name | Renaming forces updates to every shell script (`db_maintenance.sh`, `daily_backup.sh`). Stylistic improvement only. Ports differentiate (5432 vs 5433). |
| **D2** | SAME password for both instances | Both on `127.0.0.1` only — same blast radius. No security benefit from splitting. |
| **D3** | ONE parent dir: `/Library/Application Support/MiningGuardian/pgdata/` + `/Library/Application Support/MiningGuardian/pgdata-catalog/` | Trivial backup pattern. Two parents would protect against scenarios that don't apply (same physical disk). |
| **D4** | Catalog 512MB / operational 1GB `shared_buffers` | Catalog is read-mostly, ~18 MB. Operational has hot tables. Both get explicit tuning after W04. |
| **D5** | Tuning AFTER split | Per A08 phase order. Tuning before would need re-applying anyway. |
| **D6** | TWO scripts + wrapper: `backup_operational.sh`, `backup_catalog.sh`, `daily_backup.sh` | Clearer rollback if one fails. Aligns with federation where catalog ships to master but operational stays local. |
| **D7** | INCLUDE two-container provisioning in first customer .pkg | August ship locked. Per catalog design plan §2.6, federation requires both DBs separated on customer side. Shipping State A would force every customer Mini to get W14 done remotely. |

---

## E3. Pre-W14 backup (Step 0) — complete and verified

Morning §10 emphasized: *"The W14 step 7 (DROP DATABASE on the old catalog) is not [reversible], without the pre-w14 backup. Please don't skip the verify-the-backup-restore step."* Followed exactly.

**Backup files on Mini (live, not in git):**
- `/Library/Application Support/MiningGuardian/backups/pre-w14-operational-20260512-121154.dump` (24 MB, `-Fc` custom format)
- `/Library/Application Support/MiningGuardian/backups/pre-w14-catalog-20260512-121154.dump` (596 KB, `-Fc` custom format)

**Verification: restore-to-scratch test.** Both dumps were restored into temporary scratch databases and row counts compared to source. All matched exactly:

| Database | Table | Baseline | Restored |
|---|---|---|---|
| catalog | hardware.miner_models | 324 | 324 ✅ |
| catalog | hardware.manufacturers | 17 | 17 ✅ |
| catalog | firmware.firmware_releases | 6 | 6 ✅ |
| catalog | market.war_stories | 22 | 22 ✅ |
| operational | miner_readings | 17,856 | 17,856 ✅ |
| operational | action_audit_log | 19 | 19 ✅ |
| operational | miner_restarts | 8 | 8 ✅ |
| operational | llm_analysis | 98 | 98 ✅ |

The dumps are known-good rollback artifacts. **If tomorrow's W14 goes sideways at any point, restore from these two files and we're back to State A within ~15 minutes.**

Discoveries from the row-count exercise:
- **22 `market.war_stories`** — the feedback loop has been quietly aggregating since C5 daemon went live. None of it is currently read by AI. W07 fixes that.
- **0 `ops.failure_patterns`** — confirms the deep dive's observation that this table has been sitting empty since deploy.
- **17,856 `miner_readings`** — operational telemetry growing as expected.

---

## E4. Security: Anthropic API key rotation closed (5+ sessions overdue)

Morning §5.1 listed the May 11 key (prefix `sk-ant-api03-CF...`) as needing rotation. Done today:

1. Old key deleted via console.anthropic.com
2. New key created (named `mini` again)
3. New value placed in `/Library/Application Support/MiningGuardian/.env` (never pasted in chat)
4. `slack-commands` service restarted with new PID 28448

**Correction to morning plan:** Initial instructions said to restart 4 services (alerts, approval-api, dashboard-api, intelligence-report). Investigation showed those services don't import `anthropic` — only `slack-commands` does. The other 4 restarts were no-ops for this purpose. Helper scripts (daily_deep_dive, refinement_chain, weekly_train) spawn fresh processes per run and pick up the new key automatically.

---

## E5. W01 closed (pmset portion)

Morning §4 listed `disable_sleep.sh` as a tomorrow item. Ran today. Mini was already at `sleep=0, disksleep=0` (powerd + screensharingd prevent sleep on a wall-powered Mac Mini), so the script confirmed idempotency. **W01 sleep-disable portion now formally closed.**

W01 backup-destination decision (morning §5.4) remains open, but is no longer blocking — Step 0 backup proved local-disk backup works; remote destination is a hardening detail for later.

---

## E6. Catalog design dialogue locked the centerpiece vision

The biggest single artifact of the day. Full details in [`docs/strategy/05_CATALOG_DESIGN_PLAN_2026-05-12.md`](strategy/05_CATALOG_DESIGN_PLAN_2026-05-12.md). Operator quoted verbatim:

> *"The goal is to make the most comprehensive db on bitcoin only miners on the planet that is getting updated daily with these auto jobs being performed daily. Then using the library as you referenced it as a resource to make our llm and claude analysis so much more accurate. The database is supposed to have 2 sections sort of, manufacture listed specs and real world specs if there is data that has been collected. I want this to be a centerpoint and the foremost authority of btc miners in the world."*

**Cite as `NORTH-STAR-1` in commit messages when work serves this goal directly.**

### Locked decisions from the dialogue

| Citation ID | What's locked | Evidence (operator quote in design plan) |
|---|---|---|
| **NORTH-STAR-1** | Catalog is the product centerpiece, not a supporting subsystem | Full quote above |
| **OPERATOR-CADENCE-1** | Daily Pass 2 on master; weekly only on customer Minis | *"we have been doing the weekly deep dive everyday, and i will continue to do that for my system"* |
| **OPERATOR-RANGES-1** | Friend archive imports feed real-world ranges (not factory specs) | *"real world numbers would have ranges and the factory specs would be a static number"* |
| **DEFAULT-MERGE-1** | v1 default: auto-merge customer contributions with audit log; operator can review post-hoc | Operator did not directly answer; default chosen for v1 with full reversibility via the log |
| **PERPLEXITY-PASTE-1** | Slack `/intel paste` structure extractor must collapse duplicate-digit artifacts (e.g. "886886 TH/s" → "886 TH/s") | Real paste artifact observed in Perplexity outputs |

### Federation (Loop 5) locked

Operator: *"the master stays here, every month i pull data from the customer what his intelligence db learned and what his operations db learned, all of those files get added here to the masters then new files with all the new information gets pushed out to the customers."*

Direction: bidirectional. Cadence: monthly. Trigger: operator-controlled (not cron). Topology: master-on-operator-PC. What flows: catalog data only (not operational telemetry). Customer Minis run two-Postgres-instance topology too — D7 ensures this ships in customer .pkg from day one.

Conflict resolution priority:
1. `bobby_verified=TRUE` always wins
2. Higher `n_observations` wins
3. Most recent `updated_at` wins

### New work items W26-W30 (added today)

| ID | Title | Effort | When |
|---|---|---|---|
| W26 | `updated_at` discipline across catalog tables | XS (post-audit) | June |
| W27 | `ops.field_observed_specs` + mg_import_tool Layer 2.5 | M | June |
| W28 | Federation v1 (pull/merge/push + customer_contribution_log) | L | July |
| W29 | Pass 2 cadence config flag (daily/weekly) | XS | bundles with W28 |
| W30 | Enrichment CSV → structured chips/PSUs/voltage/frequency | M | June |

### New amendments A07-A10

All in [`docs/strategy/AMENDMENTS_2026-05-12.md`](strategy/AMENDMENTS_2026-05-12.md). Summary:
- **A07** — W05 is 10 services not 6 or 9 (discovered during deploy; PR #185 added feedback-loop-daemon)
- **A08** — Phase order rewritten working backward from mid-August 2026 customer ship
- **A09** — W11 expanded M→M-L; operator clarified `/intel` is a paste-the-whole-Perplexity-morning-output pattern
- **A10** — W30 added (enrichment CSV structured extraction)

---

## E7. W26 audit — Approach A locked, near-zero scope

PRE-W26-execution audit query against live catalog (PR #194):

- **Total catalog tables:** 98 across 10 schemas
- **Tables WITH `updated_at`:** 89
- **Tables WITHOUT `updated_at`:** 9 — and they're ALL intentionally append-only event logs

The 9 append-only tables and the column federation will use for them:

| Table | Federation column |
|---|---|
| knowledge.field_discovery_log | `created_at` |
| knowledge.freshness_log | `created_at` |
| knowledge.raw_ingestion_log (+5 quarterly partitions) | `ingested_at` |
| pool.bitcoin_network_snapshots | `created_at` |

**Decision (locked): Approach A.** Don't add `updated_at` to append-only tables. The federation pull (W28) uses a tiny constant mapping for them. W26 scope reduced from "under 2 hours" to "under 30 minutes" (just the cohort guard test; no schema migration).

The original schema author was disciplined — 89 of 98 tables already comply. The "big migration" anticipated in the deep dive doc isn't needed.

---

## E8. W23 Grafana — partial fix landed; investigation reclassified two non-bugs

Morning §5.2 mentioned W23/W24/W25 as parked. Today PR #193 landed the dashboards yml path fix. **Investigation also reclassified the original W23 scope:**

| Original W23 sub-bug | After investigation | Action |
|---|---|---|
| Dashboards yml path wrong | ✅ Confirmed bug | **Fixed in PR #193** |
| Datasource user `guardian_app` should be `mg` | ⚠️ Not a bug — both roles are valid Postgres users; Grafana auths with `guardian_app` fine | Deferred to W14b for codebase-wide standardization on `mg` |
| Password inlined in deployed yaml | 🚨 Real concern, separate scope | Deferred to W24 — needs proper env-var or secret-manager design |

The "datasource user is a bug" claim from AMENDMENT A05 turned out to be incorrect. The yaml uses `guardian_app`, and `guardian_app` exists as a valid login role in Postgres. Standardizing on `mg` is stylistic; not a P0 fix.

**Password inlining is a real concern** — `brew services` regenerates the plist and overwrites `${env_var}` substitution, which is why someone hardcoded the password originally. W24 deserves its own thoughtful PR.

---

## E9. Where the plan stands after today

The morning §4 "Where the plan stands going forward" table is now obsolete. Updated:

| Phase | Items | Status after 2026-05-12 |
|---|---|---|
| Phase 1 — Foundation | W01, W02, W03, W04, W05 | **W01 portion (pmset) closed today.** W05 closed today. W02/W03/W04 still in line per D5. |
| **Phase 1.5 — Architectural restoration** | W14a → W14 → W14b | **W14a closed today.** W14 happens tomorrow. W14b after. |
| Phase 2 — Closing the integration gap | W06, W07, W08, W09 | Blocked on Phase 1.5. Order TBD inside the phase; per A08 these come BEFORE the catalog-completeness items. |
| Phase 2b (NEW per A08) — Operator surfaces | W10 (extend `dual_writer`) → W11 (Slack `/intel paste`) | Blocked on W14. W11 is M-L not M per A09. |
| Phase 3 (re-scoped per A08) — Catalog completeness | W26, W27, W30 | June |
| Phase 3b — Grafana intelligence dashboard | W23 (partial today), W24, W25, W12 | Late June |
| Phase 4 — Federation v1 | W28, W29 | July (required for August ship) |
| Phase 5 — Customer ship preparation | .pkg build, notarization, August bake | Late July / early August |
| Phase 6 (post-ship) — Performance polish | W15, W17, W18-W22 | Post-August |

---

## E10. Open items at end of day

### Resolved today (moved off the open list)
- ~~🔐 Rotate the May 11 Anthropic API key~~ ✅ Done
- ~~W01 pmset~~ ✅ Done
- ~~Decisions D1-D7 for W14~~ ✅ All 7 locked at defaults
- ~~Pre-W14 backup~~ ✅ Created + restore-verified
- ~~W23 dashboards yml path bug~~ ✅ Fixed in PR #193
- ~~W26 scope unknown~~ ✅ Audited; Approach A locked

### Still open
- **W01 backup destination decision** — local backup works (Step 0 proves it); remote destination is hardening for later
- **W23 datasource user standardization** — deferred to W14b
- **W24 Grafana password secret management** — deferred to dedicated PR (real concern, separate scope)
- **W25 Grafana panel "No data"** — Bobby's preference is Path B (rebuild the 6 April-era branded dashboards)
- **W22 raw_ingestion_log partition** extension — deadline 2027-Q2, months away
- **AMS BiXBiT API key** in mg_import_tool was redacted to first 8 chars of sha256 in some old branch — investigate before customer ship
- **Customer-facing installer UI (P-040)** — deferred per morning §5.6, blocked on first-customer-ship timing
- **.pkg rebuild** — required before first customer ship; bundles everything from today plus W14's two-container provisioning

---

## E11. Tomorrow (2026-05-13)

**The job:** W14 — the two-Postgres-instance split.

**The runbook:** [`docs/strategy/W14_PREP.md`](strategy/W14_PREP.md) §"W14 — The topology change" steps 0-10. D1-D7 all locked at defaults.

**The pre-flight briefing:** [`docs/HANDOFF_2026-05-13_W14_MORNING.md`](HANDOFF_2026-05-13_W14_MORNING.md) (PR #195). Single page. Read this first tomorrow morning before anything else.

**Recommended maintenance window:** 02:00-04:00 CDT (quiet hour between the 01:00 refinement chain and the 04:00 db_maintenance). Operator can adjust based on actual schedule.

**Three corrections to apply mentally to W14_PREP.md during execution:**
1. Service count is **10** (not 9 as the doc says) — include `feedback-loop-daemon` in the bootout/bootstrap loop
2. W14a is already done — don't redo
3. Docker CLI on Mini is at `/usr/local/bin/docker` (Colima setup) — not just `docker`

**The irreversible point:** W14_PREP Step 7 (`DROP DATABASE mining_guardian_catalog` on the old container). Everything before it is reversible by stopping the new container and removing the env vars. **Step 7 requires the pre-W14 backup as the only rollback path** — and that backup is verified, on disk, ready.

---

## E12. Honest reactions on the day (for context if questioned)

**Things that went unexpectedly well.**
- The morning handoff said "if only 30 min tomorrow → just commit the strategic-docs PR." Reality blew past that prediction by an order of magnitude. The discipline of having the strategic docs already committed (yesterday) meant today's execution didn't waste time on context-loading.
- The W14a import-order crash chain (#186 → #187 → #188 → #189) could have been a bad afternoon. Each crash was localized, easy to reproduce, and the fix pattern (Path X) is reusable. The cohort guard test added in PR #186 will prevent regressions.
- The catalog design dialogue produced a single 623-line doc that locks the centerpiece vision. Future-Claude reading just `05_CATALOG_DESIGN_PLAN_2026-05-12.md` can rebuild today's context in 15 minutes.

**Things that didn't go as planned.**
- Initial Anthropic key rotation instructions said "restart 4 services" — only `slack-commands` actually needed the restart. I was guessing without checking which services import `anthropic`. Cost: 30 seconds of unnecessary bootout/bootstrap. The lesson: check imports before declaring scope.
- AMENDMENT A05's "datasource user is a bug" claim was incorrect on closer inspection. Both `mg` and `guardian_app` are valid Postgres login roles. The W23 PR scoped down accordingly, but the morning's status had me ready to fix a non-issue.
- The W14_PREP doc was written 2026-05-09 before W14a landed. Its language assumes W14a hasn't happened yet ("W14a not yet merged"). Tomorrow's pre-flight checklist accounts for this.

**What I think is at risk for tomorrow.**
- W14 is mostly waiting (containers start, restores run). The risk is operator fatigue at Step 7. Recommend a literal pause-and-confirm before running `DROP DATABASE`.
- The 10-vs-9 service count error in W14_PREP could cause `feedback-loop-daemon` to be missed during Step 5 bootout/bootstrap. If it's missed, the daemon would keep running with stale catalog DSN until next reboot. Worth a separate verification grep after Step 5.
- The post-W14 phase order (per A08) is ambitious. Mid-August customer ship is tight if W11 slips even one week. Keep an eye on W10/W11 velocity next week.

---

*End of EVENING UPDATE. Total session: ~6.5 hours of focused work, 10 PRs merged, 1 deploy, 1 verified backup, 1 architectural design dialogue, 7 prep decisions locked, 5 new work items captured. Tomorrow: W14.*

