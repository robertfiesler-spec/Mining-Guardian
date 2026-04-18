# Mining Guardian — Cron Schedule

**Last Updated:** 2026-04-18

---

## Schedule (America/Chicago CDT)

| Time | Job | Script | Notes |
|------|-----|--------|-------|
| 04:00 | Knowledge Backup | ai/backup_knowledge.py | Commits to GitHub |
| 07:00 | Morning Briefing | scripts/morning_briefing.py | Slack fleet summary |
| 12:45 | AMS Log Cleanup | scripts/cleanup_ams_logs.py | 15 min before collection |
| 13:00 | Direct Log Collection | scripts/direct_collect_logs.py | BiXBiT miner logs |
| 16:00 | Daily Deep Dive | ai/daily_deep_dive.py | Qwen per-miner analysis |
| 16:15 | Log Failure Report | scripts/daily_log_failure_report.py | Slack report |
| 00:00 | Claude Training | ai/weekly_train.py | Cohort + fingerprints |
| 01:00 | Refinement Chain | ai/refinement_chain.py | Qwen + Claude merge |
| Hourly | Benchmark | tests/run_benchmark.py | Performance metrics |

---

## PYTHONPATH Fix (2026-04-18)

All cron jobs now include `PYTHONPATH=/root/Mining-Gaurdian` to fix module import errors.

**Before (broken):**
```
cd /root/Mining-Gaurdian && /root/.../python ai/weekly_train.py
```

**After (fixed):**
```
cd /root/Mining-Gaurdian && PYTHONPATH=/root/Mining-Gaurdian /root/.../python ai/weekly_train.py
```

---

## Dependencies

- **12:45 cleanup -> 13:00 collection:** AMS queue cleared before collection
- **13:00 collection -> 16:00 deep dive:** Fresh logs for analysis
- **16:00 deep dive -> 00:00 training:** Deep dive must complete (~6-10h)
- **00:00 training -> 01:00 refinement:** Training outputs feed refinement

---

## Log Files

| Job | Log |
|-----|-----|
| Knowledge backup | /tmp/knowledge_backup.log |
| Morning briefing | /tmp/morning_briefing.log |
| AMS cleanup | /tmp/ams_cleanup.log |
| Log collection | /tmp/direct_log_collection.log |
| Deep dive | /tmp/daily_deep_dive.log |
| Log failure report | /tmp/daily_log_failure_report.log |
| Claude training | /tmp/daily_claude_training.log |
| Refinement chain | /tmp/daily_refinement_chain.log |
| Benchmark | /var/log/benchmark.log |

---

## Manual Run Commands

```bash
# Weekly training (with PYTHONPATH)
cd /root/Mining-Gaurdian && source venv/bin/activate && \
  PYTHONPATH=/root/Mining-Gaurdian python3 ai/weekly_train.py

# Refinement chain
cd /root/Mining-Gaurdian && source venv/bin/activate && \
  PYTHONPATH=/root/Mining-Gaurdian python3 ai/refinement_chain.py

# Deep dive
cd /root/Mining-Gaurdian && source venv/bin/activate && \
  PYTHONPATH=/root/Mining-Gaurdian python3 ai/daily_deep_dive.py

# Log collection
cd /root/Mining-Gaurdian && source venv/bin/activate && \
  PYTHONPATH=/root/Mining-Gaurdian python3 scripts/direct_collect_logs.py
```

---

## Note

Remove or reduce daily Claude training after ~April 25, 2026 — return to Sunday-only schedule.
