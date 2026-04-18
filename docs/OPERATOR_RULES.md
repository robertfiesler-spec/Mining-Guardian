# Mining Guardian — Operator Rules

**Last Updated:** 2026-04-18

---

## Active Operator Rules (8 Total)

### Rule 1: 20-MINUTE POST-RESTART COOLDOWN
After any restart or power cycle, wait 20 minutes before initiating profile changes, additional restarts, or any other actions. The miner needs time to stabilize and reach steady-state operation.

**Rationale:** Prevents cascading restarts and allows accurate assessment of restart effectiveness.

---

### Rule 2: OFFLINE MINER LOGIC
If a miner is confirmed offline (unreachable via direct check), do NOT recommend firmware restart.

**Decision tree:**
- Miner offline + PDU available = PDU_CYCLE
- Miner offline + no PDU = PHYSICAL_INSPECTION  
- Miner reachable but underperforming = Firmware restart OK

---

### Rule 3: DAILY LOG COLLECTION MANDATORY
Every online miner MUST get a fresh log export every day. No 24-hour dedup.

**Fallback:** If fresh export fails, use most recent existing log.
**Escalation:** Problem miners with broken exports need physical investigation.

---

### Rule 4: AMS LOG CLEANUP
Delete ALL log files from AMS daily at 12:45pm (before 1pm collection).

**Why:** Failed exports accumulate and block new exports.

---

### Rule 5: S19J PRO CONTAINER CT FANS
CT fans are manually set to 100% - no VFD feedback in HVAC data. This is intentional, NOT a fault.

---

### Rule 6: S19J PRO OVERHEATING BOARDS (AGING HARDWARE)
When an S19J Pro shows overheating (chip temp >= 84C):
1. Try ONE restart with log capture before and after
2. Compare logs to see if restart helped
3. If single restart does not fix it, these are old boards - let them run

**Do NOT:** Repeatedly restart or create tickets for aging S19J Pro thermal issues.

---

### Rule 7: WAREHOUSE MINERS OFFLINE FOR MAINTENANCE
Currently offline for 1-2 days:
- 2 Auradines (AH3880)
- 2 S21 EXP Hydro
- 2 S21 Immersion
- Warehouse HVAC system

**Do NOT:** Flag these as problems - expected back online soon.

---

### Rule 8: APPROVAL REQUIRES EXPLANATION (NEW)
When approving any action (YES/APPROVE), the operator or AI MUST provide a brief explanation of WHY the action is appropriate.

**No blind approvals** - every YES needs reasoning documented in the notes field.

**Example:**
- BAD: approve .36
- GOOD: approve .36 hashrate dropped 40% after fan failure, restart should help

---

## Temperature Thresholds

| Level | Temp | Action |
|-------|------|--------|
| Normal | < 76C | No action |
| Yellow | 76-83C | Monitor |
| Red/Alert | >= 84C | Investigate |

**Note:** Do NOT flag anything below 84C as overheating. Fleet is liquid-cooled, 67-80C is NORMAL.

---

## HVAC Rules

- USA 188 HVAC is working correctly
- Low supply/return delta-T is intentional
- Do NOT recommend checking HVAC based on low delta-T

---

## Review Checklist

Before approving, ask yourself:
1. Has 20 minutes passed since last restart?
2. Is the miner actually reachable?
3. What is the root cause, not just symptom?
4. Did I document WHY I am approving?
5. Will this action teach the AI something useful?
