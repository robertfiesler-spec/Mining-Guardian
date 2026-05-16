# HANDOFF — 2026-05-16 (Saturday evening)

> Written to the same E0–E10 template as `HANDOFF_2026-05-14_EVENING.md`.
> Source of truth is this file + `docs/EXECUTION_PLAN_STATUS.md`; the
> `~/Downloads/2026-05-16/` package is assembled FROM these, not forked.

## E0. The actual TL;DR

Three things happened today that matter, in order of importance:

1. **THE BIG FINDING — W42: the Intelligence Catalog has been silently inert
   for 11 days.** The catalog DB (`mg-catalog-db`, port 5433) is frozen at its
   324-row seed, newest `created_at`/`updated_at` = **2026-05-05**. The daily
   Perplexity scans (Aggregator Watcher, Community Intel Scanner, Firmware
   Tracker) run and find real new models/firmware every day, but their output
   goes to `latest_findings.json` / `cron_tracking/` scratch files and is
   **never ingested into the catalog DB**. The "world's most complete bitcoin
   database" — the core product premise — has not grown since 2026-05-05 while
   appearing to work. Data is NOT lost (Perplexity has it; operator can ask it
   where it writes). This is the #1 item for tomorrow. Root cause untraced by
   discipline (do not rush a DB-ingestion fix tired).

2. **W35/W36 — root cause of "nothing's worked right since the cutover" found
   and fixed.** The W14 two-DB split (2026-05-13) manually unloaded 12
   scheduled jobs and the hand-run reload missed 6. Separately, the
   log-collection/deep-dive schedule had been changed on the VPS ~3 weeks ago
   (08:00/09:00, fleet grew 36→90+) but never propagated to repo/installer, so
   the Mini shipped the stale 1PM/4PM. Both fixed and **verified on the live
   Mini** (`launchctl print` shows `Hour => 8` / `Hour => 9`). VPS crontab
   independently confirmed 08:00/09:00 as ground truth.

3. **8 PRs shipped and merged. Documentation audit produced. Branch cleanup
   21→1.** Full ledger in E1.

## E1. PR ledger for today

| PR | Item | State |
|----|------|-------|
| #224 | W17 datetime-UTC sweep (111 fixes, 30 files) + W34 status flip | Merged |
| #225 | W14a cohort-guard gap (documented tests/ exclusion never implemented) | Merged |
| #226 | CLAUDE.md Step-0 access verification + handoff tooling requirement | Merged |
| #227 | W35 — daily-deep-dive launchd job absent (the diagnosis) | Merged |
| #228 | W36 — schedule corrected 08:00/09:00 (VPS-verified) | Merged |
| #229 | B-6 allow-list fix (typo guard was red on main since #223, 2 days) | Merged |
| #230 | Documentation reconciliation audit (DOC_AUDIT_2026-05-16.md) | Merged |
| #231 | This handoff + EXECUTION_PLAN_STATUS W35/W36/W37–W42 rows | (this PR) |

## E2. Chapter 1 — W35/W36: the post-cutover schedule failure

### E2.1. The presenting problem
Since the W14 cutover, the daily learning loop never ran right on the Mini.

### E2.2. Root cause — two distinct bugs, same class
- **W35:** the W14 split manually `launchctl bootout`'d 12 scheduled jobs;
  the manual reload (no script — hand-run) missed 6: daily-deep-dive,
  log-collection, morning-briefing, operator-review, ams-cleanup,
  log-failure-report. All 6 plists were intact on disk the whole time.
- **W36:** log-collection/deep-dive schedule was changed on the VPS ~3 weeks
  ago (08:00/09:00 — operator decision, fleet grew 36→90+, ~5-6 min/miner
  deep-dive ⇒ ~8-12 h run, 09:00 start protects the 01:00 refinement passes).
  The change lived only on the VPS crontab; repo/installer/`CRON_SCHEDULE.md`
  still said the old 1PM/4PM. The 2026-05-09 Mini build shipped the stale
  schedule. **W33/W35-class: VPS reality not captured in the build.**

### E2.3. Ground truth that resolved it
VPS crontab (`root@srv1549463`, read live this session) is authoritative and
confirmed operator memory exactly: log-collection `0 8 * * *`, deep-dive
`0 9 * * *`, refinement `0 1 * * *` (daily, NOT Sunday). Also surfaced:
operator-review runs **08:15** on the VPS (`15 8 * * *`) while the Mini
plist/doc say 08:00 — logged as D6.

### E2.4. What was fixed and verified
- Operational jobs restored on the live Mini: log-collection (08:00),
  morning-briefing, operator-review, daily-deep-dive (09:00). Each via
  `sudo cp` corrected plist → `bootout` → `bootstrap` → `launchctl print`
  verified the new `Hour =>`. **deep-dive `Hour => 9` confirmed live.**
- ams-cleanup + log-failure-report: operator declared BOTH obsolete (direct
  -from-miner collection superseded the AMS path). Left absent on the Mini;
  repo decommission tracked as W37 (not done — Failure Mode 9, own item).
- Repo brought into line: PR #228 corrected both plists + `CRON_SCHEDULE.md`
  (tables + dated correction notice with reasoning).

### E2.5. Process notes worth keeping
- The terminal jammed twice on chained/multi-line ssh commands. **Mini ssh =
  one dead-simple single command at a time, wait for paste.** This is now a
  hard operating rule.
- I was wrong mid-session: I pushed back on the operator's 8/9 figure based
  on the stale doc. The operator was right; the doc was stale; the VPS
  crontab proved it. Lesson reinforced: ground truth beats prose (now a
  proposed CLAUDE.md discipline — DOC_AUDIT §4).

## E3. Chapter 2 — the documentation audit (PR #230)

`docs/DOC_AUDIT_2026-05-16.md`: read-only reconciliation, nothing deleted.
Drift register D1–D6, single-source-of-truth map, proposed CLAUDE.md
discipline (same-commit reconciliation + ground-truth-beats-prose).
Highest-risk finding **D4**: `MAC_MINI_DEPLOYMENT_RUNBOOK.md` self-declares
"canonical" but predates the W14 two-DB split by ~2 weeks, describes
single-DB topology + retired conventions, and was NOT the actual install
path. Needs an interim "DO NOT USE — pre-W14" banner + operator
rewrite/retire decision. B-6 typo guard had been RED on `main` since #223
(2026-05-14), undetected 2 days — fixed in #229; it is exhibit A for the
audit (a guard's allow-list silently drifted from the docs it guards).

## E4. THE BIG FINDING — W42: catalog ingestion is broken

### E4.1. How it surfaced
Operator: building "the world's most complete bitcoin-only database"; 4
Perplexity scans daily; *"I don't know where all the new info goes or if it
is getting added daily or if it's going somewhere at all."* The only window
into the catalog is the Intelligence Report Grafana page — which is one of
the broken pages (W41), so it couldn't be checked visually.

### E4.2. Verified directly against the live catalog DB (no Grafana needed)
Via the bridge → `ssh miningguardian@100.69.66.32` →
`/usr/local/bin/docker exec mg-catalog-db psql -U mg -d mining_guardian_catalog`:
- Both containers up: `mg-catalog-db` 127.0.0.1:5433, `mining-guardian-db`
  127.0.0.1:5432 — W14 split is genuinely live.
- `hardware.miner_models`: **324 rows. max(created_at)=max(updated_at)=
  2026-05-05 22:09:32+00.** Today is 2026-05-16. **Nothing added/updated in
  11 days.** 324 = the exact initial seed size (D-14 / runbook: "320-row
  catalog seed"). The catalog contains the seed and nothing else.
- The task log the operator pasted shows the scans writing to
  `latest_findings.json` and `cron_tracking/c8c4678d/{latest_findings,
  run_state}.json` — NOT to the catalog DB.

### E4.3. What this means (proven vs. not)
- PROVEN: the catalog DB has not grown since the seed; today's findings
  (Whatsminer M79S, Lucky Miner LV06/07/08, NerdQaxe variants, Braiins
  v26.05) are not in it.
- NOT YET TRACED: *why* — missing ingestion script, broken one, wrong
  target, or never wired. Strong hypothesis: the D-14 line-150 gap (the
  feedback path from findings → catalog was never connected; same shape as
  "the scanner doesn't consult the catalog"). Likely overlaps W06–W09.
- Schema note for whoever does the fix: the table's name column is
  `model_number`, NOT `model_name` (a naive load using the wrong field will
  silently mis-map). Treat this as W33-class: irreversible, schema-drift
  -prone, do NOT rush.

### E4.4. Why this is W42 and #1
The product premise is an AI that grows smarter from continuously growing
intelligence. The knowledge loop has been silently inert 11 days while the
scans appeared to work. It is the W35 pattern (looks alive, isn't) on the
catalog. Operator's framing for the fix is correct and is the scope:
(1) one-time backfill of findings since 2026-05-05 from the JSON/Perplexity;
(2) build the standing auto-ingest pipe so every future finding lands in the
catalog at discovery time. **Prerequisite the operator owns:** ask Perplexity
exactly where it has been writing everything (confirms the backfill source).

## E5. End-of-day state

### Repo
`main` at the merge of #230 (then #231 when this merges). Working tree clean
except always-drift `.claude/settings.json` (never staged). Local branches:
**just `main`** (21 stale branches cleaned this session, every deletion
verified `git rev-list --count <b> ^main == 0` first; 2 needed `-D` after
independent re-verification due to a tracking-branch mismatch git correctly
flagged).

### Mini at `miningguardian@100.69.66.32` (Tailscale)
- 12 scheduled jobs' correct set restored; log-collection 08:00, deep-dive
  09:00 **verified live** via `launchctl print`. morning-briefing,
  operator-review restored. ams-cleanup + log-failure-report intentionally
  absent (obsolete; repo decommission = W37).
- Always-on services healthy (scanner, dashboard-api, slack, etc. — never
  affected).
- **NOT verified:** that a deep-dive actually *completes* end-to-end (loaded
  on 09:00 but never run post-cutover — W38). First auto-run 2026-05-17 09:00.

### Postgres topology (W14, confirmed live this session)
Two containers: `mining-guardian-db` :5432 (operational `mining_guardian`),
`mg-catalog-db` :5433 (catalog `mining_guardian_catalog`, 19 hardware
tables, 324 models, frozen at 2026-05-05 — W42).

### VPS at `srv1549463` (root SSH, reachable via bridge)
Crontab is schedule ground truth (08:00/09:00/01:00, operator-review 08:15).
W33 source data intact + byte-verified at `/root/db-preserve-20260514/`
(guardian.db 4.1G, timeseries.db 5.4G, audit.db 1006M, +2 small; 328G free).

## E6. Open items at end of day

### Resolved today
W17, W14a, access-kickoff convention, W35 (diagnosed+restored), W36
(fixed+verified+repo), B-6 guard (greened), doc audit (produced), branch
cleanup.

### Newly opened today
- **W42** (catalog ingestion broken — #1) — see E4.
- **W38** (verify a deep-dive completes) — first auto-run 2026-05-17 09:00.
- **W41** (broken Grafana pages — scoped from screenshots: AI&Learning shows
  only the score panel; Intelligence Report shows a placeholder not the
  catalog search; Main dashboard HVAC panels Supply/Return Water, Delta T,
  Diff Pressure = "No data"; likely includes W31-class inline-script defect).
- **W40** (iPhone app — reads console + embeds Grafana; "Mining Guardian —
  Mobile" dashboard is prior art).
- **W37** (decommission ams-cleanup + log-failure-report from installer).
- **D4** (stale canonical deployment runbook — banner + decision).
- **D2/D3/D6** (DECISIONS.md 11→12 jobs; refinement daily-not-Sunday;
  operator-review 08:00→08:15).
- **W35 recurrence guard** (nothing stops the next job-cycling W-session
  from re-dropping scheduled jobs).
- **W39 / Gap 4** (full console job/schedule control — schedule edits
  currently write to system_schedules but don't apply to plists; confirmed
  via the Task Registry UI text).

### Still open — carried, tracked
W33 (VPS historical data migration; data safe; operator-call timing).
W10b → W11 → W06–W09 (catalog/Slack critical path — may subsume/relate to
the W42 fix; the W42 root-cause trace decides).

### Open security (unchanged — dedicated pass)
Postgres password rotation; Grafana admin password.

## E7. Where the plan stands — the final ordered backlog

- **TIER 0 (silent failures, start here):** W42 (catalog ingestion — #1),
  W38 (verify deep-dive completes).
- **TIER 1 (visibility):** W41 (broken Grafana pages — incl. the one that
  hid W42).
- **TIER 2 (landmines):** D4 (stale runbook), W33 (VPS data migration).
- **TIER 3 (debt):** W37, D2/D3/D6, W35 recurrence guard.
- **TIER 4 (product roadmap):** W40 (iPhone app), W10b→W11→W06–W09, W39/Gap4.
- **TIER 5 (pre-ship security):** Postgres pw rotation, Grafana admin pw.

## E8. Tomorrow's job — operator's call, recommended order

1. **Operator legwork first:** ask Perplexity where it has been storing all
   daily findings (W42 backfill source — only the operator can do this).
2. **W42** — trace why findings don't reach `mg-catalog-db`; design the
   one-time backfill + the standing auto-ingest pipe. Fresh-session work,
   full focus, treat like W33 (irreversible, schema-drift-prone).
3. Opportunistic: confirm W38 (the 09:00 deep-dive fired and completed —
   check after 09:00; `/tmp/daily_deep_dive.log` on the Mini).

## E9. Notes to tomorrow's Claude

- **READ CLAUDE.md Step 0 FIRST.** Access is real and already solved: laptop
  repo via the Desktop Commander MCP tool (`tool_search` for it — deferred);
  Mini + VPS via Desktop Commander running `ssh`. Do NOT waste the session
  re-litigating access — that cost ~4 h this morning before the tool was
  found. #226 codified this.
- Mini ssh: ONE simple single command at a time, wait for paste. No `&&`,
  no chained quotes — it jams the operator's zsh.
- `docker` on the Mini is `/usr/local/bin/docker` (not on non-interactive
  ssh PATH).
- Operator preference: most-correct path, never the fastest. Present the
  rigorous option as the recommendation. Document-as-you-go. Failure Mode 9
  (one bug class per PR). Never stage `.claude/settings.json`.
- The operator is customer #1; the Mini is HIS machine; offline-for-days is
  acceptable if it comes back correct. Defers technical judgment to Claude
  but wants the calls surfaced.

## E10. Quick verification commands for tomorrow

```
# Repo state
cd /Users/BigBobby/Documents/GitHub/Mining-Guardian && git checkout main && git pull --ff-only && git branch
# Mini reachable + scheduled jobs (expect 22 = 12 + 10)
ssh miningguardian@100.69.66.32 'launchctl list | grep -c com.miningguardian'
# Deep-dive schedule still 09:00?
ssh miningguardian@100.69.66.32 'sudo launchctl print system/com.miningguardian.scheduled.daily-deep-dive | grep -A4 calendarinterval'
# THE W42 reality check — has the catalog grown past 2026-05-05?
ssh miningguardian@100.69.66.32 '/usr/local/bin/docker exec mg-catalog-db psql -U mg -d mining_guardian_catalog -c "SELECT count(*), max(created_at), max(updated_at) FROM hardware.miner_models;"'
# Expected (until W42 fixed): 324, 2026-05-05, 2026-05-05
# Did the 09:00 deep-dive run? (check after 09:00)
ssh miningguardian@100.69.66.32 'tail -20 /tmp/daily_deep_dive.log'
```

*End of 2026-05-16 evening handoff.*
