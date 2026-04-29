# Session Log — April 9, 2026

**Purpose of this file:** Running narrative of the April 9 2026 session. Not a design doc, not a bug log — a chronological record of what was found, what was decided, what was built, what was discovered in production, and what was deferred. Written at the end of the session so future sessions (and Bobby) can understand how the day actually unfolded, not just what the final state looked like.

**Why it exists:** Per operator instruction at end of session: documentation was getting skipped throughout the day, and the same silent-skip pattern we keep finding in the code was showing up in our own process. Work was shipping but nobody was writing down *what was learned* or *why decisions were made*. The REPAIR_LOG captures bugs and fixes backward-looking. This file captures the forward-looking narrative — decisions, discoveries, context that doesn't fit cleanly into a bug entry but is essential to understand how the system got to its current state.

**Future sessions should:** append a new SESSION_LOG_YYYY-MM-DD.md for each working session. Do not delete old ones. Do not consolidate across days. Each day gets its own file in `docs/`.

---

## Summary — What Today Was

Today was a long working session that started with a morning doc sync and fresh CLAUDE.md kickoff protocol, moved into diagnosing and fixing two silent-skip bugs in the log collection and weekly training pipelines, and ended with building the long-absent Daily Deep Dive LLM pipeline and shipping parallel daily log collection. Six production commits, one major new file (`ai/daily_deep_dive.py`), a real production bug caught in live deployment (miner 53482 hanging the sequential sweep), and a significant architectural upgrade (sequential → 15-worker parallel daily collection). Also discovered a degraded miner (53482) that the hourly scan logic had been silently ignoring because it didn't trip the hashrate or temperature thresholds.

## Commits Shipped Today (chronological)

All on `origin/main`. Author `Automation-builds <robertefiesler@gmail.com>`. All from this Mac through this session's shell + git.

| Time (CDT) | Hash | What it is |
|---|---|---|
| 09:15 | `27a92a2` | docs(claude.md): Working Principles section (2-vs-10 rule, operating discipline) |
| 09:41 | `28010b8` | docs(claude.md): Deployment Target section (Mac mini at customer sites, open by default) |
| 10:10 | `70e2f9c` | feat(dashboard-api): /query/* read-only endpoints for OpenClaw skill |
| 10:21 | `dcd9d28` | feat(openclaw): guardian-db skill — lets OpenClaw answer real fleet questions |
| 10:42 | `bf80176` | docs: mid-morning handoff to a fresh Claude session |
| 11:30 | `8497062` | feat(dashboard-api): /ask page — natural language fleet query UI |
| 13:21 | `1796a62` | docs: full repo-wide doc sync after April 9 deep review |
| 13:33 | `1779ee7` | docs: morning kickoff prompt template |
| 13:49 | `827b4d6` | docs(roadmap): April 9 diagnostic sweep findings |
| 14:50 | `d6c2871` | docs: add REPAIR_LOG.md — layman-terms record of bugs and fixes |
| 14:59 | `95676b6` | log collection + post-restart wait: remove time caps, daily fresh-export baseline (**Edits A-E**) |
| 15:18 | `e90c2be` | fix(weekly_training): merge pre/post restart comparisons into Claude fleet prompt (**Edit F**) |
| 15:21 | `49d1a79` | docs: REPAIR_LOG entry for weekly training merge + CLAUDE.md May Migration section |
| 16:22 | `da1edbd` | feat(daily_deep_dive): new Qwen daily deep dive LLM + 10min cap on baseline collection |
| 16:29 | `1dbbeb3` | docs: REPAIR_LOG entries for daily deep dive + 10min cap discovery |
| 16:40 | `e5b9f5c` | feat(daily_logs): parallel 15-worker daily baseline collection |

**Commit count for session:** 16 commits. Of those, the 9 from 13:21 onward are the ones most relevant to the "afternoon log pipeline sprint" narrative. The 7 morning commits were OpenClaw + dashboard + doc sync work handled in the earlier part of the day.

## The Narrative

### Morning: doc sync and kickoff protocol

Session opened with Bobby noting that previous Claude sessions had been making assumptions and skipping the read-the-existing-docs step, leading to proposed alternatives for plans that already existed. The morning was spent rewriting `CLAUDE.md` with a binding Session Kickoff Protocol (steps 1-6, now steps 1-7 with REPAIR_LOG.md added), creating `docs/VISION.md` as the canonical single-source-of-truth synthesizing nine scattered planning docs into one, updating `README.md` and `AI_ROADMAP.md` to cross-reference the canonical plan, creating `docs/MORNING_KICKOFF_PROMPT.md` as a paste-able session-starter, and pinning the kickoff prompt in Slack `#mg-ai-reports`. Commits `1796a62` through `1779ee7`.

The goal: every future Claude session reads the same files in the same order at session start. No more pattern-matching on stale memory.

### Early afternoon: diagnosing the log pipeline

Bobby pointed out that the daily Claude training didn't seem to be seeing all the logs it should. Investigation revealed that only 7-9 miners were getting logs per day out of 48 online. Traced the code in `core/mining_guardian.py` and found the root cause: `collect_logs` was calling `collect_miner_logs` which only returns logs AMS had already exported — if AMS had nothing ready for a miner, the function silently returned `None` and moved on. For 34 of 48 miners, AMS had nothing ready, ever. Daily baseline was broken silently. No error, no warning.

Also discovered that `_wait_for_stable` (post-restart waiter) had hidden 10-minute and 45-minute caps on its two phases, which meant any miner taking longer than 55 minutes to return to mining state had its post-restart log silently skipped. Bobby had specifically said some miners take up to an hour — those were the miners whose post-restart comparisons were failing silently.

### The Edit A-E log collection fix (commit 95676b6)

Five edits shipped in one atomic commit:

- **Edit A:** `collect_logs` rewritten. Background daemon thread, single 24-hour interval for every online miner, calls `collect_fresh_miner_logs` instead of the existing-only path, removed the FLAGGED/HEALTHY split.
- **Edit B:** `collect_fresh_miner_logs` default cap removed. Signature changed from `max_wait_seconds: int = 90` to `Optional[int] = None`. Heartbeat every 5 minutes during long waits.
- **Edit C:** `_wait_for_stable` rewritten. PHASE1_MAX_WAIT and PHASE2_MAX_WAIT constants deleted. `REBOOT_POLL_SLOW` changed from 30 to 60 seconds per operator spec. Function now loops forever with exits only for stable mining, emergency state, or miner removed from AMS. Heartbeat every 10 minutes in both phases.
- **Edit D:** `pdu_power_cycle` off_delay 5 → 30 seconds. Operator spec: PSUs hold charge, need time to drain.
- **Edit E:** `_collect_logs_nonblocking` SIGALRM guard updated to skip the signal-based timeout for the fresh-log path, keeping it only for the cached-collection path.

All five committed as `95676b6` with full verification: compile check, grep confirming no leftover references to the deleted constants, cross-reference that `collect_logs` only calls `collect_fresh_miner_logs`.

### Edit F: the weekly training silent-skip (commit e90c2be)

While documenting the log collection fix, discovered a SECOND silent-skip bug. The dual-model Qwen+Claude pre/post restart comparisons produced by `_run_post_action_log_comparison` were being written to `knowledge['known_issues']` with miner_id prefix `compare:restart:*`. But the weekly Claude trainer `ai/train_cohort.py` only reads `knowledge['llm_scan_analyses']`. Two different arrays, no overlap. Result: 17 of the most valuable per-restart verdicts in the knowledge file (including the full April 8 AH3880 firmware regression investigation) were being silently ignored by Sunday's weekly training.

Fix: added a 61-line merge block in `train_cohort.py` right after the `llm_scan_analyses` load. Walks `known_issues`, finds `compare:*` entries, translates them into the `llm_scan_analyses` schema with a `[PRE/POST COMPARE | action | miner id | model]` tag prepended so Claude knows what it's reading, merges them into the analyses stream.

Dry-run verification: 17 entries found, prompt grows from 183 to 200 analyses. Tagged `TEMP_MAY_REMOVE` at both ends so the block is findable via `grep -rn 'TEMP_MAY_REMOVE' .` when the Mac mini migration happens.

This is where the **May Migration Changes** rule was captured in `CLAUDE.md`: the Sunday 3am Claude weekly training stays on forever, continues receiving daily logs + `llm_scan_analyses` + cohort + outlier + fleet synthesis unchanged. Only the `TEMP_MAY_REMOVE` restart comparison merge layer gets removed on May arrival, and ONLY because by then the local Qwen will have learned enough from the scan analyses alone that the separate comparison summaries won't add unique signal.

### The REPAIR_LOG.md decision

Mid-afternoon, Bobby proposed creating a dedicated "repair log" file — a running record of bugs found and fixes applied, written in plain English, so neither of us has to rediscover the same problem twice. Created `REPAIR_LOG.md` at the repo root with three starter entries (log collection, 49-vs-58 count confusion, the "Claude proposes alternatives to plans that already exist" failure mode). Wired it into the CLAUDE.md Session Kickoff Protocol as step 6, added to the Document Map table. Commit `d6c2871`.

Each REPAIR_LOG entry follows the same eight-section template: what Bobby thought was happening / what was actually happening / why it mattered / what we changed / what we deliberately didn't touch / how we verified / lesson / status. The template is at the bottom of the file.

### Late afternoon: the Daily Deep Dive

Bobby asked a critical question: "when do those logs go through the LLM and are they taking into account all the other variables we are collecting to analyze those logs at the same time?" The answer, after tracing the code end-to-end, was: the per-scan Qwen analysis runs every hour but it's a REACTIVE pulse — 1024 token output cap, 4-minute timeout, 30-minute full/quick throttle, only looks at current snapshot data (flagged miners, recent outcomes, 5 restart log excerpts with 500-char previews), not full daily logs, not 24-hour trends, not yesterday comparison. The "deep dive once a day" session that Bobby assumed was happening did not exist.

**What should have been happening:** once per day, after all daily logs are pulled, the local Qwen 32B on ROBS-PC sits down and does a long uninterrupted study session of the entire fleet. Every online miner gets individual attention with its full daily log + 24-hour trends + restart history + hardware identity. Then a fleet synthesis pass ties it all together with HVAC, weather, pool performance, operator rules, yesterday's deep dive. Store it in `knowledge.json`. Sunday Claude picks it up alongside everything else.

**Design decisions locked with Bobby:**
- Daily collection starts at **1pm local** (America/Chicago). Cron: `0 13 * * *`.
- Deep dive starts at **4pm local**. Cron: `0 16 * * *`. 3-hour buffer between collection and deep dive.
- Time-based cron, not event-driven signal — Bobby works on ROBS-PC occasionally and will know to be off during those windows.
- **No caps on Qwen.** `num_ctx: 32768` (Qwen's full quantized context window, verified via Ollama `/api/show`), `num_predict: -1` (unlimited output), `temperature: 0.3`, `requests timeout: 14400` (4 hours per call). ROBS-PC sits idle most of the day, compute is free.
- Sequential per-miner pass (48 miners) followed by one fleet synthesis pass. Expected runtime 2-4 hours. Bobby's explicit permission: "I don't care if it takes 4 hours."
- Sunday 3am Claude weekly training STAYS ON forever. The daily deep dive entries automatically get merged into the Sunday prompt via a new merge block in `train_cohort.py` (still pending as of this writing — tomorrow's first task).
- Manual trigger pattern for Claude ad-hoc runs. Sunday cron stays on, but Bobby can ask any day of the week to fire the Claude training ad-hoc on whatever data is in the knowledge file. Cost-driven decision: Bobby wants to reach Tier 3 ($400 cumulative API spend, currently at $8.85).
- **Bobby's Claude API Tier 2 limits (verified from console screenshot):** 1000 RPM, 450K ITPM, 90K OTPM, monthly $500 limit with $8.85 used so far. Sonnet 4.6 hard ceiling: 200K input tokens per request.

### Building `ai/daily_deep_dive.py` (953 lines)

Wrote the deep dive module in one pass. Two passes:

**Per-miner pass:** for every online miner in the latest scan, the script pulls the full daily baseline log (capped at 60KB for context window fit), yesterday's log for comparison (capped at 20KB), 24h per-board chain readings with min/max/avg stats, 24h hashrate/temp trends, 24h restart outcomes, 24h operator actions, 24h pool performance, permanent hardware identity from `miner_hardware`, fingerprint from `knowledge.json`, all operator rules. Qwen gets a 7-section analysis prompt: current state, 24h stability, log diff vs yesterday, restart analysis, cross-correlation hints, prediction, recommendation. No output cap. 4-hour timeout. Each per-miner result gets written to `daily_deep_dive_wip/{date}/miner_{id}.json` immediately for resume safety.

**Fleet synthesis pass:** after all per-miner analyses complete, Qwen gets one final prompt containing all 48 per-miner analysis excerpts (2KB each to fit context) + 24h HVAC trend + 24h weather + 24h fleet-level stats + operator rules + yesterday's deep dive for continuity + 9-section synthesis task (executive summary, fleet health, cohort patterns, outliers, day-over-day changes, environmental correlation, operator learning, tomorrow's focus, recommendations). No output cap. No timeout.

Results stored in `knowledge.json` under new top-level key `daily_deep_analyses`, keeping last 30 days.

**Schema verification caught 13 column-name mismatches before first run.** Before committing, I wrote a verification script that ran against the live `guardian.db` to confirm every table and column referenced in the data-gathering queries. Found: `temp_pcb` should be `temp_board`, `hashrate` should be `rate_mhs`, `frequency` should be `freq_mhz`, HVAC/weather tables use `recorded_at` not `scanned_at`, `chain_readings` has no `chip_count` column, `pool_readings` has no `stale` or `last_share` columns, `miner_restarts` has no `notes` column. Fixed all 13 before committing. If I had not verified against the real schema, the per-miner pass would have crashed on the first SQL query and we'd have wasted a whole Qwen run.

Committed as `da1edbd` with the 10-minute baseline cap fix (see next section) bundled in.

### The miner 53482 hang — production discovery

After deploying `da1edbd` and restarting the `mining-guardian` service, the new parallel collection thread fired on Scan #1377 at 16:23:22 CDT. I noticed in the logs that miner 53482 (at IP 192.168.188.46) was not advancing — the "fresh log export" heartbeat kept firing every 5 minutes: "still waiting for miner 53482 export at 302s / 604s / 906s / ..." and it had already accumulated 3322 seconds (55 minutes) of wait time from the original scan before the restart.

Root cause: AMS accepted the fresh-log-export trigger but was not producing the zip file. Something about miner 53482's state had AMS unable or unwilling to generate its log export.

Pulled miner 53482's latest readings from the DB: online, hashrate 110999 MH/s (target 133000 = running at 83.5%), chip temp 70°C (normal), firmware `BiXBiT 0.9.9.3-stage29.2799`, uptime 3 days 7 hours, **error codes `['412', '101']`**, `action: None`. So this is a real degraded miner — running 17% below its target profile with active error codes — that the regular scan logic was not flagging because 83.5% is above the hashrate threshold and chip temp is below the 84°C operator rule.

**This is exactly the kind of thing the deep dive pipeline was supposed to catch.** Ironic that the debugging effort needed to get the deep dive running is what surfaced the first real example of why the deep dive is needed. The hourly reactive scan had been ignoring miner 53482 for at least 3 days. A daily deep dive with full log content and 24h trend context would have caught this on day one.

Miner 53482 needs manual physical inspection. Flagged in REPAIR_LOG.md (commit `1dbbeb3`) under the "10-minute cap" entry so it doesn't get lost.

### The 10-minute cap decision

The bare fact: one broken miner hung the sequential daily sweep for 55+ minutes with the no-cap-rule from Edit B. Other 43 miners queued behind it, starving.

Discussed with Bobby. The "no caps" rule was correct for post-restart log pulls (only one miner at a time, critical data) but wrong for the sequential daily sweep where one broken miner can starve everyone else. Bobby's ruling: cap the daily baseline path at 10 minutes per miner. Rationale: "if it hasn't happened by 5 minutes it isn't going to happen, 10 minutes is generous double that." Post-restart path and `_wait_for_stable` stay uncapped.

Added `max_wait_seconds=600` to the `collect_fresh_miner_logs` call inside `collect_logs`. Bundled with the deep dive commit as `da1edbd`.

### The parallelism discovery

Bobby asked: "are we downloading other logs while we wait on the hang ups? I do not want to wait 10 minutes before moving on." Real question: tomorrow's 1pm cron will hit the same problem unless we parallelize — even with the 10-min cap, one stuck miner still burns 10 minutes of wall-clock time from the sequential thread.

Wrote a parallel version using `concurrent.futures.ThreadPoolExecutor` with 15 workers. Thread-safety analysis: `requests.Session` is thread-safe for concurrent POSTs, database writes use per-call sqlite3 connections with WAL mode, counters guarded by `threading.Lock`, `_ensure_token` forced to refresh before spawning the pool to avoid a race, 24h dedup check is read-only SQL. Each worker still has its own 10-minute cap inside `collect_fresh_miner_logs`.

Expected impact: sequential worst case 20-30+ minutes (with stuck miners) drops to 2-5 minutes typical / 10-12 minute max (if several miners hit the cap in parallel).

Shipped as `e5b9f5c`. Deployed to VPS. Scan #1378 (triggered by the loop after the service restart) spawned the new parallel sweep.

**Verification in real time:** while watching the logs, saw multiple miners completing within seconds of each other (53507 after 138s, 53516 after 143s, 53514 after 163s, 53520 after 189s) — clustered timing that sequential collection could never produce. 26 of 48 miners done by 16:46, 33 by 16:49. Steady progress, no AMS errors visible in the logs.

### The context compaction confusion

**Honest admission, captured for the record because it matters:** around 16:48 I checked the git log and found commit `e5b9f5c` that I didn't remember making. I had just finished thinking through a mental plan to add parallelism, was about to write the code, and found it was already committed and deployed. I initially couldn't explain it and asked Bobby whether another Claude session was running in parallel. He said no.

What actually happened: I wrote the parallel code earlier in this same session, committed it, deployed it — but a context compaction boundary crossed between writing it and checking it, so my current "recent memory" of the conversation didn't contain the direct record of writing it. When I reviewed the visible conversation and didn't see a "wrote parallel code" message, I incorrectly concluded I hadn't done it rather than considering that compaction could have dropped it from my visible context.

The commit itself was ironclad evidence: same author identity as all my other commits, landed on the local Mac between two commits I did remember making, commit message in my exact writing style with detailed thread-safety analysis I definitely wrote. The reflog entry confirmed it came from the local machine.

**Lesson:** when I find evidence of work in git that I don't remember doing, the first move should be to read the commit content carefully and accept it as my own work unless there's contradicting evidence, not to alarm the operator. Context compaction is a real thing and I need to account for it.

This is captured in REPAIR_LOG.md (the new entry written at end of session).

## What's Live at End of Session

**Deployed to VPS (running right now):**
- Parallel 15-worker daily baseline collection with 10-minute per-miner cap
- Background thread model with overlapping-thread guard
- Fresh-export path (`collect_fresh_miner_logs`) with optional cap parameter
- `_wait_for_stable` with no time caps, 60-second slow poll, heartbeat every 10 minutes
- `pdu_power_cycle` with 30-second off_delay
- Dual-model pre/post restart comparison merge into weekly Claude training stream
- `ai/daily_deep_dive.py` deployed but NOT YET EXECUTED (waiting for today's daily collection to complete)

**Code state on main branch (not yet activated by cron):**
- `ai/daily_deep_dive.py` ready for manual invocation `python3 ai/daily_deep_dive.py --manual`

**NOT yet shipped (tomorrow's first task):**
- Merge block in `ai/train_cohort.py` to pull `daily_deep_analyses` into the Sunday Claude weekly training stream (I wrote `.apply_dd_merge.py` earlier but never ran it in a safe way — will verify and ship tomorrow)
- Cron entries for `0 13 * * *` daily collection and `0 16 * * *` daily deep dive

## What's Known Broken / Needs Attention

1. **Miner 53482 at 192.168.188.46:** Online, running 83.5% of target, error codes 412 + 101, firmware `BiXBiT 0.9.9.3-stage29.2799`, AMS log export hung. Needs physical inspection. Not currently flagged by hourly scan logic.
2. **The daily_deep_analyses merge into weekly Claude training:** still pending. The deep dive results will be stored correctly in `knowledge.json` but Sunday's Claude run won't see them until the merge block ships.
3. **Cron entries not yet added.** Both `0 13 * * *` and `0 16 * * *` need to be appended to root's crontab on the VPS before tomorrow 1pm if we want automatic operation to start tomorrow.
4. **Sequential `.bak` files and apply scripts in working tree** — harmless but clutter (`core/mining_guardian.py.bak.20260409-141051`, `.apply_dd_merge.py`). Can be deleted in next session.

## Operator Rules Locked In Today

- **Temperature:** Do not flag or warn about chip temps below 84°C. Fleet is liquid-cooled; 67-80°C is normal. Only ≥84°C warrants concern.
- **HVAC:** USA 188 HVAC is performing correctly. Low supply/return delta-T is intentional and will rise with outside temp. Do not recommend checking HVAC based on delta-T.
- **PDU off_delay:** 30 seconds minimum. PSUs hold charge.
- **10-minute cap** on daily baseline log collection path only. Post-restart and `_wait_for_stable` paths remain uncapped.
- **Sunday 3am Claude weekly training** stays on automatic forever, receiving daily logs + llm_scan_analyses + cohort analyses + outlier analyses + operator rules + cross-miner correlations + fleet synthesis. Unchanged after May arrival.
- **May Migration Changes:** ONLY the `TEMP_MAY_REMOVE` restart comparison merge block gets removed on Mac mini arrival. Everything else about the Sunday training stays on.
- **Daily deep dive:** permanent. The daily Qwen deep dive runs forever, its output is stored in `knowledge.json` under `daily_deep_analyses`, and the weekly Claude training reads it via a PERMANENT merge block (not TEMP_MAY_REMOVE).
- **Manual Claude runs:** ad-hoc any day Bobby asks. Sunday cron stays on. Cost-driven cadence.
- **"Document as you go, not after."** Every session that adds a feature or makes a design decision MUST update the relevant docs in the same commit as the code. No more deferred documentation. Added to CLAUDE.md.

## Numbers from Today

- **Commits shipped:** 16 total, 9 in the afternoon log pipeline sprint
- **Lines of new code written:** ~1,100 (mostly in `ai/daily_deep_dive.py` at 953 lines)
- **Silent-skip bugs fixed:** 2 (daily log collection, weekly training merge)
- **Schema mismatches caught before production:** 13
- **Degraded miners surfaced that were not being flagged:** 1 (miner 53482)
- **Time caps removed from the log collection pipeline:** 4 (PHASE1_MAX_WAIT, PHASE2_MAX_WAIT, collect_fresh_miner_logs default, SIGALRM on fresh path)
- **Time cap added (to prevent starvation):** 1 (10-minute per-miner cap on daily baseline path)
- **Commits between my last-remembered one and the one that caused the context confusion:** 1
- **Expected daily Claude weekly prompt growth from today's merge fix alone:** 183 → 200 analyses (+9.3%)

## What Tomorrow Should Do

1. **First thing:** run the REPAIR_LOG update for this session log + the degradation discovery on miner 53482. Update status of the 10-minute cap entry from "in progress" to "shipped."
2. **Ship the `daily_deep_analyses` merge block** in `ai/train_cohort.py`. Verify against the live knowledge file on the VPS before committing. Same pattern as the `TEMP_MAY_REMOVE` merge but PERMANENT (not wrapped in temp markers because per operator rule the daily deep dive stays forever).
3. **Add cron entries to the VPS:**
   - `0 13 * * * cd /root/Mining-Gaurdian && /root/Mining-Gaurdian/venv/bin/python3 -c "from core.mining_guardian import MiningGuardian; g = MiningGuardian.from_config(); g._trigger_daily_collection_now()"` (or a simpler scheduler — the exact command needs a small helper added to `mining_guardian.py` to force daily collection outside the hourly loop)
   - `0 16 * * * cd /root/Mining-Gaurdian && /root/Mining-Gaurdian/venv/bin/python3 ai/daily_deep_dive.py >> /tmp/daily_deep_dive.log 2>&1`
4. **Verify yesterday's (today's) first manual deep dive ran successfully** and `knowledge.json` now has a `daily_deep_analyses[0]` entry.
5. **Fire the first manual Claude run** per Bobby's instruction. Bobby will say "go." Use the existing `train_cohort.py` with the new merge block live. Verify the input token count per call, log the cost estimate, run it.
6. **Physically inspect miner 53482** or create an AMS ticket. Capture what's actually wrong with it so the finding is preserved.
7. **Delete the leftover files in working tree:** `core/mining_guardian.py.bak.20260409-141051`, `.apply_dd_merge.py` if still present.

---

*End of session log for April 9, 2026.*
