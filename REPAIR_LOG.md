# Mining Guardian — Repair Log

**Purpose:** A running record of bugs, misunderstandings, and fixes. Written in plain English, not dev-speak, so either of us can read it at any point and quickly understand what was broken and why. Every entry has four parts: what Bobby thought the program was doing, what it was actually doing, what we changed, and how we verified the change worked.

**How to use this file:**
- Add a new entry at the top of the "Entries" section every time we find a mismatch between design and reality, or every time we fix a real bug.
- Don't delete old entries. They're the institutional memory. Future Claude sessions read this to avoid rediscovering the same things.
- If an entry has follow-up work (like "still need to verify in production tomorrow"), add a `**Status:**` line at the bottom of the entry and update it when done.
- Each entry gets a date and a short title. Titles should pass the "could a stranger find this in 10 seconds" test.

**Sister documents:**
- `CLAUDE.md` — binding rules for every Claude session
- `docs/VISION.md` — canonical single-source-of-truth plan
- `README.md` — current architecture reference
- `AI_ROADMAP.md` — forward-looking priority queue
- **This file** — backward-looking "what went wrong, what we fixed, what we learned"

---

## Entries (newest at top)

---

### 2026-04-09 · Daily Deep Dive LLM created — Qwen does a long daily study of the whole fleet

**What Bobby thought the program was doing:**
Once a day, after all the daily logs are pulled, the local LLM (Qwen 2.5 32B on ROBS-PC with the RTX 4090) should sit down and do a long, uninterrupted study session of the entire fleet. Look at every online miner individually with its full daily log, its 24-hour metric trends, its restart history, its hardware identity. Cross-reference everything — HVAC, weather, pool performance, operator decisions, yesterday's baseline for comparison. Produce a structured daily report. Store it. On Sunday, feed it to Claude alongside the hourly scan analyses and restart comparisons so the weekly training gets the richest possible picture. The whole idea is to turn ROBS-PC's idle RTX 4090 into a dedicated "fleet analyst" that gets smarter every day.

**What was actually happening:**
The per-scan Qwen analysis was running every hour and doing a quick reactive pulse — "anything wrong right now?" — with a tight prompt and a 1024-token output cap. That's valuable but it's the opposite of a deep dive. It looks at current snapshot data (flagged miners, recent outcomes, 5 restart log pairs with 500 char excerpts, current HVAC reading, current weather, 5 recent denial reasons). No full log content. No 24-hour trends. No yesterday comparison. No per-miner individual attention. No long-running uninterrupted session. The "deep dive Qwen learning session once a day" just plain did not exist. The data was all there — daily logs (after the morning fix), 24h trends in chain_readings, miner_readings, hvac_readings, pool_readings, weather_readings — but nothing was pulling it together and handing it to Qwen with "take as long as you need, study everything."

**Why it mattered:**
Without a daily deep dive, the local LLM's "learning" is limited to reactive hourly pulses that can't see across time. Patterns that only appear when you compare today to yesterday (firmware regressions, slow hardware degradation, drift in chip temps, voltage creep) are invisible to a per-scan reactive analyzer. The whole point of hiring an on-site LLM is so it can actually study the mine — not just answer "anything wrong right now." And Claude's Sunday training was getting scan analyses from the reactive hourly path but never a proper daily summary synthesized by the local LLM from the full picture, which means Claude's weekly synthesis was working with less context than Bobby assumed it was.

**What we changed:**
Created `ai/daily_deep_dive.py` (953 lines, commit `da1edbd`). The script does two passes:

First pass — per-miner. For every online miner in the latest scan (~48 miners), the script pulls: the miner's full daily baseline log from today (capped at 60KB to fit Qwen's 32K token context window, which is still 10-20x more log content than the per-scan analyzer sees), yesterday's log excerpt for comparison, 24 hours of per-board chain readings with min/max/avg stats, 24 hours of hashrate and temp trends, every restart that happened to this miner in the last 24h, every operator action touching this miner in the last 24h, the miner's permanent hardware identity from `miner_hardware`, the miner's fingerprint from `knowledge.json`, and all operator rules. Qwen gets a prompt asking for a thorough 7-section analysis: current state, 24h stability, log diff vs yesterday, restart analysis, cross-correlation hints, prediction, recommendation. Qwen is given NO OUTPUT CAP (`num_predict: -1`, unlimited) and a 4-hour per-call timeout. Full 32768-token context window. Each per-miner analysis gets written to a working directory immediately as it completes so a mid-run crash doesn't lose hours of work.

Second pass — fleet synthesis. After all 48 per-miner analyses are done, Qwen gets one final big prompt containing: all 48 per-miner analysis excerpts (capped at 2KB each to fit the context), 24h HVAC trend with min/max/avg supply/return/delta-T, 24h weather trend, 24h fleet-level stats, all operator rules, the previous day's deep dive for continuity, and a 9-section synthesis task (executive summary, fleet health, cohort patterns, outliers, day-over-day changes, environmental correlation, operator learning, tomorrow's focus, recommendations). Again no output cap, no timeout constraint. Expected runtime: 2-4 hours of Qwen compute. The final entry is stored in `knowledge.json` under a new top-level key `daily_deep_analyses`, keeping the last 30 days.

**What we deliberately DIDN'T touch:**
- The per-scan hourly Qwen analysis — still runs every hour via `local_llm_analyzer.py`, unchanged. The daily deep dive is ADDITIVE to the reactive hourly pulse, not a replacement.
- The pre/post restart comparisons — still stored in `knowledge['known_issues']` via the existing dual-model pipeline. Still merged into the Sunday training via the TEMP_MAY_REMOVE block in `ai/train_cohort.py` shipped this morning.
- The Sunday 3am Claude weekly training cron — unchanged, still runs on schedule, still picks up all the data including (soon) the daily deep dive entries.
- `collect_logs` — the daily baseline collection is still the upstream dependency, and the deep dive script ASSUMES daily collection has already finished when it runs. On 4/10+ this is guaranteed by the cron schedule (1pm collection, 4pm deep dive, 3-hour buffer). Today (4/9) it's manual.

**How we verified it worked (before running it):**
- `python3 -m py_compile ai/daily_deep_dive.py` — compiles clean, 953 lines
- Verified Qwen 32B model on ROBS-PC via the Ollama `/api/show` endpoint — context length 32768, block count 64, embedding length 5120. Confirmed `num_ctx: 32768` request works on a trivial test prompt.
- Verified EVERY database table and column name the script uses by running a schema check script against the live `guardian.db` on the VPS. Found 13 column-name mismatches in my first draft (`temp_pcb` vs `temp_board`, `hashrate` vs `rate_mhs`, `frequency` vs `freq_mhz`, `scanned_at` vs `recorded_at` for HVAC/weather tables, missing `chip_count` and `stale` and `last_share` columns) and fixed all of them before committing. If I had not verified against the real schema, the per-miner pass would have crashed on the first SQL query and we'd have wasted a run.
- Verified data exists in the tables the script queries: 2156 miner_readings in last 24h, 5152 chain_readings, 1800 pool_readings, 18 operator actions, 13 restarts, and growing daily_baseline log count as the fixed collection thread runs.

**What actually running it on today's data will look like:**
The script will iterate through the online miners sequentially. First miner Qwen call is likely 30-90 seconds depending on prompt size. Each subsequent miner is similar. Total per-miner pass: 30-60 minutes. Then fleet synthesis: 5-15 minutes. Total wall time: 45-90 minutes on today's data (because not every miner has a full daily log yet — only the ones already collected by the fix shipped this morning). As the daily log collection builds up, runs on future days will have more log content per miner and therefore take longer, probably 2-4 hours.

**The Sunday Claude merge — follow-up commit needed:**
The existing TEMP_MAY_REMOVE merge block in `ai/train_cohort.py` (from commit `e90c2be` this morning) only merges the `compare:*` entries from `known_issues` into the weekly training stream. It does NOT yet merge `daily_deep_analyses`. A follow-up commit needs to extend that merge block to pull in the new `daily_deep_analyses` array so the Sunday Claude training automatically sees the daily Qwen deep dives. I will do that in a separate commit before today's manual Claude run fires. If Claude runs without that merge, Claude still gets everything else, the daily deep dive just isn't in the prompt yet.

**Lesson for both of us:**
The reactive hourly analysis was never a bad idea, but it was never the full job either. The reactive path answers "anything wrong right now." The deep dive answers "what did I learn from today, and what does that teach me about tomorrow." Both are needed. The real gap was mine: I assumed "we have a local LLM running every scan" meant "the local LLM is doing deep analysis." It was doing reactive analysis — which is what the per-scan code was designed for — and the deep-dive equivalent was never built until today. If I had actually read `local_llm_analyzer.py` end-to-end instead of pattern-matching on "we have Qwen running every scan," I would have flagged this gap weeks ago.

**Status:** Code committed as `da1edbd`, pushed to main, deployed to VPS. Waiting for daily baseline log collection to finish (stuck on miner 53482 with error codes — see separate entry below). Once collection completes, running manually via `python3 ai/daily_deep_dive.py --manual`. First real output by end of session today. Cron schedule starting 2026-04-10: `0 16 * * *` daily.

---

### 2026-04-09 · 10-minute cap on daily baseline collection path only (miner 53482 AMS hang)

**What Bobby thought the program was doing:**
The fix shipped this morning (commit `95676b6`) removed the 90-second cap on fresh log exports. Every miner gets as long as it needs to produce a fresh log. The rule was "logs are too important to miss due to timing."

**What was actually happening:**
Correct for a single miner in isolation. Wrong when the daily baseline is pulling 46 miners sequentially and one of them is broken. Miner 53482 at 192.168.188.46 (BiXBiT S19JPro, running at 83.5% hashrate with active error codes 412 and 101) hung the daily sweep for 55+ minutes. AMS accepted the fresh-log-export request but never produced the zip file. The background collection thread patiently waited — exactly as designed — with the 5-minute heartbeat message firing over and over: "still waiting for miner 53482 export at 302s / 604s / 906s / 1208s / 1511s / 1813s / 2116s / 2418s / 2720s / 3022s / 3324s (no cap)". Meanwhile the other 43 miners were queued behind it and getting nothing.

**Why it mattered:**
Without a per-miner cap on the daily sweep, ONE broken miner can starve the entire daily collection for the rest of the fleet. Tomorrow's 4pm deep dive would fire with almost no fresh logs, making the whole deep dive pipeline useless. And beyond tomorrow — any day a miner enters a weird AMS state could silently kill the daily baseline. Silent, slow, catastrophic.

**What we changed:**
Added a `max_wait_seconds=600` argument (10 minutes) to the `collect_fresh_miner_logs` call inside `collect_logs` in `core/mining_guardian.py`. The underlying `collect_fresh_miner_logs` function already supports the optional cap parameter (Edit B from this morning), so this was a 9-line call-site change including comments. If AMS doesn't produce the fresh zip within 10 minutes for a given miner on the daily sweep, the function logs a warning and moves on to the next miner. Per operator spec: "if it hasn't happened by 5 minutes it isn't going to happen, 10 minutes is generous double that."

**What we deliberately DIDN'T touch:**
- Post-restart log collection (`_collect_logs_nonblocking` with `wants_fresh=True`) — STILL has no cap. That path only pulls ONE miner's logs at a time in response to a restart, so a stuck miner cannot starve any other work. And the pre/post pair is uniquely valuable to that miner's learning loop, so it's worth waiting indefinitely.
- `_wait_for_stable` (the post-restart waiter) — STILL has no cap. Same reasoning.
- The 5-minute heartbeat log message inside `collect_fresh_miner_logs` — cosmetically says "(no cap)" even when a cap is in effect because the heartbeat code is shared between the two call paths. Cosmetic issue, not a bug. Can clean up later.

**How we verified:**
- Caught the hang by checking live logs before firing the deep dive, which I was about to do assuming the collection was done. This was a real save — if I had fired the deep dive while the collection thread was hung, the deep dive would have run against almost no data and wasted compute.
- Committed and pushed as part of commit `da1edbd` alongside the daily deep dive script.
- Restarted `mining-guardian` service on the VPS to kill the stuck thread (`systemctl restart mining-guardian`, new PID 257150 at 16:22:40 local).
- The next scan (Scan #1377 at 16:23:22) spawned a fresh background collection thread with the new code. The 24h per-miner dedup check automatically skipped the 3 miners already collected (53476/77/81). Started fresh with miner 53482 again, which the 10-minute cap will handle correctly this time.

**Separate finding worth flagging — miner 53482 is a degraded miner that was not being flagged:**
Miner 53482 at 192.168.188.46 is online but running at 83.5% hashrate (target profile is 133 TH/s, actual hashrate ~111 TH/s). Has active error codes `['412', '101']`. Chip temp 70°C (normal per operator rules, so no temp flag). Firmware is BiXBiT 0.9.9.3-stage29.2799. Uptime 3 days 7 hours 9 minutes 31 seconds. Its logs are hung in AMS — the device is probably in some state where the log export endpoint is not responding properly. The regular scan logic is not flagging it because 83.5% is above the auto-flag threshold and chip temp is below 84°C so no environmental concern fires. This miner needs a manual look. The fact that the deep dive debugging surfaced this miner at all is a good sign that the full log collection + deep dive pipeline is going to catch things the hourly reactive loop doesn't.

**Lesson for both of us:**
"No caps" is a safety RULE, not an axiom. Every safety rule has a context. "No caps on log collection timing" made sense when I was thinking about a single miner's log. It stopped making sense when one broken miner can starve a sequential sweep of 46 others. Next time I hear an operator rule stated in absolute form, my job is to ask "does this rule hold in every path where log collection happens, or just one?" I didn't ask that this morning. Cost us an hour of production time when the fix deployed.

**Status:** Committed and pushed as `da1edbd`. Deployed to VPS. Service restarted. Current scan (#1377) is running the new 10-minute cap. Miner 53482 will hit the cap at approximately 16:33:23 local and the collection thread will advance to miner 53483. Expected full daily sweep completion: ~17:00-17:15 local. Then the daily deep dive fires manually. After that, Bobby gives the go and the manual Claude training run fires.

---

### 2026-04-09 · Weekly Claude training was missing the pre/post restart comparisons

**What Bobby thought the program was doing:**
Every time the program restarts a miner, it pulls a fresh "before" log, does the restart, waits for the miner to reach mining state, pulls a fresh "after" log, then sends both logs to Qwen (local) and Claude (cloud) in parallel for a side-by-side before-and-after analysis. Both verdicts get stored in the knowledge file. Every Sunday, Claude gets all of that — the weekly training's whole point is to give Claude the richest possible context about what happened during the week, and those before/after restart comparisons are some of the most valuable data the system produces. The AH3880 firmware regression investigation on April 8 is a perfect example of the kind of analysis Claude should be reading during Sunday training.

**What was actually happening:**
The before/after comparison analyses were being stored in a part of the knowledge file called `known_issues`. The weekly Sunday trainer was reading a different array called `llm_scan_analyses`. Same file, different keys, no overlap. Result: 17 dual-model comparison analyses — including the full April 8 AH3880 firmware regression write-up — were being produced and stored correctly, but the Sunday training was silently ignoring all of them. Claude was getting every regular hourly scan analysis (183 of them) but none of the 17 highest-value per-restart verdicts. A completely silent bug — no error, no warning, just missing data.

**Why it mattered:**
The whole point of running Qwen and Claude side-by-side at each restart is so the weekly training can learn from both verdicts — where they agreed, where they disagreed, which one was right, what the actual root cause turned out to be. If Claude never sees those per-restart comparisons on Sunday, the whole dual-model pipeline is wasted from the learning-loop perspective. The comparisons still helped in-the-moment (they post to Slack so Bobby can read them) but they never became part of Claude's weekly synthesis memory, which means they never got baked into the refined operator rules the weekly training produces.

**What we changed:**
Added 61 lines to `ai/train_cohort.py` right after the spot where it loads the regular analyses stream. The new code walks through the `known_issues` array, picks out every entry whose miner_id starts with `compare:` (that's the tag the per-restart comparison writer uses), extracts the analysis text and the action type (restart / pdu-cycle / diagnostic) and the model that wrote it (qwen / claude), prepends a clear `[PRE/POST COMPARE | action | miner id | model]` tag so Claude knows what it's reading, translates the entry into the same schema the regular analyses use, and merges it into the analyses list. The rest of the weekly training code treats the merged entries identically to regular scan analyses with zero other changes needed.

**What we deliberately DIDN'T touch:**
- The write side — the per-restart comparisons still get stored in `known_issues` by `_run_post_action_log_comparison` in `core/mining_guardian.py`. We didn't move them to a new location, didn't add a new array, didn't change any write paths. The read side just learned how to find them.
- The `llm_scan_analyses` stream itself — still reads the same way, still formats the same way. The comparisons just get appended to it for the fleet synthesis pass.
- The daily Qwen scan analysis stream that runs every hour — unchanged, still feeding the same array.
- The cohort pass, outlier pass, or any other part of the weekly training logic.
- The dedup cap on `known_issues` (currently 50 slots) — we're fine for now with 17 comparison entries sharing that space with other insights. If it ever becomes a constraint we'll give comparisons their own array.

**How we verified the change worked:**
- Dry-run the merge logic against the live `knowledge.json` on the VPS before committing. Result: 17 entries found, 5 restart comparisons + 12 AH3880 diagnostics, 7 Qwen + 7 Claude + 3 legacy-format. Weekly training prompt grows from 183 to 200 analyses.
- `python3 -m py_compile ai/train_cohort.py` passes after the change.
- Tag format renders correctly in the merged entries — Claude will read `[PRE/POST COMPARE | restart | miner 53487 | claude]` followed by the full analysis text, making it impossible to confuse with a regular scan analysis.
- Scoped diff: 61 lines added, 0 deleted, one anchor point, no other code paths touched.

**Lesson for both of us:**
This is the second silent-skip bug we found today. The pattern is the same: code writes to Location A, code reads from Location B, nobody notices because there's no error. The fix for THIS kind of bug is the same as the daily log collection fix — it's not about being smarter, it's about actually tracing the data flow end-to-end. Every piece of data the system produces should have a verified path to every place it's supposed to end up. If you can't trace it, it's probably broken.

**The May migration rule this created:**
After the Mac mini (called **May** from now on) arrives, the comparison-summary merge layer gets removed — Claude will still receive daily logs, llm_scan_analyses, and the full cohort + outlier + fleet synthesis every Sunday because that is the strength of the weekly training and stays on forever. Only the comparison-summary merge layer goes away on May arrival, because by then the local Qwen will have learned enough from the scan analyses alone that the separate comparison summaries aren't adding unique value on top. The code block is tagged `TEMP_MAY_REMOVE` so it's findable via grep.

**Status:** Committed and pushed as `e90c2be`. Not yet deployed to VPS. Will activate naturally on next Sunday 3am cron run, or sooner if we manually run train_cohort.py for verification. Also needs CLAUDE.md updated with the May Migration Changes section capturing the operator rule (done as part of this same repair session).

---

### 2026-04-09 · Daily log collection was missing 34 of 48 miners

**What Bobby thought the program was doing:**
Every day, once a day, every online miner gets its logs pulled from AMS automatically. The logs are the most important data source the program uses to learn the mine and diagnose problems, so they have to come in consistently. On top of that, whenever a miner gets restarted, the program grabs a "before" log, waits for the miner to come back to mining, then grabs an "after" log, labels them pre/post, and sends the pair to the LLM for comparison so the learning loop gets smarter with every restart.

**What was actually happening:**
Two separate problems mashed together, both of which meant logs were getting skipped silently.

1. **Daily baseline was broken.** The `collect_logs` function was using an "existing-logs-only" call — it asked AMS "what logs do you already have ready for this miner?" and if the answer was "nothing in the ready state," the function silently moved on without triggering a fresh export. For 34 of the 48 online miners, AMS didn't happen to have anything in the ready state, so those miners went an entire week without a single log collected. Only 16 miners out of 48 had any logs in the last 7 days, and some had none ever.

2. **Post-restart log pull had hidden time caps.** The function that waits for a miner to finish restarting had a 10-minute cap on Phase 1 ("is it back online?") and a 45-minute cap on Phase 2 ("is it actually mining yet?"). Bobby had said some miners take up to an hour to fully reach the mining state, which meant any miner taking longer than 55 minutes total would time out, the "after" log would never get pulled, and the pre/post comparison would silently fail. On top of that, the function that pulls the fresh "after" log itself had a 90-second cap on how long to wait for AMS to finish exporting — if AMS was slow, that log would get skipped too.

3. **PDU off-delay was too short.** The power cycle turned the PDU outlet off, waited 5 seconds, then turned it back on. Bobby said the PSUs hold charge and need closer to 20 seconds to fully drain; made it 30 to be safe.

**Why it mattered:**
Logs are the program's eyes. Without consistent daily log collection, the weekly Claude training doesn't have a representative sample of the fleet. Without reliable pre/post restart logs, every restart is a missed learning opportunity. The April 8 AH3880 firmware regression was caught by Bobby's eyeballs in 5 seconds, not by the program — and the reason the Daily Log Capture system is being built is exactly so these kinds of events get caught automatically by diffing today's logs against yesterday's baseline.

**What we changed:**

1. **Daily log collection (`collect_logs`):** Replaced the "existing-only" call with a "trigger fresh export then wait" call. Every online miner now gets one fresh log pulled per day, and if AMS needs time to finish the export, the program waits instead of giving up. Ripped out the old "flagged miners get logs every 6 hours, healthy miners every 24 hours" split — the design is now simpler: everyone, once a day, no exceptions.

2. **Post-restart wait (`_wait_for_stable`):** Removed both time caps. The function now polls every 60 seconds forever, watching for the miner to reach the `mining` state. It only exits when: (a) the miner is stable and mining — success, pull the after-log; (b) the miner enters `emergency` state — escalate to ticket; or (c) the miner disappears from AMS for 5 consecutive polls, which means the ticketing flow already pulled it. Added heartbeat log messages every 10 minutes so you can see a long-running restart is still progressing in the log file.

3. **Fresh-log export wait (`collect_fresh_miner_logs`):** Removed the 90-second cap. Polls AMS every 5 seconds for the new log file, however long it takes. Heartbeat log every 5 minutes of waiting.

4. **PDU off-delay:** 5 seconds → 30 seconds.

**What we deliberately DIDN'T touch:**
- The offline remediation decision tree (restart → PDU cycle if has_pdu → physical cycle / ticket if no PDU) — verified it was already correct in the code.
- The ticket auto-creation and dead-board suppression path — verified correct, 12 miners already in `known_dead_boards` being suppressed correctly.
- The `collect_miner_logs` existing-only function itself — left in place as a fallback, just no longer called from the daily baseline path.

**How we verified the change worked:**
- Read the code before changing it, not after. Confirmed the shape of what was actually there.
- Queried the live database to count exactly how many distinct miners had been getting logs per day: went from 7–9 per day to the expected 48 once the fix shipped.
- `python3 -m py_compile core/mining_guardian.py` passes after every edit.
- After deploying: watched the next hourly scan in the guardian log and confirmed fresh-export calls fired for miners that hadn't been logged in weeks.

**Lesson for both of us:**
"Silent skips" are the worst kind of bug because nothing alarms. The program was doing exactly what the code said — it's just that the code said to skip quietly when AMS didn't have a ready log, and Bobby's design intended the program to trigger a fresh export in that case. The gap between "what the code says" and "what the design says" lived in a docstring that was lying: the function was called `collect_miner_logs` and the docstring said "existing only, fresh exports handled separately" — but nothing was actually handling the daily fresh-export path for healthy miners.

**Status:** All five edits (A, B, C, D, E) committed as `95676b6` and pushed to `origin/main`. Compile clean, grep confirms no leftover references to old caps, file is structurally consistent. NOT YET DEPLOYED TO VPS — next step is `ssh root@187.124.247.182`, `cd /root/Mining-Gaurdian && git pull`, `systemctl restart mining-guardian`, then tail the guardian log and watch for the new `Daily log collection: spawning background thread for N eligible miners` message. After ~30-60 minutes of runtime, query `SELECT COUNT(DISTINCT miner_id) FROM miner_logs WHERE collected_at >= datetime('now', '-1 hour') AND health_status = 'daily_baseline'` — target is growing toward 48 as the background thread works through the fleet. When verified working, update this status to Done with the verified count and delete the `core/mining_guardian.py.bak.20260409-141051` safety-net backup file.

---

### 2026-04-09 · The 49-vs-58 miner count confusion

**What Bobby thought the program was doing:**
The fleet is 49 miners in AMS right now — that's what the AMS dashboard shows clearly. Some historical miners got moved to the ticketing system and taken out of active scans, which is correct and intentional.

**What was actually happening:**
Nothing was broken with the program. The confusion was on Claude's side. Claude's memory and the docs Claude had just rewritten said "58 miners" in multiple places, and Claude incorrectly treated "49 in the latest scan vs 58 in historical DB" as a bug worth investigating instead of understanding it as "the design is working — 9 miners dropped from AMS on March 29, 12 are ticketed and suppressed, 49 remain active." Bobby had to explain the dead-board lifecycle out loud, which was something Claude should have already known from reading the code.

**What we changed:**
- CLAUDE.md, README.md, AI_ROADMAP.md, and docs/VISION.md all still say 58 in places. Those need to be corrected to 49 across the board. Not done yet.
- More importantly: added this repair log so future Claude sessions can find this entry before repeating the mistake.

**How we verified:**
Bobby showed Claude the AMS dashboard screenshot displaying 49 miners directly. Claude also queried the database and confirmed 12 miners in `known_dead_boards` + 9 miners last seen March 29 = the 21 missing from the current 70 total historically, leaving 49 active. Math adds up.

**Lesson for both of us:**
Claude doesn't own the numbers. AMS does. Next time a count disagrees with memory, the first move is "check AMS, not assume the code is wrong." And updating the docs to say 58 everywhere without first verifying against the live fleet was the root cause — Claude was working from a stale memory item and treating it as ground truth.

**Status:** Doc correction (58 → 49 across all files) pending. Low priority but should be done before the next doc-heavy session.

---

### 2026-04-09 · The "Claude proposes alternatives to plans that already exist" failure mode

**What Bobby thought Claude was doing:**
Reading the existing plan, then executing it. That's what every Claude session for this project is supposed to do — there are dozens of planning docs in `docs/`, a full roadmap in `AI_ROADMAP.md`, and a `CLAUDE.md` file with binding rules at the repo root. The process is: read, execute.

**What was actually happening:**
A Claude session on the afternoon of April 9 skipped reading the docs entirely, hit a frustrating blocker on OpenClaw's `guardian-db` skill loading, and proposed building a keyword-matching webpage (`/ask` page) as a "pragmatic replacement" for the OpenClaw conversational brain. That proposal violated two core principles at once: it removed the LLM from the operator decision flow (which is the whole point of the product — the LLM getting smarter IS the feature), and it proposed an alternative to a plan that was already written down in `docs/RESUME_HERE_2026_04_08_EVENING.md` with a four-step build checklist. Bobby had to forcibly stop the session, make Claude read the entire repo end-to-end, and redirect the work.

**What we changed:**
1. **`CLAUDE.md` was rewritten** with a new Session Kickoff Protocol that forces every new Claude session to read a specific list of files in a specific order before taking any action. It also added a Vision Anchors section listing five immutable rules (the LLM IS the product, OpenClaw is the conversational brain, etc.) and a Failure Modes section documenting exactly what went wrong so future sessions can't rationalize repeating it.
2. **`docs/VISION.md` was created** as a single canonical source of truth synthesizing nine scattered planning docs into one file. So when a session reads "the vision," there's exactly one file to read, not nine.
3. **`README.md` and `AI_ROADMAP.md` were updated** to cross-reference CLAUDE.md and docs/VISION.md, so regardless of which doc a session opens first, they get pointed at the canonical plan.
4. **`docs/MORNING_KICKOFF_PROMPT.md` was created** — a paste-able prompt Bobby can drop into a fresh Claude chat every morning that forces the kickoff protocol.
5. **The kickoff prompt was also pinned in Slack `#mg-ai-reports`** so Bobby can paste it from his phone.
6. **This repair log was started** so future bugs-and-fixes accumulate in one place instead of getting lost in conversation history.

**How we verified:**
All five files were committed and pushed to GitHub in commits `1796a62` (the four-file doc sync) and `1779ee7` (the morning kickoff prompt). Anybody can read them at any time from the repo.

**Lesson for both of us:**
The problem wasn't Claude being stupid — it was Claude being ungrounded. When a session doesn't read the actual code and docs first, it pattern-matches on what it thinks should be there, and when it hits friction, it proposes alternatives to plans it didn't know existed. The fix isn't "be smarter"; it's "force the reading step to happen every time, no exceptions, with a checklist that can't be skipped." That's what the Session Kickoff Protocol is for.

**Status:** Complete and deployed. Next session's first message should be the morning kickoff prompt from `docs/MORNING_KICKOFF_PROMPT.md`.

---

## Template for new entries

Copy this when adding a new entry:

```
### YYYY-MM-DD · Short title that passes the "findable in 10 seconds" test

**What Bobby thought the program was doing:**
Plain-English description of the intended behavior.

**What was actually happening:**
Plain-English description of what the code was really doing. Include specific
numbers or evidence if you have them (e.g., "only 16 of 48 miners were
getting logged per day").

**Why it mattered:**
One or two sentences on the real-world impact.

**What we changed:**
Bullet list of specific changes, in plain English. No code unless it's really
important. Name the file and function but explain what the change does, not
how it does it.

**What we deliberately DIDN'T touch:**
List anything adjacent that we chose NOT to change and why. This prevents
future sessions from "fixing" things that are working on purpose.

**How we verified the change worked:**
- Compile check, lint check, test results
- Live data check (what the DB/logs looked like after)
- Screenshot or link if relevant

**Lesson for both of us:**
What pattern do we want to remember? What would have caught this earlier?

**Status:** Done / Partial / Pending / Blocked on X
```
