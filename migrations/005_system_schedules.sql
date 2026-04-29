-- migrations/005_system_schedules.sql
--
-- Mining Guardian — Bucket 9 §10.7 — Operator-controlled schedule table.
--
-- Lets operators retime in-process daemons (overnight window, intelligence
-- report, scanner intervals, etc.) from the Web GUI without restarting
-- launchd services. Each daemon reads its row at the top of every loop
-- iteration so changes hot-reload within one cycle.
--
-- Design notes:
--   * Generic enough that future jobs slot in by INSERT, no schema change.
--   * Three schedule_type values cover every existing in-process job:
--       window       — start_hour/start_minute → end_hour/end_minute, days_of_week
--       time_of_day  — start_hour/start_minute, days_of_week (run once per day)
--       interval     — interval_seconds (poll cadence)
--   * Application layer enforces value ranges. DB stores the raw values.
--   * `enabled=FALSE` lets operator pause a job without losing the schedule.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS system_schedules (
    job_key            TEXT PRIMARY KEY,
    enabled            BOOLEAN NOT NULL DEFAULT TRUE,
    schedule_type      TEXT NOT NULL CHECK (schedule_type IN ('window', 'time_of_day', 'interval')),
    start_hour         INTEGER CHECK (start_hour BETWEEN 0 AND 23),
    start_minute       INTEGER CHECK (start_minute BETWEEN 0 AND 59),
    end_hour           INTEGER CHECK (end_hour BETWEEN 0 AND 24),
    end_minute         INTEGER CHECK (end_minute BETWEEN 0 AND 59),
    interval_seconds   INTEGER CHECK (interval_seconds BETWEEN 5 AND 86400),
    days_of_week       TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6',
    description        TEXT,
    category           TEXT,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by         TEXT
);

CREATE INDEX IF NOT EXISTS idx_system_schedules_enabled ON system_schedules(enabled);
CREATE INDEX IF NOT EXISTS idx_system_schedules_category ON system_schedules(category);

-- Seed the five Mac Mini in-process jobs with their current hard-coded defaults.
-- ON CONFLICT ensures re-running this migration never clobbers operator changes.

INSERT INTO system_schedules
    (job_key, enabled, schedule_type, start_hour, start_minute, end_hour, end_minute,
     interval_seconds, days_of_week, description, category, updated_by)
VALUES
    ('overnight_window', TRUE, 'window', 0, 0, 24, 0, NULL,
     '0,1,2,3,4,5,6', 'Autonomous decision window for overnight automation',
     'overnight', 'migration_005'),
    ('ams_alert_poll', TRUE, 'interval', NULL, NULL, NULL, NULL, 15,
     '0,1,2,3,4,5,6', 'AMS alert listener polling interval',
     'polling', 'migration_005'),
    ('slack_listener_poll', TRUE, 'interval', NULL, NULL, NULL, NULL, 15,
     '0,1,2,3,4,5,6', 'Slack approval listener polling interval',
     'polling', 'migration_005'),
    ('catalog_auto_refresh', TRUE, 'interval', NULL, NULL, NULL, NULL, 300,
     '0,1,2,3,4,5,6', 'Intelligence catalog auto-reload poll interval',
     'polling', 'migration_005')
ON CONFLICT (job_key) DO NOTHING;
