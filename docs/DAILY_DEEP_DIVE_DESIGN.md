# Daily Deep Dive — Design Doc

**File:** `ai/daily_deep_dive.py`
**Created:** April 9, 2026 (commit `da1edbd`)
**Status:** Code deployed to VPS, cron not yet active, first manual run pending (awaiting completion of today's daily log sweep)
**Author:** Mining Guardian afternoon log pipeline sprint

## Purpose

Once per day, the local Qwen 32B LLM on ROBS-PC (RTX 4090) performs a long, uninterrupted study session of the entire fleet. Per-miner individual analyses + fleet-wide synthesis. This is the "sit down and actually study the mine" pass that complements the reactive per-scan analysis. The deep dive produces a structured daily report stored in `knowledge.json` under `daily_deep_analyses`, which the weekly Sunday Claude training then consumes alongside every other data source.

**Why this exists:** the per-scan Qwen analysis in `ai/local_llm_analyzer.py` was a reactive pulse — "is anything wrong right now?" — with a 1024-token output cap, a 4-minute timeout, and a 30-minute full/quick throttle. It never looked at full daily log content, never compared today to yesterday, never saw 24-hour trends, never gave each miner individual attention. The deep dive was always supposed to exist; it just never got built until April 9, 2026.

## Design Principles

1. **No caps on Qwen.** ROBS-PC's RTX 4090 sits idle most of the day. Compute is free. Take as long as needed.
   - `num_ctx: 32768` (Qwen 2.5 32B quantized model's full context window, verified via Ollama `/api/show`)
   - `num_predict: -1` (Ollama convention for unlimited output tokens)
   - `temperature: 0.3` (low for factual analysis, same as the per-scan analyzer)
   - Request timeout: `14400` seconds (4 hours per LLM call — generous upper bound, not a target)
2. **Sequential per-miner, one fleet synthesis.** Per-miner pass runs one miner at a time through Qwen. Expected ~1-5 minutes per miner depending on log size and prompt complexity. Then one final fleet synthesis pass that reads all per-miner analyses. Expected 5-15 minutes for the synthesis.
3. **Resume-safe.** Each per-miner analysis is written to `daily_deep_dive_wip/{YYYY-MM-DD}/miner_{id}.json` immediately as it completes. If the script crashes or is interrupted mid-run, a re-run will pick up where it left off — it reads the wip directory on startup and skips miners with existing completed files.
4. **Cron-triggered at 16:00 local** (America/Chicago) starting April 10, 2026. Today's first run is manual.
5. **Assumes daily collection has already run.** The deep dive does NOT collect logs — it reads logs that `collect_logs` in `core/mining_guardian.py` has already pulled. The 3-hour gap between 13:00 collection start and 16:00 deep dive start is the safety window.
6. **Results flow into Sunday Claude training unchanged.** The Sunday weekly trainer's merge block in `ai/train_cohort.py` reads `knowledge['daily_deep_analyses']` and includes it in the fleet synthesis prompt alongside everything else. See "Sunday Claude Integration" below.

## Data Sources

The per-miner prompt gathers:

- **`miner_readings`** (latest + 24h trend): hashrate %, chip temp, board temp, current profile, miner status, consumption, action history
- **`miner_logs`** (today's `daily_baseline` + yesterday's for comparison): full `miner.log` content (capped at 60KB for today's, 20KB for yesterday's, to fit the 32K token context window alongside trends and rules)
- **`chain_readings`** (24h): per-board rate_mhs, temp_chip, temp_board, voltage, freq_mhz, hw_errors. Compressed into min/max/avg per board.
- **`miner_restarts`** (24h): restart type, outcome, hashrate before/after, recovery time
- **`action_audit_log`** (24h): approvals, denials, operator actions affecting this miner
- **`pool_readings`** (24h): accepted, rejected, accepted_diff, rejected_diff, pool URLs, pool status
- **`miner_hardware`** (permanent identity): serial numbers, firmware version, MAC, board serials, chip bin, PCB version
- **`knowledge['miner_fingerprints'][miner_id]`**: learned fingerprint from past sessions
- **`knowledge['operator_rules']`**: all accumulated operator rules

The fleet synthesis prompt additionally gathers:

- **`hvac_readings`** (24h): supply_temp_f, return_temp_f, delta_t_f, pump percentages, diff_pressure, spray_pump_on. Compressed into min/max/avg.
- **`weather_readings`** (24h): temp, humidity, feels-like. Compressed into min/max/avg.
- **`scans`** (24h): fleet-level online/offline/issue counts.
- **Previous day's `daily_deep_analyses[0]`** for continuity. Lets Qwen notice day-over-day changes.

## Prompt Structure

### Per-miner prompt (one per online miner)

```
You are Mining Guardian's deep-dive fleet analyst running on ROBS-PC (RTX 4090).
This is the DAILY DEEP DIVE — a long-running, comprehensive per-miner analysis.
Take your time. Be thorough. Cite specific data points. No word count limit.

=== MINER {id} ({ip}) — {model} ===
Current state: status={status} action={action} profile={profile} uptime={uptime}

--- HARDWARE IDENTITY (permanent) ---
  serial_number: ...
  firmware: ...
  model_string: ...
  mac_address: ...
  board_serials: ...
  chip_bin: ...
  pcb_version: ...

--- FINGERPRINT (learned over time) ---
  [learned attributes from knowledge.json]

--- 24-HOUR PER-BOARD TRENDS (min/max/avg) ---
  Board 0: HR=... MH/s | temp=...°C | V=... | freq=... | HW errs=... total | scans=...
  Board 1: ...
  Board 2: ...

--- 24-HOUR FLEET-LEVEL TRENDS ---
  Hashrate %: min=...% max=...% avg=...%
  Chip temp: min=...°C max=...°C avg=...°C
  Profiles seen: ...
  Scan count: ...

--- RESTARTS IN LAST 24H ({count}) ---
  [list of restarts with before/after hashrate and recovery time]

--- OPERATOR ACTIONS IN LAST 24H ({count}) ---
  [list of approvals/denials with notes]

--- 24-HOUR POOL PERFORMANCE ---
  Accepted: ... | Rejected: ... | Stale: ...
  Reject rate: ...%

--- OPERATOR RULES (MUST FOLLOW) ---
  • [all accumulated rules]

--- CRITICAL OPERATOR RULES ---
  • TEMPERATURE: do not flag or warn about chip temps BELOW 84°C...
  • HVAC: USA 188 HVAC is working correctly, low delta-T is intentional...
  • Bias toward documenting hardware patterns over environmental recommendations.

--- TODAY'S DAILY BASELINE LOG ({size} chars, showing first {capped}) ---
[full log content, capped at 60KB]

--- YESTERDAY'S LOG EXCERPT ({size} chars, showing first {capped}) ---
[log content, capped at 20KB]

=== YOUR DEEP DIVE TASK ===
1. CURRENT STATE: healthy, degraded, or failing?
2. 24-HOUR STABILITY: stable, trending, spiking, flapping?
3. LOG ANALYSIS (today vs yesterday): what changed?
4. RESTART HISTORY (if any): did restarts fix root cause or mask symptom?
5. CROSS-CORRELATION: consistent with neighbors, or outlier?
6. PREDICTION: what to expect in next 24h?
7. RECOMMENDATION: what should operator do (if anything)?
```

### Fleet synthesis prompt (one call at the end)

```
You are Mining Guardian's deep-dive fleet analyst.
You have just finished reading individual per-miner analyses for every online
miner in the fleet. Now produce the FLEET-WIDE SYNTHESIS for today.

Date: YYYY-MM-DD
Miners online: N
Miners analyzed: M

--- PREVIOUS DAILY SYNTHESIS ({date}) — for continuity ---
[yesterday's fleet synthesis, first 4000 chars]

--- 24-HOUR HVAC TREND (USA 188) ---
  Supply: min=...°F max=...°F avg=...°F
  Return: min=...°F max=...°F avg=...°F
  Delta-T: min=...°F max=...°F avg=...°F
  NOTE: HVAC is performing correctly. Low delta-T is intentional (seasonal).

--- 24-HOUR WEATHER TREND (Fort Worth) ---
  Temp: min=... max=... avg=...
  Humidity: ...

--- 24-HOUR FLEET-LEVEL STATS ---
  Scans: N | avg online: ... | avg offline: ...
  Total issues flagged across day: ...

--- OPERATOR RULES (MUST FOLLOW) ---
  [rules]

--- CRITICAL OPERATOR RULES ---
  [reminder of temperature / HVAC / action bias rules]

=== PER-MINER ANALYSES ({N}) ===
--- miner {id} ---
[per-miner analysis, capped at 2000 chars each]
... (repeated for all online miners)

=== YOUR FLEET SYNTHESIS TASK ===
1. EXECUTIVE SUMMARY (3-5 sentences)
2. FLEET HEALTH
3. COHORT PATTERNS (by model / firmware / cooling zone)
4. OUTLIERS
5. DAY-OVER-DAY CHANGES
6. ENVIRONMENTAL CORRELATION
7. OPERATOR LEARNING
8. TOMORROW'S FOCUS
9. RECOMMENDATIONS
```

## Output Schema

Each daily run produces one entry in `knowledge['daily_deep_analyses']`:

```json
{
  "date": "2026-04-09",
  "timestamp": "2026-04-09T18:43:12.451",
  "wall_time_seconds": 7234,
  "miners_online": 48,
  "miners_analyzed": 46,
  "miners_failed": ["53482", "53521"],
  "per_miner": {
    "53476": "... full per-miner analysis text ...",
    "53477": "... full per-miner analysis text ...",
    ...
  },
  "fleet_synthesis": "... full fleet synthesis text ...",
  "source": "qwen_daily_deep_dive"
}
```

The array keeps the last **30 days** of deep dives (configurable in the script, currently hardcoded).

## Sunday Claude Integration

**Not yet shipped as of end-of-session April 9** — tomorrow's first task. Same pattern as the existing `TEMP_MAY_REMOVE` merge block in `ai/train_cohort.py`, but **NOT wrapped in TEMP_MAY_REMOVE markers** because per operator rule the daily deep dive stays permanent.

The merge block will walk `knowledge['daily_deep_analyses']`, pull out each day's `fleet_synthesis` and per-miner analyses, tag them with `[DAILY DEEP DIVE FLEET SYNTHESIS | {date}]` and `[DAILY DEEP DIVE PER-MINER | {date} | miner {id}]` respectively, translate them into the `llm_scan_analyses` schema, and append them to `all_local_llm_analyses` so the Sunday Claude fleet prompt sees them identically to every other analysis.

See `.apply_dd_merge.py` in the working tree (written during this session but not yet executed — tomorrow's first task to verify and commit).

## Runtime Expectations

**First day (today, April 9):** expected 30-60 minutes total. Fewer miners have full daily logs because today's collection only started shipping fresh exports after the morning fix deployed. Some miners will have no yesterday log to compare against (first-time baselines).

**Steady state (April 10+):** expected 2-4 hours total. Every miner has a full 24-hour log pair. Qwen is giving every miner real individual attention. Fleet synthesis has full context from all per-miner passes.

**Per-miner pass breakdown:**
- Small prompts (healthy miner, minimal log content): 30-60 seconds per miner
- Typical prompts (full log, trends, restart history): 90-180 seconds per miner
- Heavy prompts (degraded miner with lots of errors to analyze): 300+ seconds per miner
- 48 miners × average 120 seconds ≈ 96 minutes per-miner pass

**Fleet synthesis pass:** 5-20 minutes depending on how much content Qwen decides to produce.

**Total expected wall time:** 100-180 minutes steady state. If it takes longer, that's fine per operator spec — no caps on Qwen side, no caps on timeout.

## Invocation

**Manual:**
```bash
cd /root/Mining-Gaurdian
venv/bin/python3 ai/daily_deep_dive.py --manual
```

**Dry run (list what would be analyzed without calling Qwen):**
```bash
venv/bin/python3 ai/daily_deep_dive.py --dry-run
```

**Cron (starting April 10, 2026):**
```
0 16 * * * cd /root/Mining-Gaurdian && /root/Mining-Gaurdian/venv/bin/python3 ai/daily_deep_dive.py >> /tmp/daily_deep_dive.log 2>&1
```

## Thread Safety & Concurrency

The script runs single-process, sequential per-miner. No thread pool. No concurrent Qwen calls. Sequential is the right choice because:
- Qwen on ROBS-PC is one GPU, running one model at a time. Parallel Qwen requests would serialize at the Ollama server anyway.
- Writing per-miner results to disk immediately after each one completes is simpler and safer than managing a thread pool's output queue.
- Resume semantics are trivial with sequential writes.
- The whole point is "take as long as you need" — there's no wall-clock optimization pressure.

## What This Does NOT Do

- **Does not call Claude.** The Sunday 3am Claude weekly training is a separate job (`ai/weekly_train.py` → `ai/train_cohort.py`) that reads the deep dive results on its own schedule. The deep dive is Qwen-only.
- **Does not collect logs.** Relies on `collect_logs` in `core/mining_guardian.py` having already run. The 3-hour gap between 13:00 collection and 16:00 deep dive is the buffer.
- **Does not replace the per-scan Qwen analysis.** `ai/local_llm_analyzer.py` still runs every hour from the scan loop, producing reactive quick-check analyses that feed into `knowledge['llm_scan_analyses']`. The deep dive is ADDITIVE, not a replacement.
- **Does not modify the restart comparison dual-model pipeline.** Pre/post restart comparisons still happen at the moment of each restart via `_run_post_action_log_comparison` and still flow into `knowledge['known_issues']` with the `compare:*` prefix. The deep dive reads from different sources and produces a different output.

## May Migration (Mac Mini Arrival)

The daily deep dive is **PERMANENT**. Unlike the `TEMP_MAY_REMOVE` restart comparison merge block, the daily deep dive stays on forever and its output keeps flowing into the Sunday Claude training stream indefinitely.

On May arrival, two things happen to the deep dive:
1. The script moves from VPS (`/root/Mining-Gaurdian/`) to the Mac mini deployment path.
2. The `LLM_URL` config value changes from `http://100.110.87.1:11434` (ROBS-PC Tailscale) to `http://localhost:11434` (Mac mini's own Ollama). This is a config change, not a code change.

Nothing else changes. The logic stays identical.

The pre/post restart comparison merge in `train_cohort.py` (the `TEMP_MAY_REMOVE` block) goes away on May arrival per operator rule, but the daily deep dive merge (separate block, not wrapped in TEMP markers) stays.

## Known Limitations & Future Work

- **Log size cap at 60KB per miner for today's baseline log.** Qwen's 32K context window means we can't fit 200-500KB raw miner.log files. 60KB captures the most recent 1-2 days of per-line activity for most miners. If a specific investigation needs more, we can expand this selectively.
- **Per-miner analysis cap at 2000 chars in fleet synthesis.** 48 miners × 2000 chars = 96000 chars ≈ 24K tokens for the per-miner block alone, leaving ~8K tokens for HVAC trends + weather + operator rules + the synthesis task itself. This fits but is tight. If we add more fleet-level data sources, we'll need to either trim per-miner excerpts further or split the synthesis into multiple passes.
- **No handling of miners that drop offline mid-run.** If a miner was online at script start but goes offline before its per-miner pass runs, the script will try to pull its 24h trends from the DB and those will be incomplete or empty. The Qwen prompt will still run but with degraded signal. Acceptable for now.
- **No fleet-wide trend comparison across multiple deep dives.** The current design compares today vs yesterday (the most recent previous deep dive). It does not look at week-over-week trends. That's the Sunday Claude training's job.

## Troubleshooting

**"Qwen HTTP error 500" or "Qwen connection error":** ROBS-PC is not reachable via Tailscale, or Ollama is down, or Qwen model is not loaded. SSH to the VPS, `curl http://100.110.87.1:11434/api/tags` to check if Ollama is up. `curl http://100.110.87.1:11434/api/show -d '{"name":"qwen2.5:32b-instruct-q4_K_M"}'` to check if the model is available.

**"Miner X returned no files":** The miner's daily baseline collection failed or timed out. Check the guardian log for `Fresh log:` entries around the time the deep dive ran. If the 10-minute cap is firing for specific miners repeatedly, those miners need AMS-side investigation (see miner 53482 as the canonical example from April 9).

**Script takes longer than expected:** That's fine. No caps. If the per-miner pass is taking more than 5 minutes per miner, check Qwen's CPU/GPU usage on ROBS-PC — if it's saturated, that's just the model working through a large prompt. If it's idle, something is wrong with the Ollama connection.

**Knowledge file grew huge:** `daily_deep_analyses` is capped at 30 entries (30 days) automatically. If the file is still growing unbounded, check the `_save_to_knowledge` function — the dedup-by-date logic should prevent duplicate entries.

**Resume from crash:** just re-run with `--manual`. The script reads `daily_deep_dive_wip/{today}/` on startup and skips any miner with an existing `miner_{id}.json` file.

## Related Files

- `core/mining_guardian.py` — `collect_logs` function (the daily collection that feeds the deep dive)
- `core/mining_guardian.py` — `collect_fresh_miner_logs` function (fresh log export with 10-min daily cap)
- `ai/local_llm_analyzer.py` — the per-scan reactive Qwen analyzer (different job, runs every hour)
- `ai/train_cohort.py` — the Sunday Claude weekly trainer that consumes deep dive results
- `ai/knowledge_manager.py` — knowledge.json read/write helpers
- `REPAIR_LOG.md` — "Daily Deep Dive LLM created" entry
- `CLAUDE.md` — May Migration Changes section (references this design)
- `docs/SESSION_LOG_2026-04-09.md` — the session that built this

## Permanent Markers for Future Sessions

- If you grep `# TEMP_MAY_REMOVE` in the codebase, you will find the restart comparison merge block in `train_cohort.py`. **That block goes away on May arrival. This daily deep dive does NOT.** Do not conflate them.
- If you grep `daily_deep_analyses` in the codebase, you should find: (1) this file (`daily_deep_dive.py`) writing to the key, (2) the merge block in `train_cohort.py` reading from the key (pending tomorrow's commit), (3) the design doc you are reading now.
- If a future session proposes removing the daily deep dive, STOP and read the REPAIR_LOG.md entry for this feature, the May Migration Changes section of CLAUDE.md, and the SESSION_LOG for April 9, 2026. The deep dive was explicitly built to close a silent gap (reactive-only LLM) and is intended to run forever.

---

## Prompt Size Cap (Added 2026-04-16)

### Problem
Some miners accumulate massive log files (5MB+) that generate prompts of 66K-86K characters. These take 60-90 minutes per miner to analyze, causing the entire deep dive to run for many hours.

### Solution
Added MAX_PROMPT_CHARS = 45000 (~12K tokens) cap in ai/daily_deep_dive.py.

### Behavior
- Miners with prompts > 45K chars are automatically SKIPPED
- Skip marker file written for resume safety:
  ```json
  {
    "miner_id": "53499",
    "skipped": true,
    "skip_reason": "prompt too large: 86153 chars"
  }
  ```
- Log message: "SKIPPED — prompt too large (86153 chars > 45000 max)"

### Why 45K?
- 45K chars ≈ 12K tokens
- Fits comfortably in Qwen's 32K context window
- Leaves room for system prompt and output
- Still provides substantial analysis capability
- Typical analysis takes 5-15 minutes at this size

### Affected Miners
Miners with large prompts typically have:
- Very active restart history
- Large daily logs (many events)
- Extended error sequences in logs

These miners may need manual log review or log rotation to reduce size.
