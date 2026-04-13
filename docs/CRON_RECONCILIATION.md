# Cron Schedule Reconciliation

**Created:** April 13, 2026

## Official Cron Schedule (VPS)

From session continuity prompt (current as of Apr 13):

```
0  4  * * *  ai/backup_knowledge.py
0  7  * * *  scripts/morning_briefing.py
0 10  * * *  scripts/cleanup_ams_logs.py
0 13  * * *  scripts/daily_collect_logs.py
0 16  * * *  ai/daily_deep_dive.py
15 16  * * *  scripts/daily_log_failure_report.py
0  0  * * *  ai/weekly_train.py (daily until Apr 25)
0  1  * * *  ai/refinement_chain.py
0  *  * * *  tests/run_benchmark.py (S21 Imm only)
```

## Mac launchd (every 5 min)
- com.bixbit.hvac-collector → pushes HVAC to VPS

## Total: 9 VPS cron + 1 Mac launchd = 10 scheduled jobs

See docs/CRON_SCHEDULE.md for detailed explanations.
