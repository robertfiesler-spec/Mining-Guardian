# Mining Guardian — Cron Schedule

**Last Updated:** 2026-04-18

---

## Daily Schedule

| Time | Job | Script | Purpose |
|------|-----|--------|---------|
| 12:45 PM | AMS Cleanup | cleanup_ams_logs.py | Clear AMS logs before collection |
| 1:00 PM | Log Collection | direct_collect_logs.py | Collect logs directly from miners |
| 4:00 PM | Deep Dive (Pass 1) | daily_deep_dive.py | Qwen analyzes each miner |
| 4:15 PM | Log Failure Report | daily_log_failure_report.py | Report failed log collections |
| 3:00 AM | Claude Training (Pass 2) | weekly_train.py | Claude cohort analysis |
| 4:00 AM | Refinement (Pass 3+4) | refinement_chain.py | Qwen reflection + Claude merge |
| 4:00 AM | Knowledge Backup | backup_knowledge.py | Backup knowledge.json |
| 7:00 AM | Morning Briefing | morning_briefing.py | Daily summary to Slack |
| Hourly | Benchmark | run_benchmark.py | Performance tracking |

---

## Cron Commands

```bash
# AMS cleanup (15 min before direct collection)
45 12 * * * cd /root/Mining-Gaurdian && PYTHONPATH=/root/Mining-Gaurdian /root/Mining-Gaurdian/venv/bin/python scripts/cleanup_ams_logs.py >> /tmp/ams_cleanup.log 2>&1

# Direct log collection from miners
0 13 * * * cd /root/Mining-Gaurdian && PYTHONPATH=/root/Mining-Gaurdian /root/Mining-Gaurdian/venv/bin/python scripts/direct_collect_logs.py >> /tmp/direct_log_collection.log 2>&1

# Pass 1 - Qwen daily deep dive
0 16 * * * cd /root/Mining-Gaurdian && PYTHONPATH=/root/Mining-Gaurdian /root/Mining-Gaurdian/venv/bin/python ai/daily_deep_dive.py >> /tmp/daily_deep_dive.log 2>&1

# Daily log failure report
15 16 * * * cd /root/Mining-Gaurdian && PYTHONPATH=/root/Mining-Gaurdian /root/Mining-Gaurdian/venv/bin/python scripts/daily_log_failure_report.py >> /tmp/daily_log_failure_report.log 2>&1

# Pass 2 - Claude cohort training (moved from midnight to 3 AM)
0 3 * * * cd /root/Mining-Gaurdian && PYTHONPATH=/root/Mining-Gaurdian /root/Mining-Gaurdian/venv/bin/python ai/weekly_train.py >> /tmp/daily_claude_training.log 2>&1

# Pass 3+4 - Qwen reflection + Claude merge (moved from 1 AM to 4 AM)
0 4 * * * cd /root/Mining-Gaurdian && PYTHONPATH=/root/Mining-Gaurdian /root/Mining-Gaurdian/venv/bin/python ai/refinement_chain.py >> /tmp/daily_refinement_chain.log 2>&1

# Knowledge backup
0 4 * * * cd /root/Mining-Gaurdian && PYTHONPATH=/root/Mining-Gaurdian /root/Mining-Gaurdian/venv/bin/python ai/backup_knowledge.py >> /tmp/knowledge_backup.log 2>&1

# Morning briefing
0 7 * * * cd /root/Mining-Gaurdian && PYTHONPATH=/root/Mining-Gaurdian /root/Mining-Gaurdian/venv/bin/python scripts/morning_briefing.py >> /tmp/morning_briefing.log 2>&1

# Hourly benchmark
0 * * * * cd /root/Mining-Gaurdian && source venv/bin/activate && PYTHONPATH=/root/Mining-Gaurdian python3 tests/run_benchmark.py >> /var/log/benchmark.log 2>&1
```

---

## Schedule Changes Log

### 2026-04-18
- **Claude training:** Midnight → 3 AM
- **Refinement chain:** 1 AM → 4 AM
- **Reason:** Deep dive takes ~110 min per miner, needs time to complete before next jobs

### 2026-04-17
- **AMS cleanup:** 10 AM → 12:45 PM (15 min before log collection)

---

## Notes

- Deep dive uses Qwen (local LLM on ROBS-PC RTX 4090)
- Claude training uses Claude API (cloud)
- They can run in parallel since different resources
- Moved to 3 AM/4 AM to give deep dive buffer time

