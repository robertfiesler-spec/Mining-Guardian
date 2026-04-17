# Mining Guardian — Cron Schedule

**Last Updated:** 2026-04-17

---

## Daily Schedule (America/Chicago timezone)

| Time | Job | Script | Description |
|------|-----|--------|-------------|
| 04:00 | Knowledge Backup | ai/backup_knowledge.py | Backup knowledge.json to GitHub |
| 07:00 | Morning Briefing | scripts/morning_briefing.py | Slack summary of fleet status |
| 12:45 | AMS Log Cleanup | scripts/cleanup_ams_logs.py | Clear AMS log queue (15 min before collection) |
| 13:00 | Direct Log Collection | scripts/direct_collect_logs.py | Collect logs directly from miners (with filtering) |
| 16:00 | Daily Deep Dive | ai/daily_deep_dive.py | Qwen analyzes all miners (45K prompt cap) |
| 16:15 | Log Failure Report | scripts/daily_log_failure_report.py | Report miners with collection failures |
| 00:00 | Weekly Training | ai/weekly_train.py | Claude cohort training |
| 01:00 | Refinement Chain | ai/refinement_chain.py | Qwen reflection + Claude merge |

---

## Hourly Jobs

| Time | Job | Script | Description |
|------|-----|--------|-------------|
| Every hour | Benchmark | tests/run_benchmark.py | Performance benchmarks |

---

## Key Dependencies

- **12:45 cleanup -> 13:00 collection:** AMS queue must be cleared before collection
- **13:00 collection -> 16:00 deep dive:** Fresh logs needed for analysis
- **16:00 deep dive -> 00:00 training:** Deep dive must complete first
- **00:00 training -> 01:00 refinement:** Training outputs feed refinement

---

## Log Files

| Job | Log File |
|-----|----------|
| Knowledge backup | /tmp/knowledge_backup.log |
| Morning briefing | /tmp/morning_briefing.log |
| AMS cleanup | /tmp/ams_cleanup.log |
| Direct log collection | /tmp/direct_log_collection.log |
| Deep dive | /tmp/daily_deep_dive.log |
| Log failure report | /tmp/daily_log_failure_report.log |
| Weekly training | /tmp/daily_claude_training.log |
| Refinement chain | /tmp/daily_refinement_chain.log |
| Benchmark | /var/log/benchmark.log |

---

## Recent Changes

### 2026-04-17
- AMS cleanup moved from 10:00 to 12:45 (15 min before collection)
- Log filtering added to direct_collect_logs.py
- Date filtering added (only keep todays log lines)
- 45K prompt cap confirmed working in daily_deep_dive.py

### 2026-04-16
- Direct log collection implemented (bypasses AMS)
- 45K prompt cap added to daily_deep_dive.py
- Progress monitor and report watcher scripts added

---

## Notes

- All times are CDT (America/Chicago)
- Direct log collection bypasses AMS entirely, hits miners via Tailscale
- Log filtering removes frequency tuning spam (~95% reduction in noise lines)
- Date filtering keeps only todays logs (~80% reduction in size)
- 45K prompt cap skips miners with huge logs to prevent multi-hour analysis
