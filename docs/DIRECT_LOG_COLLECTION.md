# Direct Miner Log Collection

**Created:** 2026-04-16  
**Status:** Production (replaces AMS-based collection)

## Overview

Direct log collection bypasses AMS entirely by hitting each BiXBiT miner directly via Tailscale. This is significantly faster and more reliable than the AMS queue-based approach.

## Performance Comparison

| Method | Miners | Duration | Success Rate |
|--------|--------|----------|--------------|
| AMS (old) | 34 | 30+ min | 0% (queue overflow) |
| Direct (new) | 49 | ~107s | 80% (39/49) |

## How It Works

### Authentication
- **Protocol:** HTTP Digest Auth
- **Credentials:** `root:root` (BiXBiT firmware standard)
- **Access:** Via Tailscale subnet routing through ROBS-PC

### API Flow

1. **Trigger log backup:**
   ```
   POST http://<miner_ip>/cgi-bin/create_log_backup.cgi
   Content-Type: application/json
   Body: ["/2026-04/16"]  # Format: /YYYY-MM/DD
   
   Response: {"stats":"success","code":"L000","msg":"Antminer_S19j_Pro_2026-04-16.tar.bz2"}
   ```

2. **Download the archive:**
   ```
   GET http://<miner_ip>/log/<filename>
   
   Returns: tar.bz2 file containing:
   - nvdata/YYYY-MM/DD/cglog_init_*/
     - miner.log (main log)
     - temp.log
     - power.log
     - api.log
     - dev.log
     - messages
     - status.log
     - autotune.log
   ```

3. **Extract and store:**
   - Extract `miner.log` from tar.bz2
   - Store in `miner_logs` table

## Cron Schedule

```
# Direct log collection at 1pm - bypasses AMS, hits miners directly via Tailscale
0 13 * * * cd /root/Mining-Gaurdian && /root/Mining-Gaurdian/venv/bin/python scripts/direct_collect_logs.py >> /tmp/direct_log_collection.log 2>&1
```

## Script Location

`/root/Mining-Gaurdian/scripts/direct_collect_logs.py`

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

## Supported Miners

| Firmware | Supported | Notes |
|----------|-----------|-------|
| BiXBiT | ✅ Yes | Uses `create_log_backup.cgi` |
| Stock Bitmain | ❌ No | Different API (returns 404) |
| Auradine | ❌ No | Different firmware entirely |
| S21 Immersion | ❌ No | Often offline, different API |

## Failure Modes

| Error | Meaning | Action |
|-------|---------|--------|
| `create:404` | Stock firmware | Skip (not BiXBiT) |
| `conn err` | Miner offline/unreachable | Skip |
| `timeout` | Slow response | Retry next run |
| `not bzip2` | Wrong response format | Check firmware |
| `download:404` | Log file not ready | Retry next run |

## Slack Notifications

Reports to `#mg-logs` channel with:
- ✅ Success count
- ⚠️ Failure count
- Duration
- List of failures (if ≤10)

## Network Requirements

- **Tailscale** must be running on VPS
- **ROBS-PC** must be online (advertises 192.168.188.0/24)
- Miners reachable on port 80

## Advantages Over AMS

1. **No queue overflow** - Direct to miner, no AMS bottleneck
2. **Faster** - 107s vs 30+ min
3. **More reliable** - No dependency on AMS export jobs
4. **Simpler** - One request to trigger, one to download
5. **Today's logs only** - No historical log accumulation

## Logs

- **Collection log:** `/tmp/direct_log_collection.log`
- **Slack report:** Posted to `#mg-logs`

## Manual Run

```bash
cd /root/Mining-Gaurdian
source venv/bin/activate
python3 scripts/direct_collect_logs.py
```
