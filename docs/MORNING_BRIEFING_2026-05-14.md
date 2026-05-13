# Morning Briefing — 2026-05-14 (W26b Execution Day)

> **You are reading this at the START of a new Claude session.** This is the single document that brings the new session up to speed without needing to ask the operator questions. Read this file top-to-bottom in order. Linked references are listed inline so you can pull them as needed.
>
> **The operator (Bobby) has explicitly stated:** "I would rather not spend 30-60 minutes answering questions about what the day is about and what we have done and what is the right way to do things." Honor that. Read the doc, read the linked files, then state what you're going to do.
>
> **Today's job:** W26b — copy the 8 VPS-restored Grafana dashboards from the Mini into the repo's installer bundle, in a clearly-labeled `reference-mini/` subfolder, so the installer ships parity with production.

---

## 0 · Required reading order (do this BEFORE the first action)

Read these files in this exact order. Each is canonical for its domain. Don't ask the operator about anything in these files — read them.

| # | File | Why |
|---|---|---|
| 1 | This file (`docs/MORNING_BRIEFING_2026-05-14.md`) | Single-page orientation + reading order |
| 2 | `docs/HANDOFF_2026-05-13_EVENING.md` | **What actually happened yesterday.** 11 PRs across two chapters (W14 ship + W14b + backups → cohort cleanups + W25/W25b/W26a). Read E0 through E9. |
| 3 | `docs/strategy/W26b_PREP.md` | **The authoritative W26b runbook** — 6 steps with rollback notes. Start of execution. |
| 4 | `docs/EXECUTION_PLAN_STATUS.md` | Source of truth for what's done. Check the History section tail. |
| 5 | `CLAUDE.md` in repo root | Working conventions (Failure Mode 9, sibling sweeps, evidence-before-fix, live-Mini smoke, the new W14b two-target rule, the `.env` quote-stripping rule). Skim if you have it already. |
| 6 | `docs/strategy/04_MASTER_EXECUTION_PLAN.md` — §"New W-items" only | W26 family rationale. Reference only. Don't read top-to-bottom unless asked. |

**After reading those, you have hour-4 context.** Don't ask the operator to re-explain any of it.

---

## 1 · Today's job in one paragraph

The Mac Mini at `100.69.66.32` runs 9 Grafana dashboards: 1 in the repo's installer (the Intelligence Catalog dashboard shipped in W26a / PR #211) plus 8 restored from the old VPS tarball that are **only** on the Mini's filesystem. The repo's installer otherwise ships only 3 May-era dashboards (`fleet_overview.json`, `miner_models_catalog.json`, `scans_health.json`) which are strictly worse than what production runs. Today closes that drift by pulling the 8 VPS-restored dashboards into the repo. **5 of the 8 have hardcoded `100.69.66.32` references** in iframe URLs and other panel content — this is Bobby's specific Tailscale IP and would not work on a customer install. **Decision locked yesterday evening:** ship them as-is in `installer/macos-pkg/resources/grafana/dashboards/reference-mini/` to clearly label them as Mini-specific, defer the IP-templating problem to a future W item (W27 or W28). The installer's main dashboards folder continues to hold customer-deployable dashboards only.

---

## 2 · Locked decisions (do NOT re-litigate these today)

- **Path: ship as-is in `reference-mini/`.** Not "edit hardcoded IPs out." Not "skip the 5 with IPs." Not "template at build time." If you want to challenge this, do it concisely up front; do not silently choose a different path.
- **Naming collision is fine.** Repo has `fleet_overview.json` (7.5K, May-2 era). Mini has `mining_guardian_fleet_overview.json` (11.8K, VPS-era). They are **different files**. The new one ships with its `mining_guardian_` prefix. The old one stays untouched unless explicitly discussed.
- **Old 3 dashboards stay in the main dashboards/ folder.** They're customer-deployable as written; don't move them.
- **Cohort scope:** the 8 dashboards listed in §3 below. Nothing else. If you find a 9th file on the Mini, stop and ask.
- **Cohort guard scope:** sibling-sweep that asserts every dashboard JSON in the installer parses, has a sane `schemaVersion`, and that any file under `reference-mini/` is allowed to contain hardcoded IPs while anything outside it must not. Same shape as W26a S6.

---

## 3 · The 8 dashboards being added today

Pulled from `/Library/Application Support/MiningGuardian/grafana/dashboards/` on Mini:

| File | Size | Has `100.69.66.32`? |
|---|---|---|
| `mining_guardian_ai_learning.json` | 27 K | yes (2 sites) |
| `mining_guardian_board_health.json` | 8.8 K | yes (1 site) |
| `mining_guardian_fleet_overview.json` | 11.9 K | yes (1 site) |
| `mining_guardian_intelligence_report.json` | 61 K | yes (1 site) |
| `mining_guardian_main.json` | 27 K | no |
| `mining_guardian_mobile.json` | 8.2 K | no |
| `mining_guardian_per_miner.json` | 15.5 K | yes (1 site) |
| `mining_guardian_pool_stats.json` | 13.7 K | no |

Note: `intelligence_catalog_live_queries.json` is **already in the repo** (W26a PR #211, top-level dashboards/ folder). Don't re-copy it.

The pre-W26-fix backup files (`*.pre-w26-text-fix`, `*.pre-w26-schema-fix`) on the Mini are local-only safety nets from yesterday's debugging — **don't ship those**.

---

## 4 · Production state as of end of 2026-05-13

### Mini at `miningguardian@100.69.66.32` (Tailscale)
- macOS 26.4.1, M4, 16GB RAM
- Install root: `/Library/Application Support/MiningGuardian/` (NOT git-managed; manual scp delivery)
- Colima Docker, CLI at `/usr/local/bin/docker`

### Postgres topology (post-W14)
- `mining-guardian-db` (port 5432:5432) — operational only
- `mg-catalog-db` (port 5433:5432) — catalog only

### Baseline row counts (must match after any rollback)
| Database | Table | Rows |
|---|---|---|
| catalog | hardware.miner_models | 324 |
| catalog | hardware.manufacturers | 17 |
| catalog | firmware.firmware_releases | 6 |
| catalog | market.war_stories | 22 |
| operational | miner_readings | 17,856+ |

### launchd
- 10 always-on services, `ProcessType=Standard`, cluster 66707-66788
- 22 jobs total (12 cron + 10 always-on)

### Grafana 13.0.1
- `http://100.69.66.32:3000` over Tailscale
- 4 datasources (1 operational PG + 2 catalog PG + 1 Prometheus)
- 9 dashboards loaded (W26b will mirror 8 into the repo)
- Admin: `admin / W25test` (rotation deferred)

### dashboard_api
- Bound `0.0.0.0:8585` (W25)
- `/fleet/board_stats` Postgres-strict (W25b)
- All P-038 slice sites converted (#206 #207)

### Main HEAD at start of session
- Expected: `5cf154f` (PR #211 merge) — verify with `git log --oneline -1`

---

## 5 · Working conventions cheat-sheet

Pulled from `CLAUDE.md`. **These are binding** — do not silently violate.

- **Failure Mode 9** — sibling sweeps in one PR are OK if same bug class; mixed bug classes never bundled.
- **Evidence before fix** — live-Mini evidence required before fix; live-Mini smoke required before commit.
- **Cohort guard tests** — every fix lands with a guard test that catches unsurfaced siblings. W26b's guard tests in the spirit of W26a S6 (sibling sweep across all installer dashboards).
- **Failure mode for installer dashboards** — the new W26b convention: anything under `reference-mini/` may contain hardcoded IPs and other Mini-specific content; anything outside it must not. Cohort guard test enforces.
- **Postgres access** (W14b binding rule 1) — through `core.db_targets` only. Enforced by `tests/test_w14a_no_direct_pg_env_reads.py`.
- **`.env` quote-stripping** (W14b binding rule 2) — through `xargs`. Enforced by `tests/test_w14_password_quote_consistency.py`.
- **Bobby's SSH session has sudo; Claude's does not.** When you need sudo on the Mini, hand the command to Bobby.
- **Bobby's preferred working style** — clarifying questions OK but only when actually ambiguous; explain reasoning when teaching ("i really like to learn").
- **No emojis unless Bobby uses them first** — minimal exception: ✅ ❌ for status, 🔐 for security flags.

---

## 6 · The W26b plan (read W26b_PREP.md for full detail)

Six steps (estimated wall time in parentheses):

1. **Pull files from Mini** (~5 min) — scp the 8 dashboards to `/tmp/w26b/`, sanity-check sizes match expected.
2. **Stage in repo** (~5 min) — `mkdir -p installer/macos-pkg/resources/grafana/dashboards/reference-mini/`, copy files in, do NOT modify.
3. **Update README** (~10 min) — explain the `reference-mini/` folder in the installer README.
4. **Cohort guard test** (~25 min) — `tests/test_w26b_installer_dashboard_set.py`. Asserts:
   - The 8 expected dashboards exist under `reference-mini/`
   - All parse as valid JSON
   - All have `schemaVersion >= 30`
   - `reference-mini/` files are allowed to contain hardcoded IPs
   - Files under `dashboards/` directly (the customer-deployable set) must NOT contain hardcoded IPs
5. **Live-Mini smoke** (~5 min) — refresh each of the 8 dashboards in Safari, confirm panels render. (No deploy step needed — Mini already has these files; we're only mirroring to repo.)
6. **PR + merge + cleanup** (~10 min).

**Total: ~60 min of focused work**, plus testing buffer.

The 3 untracked wordmark PNGs (`installer/macos-pkg/resources/grafana/mining_guardian_{icon,primary,wordmark}.png`) can land in this same PR — they're brand assets restored during W25, currently untracked.

---

## 7 · Open items not in scope for W26b (don't pull them in)

- 🔐 **Postgres password rotation** — leaked in chat May 11 + May 13. Bobby decided handle later. ~30-60 min careful work. Schedule for a dedicated session.
- 🔐 **Grafana admin password rotation** — currently `W25test`. Before customer ship.
- **W17** — 151 naked `datetime.now()`. Sweep, not deep work.
- **W24** — Grafana password secret management. Real concern, separate scope.
- **catalog_import permissions** — pre-existing bug, tracked.
- **`daily_deep_dive` stale last-run-date** — pre-existing bug, tracked.
- **feedback-loop-daemon catalog writes** — not writing to catalog since 2026-05-09.
- **`.claude/settings.json` plugin marketplace migration** — working-tree drift, not committed.

If any of these become urgent mid-session, surface them but don't fold them into W26b. Failure Mode 9: same bug class only.

---

## 8 · Sanity-check commands (run after reading, before proposing the plan)

```bash
# Repo state
cd /Users/BigBobby/Documents/GitHub/Mining-Guardian
git status                                              # working tree clean (modulo .claude + 3 PNGs)
git log --oneline -1                                    # 5cf154f or later
git log --oneline -5 origin/main                        # main aligned

# Test suite green
.venv-p018-tests/bin/python -m pytest tests/ 2>&1 | tail -5
# Expected: all pass

# Mini reachable
ssh miningguardian@100.69.66.32 'echo ok && date'       # should respond <2s

# Grafana healthy
curl -s http://100.69.66.32:3000/api/health
# Expected: {"database":"ok","version":"13.0.1-0",...}

# Both Postgres instances responding
ssh miningguardian@100.69.66.32 'docker ps --format "{{.Names}} {{.Status}}"' | grep mg-
# Expected: mining-guardian-db Up X / mg-catalog-db Up Y

# Always-on services healthy
ssh miningguardian@100.69.66.32 'sudo launchctl list | grep com.miningguardian | wc -l'
# Expected: 22 (12 cron + 10 always-on)

# The 8 W26b source files exist on Mini
ssh miningguardian@100.69.66.32 'ls "/Library/Application Support/MiningGuardian/grafana/dashboards/" | grep "^mining_guardian_" | grep -v "pre-w26" | wc -l'
# Expected: 8
```

After verification, propose the W26b plan to Bobby in your own words. Don't ask questions that are answered in this brief or in W26b_PREP.md.

---

## 9 · After W26b — what's next

Three reasonable follow-ups depending on time and energy:

1. **W24** — Grafana password secret management. The yaml needs to read passwords from env, not have them inlined. Coupled with the Postgres password rotation.
2. **W23 final close** — the only remaining bit is the `guardian_app` → `mg` standardization across the codebase (datasource user). Trivial scan-and-replace.
3. **W17 begin** — 151 `datetime.now()` → `datetime.now(timezone.utc)` calls. Sweep, doesn't need a lot of architectural thought.

If W26b finishes inside an hour, Bobby may want to roll into one of these or save the bandwidth.

---

## 10 · Today's PR list (for reference if you need to inspect)

From yesterday's evening handoff E1:

| # | PR | Summary |
|---|---|---|
| 1 | #201 | W14 close-out: status + post-mortem |
| 2 | #202 | W14 password quote-consistency cohort guard |
| 3 | #203 | W14b convention lock |
| 4 | #204 | W14 Step 9 backup pipeline |
| 5 | #205 | db_maintenance.sh Colima socket fix |
| 6 | #206 | P-038 v2 19 timestamptz slice sites |
| 7 | #207 | P-038 v2 14 HTML render slice sites |
| 8 | #208 | Dead-code sweep archive/ + fixes/ |
| 9 | #209 | W25 dashboard_api bind |
| 10 | #210 | W25b /fleet/board_stats Postgres GROUP BY |
| 11 | #211 | W26a Intelligence Catalog dashboard |
| 12 | (this bundle's PR) | Handoff docs + W26b prep |

---

*End of morning briefing. Start with §0 (read the linked files), do §8 (sanity checks), then propose your execution plan to the operator. Don't ask questions answered in these docs.*
