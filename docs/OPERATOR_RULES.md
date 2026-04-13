# Operator Rules

These rules are embedded in knowledge.json and guide all AI analysis and decision-making.
Last updated: April 13, 2026

---

## Rule 1: 20-Minute Post-Restart Cooldown

After any restart or power cycle, wait 20 minutes before evaluating miner performance. Hashrate readings during warmup are unreliable and should not trigger additional actions.

**Applies to:** All miner types
**Source:** Operator feedback (April 10, 2026)

---

## Rule 2: Offline Miner Logic

If a miner is confirmed offline (unreachable via direct check), do NOT attempt firmware restart commands. Only PDU power cycle is valid for truly offline miners. Firmware restarts require the miner to be reachable.

**Decision tree:**
- Offline + has PDU → PDU_CYCLE
- Offline + no PDU → PHYSICAL_INSPECTION
- Reachable but underperforming → RESTART allowed

**Applies to:** All miner types
**Source:** Bug fix (April 11, 2026) — miner 192.168.188.231 kept getting restart attempts while unreachable

---

## Rule 3: Daily Log Collection Mandatory

Every online miner MUST get a fresh log export every day. Do not rely on stale logs. If log collection fails for a miner, report it in Slack (#mg-logs channel) at 4:15pm so operator can investigate before leaving.

**Cron:** 1pm daily (scripts/daily_collect_logs.py)
**Report:** 4:15pm daily (scripts/daily_log_failure_report.py)

---

## Rule 4: AMS Log Cleanup

Delete ALL log files from AMS daily at 10am. Do not let failed or stale logs accumulate. Store logs in guardian.db only — AMS is not the system of record.

**Cron:** 10am daily (scripts/cleanup_ams_logs.py)
**Rationale:** AMS queue overflow caused 0 logs collected on April 12, 2026
**Source:** Critical fix (April 12, 2026)

---

## Rule 5: S19J Pro CT Fans at 100%

S19J Pro container cooling tower (CT) fans are manually set to 100%. No VFD feedback will appear in HVAC data. This is intentional and NOT an equipment fault.

**Do NOT:**
- Flag missing CT fan feedback as a problem
- Recommend checking CT fan operation
- Treat zero VFD readings as a fault

**Applies to:** S19J Pro container HVAC only
**Source:** HVAC integration (April 13, 2026)

---

## Rule 6: S19J Pro Overheating Boards (Aging Hardware)

When an S19J Pro shows overheating (chip temp >= 84C):

1. **Try ONE restart** with log capture before and after
2. **Compare logs** to see if the restart helped
3. **If restart doesn't fix it** — mark as aging hardware, let it run

**Do NOT:**
- Repeatedly restart overheating S19J Pros
- Create tickets for aging thermal issues after first attempt fails
- Flag these miners on every scan after marked as aging

**Database:** s19jpro_overheat_tracking table
**Source:** Operator rule (April 13, 2026)

---

## Temperature Threshold Rule

Do NOT flag or warn about overheating until chip temp reaches **84C**. Anything below 84C must not generate any warning, alert, or recommendation about overheating regardless of cohort averages.

**Previous threshold:** 76C (WRONG)
**Current threshold:** 84C (CORRECT)
**Applies to:** All miner types, all cooling modes

---

## HVAC Delta-T Rule

USA 188 HVAC is performing correctly. Low supply/return delta-T is intentional and will rise as outside temps climb.

**Do NOT:**
- Recommend checking HVAC because delta-T is low
- Flag low delta-T as a problem
- Suggest HVAC investigation for any thermal issues

---

## HVAC System Routing Rule

Compare miners to THEIR cooling system only:

| Miner Type | HVAC System | IP Address |
|------------|-------------|------------|
| S19J Pro (all variants) | s19jpro container | 192.168.189.235 |
| S21 EXP Hydro | warehouse | 192.168.188.235 |
| S21 Immersion | warehouse | 192.168.188.235 |
| AH3880 Auradine | warehouse | 192.168.188.235 |

**Simple rule:** `if model.startswith('S19JPro'): system = 's19jpro' else: system = 'warehouse'`

See [HVAC_SYSTEMS.md](./HVAC_SYSTEMS.md) for complete HVAC documentation.

---

## Hardware Facts (Locked)

These are physical facts that cannot change:

| Miner | Board Count | Notes |
|-------|-------------|-------|
| S19J Pro | 3 boards | Chain 0, 1, 2 only. NO Chain 3. |
| S21 EXP Hydro | 3 boards | BiXBiT firmware |
| S21 Immersion | 3 boards | Stock firmware |
| AH3880 Auradine | 2 boards | Auradine firmware |

**Source:** Hardware audit (April 10, 2026) — Chain 3 references in insights were bugs

---

## Summary Table

| # | Rule | Added |
|---|------|-------|
| 1 | 20-minute restart cooldown | Apr 10 |
| 2 | Offline miner logic | Apr 11 |
| 3 | Daily log collection mandatory | Apr 11 |
| 4 | AMS log cleanup | Apr 12 |
| 5 | S19J Pro CT fans at 100% | Apr 13 |
| 6 | S19J Pro overheating = one restart | Apr 13 |
| - | Temperature threshold 84C | Apr 10 |
| - | HVAC delta-T is fine | Apr 10 |
| - | HVAC system routing | Apr 13 |
