# Mining Guardian Cron Schedule

**Updated:** 2026-04-16

## Active Cron Jobs

| Time | Job | Script | Description |
|------|-----|--------|-------------|
| 04:00 | Knowledge Backup | `backup_knowledge.py` | Backup knowledge.json to GitHub |
| 07:00 | Morning Briefing | `morning_briefing.py` | Slack briefing with fleet status |
| 10:00 | AMS Cleanup | `cleanup_ams_logs.py` | Delete old logs from AMS to prevent queue overflow |
| 13:00 | **Direct Log Collection** | `direct_collect_logs.py` | Download today's logs directly from miners via Tailscale |
| 16:00 | Daily Deep Dive | `daily_deep_dive.py` | Qwen analysis of all miners + fleet synthesis |
| 00:00 | Weekly Training | `weekly_train.py` | Claude cohort training (runs Sunday only) |
| 01:00 | Refinement Chain | `refinement_chain.py` | Qwen reflection + Claude merge |
| Hourly | Benchmark | `run_benchmark.py` | Hourly performance benchmark |

## Full Crontab

```cron
# Knowledge backup at 4am
0  4  * * *   cd /root/Mining-Gaurdian && /root/Mining-Gaurdian/venv/bin/python scripts/backup_knowledge.py >> /tmp/backup_knowledge.log 2>&1

# Morning briefing at 7am
0  7  * * *   cd /root/Mining-Gaurdian && /root/Mining-Gaurdian/venv/bin/python scripts/morning_briefing.py >> /tmp/morning_briefing.log 2>&1

# AMS log cleanup at 10am - prevents queue overflow
0 10  * * *   cd /root/Mining-Gaurdian && /root/Mining-Gaurdian/venv/bin/python scripts/cleanup_ams_logs.py >> /tmp/ams_cleanup.log 2>&1

# Direct log collection at 1pm - bypasses AMS, hits miners directly via Tailscale
0 13  * * *   cd /root/Mining-Gaurdian && /root/Mining-Gaurdian/venv/bin/python scripts/direct_collect_logs.py >> /tmp/direct_log_collection.log 2>&1

# Daily deep dive at 4pm
0 16  * * *   cd /root/Mining-Gaurdian && /root/Mining-Gaurdian/venv/bin/python ai/daily_deep_dive.py >> /tmp/daily_deep_dive.log 2>&1

# Weekly training at midnight Sunday
0  0  * * 0   cd /root/Mining-Gaurdian && /root/Mining-Gaurdian/venv/bin/python ai/weekly_train.py >> /tmp/weekly_train.log 2>&1

# Refinement chain at 1am
0  1  * * *   cd /root/Mining-Gaurdian && /root/Mining-Gaurdian/venv/bin/python ai/refinement_chain.py >> /tmp/refinement_chain.log 2>&1

# Hourly benchmark
0  *  * * *   cd /root/Mining-Gaurdian && /root/Mining-Gaurdian/venv/bin/python scripts/run_benchmark.py >> /tmp/benchmark.log 2>&1
```

## Log Files

| Job | Log Location |
|-----|--------------|
| Knowledge Backup | `/tmp/backup_knowledge.log` |
| Morning Briefing | `/tmp/morning_briefing.log` |
| AMS Cleanup | `/tmp/ams_cleanup.log` |
| Direct Log Collection | `/tmp/direct_log_collection.log` |
| Daily Deep Dive | `/tmp/daily_deep_dive.log` |
| Weekly Training | `/tmp/weekly_train.log` |
| Refinement Chain | `/tmp/refinement_chain.log` |
| Benchmark | `/tmp/benchmark.log` |

## Slack Notifications

| Job | Channel |
|-----|---------|
| Morning Briefing | `#mg-ai-reports` |
| Direct Log Collection | `#mg-logs` |
| Daily Deep Dive | `#mg-ai-reports` |
| Deep Dive Complete | Bobby DM |

## Dependencies

### Network
- **Tailscale** - Required for direct log collection
- **ROBS-PC** - Must be online to route 192.168.188.0/24

### AI
- **Qwen 32B** on ROBS-PC (port 11434) - For daily deep dive
- **Claude API** - For weekly training only

## Timezone

All times are in **CDT (UTC-5)**.

## Deprecated

| Job | Replaced By | Date |
|-----|-------------|------|
| `daily_collect_logs.py` (AMS) | `direct_collect_logs.py` | 2026-04-16 |

The old AMS-based log collection is deprecated due to:
- Queue overflow issues
- 30+ minute collection times
- Frequent failures (0% success rate on some days)

The new direct collection completes in ~2 minutes with 80%+ success rate.
