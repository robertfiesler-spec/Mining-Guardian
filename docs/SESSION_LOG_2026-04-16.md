# Session Log — April 16, 2026

## Summary

Major session focused on diagnosing cron job failures and implementing a new direct log collection system that bypasses AMS entirely.

## Key Accomplishments

### 1. Root Cause Analysis of Cron Failures

Investigated why cron jobs have been failing over the past 2 days:

| Date | Job | Issue | Root Cause |
|------|-----|-------|------------|
| Apr 13 | Deep Dive | Code bug | `build_per_miner_prompt()` missing `facility` parameter |
| Apr 13 | Deep Dive | Code bug | `name 'miner' is not defined` in synthesis |
| Apr 15 | Deep Dive | Stuck | Miner 53499 had 86K char prompt (5MB logs) |
| Apr 16 | Deep Dive | 0 miners | Bad scan 1562 showed 0 online due to AMS blip |
| Apr 16 | Log Collection | 0 collected | AMS log queue overflow, exports failing |

### 2. Direct Log Collection Implementation

**Problem:** AMS-based log collection was failing due to:
- Log queue overflow (too many pending exports)
- Slow export times (5+ minutes per miner)
- 30+ minute total collection time
- 0% success rate on failing days

**Solution:** New `direct_collect_logs.py` that:
- Hits miners directly via Tailscale subnet routing
- Uses BiXBiT firmware's `create_log_backup.cgi` endpoint
- Downloads today's logs only (no historical accumulation)
- Completes in ~107 seconds with 80% success rate

**API Discovery:**
```
1. POST /cgi-bin/create_log_backup.cgi with ["/YYYY-MM/DD"]
   → Returns: {"stats":"success","msg":"Antminer_S19j_Pro_2026-04-16.tar.bz2"}

2. GET /log/<filename>
   → Returns: tar.bz2 with miner.log, temp.log, power.log, etc.
```

**Auth:** HTTP Digest with `root:root`

### 3. Cron Job Updates

Replaced AMS-based collection with direct collection:
```
# OLD (deprecated)
0 13 * * * ... daily_collect_logs.py

# NEW
0 13 * * * ... direct_collect_logs.py
```

### 4. Bad Scan Cleanup

Deleted scan 1562 which showed 0 online miners due to AMS connectivity blip:
```sql
DELETE FROM scans WHERE id = 1562;
```

### 5. Documentation Created

- `docs/DIRECT_LOG_COLLECTION.md` — Full documentation of new system
- `docs/CRON_SCHEDULE.md` — Updated cron schedule

## Files Created/Modified

| File | Action |
|------|--------|
| `scripts/direct_collect_logs.py` | Created |
| `scripts/deep_dive_progress_monitor.py` | Created (earlier) |
| `scripts/send_deep_dive_report.py` | Created |
| `docs/DIRECT_LOG_COLLECTION.md` | Created |
| `docs/CRON_SCHEDULE.md` | Updated |

## Performance Comparison

| Metric | AMS (old) | Direct (new) |
|--------|-----------|--------------|
| Duration | 30+ min | 107 sec |
| Success Rate | 0% (failing) | 80% (39/49) |
| Queue Issues | Yes | No |
| Dependencies | AMS online | Tailscale + ROBS-PC |

## Outstanding Items

1. **Large prompt handling** — Miners with 5MB+ logs generate 66K+ char prompts that cause Qwen timeouts. Need prompt size cap or log truncation.

2. **Stock firmware miners** — 54504, 63940 use stock Bitmain firmware (not BiXBiT), need different API.

3. **S21 Immersion / Auradine** — Currently offline. May need different log collection approach when online.

4. **AMS cleanup timing** — Consider running cleanup at 12:50pm (before collection) instead of 10am.

## Deep Dive Status

Fresh deep dive started at 17:37 with:
- 37 online miners
- First prompt: 27K chars (reasonable size)
- Progress monitor and report watcher running
- Will DM Bobby when complete

## Commands Reference

### Run direct log collection manually:
```bash
cd /root/Mining-Gaurdian && source venv/bin/activate
python3 scripts/direct_collect_logs.py
```

### Check deep dive progress:
```bash
tail -f /tmp/deep_dive_fresh.log
```

### View cron schedule:
```bash
crontab -l
```

---

## Final Session Update (19:15 CDT)

### Deep Dive Results
- **Miner 53521:** Completed analysis (86 min for 27K prompt)
- **Miner 53499:** Skipped (86K prompt would take hours)
- **Remaining miners:** Deep dive killed to prevent multi-hour run

### Prompt Size Cap Added
Added `MAX_PROMPT_CHARS = 45000` to `ai/daily_deep_dive.py`:
- Miners with prompts > 45K chars (~12K tokens) are now automatically skipped
- Skip marker file written with reason for resume safety
- Prevents 60-90 minute per-miner analysis runs

### Repair Queue Created
New `docs/REPAIR.md` tracking miners needing physical intervention:
- **Miner 53521** added as CRITICAL
- All 3 hashboards failing (0/126 ASICs, 126 bad chips each)
- Needs physical inspection and likely board replacement

### Documentation Created/Updated
| File | Description |
|------|-------------|
| `docs/REPAIR.md` | NEW - Repair queue and maintenance log |
| `docs/DIRECT_LOG_COLLECTION.md` | NEW - Direct miner API documentation |
| `docs/CRON_SCHEDULE.md` | UPDATED - New 1pm direct collection |
| `docs/SESSION_LOG_2026-04-16.md` | NEW - This session |

### Code Changes
| File | Change |
|------|--------|
| `scripts/direct_collect_logs.py` | NEW - Direct miner log collection |
| `scripts/deep_dive_progress_monitor.py` | NEW - Slack progress updates |
| `scripts/send_deep_dive_report.py` | NEW - DM report on completion |
| `ai/daily_deep_dive.py` | MODIFIED - Added MAX_PROMPT_CHARS cap |

### Git Commits
1. "Add direct log collection system, bypasses AMS"
2. "Add MAX_PROMPT_CHARS cap (45K) to daily deep dive"

### Performance Improvements
| Metric | Before | After |
|--------|--------|-------|
| Log collection time | 30+ min | 107 sec |
| Log collection success | 0% (failing) | 80% (39/49) |
| Deep dive per-miner | 60-90 min (large) | Skipped if >45K |
