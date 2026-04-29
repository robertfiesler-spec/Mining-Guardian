-- migrations/004_system_settings.sql
-- Bucket 9 (§10.1/§10.2) — system_settings key/value store for the Web GUI
--
-- Creates a small generic settings table so the operator-facing Web GUI
-- (approval_api.py :8686 /ui) can persist the global automation mode —
-- FULL_AUTO | SEMI_AUTO | MANUAL — without requiring a new bespoke table
-- every time we add an operator-controllable knob.
--
-- Design notes
-- ------------
-- 1. Generic key/value: `key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMPTZ,
--    updated_by TEXT`. Future knobs (approval_timeout_seconds, slack_muted_until,
--    etc.) slot in here without new migrations.
-- 2. `updated_by` is for audit trail — every mutation records who flipped it.
-- 3. Seeds a single row for `automation_mode` defaulting to `FULL_AUTO` so the
--    existing overnight_automation.py behavior is preserved on first deploy.
-- 4. Idempotent: CREATE TABLE IF NOT EXISTS, ON CONFLICT DO NOTHING on seed.
-- 5. No cross-schema fan-out — stays in `public`, simple grants.

CREATE TABLE IF NOT EXISTS system_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by  TEXT NOT NULL DEFAULT 'system'
);

COMMENT ON TABLE system_settings IS
    'Generic key/value store for operator-controllable knobs exposed by the Web GUI on :8686. Bucket 9 §10.1/§10.2.';

COMMENT ON COLUMN system_settings.key IS
    'Well-known setting name, e.g. automation_mode.';
COMMENT ON COLUMN system_settings.value IS
    'Setting value as a string. Application layer parses/validates.';
COMMENT ON COLUMN system_settings.updated_by IS
    'Operator identifier (slack user id or "web_gui:<name>") that made the last change.';

-- Seed the default automation_mode so behavior is preserved on first deploy.
INSERT INTO system_settings (key, value, updated_by)
VALUES ('automation_mode', 'FULL_AUTO', 'system')
ON CONFLICT (key) DO NOTHING;
