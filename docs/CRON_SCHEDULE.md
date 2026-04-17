# Mining Guardian — Cron Schedule

**Last Updated:** 2026-04-17

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

## Hourly

| Time | Job | Script |
|------|-----|--------|
| Every hour | Benchmark | tests/run_benchmark.py |

## Key Changes (Apr 17)

- AMS cleanup moved from 10:00 to 12:45 (15 min before collection)
- Log filtering added to direct_collect_logs.py
- 45K prompt cap in daily_deep_dive.py

## Log Files

| Job | Log File |
|-----|----------|
| Knowledge backup | /tmp/knowledge_backup.log |
| Morning briefing | /tmp/morning_briefing.log |
| AMS cleanup | /tmp/ams_cleanup.log |
| Direct log collection | /tmp/direct_log_collection.log |
| Deep dive | /tmp/daily_deep_dive.log |
| Weekly training | /tmp/daily_claude_training.log |
| Refinement chain | /tmp/daily_refinement_chain.log |
