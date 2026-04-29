# Operator Schedules — Bucket 9 §10.7

**Status:** Shipped 2026-04-29 PM (PR #89).

The operator console at `http://localhost:8686/ui` now exposes a **Schedules**
tab. From there the operator picks when each Mac Mini background job runs —
no shell, no cron, no `launchctl` knowledge required. Every in-process daemon
re-reads its row at the top of every loop iteration, so changes take effect
within one cycle without restarting any service.

## Jobs you can retime

| `job_key` | Type | Default | What it controls |
|---|---|---|---|
| `overnight_window` | window | 00:00 → 24:00, every day | The autonomous-decision window for `core/overnight_automation.py`. Outside this window, no AUTO action runs even if the mode selector is `FULL_AUTO`. |
| `ams_alert_poll` | interval | 15 s | How often `api/ams_alert_listener.py` polls the AMS notifications endpoint. |
| `slack_listener_poll` | interval | 15 s | How often `api/slack_approval_listener.py` polls Slack threads for `APPROVE` / `DENY` keywords. |
| `catalog_auto_refresh` | interval | 300 s | How often `api/intelligence_report_api.py` re-reads `unified_miner_index.json` to pick up upstream catalog changes. |

Future jobs slot in by `INSERT` into `system_schedules` plus a small
`get_schedule(...)` call inside the daemon's loop — no schema change.

## Three schedule types

**`window`** — the job runs continuously, but only inside the configured
hours and on the configured days of week. Pick a Start time and an End time
(End = `24:00` is a sentinel meaning "end of day"). Days of week chips let
you, for example, run overnight automation only on weekdays.

**`time_of_day`** — the job runs once per day at the configured hour and
minute, on the configured days. Reserved for future jobs (e.g. once-daily
report generation); none of the four shipped jobs use this type yet.

**`interval`** — the job runs continuously and uses `interval_seconds` as
its sleep cadence. Disabling an interval job has **no effect** at runtime —
to actually stop one of these daemons, the operator must `launchctl unload`
the corresponding plist. The Enabled toggle on `interval` rows is preserved
for forward compatibility but documented here as a no-op.

## Database schema

```sql
CREATE TABLE system_schedules (
    job_key            TEXT PRIMARY KEY,
    enabled            BOOLEAN NOT NULL DEFAULT TRUE,
    schedule_type      TEXT NOT NULL,            -- window | time_of_day | interval
    start_hour         INTEGER,
    start_minute       INTEGER,
    end_hour           INTEGER,                  -- 0..24 (24 = end-of-day)
    end_minute         INTEGER,
    interval_seconds   INTEGER,
    days_of_week       TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6',  -- 0=Mon..6=Sun
    description        TEXT,
    category           TEXT,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by         TEXT
);
```

Migration `005_system_schedules.sql` is idempotent. It seeds the four shipped
job rows with their current defaults using `ON CONFLICT (job_key) DO NOTHING`
— re-running it never clobbers operator changes.

## Endpoints

All endpoints require the `X-Internal-Secret` header (same as `/approve`,
`/deny`, `/mode`).

- `GET /schedules` — return every row with description and category.
- `POST /schedules/{job_key}` — UPSERT one row. Body:

  ```json
  {
    "schedule_type": "window",
    "enabled": true,
    "start_hour": 22, "start_minute": 0,
    "end_hour": 6,    "end_minute": 0,
    "days_of_week": "0,1,2,3,4",
    "operator": "bobby"
  }
  ```

  Application-layer validation rejects invalid hours, minutes, intervals
  outside `[5, 86400]` seconds, and unknown `schedule_type`s.

## Failure modes

- **DB unreachable:** `get_schedule()` returns the in-code default (mirrors
  the migration seed exactly). Daemons keep running with their shipped
  defaults — exactly the behaviour they had before §10.7 existed.
- **Row missing:** same fallback as DB-unreachable.
- **Corrupt `days_of_week`:** falls back to all-days.
- **`interval_seconds < 5`:** rejected at write time and at read time.

The design choice everywhere is **fail open** — never silently halt the
fleet because of a transient setting issue.

## Operator-side ship steps (after merge)

```bash
cd ~/Documents/GitHub/Mining-Guardian
git pull --ff-only
psql -U guardian_app -d mining_guardian -f migrations/005_system_schedules.sql
sudo launchctl kickstart -k system/com.miningguardian.approvalapi          # picks up /schedules endpoints
sudo launchctl kickstart -k system/com.miningguardian.overnight-automation  # picks up window read
sudo launchctl kickstart -k system/com.miningguardian.alerts               # picks up interval read
sudo launchctl kickstart -k system/com.miningguardian.slack-listener       # picks up interval read
sudo launchctl kickstart -k system/com.miningguardian.intelligence-report  # picks up catalog refresh
```

After the kickstart, future schedule edits in the GUI **do not** require
another kickstart — each daemon hot-reloads.

## Limitations / future work

- **VPS cron jobs** (the 9 entries in `docs/CRON_RECONCILIATION.md`) are
  out of scope for this PR. They run on `root@srv1549463`, not the Mac
  Mini. A follow-up will let the customer app push schedule changes to
  the VPS over SSH or ship a schedule-daemon to replace cron.
- **`time_of_day` jobs** have no consumer in the v1 ship set — the schema
  and validation are in place so the next job (likely a daily intelligence
  report trigger) can use them without code changes.
- **No audit log** of schedule changes yet. `updated_at` and `updated_by`
  capture the latest, not the history. If the operator wants a full
  history, we can write to `action_audit_log` on every UPSERT in a
  follow-up PR.
