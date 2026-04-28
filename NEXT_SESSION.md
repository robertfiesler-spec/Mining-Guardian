> # ⚠️ SUPERSEDED — DO NOT ACT ON THIS DOCUMENT
>
> **Superseded:** 2026-04-28 by PRs #25 / #26 / #27 / #29 / #30
> **Status:** Historical record only — kept for audit trail per
> "comprehensive + over-document always" lock.
>
> ## Why this is superseded
>
> This document was written 2026-04-23 as a "Step 7: Scratch Router Test" plan
> for the **split-SQLite** architecture. Five days of work between 2026-04-23
> and 2026-04-28 has made every operational instruction below incorrect:
>
> | Stale assumption in this doc | Current reality |
> |---|---|
> | `/root/Mining-Gaurdian/guardian.db` is the live DB (monolithic SQLite, ~6.6 GB) | Postgres 16 in container `mining-guardian-db`, db `mining_guardian`, is the canonical store. SQLite is **never** referred to as live. (D-1) |
> | Path uses `Mining-Gaurdian/` (typo) | Renamed to `Mining-Guardian/` (correct spelling) on 2026-04-26 in PR #1 |
> | "Step 7: Scratch Router Test" is the next action | Moot — Postgres migration replaced the split-SQLite experiment in one step |
> | Mac Mini May-5-9 stand-up plan | Still upcoming, but rewritten — see D-13 (Ollama RAM auto-detect), Q1 (Hybrid ~500 MB .pkg installer, double-click), cutover scope γ (Mini replaces both Hostinger VPS and ROBS-PC catalog) |
> | "GitHub PAT in VPS .git/config still exposed" | Resolved — see `docs/SESSION_LOG_2026-04-27.md` |
> | "Hardcoded password in scripts/migrate_to_postgres.py" | Already noted as resolved 2026-04-27 in this doc itself, under CRIT-1 |
>
> ## Where to look instead
>
> | For… | Read this |
> |---|---|
> | Current architecture, paths, branches, schema | `docs/CLAUDE.md` (rewritten 2026-04-27, PR #27 / `3248bde`) |
> | All locked decisions including D-13 Ollama RAM auto-detect | `docs/DECISIONS.md` |
> | Live-DB cutover record, addendum #3 | `docs/SESSION_LOG_2026-04-27.md` |
> | Known but unfixed defects | `docs/LATENT_BUGS.md` (rewritten 2026-04-28, PR #30 / `121dcd4`) |
> | Brand system | `branding/BRANDING.md` (PR #29 / `4313ba9`) |
> | Installer-build branch history | tag `archive/installer-build-20260428` → `ec7d359` |
>
> ## What was preserved verbatim below
>
> The original 2026-04-23 body is left **intact and unedited** below this banner
> as historical record. Do not act on any instruction in it. Read it only to
> understand what the plan looked like five days ago.
>
> ---

# Next Session Notes — Mining Guardian

**Last Updated:** 2026-04-23 05:45 CDT

This doc was rewritten on 2026-04-23 to reflect current reality. The previous
version (written 2026-04-22 18:30 CDT, committed in 3a38112) described the
split-DB router as production. That stopped being true at 2026-04-22 16:35
when the router was reverted due to cross-table-join bugs. See
`docs/DB_STATE_2026-04-23.md` for the full story.

---

## Where We Are Right Now

**Single source of truth:** `/root/Mining-Gaurdian/guardian.db` (monolithic
SQLite, ~6.6 GB). All 8 systemd services write here via `_connect()` which
is pinned to the legacy path.

**Frozen cold (do not delete — rollback points):**
- `databases/operational.db` + `timeseries.db` + `ai_knowledge.db` + `audit.db`
- Last written 2026-04-22 16:33

**Empty-schema staging:**
- VPS Postgres `mining_guardian` DB, `public` schema, 25 tables, zero rows.
  Reserved for a real future SQLite→Postgres migration.

**Separate system, not on the VPS:**
- PC Docker `mining-guardian-db` Postgres — Field Intelligence catalog.
  317 models, 12,852 Tier-1 aliases, 1,494 Tier-2 aliases, 14k field-log rows.
  Stays on PC until Mac Mini arrives (ETA May 5-9).

---

## Today's Work (2026-04-23, this session)

All 12 commits pushed to origin/main:

1. `64f31e7` Daily knowledge backup — 2026-04-23 04:00
2. `215c453` fix: stabilize mining-guardian on legacy guardian.db
3. `ef86b7f` chore: gitignore generated PDF reports
4. `e246022` chore: save Phase 2 migration script (WIP)
5. `8aa6b53` docs: audit core/database.py for cross-table-join bugs
6. `aab2769` fix(database): route count_outcome_failures to miner_restarts DB
7. `fec4a64` fix(database): route _count_pdu_cycles to action_audit_log DB
8. `789763f` fix(database): split load_known_firmware into two DB connections
9. `3507db6` fix(database): route save_logs lookup to miner_readings DB
10. `423e058` fix(database): split expire_old_pending_approvals across two DBs
11. `c10fb58` fix(database): split save_scan into two DB connections
12. `41500c9` fix(database): partition _init_db across three split DBs

All 7 cross-table-join bugs catalogued in `docs/CORE_DATABASE_AUDIT_2026-04-23.md`
are now fixed. `mining-guardian` was restarted on new PID 57931 at 05:35 CDT;
scan 1691 completed cleanly end-to-end, confirming the fixes are no-ops under
the monolithic DB pin.

---

## Next Session — Step 7: Scratch Router Test

**Goal:** Validate the 7 fixes actually work when the router is active, without
touching production data.

**Setup:**
1. Copy `databases/*.db` to `/tmp/split_test/` (scratch copies)
2. Write a temporary subclass `GuardianDBScratch(GuardianDB)` that overrides
   `_connect()` to use the original router-based routing, but pointed at the
   scratch DB directory instead of `/root/Mining-Gaurdian/databases/`
3. Or: use env-var gating so we can flip router on/off without code change

**Tests to run against scratch copies:**
- Instantiate `GuardianDBScratch()` — confirms `_init_db` creates schemas in
  the correct split DBs (Bug 1)
- Call `save_scan([mock_miner])` — confirms `save_scan` splits cleanly (Bug 4)
- Call `expire_old_pending_approvals()` — confirms the 2-block split (Bug 2)
- Call `save_logs()`, `load_known_firmware()`, `count_outcome_failures()`,
  `_count_pdu_cycles()` — confirms the remaining 4 fixes

**If all pass:** document that the router is validated, decide later whether
to re-enable in production (probably NOT until Mac Mini / Postgres migration
lets us skip the split-SQLite step entirely).

**If any fail:** debug in the scratch sandbox, fix in a new commit, repeat.

---

## Known Outstanding Items (unchanged from yesterday)

### Physical / operator
- Power cycle miner 53476 (.31) at facility — AI has flagged multiple days
  running (zero hashrate while drawing power)
- Inspect miner 53494 — critical flags from 2026-04-22 overnight analysis
- **Thursday Apr 24:** HVAC work complete, re-enable S21/Auradine analysis,
  remove `hvac_work_apr2026` hardware fact
- **Miner 53521** — CRITICAL, all 3 hashboards failing (0/126 ASICs each),
  likely needs board replacement
- **Miner 53482** (.46) — BiXBiT S19JPro running 83.5% of target

### Code / infra
- **GitHub PAT** still exposed in VPS `.git/config` remote URL — deferred by
  user but still needs rotation before the Mac Mini cutover
- `scripts/cleanup_ams_logs.py` — cron removed today, script itself still in
  repo. Delete when convenient (it has a pre-existing `datetime` import bug)
- ~~Hardcoded password in `scripts/migrate_to_postgres.py`~~ — **resolved
  2026-04-27** under CRIT-1: literal purged, script now reads `MG_DB_PASSWORD`
  from env and refuses to run unless the env var is set
- Field Intelligence Pipeline v3.3 deployment — if Field Intelligence work
  resumes, see previous `NEXT_SESSION.md` in commit `3a38112`

### Project plans
- **May 5-9: Mac Mini arrives.** Triggers: migrate Cloudflare tunnels off the
  VPS, stand up the Mac as the real local LLM + on-site database host,
  decide on clean Postgres migration (probably replaces both split-SQLite
  experiments in one clean step)

---

## System Status

### Services
All 8 systemd services active on monolithic guardian.db:
- mining-guardian (restarted today 05:35 CDT, new code active)
- dashboard-api (:8585)
- approval-api (:8686)
- slack-listener
- slack-commands
- overnight-automation
- mining-guardian-alerts
- intelligence-report

### Safety net
`/root/mg_safety_snapshot_2026-04-23.tar.gz` (1.8 GB) — full working tree
snapshot from 04:24 CDT before today's cleanup began. Rollback point if
anything in today's 12 commits needs to be undone.

---

## Quick Reference

### SQL queries against the live DB
```bash
sqlite3 /root/Mining-Gaurdian/guardian.db 'SELECT id, scanned_at FROM scans ORDER BY id DESC LIMIT 5;'
```

### Log files
```
/tmp/daily_deep_dive.log        # 4pm Qwen deep dive
/tmp/direct_log_collection.log  # 1pm log collection
/tmp/daily_claude_training.log  # midnight Claude training
/tmp/daily_refinement_chain.log # 1am Qwen+Claude refinement
/tmp/morning_briefing.log       # 7am briefing
/tmp/knowledge_backup.log       # 4am git push
```

### Key docs
- `docs/DB_STATE_2026-04-23.md` — three-database reality (canonical)
- `docs/CORE_DATABASE_AUDIT_2026-04-23.md` — 7 cross-table bugs, now all fixed
- `docs/SESSION_REPORT_2026-04-23.md` — plain-language overview of today
