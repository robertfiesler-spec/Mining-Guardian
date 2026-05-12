# Morning Briefing — 2026-05-13 (W14 Execution Day)

> **You are reading this at the START of a new Claude session.** This is the single document that brings the new session up to speed without needing to ask the operator questions. Read this file in order, top to bottom. Linked references are listed inline so you can pull them as needed.
>
> **The operator (Bobby) has explicitly stated:** "I would rather not spend 30-60 minutes answering questions about what the day is about and what we have done and what is the right way to do things." Honor that. Read the doc, read the linked files, then state what you're going to do.
>
> **Today's job:** W14 — split the single Postgres container holding two databases into two separate Postgres containers. Operational stays on port 5432. Catalog moves to port 5433.

---

## 0 · Required reading order (do this BEFORE the first action)

Read these files in this exact order. Each one is canonical for its domain. Don't ask the operator about anything in these files — read them.

| # | File | Why |
|---|---|---|
| 1 | This file (`docs/MORNING_BRIEFING_2026-05-13.md`) | Single-page orientation + reading order |
| 2 | `docs/HANDOFF_2026-05-13_W14_MORNING.md` | Tomorrow's pre-flight briefing (written yesterday). Has condensed steps + corrections to apply to W14_PREP. |
| 3 | `docs/HANDOFF_2026-05-12_EVENING.md` — **only the EVENING UPDATE section (E0–E12)** | What ACTUALLY happened yesterday. 10 PRs landed. The morning section above E0 is historical record of yesterday's planning intent — read for context but treat as obsolete. |
| 4 | `docs/strategy/W14_PREP.md` | The authoritative W14 runbook. 10 steps. D1-D7 are locked. **Apply the 4 corrections from MORNING_BRIEFING §3 below as you read.** |
| 5 | `docs/EXECUTION_PLAN_STATUS.md` | Source of truth for what's done. Check the History section for the most recent state. |
| 6 | `CLAUDE.md` in repo root | Working conventions (Failure Mode 9, sibling sweeps, evidence-before-fix, live-Mini smoke, etc) |
| 7 | `docs/strategy/05_CATALOG_DESIGN_PLAN_2026-05-12.md` | Catalog centerpiece design + W26-W30 + federation. Pull when you need the WHY behind a decision. |
| 8 | `docs/strategy/AMENDMENTS_2026-05-12.md` | A01-A10 plan deltas. Pull when you need rationale for a phase reorder or scope change. |

**After reading those 8 files, you have hour-4 context.** Don't ask the operator to re-explain any of it.

---

## 1 · Today's job in one paragraph

W14 is the architectural restoration that was deferred from Phase 4 to Phase 1.5 by operator decision 2026-05-11. The Mac Mini currently runs one Docker container (`mining-guardian-db`) with two databases inside (operational + catalog). Tomorrow's job is to spin up a second container (`mg-catalog-db`) on port 5433, restore the catalog DB into it, update `.env`, restart all 10 launchd services, smoke-test, then DROP the catalog DB from the old container. There are 10 steps; **Step 7 (DROP DATABASE) is the irreversible gate.** Everything before Step 7 is reversible by stopping the new container and removing env vars.

---

## 2 · Locked decisions (do NOT re-litigate these tomorrow)

### D1-D7 — all at defaults
| | Locked value |
|---|---|
| D1 | KEEP container name `mining-guardian-db` |
| D2 | SAME password for both instances |
| D3 | ONE parent dir for data volumes |
| D4 | Catalog 512MB / operational 1GB `shared_buffers` |
| D5 | Tuning AFTER split |
| D6 | TWO backup scripts + wrapper |
| D7 | INCLUDE two-container provisioning in first customer .pkg |

Full text + rationale in `docs/strategy/W14_PREP.md` §"Open decisions before execution".

### Other decisions locked yesterday (don't re-discuss)
- W14a is done (PRs #186 #187 #188 #189 — deployed to Mini, 37+ min clean soak as of 2026-05-12 10:22 CDT)
- All 10 launchd services on `ProcessType=Standard` (W05 — PR #184, #185)
- Anthropic API key rotated; only `slack-commands` needed the restart (other anthropic-using files are helper scripts that fork fresh per run)
- pmset sleep=0 disksleep=0 on Mini (W01 portion)
- Pre-W14 backups exist on Mini at `/Library/Application Support/MiningGuardian/backups/` and have been restore-verified
- `core/db_targets.py` resolver functions for catalog host/port are **already pre-staged in main** via PR #197 — tomorrow's Step 4 is "scp + .env edit", NOT "edit Python live"
- W26 (`updated_at` discipline) is closed with cohort guard test at `tests/test_w26_catalog_timestamp_columns.py`
- **W25 Grafana preference:** debug existing dashboards (Path A), NOT rebuild (Path B). The operator quote is `"i did not know i said rebuild them i just want them working, they already were close to perfect."` Earlier docs were wrong; PR #199 corrected this across 4 files.

---

## 3 · Corrections to apply mentally to W14_PREP.md while reading it

W14_PREP.md was written 2026-05-09. Four things in it are now stale. Apply these corrections in your head as you read:

1. **"9 always-on services"** in Step 5 — should be **10**. The 10th is `feedback-loop-daemon` (added in PR #185, AMENDMENT A07). Include it in the bootout/bootstrap loop.
2. **"W14a not yet done"** language throughout — **W14a is done.** Don't redo. PRs #186-#189 merged + deployed yesterday.
3. **Docker CLI path** — use full path `/usr/local/bin/docker` (Colima). Not just `docker`. Non-interactive SSH sessions don't have it on PATH.
4. **Step 4 says edit `core/db_targets.py` live** — DON'T. The resolver functions are already in `main` via PR #197. Just `scp` the file from the laptop to Mini's install root. The new resolvers are backward-compatible by design (fall back to operational host/port when catalog env vars are unset), so deploying the file pre-W14 is safe; behavior change is gated on the `.env` edit in Step 4.

---

## 4 · Production state as of end of 2026-05-12

### Mini at `miningguardian@100.69.66.32` (Tailscale)
- macOS 26.4.1, M4, 16GB RAM
- Install root: `/Library/Application Support/MiningGuardian/` (NOT git-managed; manual scp delivery)
- Colima Docker, CLI at `/usr/local/bin/docker`
- Container `mining-guardian-db` running (postgres:16-bookworm), port 5432:5432
- Two databases inside: `mining_guardian` (74 MB operational) + `mining_guardian_catalog` (18 MB)
- All 10 launchd services healthy, `ProcessType=Standard`
- pmset: sleep=0, disksleep=0

### Baseline row counts (must match after any rollback)
| Database | Table | Rows |
|---|---|---|
| catalog | hardware.miner_models | **324** |
| catalog | hardware.manufacturers | **17** |
| catalog | firmware.firmware_releases | **6** |
| catalog | market.war_stories | **22** |
| catalog | ops.failure_patterns | 0 |
| operational | miner_readings | **17,856** |
| operational | action_audit_log | **19** |
| operational | miner_restarts | **8** |
| operational | llm_analysis | **98** |

### Pre-W14 backup files (on Mini, restore-verified)
- `/Library/Application Support/MiningGuardian/backups/pre-w14-operational-20260512-121154.dump` (24 MB)
- `/Library/Application Support/MiningGuardian/backups/pre-w14-catalog-20260512-121154.dump` (596 KB)

### Repo at `/Users/BigBobby/Documents/GitHub/Mining-Guardian/` (laptop)
- main HEAD at session start: **`fd2dc36`** (PR #199 merge) plus this morning briefing PR
- Test venv: `/Users/BigBobby/Documents/GitHub/Mining-Guardian/.venv-p018-tests/bin/python`

### Bobby's environment
- Has sudo on the Mini via his interactive SSH session (not Claude's non-interactive sessions)
- Anthropic key rotated yesterday; `slack-commands` running on PID 28448 with new key

---

## 5 · The W14 execution flow at a glance

Pull `docs/strategy/W14_PREP.md` for the full step-by-step. This is the summary:

| Step | What | Reversible? |
|---|---|---|
| 0 | Pre-W14 backups (DONE yesterday) | n/a |
| 1 | Unload the 12 scheduled launchd jobs (leave the 10 always-on running) | Yes |
| 2 | `docker run` new `mg-catalog-db` container on port 5433 with `/Library/Application Support/MiningGuardian/pgdata-catalog/` volume | Yes — stop+remove container |
| 3 | Drop empty bootstrap DB in new container, restore from `pre-w14-catalog-*.dump` | Yes — stop+remove |
| 4 | Add `GUARDIAN_PG_CATALOG_HOST=127.0.0.1` and `GUARDIAN_PG_CATALOG_PORT=5433` to `.env`. **`core/db_targets.py` is already pre-staged** — just `scp` from laptop to Mini install root. | Yes — remove env vars + revert scp |
| 5 | Bootout/bootstrap **all 10** always-on services | Yes — just restart |
| 6 | Smoke test: `core.db_targets` reports catalog on `127.0.0.1:5433`; one deep-dive smoke run; one normal scan | n/a |
| 7 | **`DROP DATABASE mining_guardian_catalog` on `mining-guardian-db`** | 🚨 **IRREVERSIBLE** without restoring from backup |
| 8 | Reload the 12 scheduled jobs | n/a |
| 9 | Update `scripts/daily_backup.sh` per D6 (separate PR) | (post-W14) |
| 10 | Update installer (`install_colima.sh`, `postinstall.sh`) per D7 (separate PR) | (post-W14) |

**Recommended maintenance window:** 02:00-04:00 CDT (between the 01:00 refinement chain and the 04:00 db_maintenance). Operator may choose differently based on actual schedule.

---

## 6 · After W14 lands (don't start tomorrow)

Per `docs/strategy/05_CATALOG_DESIGN_PLAN_2026-05-12.md` §6 + AMENDMENT A08, locked phase order working backward from mid-August 2026 customer ship:

1. **W14b** (XS, ~1h) — lock two-target convention in CLAUDE.md + .env.example + postinstall.sh — day after W14 stable
2. **W10** (S, ~1 day) — extend `dual_writer` with 5 new `propose_*` functions
3. **W11** (M-L, ~2-3 days) — Slack `/intel paste` + intake API + structure extractor
4. **W06, W07, W08** (S each) — AI reads `model_known_issues`, `war_stories`, `environmental_correlations`
5. **W09** (M, ~1-2 days) — Daily Pass 2 reads catalog. **Biggest unrealized AI value.**
6. **W27, W30** (M each, June) — catalog completeness (`ops.field_observed_specs` + enrichment CSV extraction)
7. **W25** (M, late June) — debug existing Grafana dashboards (NOT rebuild — see §2 above)
8. **W24** (M, late June) — Grafana password secret management
9. **W12** (S, early July) — morning briefing catalog visibility additions
10. **W28, W29** (L + XS, July) — federation v1 (required for August ship)
11. **August** — .pkg rebuild, notarization, bake, dry-run, first customer ship

**Realistic ETAs (per operator question yesterday):**
- Catalog being FED daily (Loops 1-3 all live): ~May 22
- Catalog being READ by AI daily (Loop 4 closed) — **when the centerpiece feels real**: ~early June
- Catalog comprehensive (Tier 3): ~end of June
- Grafana panels showing data: ~late June
- Federation v1 working: ~mid July
- First customer ship: mid-August 2026

---

## 7 · Operating principles for this session

The operator has been working hard for weeks and explicitly said today: "i would rather not spend 30-60 minutes answering questions." Honor that with these behaviors:

- **Don't ask questions you can answer by reading.** The 8 files in §0 contain the answers.
- **Don't re-litigate locked decisions.** §2 lists what's locked. If the operator wants to revisit a locked decision, they'll bring it up.
- **State your plan, then execute.** Not "should I do X, then Y, then Z?" — instead "I'm going to X, then Y, then Z. Pushing back, ok?"
- **Cite evidence over memory.** When something is in a doc, link the doc. When you're guessing, say so.
- **Honest about uncertainty.** "Based on the symptoms, most likely it's X" beats "It's X." (See the W25 conversation from yesterday — over-confident estimates cost trust.)
- **Use the established conventions.** Read CLAUDE.md if you haven't yet. Cohort guards, sibling sweeps, evidence-before-fix, live-Mini smoke before commit.
- **Branch-per-PR pattern is established.** Today's session merged 12 PRs (#184-#199) using the same flow: branch off main → commit → push → open PR via the URL printed by git → operator merges → local cleanup.
- **End-of-conversation/end-of-day docs go to existing files.** `HANDOFF_<date>_<context>.md` for end-of-day. Don't create new top-level docs unless there's a structural reason.
- **Time-tracking is the operator's job, not yours.** Don't claim "we have X minutes left" — the operator knows their schedule. If they share remaining time, work with it. Otherwise let them call breaks.

---

## 8 · Sanity check before running W14 Step 1

Verify these 6 boxes in order before executing anything destructive:

```bash
# Box 1: Local repo matches main HEAD
cd /Users/BigBobby/Documents/GitHub/Mining-Guardian && git log --oneline -1
# Expected: a fd2dc36-or-later merge commit

# Box 2: Pre-W14 backup files exist on Mini
ssh miningguardian@100.69.66.32 'ls -lh "/Library/Application Support/MiningGuardian/backups/"'
# Expected: pre-w14-operational-20260512-121154.dump (24M) + pre-w14-catalog-20260512-121154.dump (596K)

# Box 3: Old container still healthy
ssh miningguardian@100.69.66.32 '/usr/local/bin/docker ps --format "{{.Names}} {{.Status}}"'
# Expected: mining-guardian-db Up ...

# Box 4: All 10 always-on services + 12 scheduled = 22 entries
ssh miningguardian@100.69.66.32 'sudo launchctl list | grep com.miningguardian | wc -l'
# Expected: 22 (10 always-on with numeric PIDs + 12 scheduled with '-' for PID)

# Box 5: db_targets.py with W14 pre-staging on the laptop
grep -q "_resolve_catalog_host" /Users/BigBobby/Documents/GitHub/Mining-Guardian/core/db_targets.py && echo "✓ Pre-staged" || echo "✗ MISSING"
# Expected: ✓ Pre-staged

# Box 6: Maintenance window scheduled
# Operator: confirm 2+ hours uninterrupted, sudo SSH session live, recovery resources within reach.
```

If all 6 boxes check, you're cleared for Step 1.

---

## 9 · Quick-reference: file paths on Mini

```
/Library/Application Support/MiningGuardian/                 # install root
├── .env                                                      # secrets
├── core/db_targets.py                                        # what W14 Step 4 scp's into
├── venv/bin/python                                           # production Python 3.12.7
├── backups/                                                  # Step 0 dumps live here
│   ├── pre-w14-operational-20260512-121154.dump
│   └── pre-w14-catalog-20260512-121154.dump
├── pgdata/                                                   # operational pgdata (existing)
└── pgdata-catalog/                                           # catalog pgdata (W14 creates)

/Library/LaunchDaemons/com.miningguardian.*.plist             # 22 plists (10 services + 12 scheduled)
/opt/homebrew/var/lib/grafana/                                # Grafana 13.0.1
```

---

## 10 · Yesterday's full PR list (12 PRs, in order)

For reference if you need to inspect the commits:

| # | PR | Summary |
|---|---|---|
| 1 | #184 | W05 ProcessType=Standard on 9 services |
| 2 | #185 | W05b feedback-loop-daemon (10th service, A07) |
| 3 | #186 | W14a refactor 27 files through core.db_targets |
| 4 | #187 | W14a import-order hotfix 7 entry-point files |
| 5 | #188 | W14a import-order sweep 5 latent siblings |
| 6 | #189 | W14a self-contained sys.path / Path X 12 files |
| 7 | #190 | Catalog design plan locked (623-line doc) |
| 8 | #191 | EXECUTION_PLAN_STATUS update with today's progress |
| 9 | #192 | W14_PREP D1-D7 locked + pre-W14 status |
| 10 | #193 | W23 Grafana dashboards yml path fix |
| 11 | #194 | W26 audit results (Approach A locked) |
| 12 | #195 | HANDOFF_2026-05-13 morning briefing (the original) |
| 13 | #196 | HANDOFF_2026-05-12 EVENING UPDATE append |
| 14 | #197 | W14 pre-stage `_resolve_catalog_host/port` resolvers |
| 15 | #198 | W26 cohort guard test landed |
| 16 | #199 | W25 Grafana preference correction (Path A, not B) |

(PRs #195 #196 #197 #198 #199 sit on top of yesterday's main; deploy state is verified separately.)

---

*End of morning briefing. Start with §0 (read the linked files), do §8 (sanity checks), then propose your execution plan to the operator. Don't ask questions answered in these docs.*
