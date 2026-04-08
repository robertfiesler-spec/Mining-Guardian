# Daily Log Capture & 14-Day Rolling Baseline System

**Captured: April 8, 2026 by Bobby (verbatim intent)**
**Status: VISION — operational requirement, not yet built.**
**Triggered by: April 8 firmware regression on Auradine AH3880 #28 and #55**

---

## The trigger event

On April 8, 2026 Bobby updated the firmware on both Auradine AH3880 miners
in his fleet (192.168.188.28 and 192.168.188.55). After the update, both
miners began exhibiting:

- DVFS power overshoot alarms (power clipping at 11.5kW against 10kW budget)
- PowerState voltage clipping at both Vmin (31V) and Vmax (47V)
- PSU IOUT 0x02 overcurrent shutdown trips
- PSU AC input fault (Status 0x10)
- PSU fan fault (Status 0x02)
- Hundreds of pool stratum panics in the gcminer process
- Hashrate stuck at ~79% of tune target

**The dual-model LLM analysis (Qwen + Claude) ran on logs from both miners
and confidently diagnosed "Replace PSU" with HIGH confidence.** Both LLMs
were *technically reading the symptoms correctly* but *blamed the wrong
component* because they had no historical baseline showing these miners
were healthy on the previous firmware version.

**The PSUs are probably fine.** The new firmware appears to be
mismanaging DVFS power delivery in a way that looks like PSU instability
to a logs-only diagnostic. Bobby has emailed Auradine to request the
previous firmware version for rollback.

This is the canonical example of why **daily log capture with rolling
baseline retention** is operationally critical.

---

## What Bobby asked for in his own words

> "I recently updated the firmware for these two models and it seems like
> that is what has caused all of these problems. I just emailed the company
> to get a copy of the previous version to roll back to. Please put that in
> the notes for learning. This is why having logs one a day is so important
> on every miner, that way in analysis is can pick up those differences and
> offer solutions. After 2 weeks the old one get pushed out and deleted,
> but that should be enough time to reference it if needed."

---

## The system this requires

### 1. Daily log capture cron — once per day per miner
- Runs at a fixed quiet-hours time (e.g. 03:00 local) so it doesn't compete
  with operator workload or scan cycles
- Captures the freshest miner.log (or vendor equivalent) from EVERY miner
  in the fleet, not just flagged ones
- Saves into `miner_logs` under a new `health_status='daily_baseline'`
- Tags the row with the **current firmware version** at capture time so
  later regression analysis can link a fault pattern to a firmware change

### 2. 14-day rolling retention — auto-prune
- After 14 days, daily_baseline rows older than 14 days get deleted
- 14 days × ~58 miners × ~2 MB per log = ~1.6 GB rolling window
- Existing `purge_old_logs()` function in `core/mining_guardian.py` already
  does day-based cleanup but only on its current 7-day setting and not
  scoped to the daily_baseline label — needs an extension to keep
  pre/post/diagnostic forever AND keep daily_baseline on a 14-day window
- New label `daily_baseline` is critical so the existing `pre-restart`,
  `post-restart`, `pre-pdu-cycle`, `post-pdu-cycle`, and `diagnostic` rows
  remain permanent (those have audit-trail value forever)

### 3. Firmware version tracking
- `miner_readings` table already has a `firmware_version` field — verify
  it's actually populated for every scan
- Add a `firmware_changes` table:
  ```sql
  CREATE TABLE firmware_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    miner_id TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    previous_version TEXT,
    new_version TEXT,
    detected_via TEXT,  -- 'scan_diff', 'manual_note', 'ams_event'
    notes TEXT
  );
  ```
- A scan that sees `firmware_version` differ from the previous scan for the
  same miner inserts a row in `firmware_changes` automatically
- This becomes a first-class event the analysis can correlate against

### 4. Auto-comparison of current logs vs pre-firmware-change baseline
- When a miner's current daily_baseline log shows new fault patterns
  (panic count up, error count up, hashrate down, new alarm types), the
  system pulls the most recent daily_baseline from BEFORE the most recent
  firmware_change for the same miner
- Runs the dual-model comparison with both logs labeled correctly
  (`pre_firmware_X.Y.Z` vs `post_firmware_A.B.C`)
- The LLMs now have the operator context they need to detect a regression
  rather than a hardware fault

### 5. Cross-miner regression detection
- When the same fault pattern appears on **multiple miners of the same
  model within a small time window after a firmware update**, the system
  promotes it from "individual miner fault" to **"firmware regression
  candidate"**
- Bumps it to a higher Slack priority and adds a recommended action:
  *"Multiple [model] miners show [fault pattern] within [N] hours of
  firmware update from [old_ver] to [new_ver]. Consider firmware rollback
  before pursuing hardware repair on individual miners."*
- This is exactly the alert that would have caught the AH3880 firmware
  regression today — both miners showed the SAME fault patterns, both had
  been updated at roughly the same time, and the LLM verdict of "replace
  PSU on both miners" should have been overridden by a regression flag

---

## Implementation notes

### Reuses existing infrastructure
- `GuardianDB.save_logs()` already handles dedup-by-(miner_id, log_file,
  health_status) so daily_baseline rows won't collide with other labels
- `GuardianDB._collect_logs_nonblocking()` already does fresh log collection
  via AMS — can be called from a daily cron with `label='daily_baseline'`
- `_run_post_action_log_comparison()` helper can be generalized to handle
  arbitrary baseline-vs-current comparisons, not just pre/post-action
- Existing `purge_old_logs()` cleanup logic only needs a label-aware
  modification to spare the audit-trail rows

### New code needed
- **Cron entry point script**: `scripts/daily_baseline_capture.py` —
  iterates the fleet, calls `_collect_logs_nonblocking()` with
  `label='daily_baseline'` for each healthy miner
- **Firmware change detector**: lives inside the regular scan loop in
  `core/mining_guardian.py`, runs the diff against the previous scan
- **Regression analyzer**: new module `ai/regression_detector.py` — looks
  for fault patterns appearing on N+ miners of the same model within K
  hours of a firmware_changes row
- **Retention modification**: extend `purge_old_logs()` to take an
  optional `label_retention_days` dict so daily_baseline=14 days,
  pre-restart=forever, etc.

### Auradine-specific consideration
- Auradine logs are NOT available via the AMS WebSocket — they have to
  be pulled via the discovered `POST /log` undocumented endpoint
  (see `clients/auradine_client.py`)
- The daily capture for Auradine miners needs to call
  `auradine_client.get_all_logs()` directly, not the AMS path
- Same for any future vendors that don't expose logs through AMS

---

## What this would have done for the April 8 firmware regression

If this system had been running BEFORE Bobby updated the AH3880 firmware:

1. **April 7 (or earlier)** — daily_baseline captures for both miners
   showed: hashrate ~590 TH/s, no panics, no PSU faults, normal DVFS,
   firmware version `<old>`
2. **April 8 morning** — Bobby applied firmware update on both miners
3. **April 8 next scan** — `firmware_version` differs from previous scan
   for both 192.168.188.28 and 192.168.188.55 → two `firmware_changes`
   rows inserted within minutes of each other
4. **April 8 next daily_baseline (or even on the next post-scan analysis
   cycle)** — current logs show panics, PSU trips, voltage clipping
5. **Regression detector** notices: TWO miners of the SAME model
   (AH3880) both showing the SAME fault pattern within a SMALL time
   window of firmware_changes rows that BOTH happened in the same window
6. **Slack alert** to `#mining-guardian-alerts`:
   ```
   🚨 FIRMWARE REGRESSION CANDIDATE
   2 miners (192.168.188.28, 192.168.188.55) of model Auradine AH3880
   exhibit identical fault pattern (PSU IOUT trips, voltage clipping,
   stratum panics) within 2 hours of firmware update from <old> to <new>.
   Recommended action: roll back firmware before pursuing hardware repair.
   Pre-update daily baselines available for both miners.
   Run /compare-logs auradine_28 daily_baseline_pre_firmware_change to
   see the side-by-side analysis.
   ```
7. **Bobby reads the alert**, decides to roll back instead of replacing
   PSUs that don't need replacing

---

## Why the 14-day window is the right answer

- Long enough to span: weekend schedules, vendor response times for
  firmware support tickets, scheduled maintenance windows that might
  defer the rollback decision
- Short enough to not blow out disk usage (~1.6 GB rolling)
- Long enough to catch slow-developing regressions (firmware bug that
  only manifests after a few days of accumulated runtime)
- Matches operator working memory — Bobby can reasonably remember
  "what changed in the last two weeks" but not "what changed three
  months ago"
- Forces analysis to be timely — if a regression isn't caught within
  14 days, it's likely become the new baseline and should be treated
  as such

---

## Open questions (resolve before building)

1. **Daily capture time** — 03:00 local (current quiet hours start)?
   Or stagger across the fleet to avoid hammering AMS at once?
2. **What about flagged/offline miners on the daily run** — skip them
   (we already have rich data from the action audit log) or capture
   anyway as evidence of the ongoing fault?
3. **Daily retention vs total retention** — should daily_baseline rows
   be the FIRST thing pruned when disk is tight, or LAST? Probably
   first since they're the easiest to recapture.
4. **Cross-vendor firmware tracking** — do we trust each vendor's
   reported version string or do we hash the firmware blob? Trust for
   now, hash later if vendors lie.
5. **Regression detector sensitivity** — how many miners need to show
   the same pattern? 2 (today's case) or 3+ (avoid false positives on
   small fleets)?
6. **Rollback automation** — should the system EVER auto-roll-back
   firmware, or always require operator approval? Always operator
   approval. Firmware rollback is destructive and too easy to corrupt
   a fleet if the wrong version gets pushed.
7. **Spec-update scheduling** — when Auradine ships a firmware version
   that fixes a regression, the system should know about it. Manual
   update of `model_specs.firmware_known_good` field?
8. **Comparison budget** — running dual-model comparisons on every
   daily_baseline-vs-pre-firmware pair across the whole fleet on every
   scan would be expensive. Batch them weekly? Run only on miners with
   detected regressions?

---

## Build phase priority

This is a Phase 0 / pre-Open-Log-Uploader item because it doesn't
require any of the bigger system. It can ship in **3-5 days** of
focused work:

- Day 1: `daily_baseline_capture.py` script + cron entry + label-aware
  retention
- Day 2: `firmware_changes` table + scan-loop change detector
- Day 3: Generalize `_run_post_action_log_comparison` to handle
  arbitrary baseline-vs-current pairs + add `daily_baseline` as a valid
  comparison source
- Day 4: `ai/regression_detector.py` + Slack alert wiring
- Day 5: Backfill: capture daily_baseline today on every miner so
  there's at least a starting point for next regression detection

**Recommend building this BEFORE the Open Log Uploader.** It's smaller
in scope, addresses a real fire that just happened today, and the
infrastructure (label support, fresh log capture, dual-model comparison)
is already in place.
