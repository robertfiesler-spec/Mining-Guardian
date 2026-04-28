# Direct Miner Log Collection

**Last Updated:** 2026-04-17  
**Status:** Production (replaces AMS-based collection)

---

## Overview

Direct log collection bypasses AMS entirely by hitting each BiXBiT miner directly via Tailscale. This is significantly faster and more reliable than the AMS queue-based approach.

---

## Performance Comparison

| Method | Miners | Duration | Success Rate |
|--------|--------|----------|--------------|
| AMS (old) | 34 | 30+ min | 0% (queue overflow) |
| Direct (new) | 49 | ~130s | 75-80% (37-39/49) |

---

## How It Works

### Authentication
- **Protocol:** HTTP Digest Auth
- **Credentials:** root:root (BiXBiT firmware standard)
- **Access:** Via Tailscale subnet routing through ROBS-PC

### API Flow

1. **Trigger log backup:**
   ```
   POST http://<miner_ip>/cgi-bin/create_log_backup.cgi
   Content-Type: application/json
   Body: ["/2026-04/17"]  # Format: /YYYY-MM/DD
   
   Response: {"stats":"success","code":"L000","msg":"Antminer_S19j_Pro_2026-04-17.tar.bz2"}
   ```

2. **Download the archive:**
   ```
   GET http://<miner_ip>/log/<filename>
   
   Returns: tar.bz2 file containing nvdata/YYYY-MM/DD/cglog_init_*/
   ```

3. **Extract and filter:**
   - Extract miner.log from tar.bz2
   - Apply date filtering (keep only todays lines)
   - Apply noise filtering (remove freq tuning spam)
   - Store in miner_logs table

---

## Log Filtering

### Date Filtering (Added 2026-04-17)
BiXBiT API returns entire log folder with multiple days even when requesting specific date.
We filter after extraction to keep only lines starting with target date.

```python
date_prefix = "[" + target_date.strftime("%Y/%m/%d")
lines = [line for line in lines 
         if line.startswith(date_prefix) or not line.startswith("[")]
```

**Impact:** 1.9MB logs reduced to ~400KB (80% reduction)

### Noise Filtering
Removes high-volume repetitive lines:
- INFO: Set chain N freq (50K+ lines/day)
- INFO: Psu current voltage
- INFO: Total cpu:
- INFO: Temp max NC
- INFO: Chain[N] chip temp

**Impact:** Additional 30-40% reduction after date filtering

### Combined Result
| Metric | Before | After |
|--------|--------|-------|
| Log size | 1.9MB | 400KB |
| Prompt size | 86K chars | 35K chars |
| Deep dive status | SKIPPED | ANALYZED |

---

## Cron Schedule

```
# 12:45pm: AMS cleanup (15 min before collection)
45 12 * * * cd /root/Mining-Guardian && venv/bin/python scripts/cleanup_ams_logs.py

# 1pm: Direct log collection
0 13 * * * cd /root/Mining-Guardian && venv/bin/python scripts/direct_collect_logs.py
```

---

## Script Location

/root/Mining-Guardian/scripts/direct_collect_logs.py

---

## Database Table

```sql
CREATE TABLE miner_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collected_at  TEXT NOT NULL,
    miner_id      TEXT NOT NULL,
    model         TEXT,
    health_status TEXT,
    log_file      TEXT NOT NULL,
    content       TEXT NOT NULL
);
```

---

## Supported Miners

| Firmware | Supported | Notes |
|----------|-----------|-------|
| BiXBiT | Yes | Full support |
| Stock Bitmain | No | Returns 404 on create_log_backup |
| Auradine | No | Different log format (not bzip2) |

---

## Error Codes

| Error | Meaning | Action |
|-------|---------|--------|
| create:404 | Stock firmware, no backup endpoint | Exclude from collection |
| download:404 | Log file not found | Retry or skip |
| conn err | Miner offline/unreachable | Check network |
| not a bzip2 file | Different firmware format | Exclude from collection |
| timeout | Slow response | Increase timeout or retry |

---

## Troubleshooting

### Logs too large
- Check if date filtering is working (look for [LOG FILTER: header)
- Verify target_date is being passed to filter_log_content()

### Many miners failing
- Check Tailscale connectivity to ROBS-PC
- Verify ROBS-PC is advertising routes
- Check miner IPs are correct in AMS

### Deep dive still skipping
- Check prompt sizes in deep dive log
- Verify MAX_LOG_CHARS setting (should be 60K)
- Check 45K prompt cap is working
