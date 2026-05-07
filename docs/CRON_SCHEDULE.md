# Mining Guardian — Cron Schedule

**Last Updated:** 2026-05-04 (D-18 Gap 4 / P-007 — converted from cron to launchd)

> **2026-05-04 update (D-18 Gap 4 / P-007):** The 11 entries below are no
> longer installed as crontab entries on the Mac Mini. They are launchd
> plists at `/Library/LaunchDaemons/com.miningguardian.scheduled.*.plist`,
> bootstrapped by `postinstall.sh::step_install_scheduled_plists_and_bootstrap`
> (`.pkg` install path) or by `scripts/setup.sh::phase_10_scheduled`
> (operator install path). Both paths invoke the same 11 plist files
> committed at `installer/macos-pkg/resources/launchd/scheduled/`. One
> generic launcher (`scheduled_job_launcher.sh`) under
> `${INSTALL_ROOT}/bin/` sources `.env`, dispatches by file extension,
> and stamps `${INSTALL_ROOT}/logs/scheduled/<task_key>.last-run.json`
> for the operator console.
>
> The cron table below remains the canonical source of truth for fire
> times, entrypoints, and intent. The `Cron Commands` section is
> retained as historical reference — it documents the VPS-era schedule
> that was the source for the launchd plist set.

---

## Daily Schedule

| Time | Job | Script | Purpose |
|------|-----|--------|---------|
| 12:00 AM | Claude Training (Pass 2) | weekly_train.py | Claude cohort analysis |
| 1:00 AM | Refinement (Pass 3+4) | refinement_chain.py | Qwen reflection + Claude merge |
| 3:30 AM | DB Maintenance | db_maintenance.sh | WAL checkpoint, vacuum, integrity |
| 4:00 AM | Knowledge Backup | backup_knowledge.py | Backup knowledge.json |
| 7:00 AM | Morning Briefing | morning_briefing.py | Daily summary to Slack |
| 8:00 AM | Operator Review | daily_operator_review.py | Generate operator review report |
| 12:45 PM | AMS Cleanup | cleanup_ams_logs.py | Clear AMS logs before collection |
| 1:00 PM | Log Collection | direct_collect_logs.py | Collect logs directly from miners |
| 4:00 PM | Deep Dive (Pass 1) | daily_deep_dive.py | Qwen analyzes each miner |
| 4:15 PM | Log Failure Report | daily_log_failure_report.py | Report failed log collections |
| Hourly | Benchmark | run_benchmark.py | Performance tracking |

---

## Learning Chain Pipeline

| Pass | Time | Engine | Script | Description |
|------|------|--------|--------|-------------|
| 1 | 4:00 PM | Qwen (GPU) | daily_deep_dive.py | Per-miner analysis with logs |
| 2 | Midnight | Claude API | weekly_train.py | Cohort pattern analysis |
| 3 | 1:00 AM | Qwen (GPU) | refinement_chain.py | Reflection pass |
| 4 | 1:00 AM | Claude API | refinement_chain.py | Final knowledge merge |

---

## Cron Commands

```bash
# Pass 2 - Claude cohort training (midnight)
0 0 * * * cd /root/Mining-Guardian && PYTHONPATH=/root/Mining-Guardian /root/Mining-Guardian/venv/bin/python ai/weekly_train.py >> /tmp/daily_claude_training.log 2>&1

# Pass 3+4 - Qwen reflection + Claude merge (1 AM)
0 1 * * * cd /root/Mining-Guardian && PYTHONPATH=/root/Mining-Guardian /root/Mining-Guardian/venv/bin/python ai/refinement_chain.py >> /tmp/daily_refinement_chain.log 2>&1

# Knowledge backup (4 AM)
0 4 * * * cd /root/Mining-Guardian && PYTHONPATH=/root/Mining-Guardian /root/Mining-Guardian/venv/bin/python ai/backup_knowledge.py >> /tmp/knowledge_backup.log 2>&1

# Morning briefing (7 AM)
0 7 * * * cd /root/Mining-Guardian && PYTHONPATH=/root/Mining-Guardian /root/Mining-Guardian/venv/bin/python scripts/morning_briefing.py >> /tmp/morning_briefing.log 2>&1

# Daily operator review (8 AM)
0 8 * * * cd /root/Mining-Guardian && PYTHONPATH=/root/Mining-Guardian /root/Mining-Guardian/venv/bin/python scripts/daily_operator_review.py >> /tmp/daily_operator_review.log 2>&1

# AMS cleanup (12:45 PM - 15 min before log collection)
45 12 * * * cd /root/Mining-Guardian && PYTHONPATH=/root/Mining-Guardian /root/Mining-Guardian/venv/bin/python scripts/cleanup_ams_logs.py >> /tmp/ams_cleanup.log 2>&1

# Direct log collection from miners (1 PM)
0 13 * * * cd /root/Mining-Guardian && PYTHONPATH=/root/Mining-Guardian /root/Mining-Guardian/venv/bin/python scripts/direct_collect_logs.py >> /tmp/direct_log_collection.log 2>&1

# Pass 1 - Qwen deep dive (4 PM)
0 16 * * * cd /root/Mining-Guardian && PYTHONPATH=/root/Mining-Guardian /root/Mining-Guardian/venv/bin/python ai/daily_deep_dive.py >> /tmp/daily_deep_dive.log 2>&1

# Daily log failure report (4:15 PM)
15 16 * * * cd /root/Mining-Guardian && PYTHONPATH=/root/Mining-Guardian /root/Mining-Guardian/venv/bin/python scripts/daily_log_failure_report.py >> /tmp/daily_log_failure_report.log 2>&1

# Hourly benchmark
0 * * * * cd /root/Mining-Guardian && source venv/bin/activate && PYTHONPATH=/root/Mining-Guardian python3 tests/run_benchmark.py >> /var/log/benchmark.log 2>&1
```

---

## Schedule Changes Log

### 2026-04-21
- **GPU Fixed:** ROBS-PC RTX 4090 now running Qwen properly (~2 sec response vs 75+ min CPU)
- **Claude fallback removed:** All jobs back on Qwen

### 2026-04-18
- **Claude training:** Midnight (was considering 3 AM but kept at midnight)
- **Refinement chain:** 1 AM (was considering 4 AM but kept at 1 AM)

### 2026-04-17
- **AMS cleanup:** 10 AM → 12:45 PM (15 min before log collection)

---

## Infrastructure

### LLM Routing
- **Local Ollama on the Mac Mini:** runs at `http://127.0.0.1:11434` post-cutover
  (D-7 / D-9 / S-13). RAM-tier model pick at install time per D-13:
  `llama3.2:3b` on 16 GB Minis, `qwen2.5:14b-instruct-q4_K_M` on 24 GB+. The
  pre-cutover ROBS-PC RTX 4090 host (Tailscale 100.110.87.1:11434, Qwen
  2.5 32B Q4) is decommissioned for MG; the runtime refuses any
  `OLLAMA_URL` pointing at that range.
- **Claude Sonnet API:** Cloud API for Pass 2 and Pass 4 (API key in Mac Mini `.env`; historical VPS era kept it in VPS `.env`)

### Log Locations
| Log | Path |
|-----|------|
| Deep dive | /tmp/daily_deep_dive.log |
| Claude training | /tmp/daily_claude_training.log |
| Refinement chain | /tmp/daily_refinement_chain.log |
| Log collection | /tmp/direct_log_collection.log |
| Morning briefing | /tmp/morning_briefing.log |
| Operator review | /tmp/daily_operator_review.log |
| Benchmark | /var/log/benchmark.log |

---

## Notes

- All times are CDT (Mac Mini timezone; historical: VPS timezone)
- Deep dive uses Qwen (local GPU) - fastest for per-miner analysis
- Claude used for cohort analysis and final knowledge merge
- Hourly benchmark tracks system performance
- GPU fix verified April 21, 2026 - Qwen responding in ~2 seconds

