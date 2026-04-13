# Operator Rules

These rules are embedded in knowledge.json and guide all AI analysis and decision-making.

## Rule 1: 20-Minute Post-Restart Cooldown
After any restart or power cycle, wait 20 minutes before evaluating miner performance. Hashrate readings during warmup are unreliable and should not trigger additional actions.

## Rule 2: Offline Miner Logic
If a miner is confirmed offline (unreachable via direct check), do NOT attempt firmware restart commands. Only PDU power cycle is valid for truly offline miners. Firmware restarts require the miner to be reachable.

## Rule 3: Daily Log Collection Mandatory
Every online miner MUST get a fresh log export every day. Do not rely on stale logs. If log collection fails for a miner, report it in Slack (#mg-logs channel) at 4:15pm so operator can investigate before leaving.

## Rule 4: AMS Log Cleanup
Delete ALL log files from AMS daily at 10am. Do not let failed or stale logs accumulate. Store logs in guardian.db only — AMS is not the system of record.

## Rule 5: S19J Pro CT Fans at 100%
S19J Pro container CT fans are manually set to 100%. No VFD feedback will appear in HVAC data. This is intentional and NOT an equipment fault. Do NOT flag missing fan feedback as a problem.

## HVAC-Related Rules

### Temperature Threshold
Do NOT flag or warn about overheating until chip temp reaches **84°C**. Anything below 84°C must not generate any warning, alert, or recommendation about overheating regardless of cohort averages.

### HVAC Delta-T
USA 188 HVAC is performing correctly. Low supply/return delta-T is intentional and will rise as outside temps climb. Do NOT recommend checking HVAC because delta-T is low.

### System-Specific Correlation
Compare miners to THEIR cooling system only:
- **S19J Pro** miners → S19J Pro Container HVAC (192.168.189.235)
- **All other miners** → Warehouse HVAC (192.168.188.235)

See [HVAC_SYSTEMS.md](./HVAC_SYSTEMS.md) for complete HVAC documentation.

---
*Last updated: April 13, 2026*

## Rule 6: S19J Pro Overheating Boards (Aging Hardware)

When an S19J Pro shows overheating (chip temp >= 84°C):

1. **Try ONE restart** with log capture before and after
2. **Compare logs** to see if the restart helped
3. **If restart doesn't fix it** — these are old boards, let them run as-is

**Do NOT:**
- Repeatedly restart overheating S19J Pros
- Create tickets for aging thermal issues after first attempt fails
- Flag these miners on every scan

**Rationale:** S19J Pros are older hardware. As boards age, some will run hotter. One restart attempt is worth trying, but if it doesn't help, the hardware is simply aging and should be allowed to run until it fails naturally.

### Database Table
The  table tracks:
-  — Unique miner identifier
-  — When overheating was first detected
-  — When we tried the restart
-  /  — Logs for comparison
-  — 1=yes, 0=no, NULL=pending
-  — When we gave up and marked as aging

### Logic Flow
1. S19J Pro hits 84°C+ → Check tracking table
2. If new → Record, try restart with log capture
3. After restart → Compare logs
4. If temps still high → Mark as aging, suppress future flags
5. If temps normal → Remove from tracking


### Database Table
The s19jpro_overheat_tracking table tracks:
- miner_id — Unique miner identifier
- first_overheat_at — When overheating was first detected
- restart_attempted_at — When we tried the restart
- log_before / log_after — Logs for comparison
- restart_helped — 1=yes, 0=no, NULL=pending
- marked_aging_at — When we gave up and marked as aging

### Logic Flow
1. S19J Pro hits 84C+ -> Check tracking table
2. If new -> Record, try restart with log capture
3. After restart -> Compare logs
4. If temps still high -> Mark as aging, suppress future flags
5. If temps normal -> Remove from tracking
