# Mining Guardian — Repair & Maintenance Log

**Created:** 2026-04-16  
**Purpose:** Track miners requiring physical intervention, repairs, and maintenance actions

---

## Active Repair Queue

### Miner 53521 — CRITICAL
| Field | Value |
|-------|-------|
| **IP** | 192.168.188.12 |
| **Model** | Antminer S19JPro |
| **Status** | FAILING |
| **Identified** | 2026-04-16 |
| **Source** | Daily Deep Dive AI Analysis |

**Problem:**
All 3 hashboards showing 0/126 ASICs detected with 126 bad chips each. Miner enters emergency sleep mode repeatedly due to fatal errors. Multiple restarts have not resolved the issue.

**AI Analysis Summary:**
> The miner is currently online but failing. All three chains (hashboards) have been disabled due to too many bad chips. Each chain found zero ASICs out of 126, with 126 bad chips reported. Despite multiple restarts, there has been no improvement in performance or stability.

**Recommended Actions:**
1. Physical inspection required
2. Check for loose connections or damaged boards
3. Likely needs board replacement
4. Monitor closely post-repair before returning to production

**Log Evidence:**
- Repeated warnings: "Chain X found 0 ASICs, 126 bad chips"
- Fatal errors causing emergency sleep mode
- 75% restart success rate (degraded)
- No hardware errors reported in API (masking issue)

---

## Repair History

| Date | Miner | Issue | Resolution | Duration |
|------|-------|-------|------------|----------|
| 2026-04-16 | 53521 | All hashboards failing | PENDING | - |

---

## Common Failure Patterns

### Pattern: All Hashboards Report Bad Chips
**Symptoms:**
- 0/126 ASICs detected per chain
- 126 bad chips per chain
- Emergency sleep mode triggered
- Restarts ineffective

**Likely Causes:**
- Control board failure
- Ribbon cable damage/disconnection
- Power supply issue
- Physical damage to hashboards

**Resolution:**
- Physical inspection required
- Check all cable connections
- Test with known-good PSU
- Replace faulty components

---

## Escalation Criteria

A miner should be added to the repair queue when:

1. **AI Deep Dive** flags it as "failing" with hardware issues
2. **3+ consecutive restart failures** in overnight automation
3. **Dead board** detected and confirmed
4. **Known issues** table shows repeated failures for same problem
5. **Manual operator observation** of physical problems

---

## Integration with Mining Guardian

### Automatic Detection
- Daily Deep Dive analyzes all miners and flags failing units
- Overnight automation tracks restart failures
- Dead board detection creates AMS tickets automatically

### Tables Involved
- known_dead_boards — Miners with confirmed dead boards
- miner_restarts — Restart history and success rates
- llm_analysis — AI analysis results
- action_audit_log — All operator interventions

### Slack Notifications
- Failing miners flagged in #mg-ai-reports
- Dead board tickets in #mg-alerts
- Deep dive reports sent to operator DM

---

## Notes

- Always verify AI recommendations with physical inspection
- Document all repairs in this file for pattern recognition
- Update known_dead_boards table after confirming hardware issues
- Create AMS ticket for tracking warranty/RMA if applicable
