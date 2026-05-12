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

*End of handoff. Prepared 2026-05-12 evening, Tuesday. Companion artifacts in `docs/strategy/`, `scripts/`, and `patches/`. Living document — amend tomorrow as work begins.*
