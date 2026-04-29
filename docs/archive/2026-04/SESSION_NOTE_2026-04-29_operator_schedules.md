# Session Note 2026-04-29 — Operator Schedules (Bucket 9 §10.7)

**Filed:** 2026-04-29 PM, third session of the day after PRs #85 / #86 / #87 / #88 shipped.

## What this PR does

Adds operator-controlled scheduling to the Web GUI shipped in PR #88. The
operator can now retime `overnight_window`, `ams_alert_poll`,
`slack_listener_poll`, and `catalog_auto_refresh` from the **Schedules** tab
at `http://localhost:8686/ui` — no shell, no cron syntax, no `launchctl`.

## Why this scope, this size

Bobby asked: "also need to be able to set schedules, run this at this time
or run that at this time etc". He confirmed three specific decisions in a
follow-up:

1. **Scope:** all Mac Mini in-process daemons; **VPS cron jobs are out**
   ("the mac mini isnt using a vps remember"). VPS cron control comes when
   the customer app exists.
2. **Expression:** simple time-of-day + days-of-week pickers, no cron strings.
3. **Apply mode:** hot-reload — daemons re-read the `system_schedules` row
   each loop iteration, mirroring the `system_settings` pattern shipped in
   PR #88.

I also chose to ship §10.7 as its own PR (not bundled with §10.1/§10.2)
because PR #88 was already pushed and tested when Bobby's request arrived.
"One thing at a time" wins over a bigger combined diff.

## Architecture

```
┌────────────────────────────────────┐         ┌─────────────────────────┐
│  approval_ui.html → Schedules tab  │  POST   │  /schedules/{job_key}   │
│  (vanilla JS, time pickers, DOW    │ ──────▶ │  in approval_api.py     │
│   chips, single-file)              │         └─────────────┬───────────┘
└────────────────────────────────────┘                       │
                                                             ▼
┌────────────────────────────────────┐                   ┌─────────────┐
│  Each daemon (overnight, ams,      │   each loop       │  system_    │
│  slack, catalog) calls             │  ──────────────▶  │  schedules  │
│  is_in_window() / get_interval...  │                   │  table      │
└────────────────────────────────────┘                   └─────────────┘
```

Hot-reload is the operator-facing UX promise: "click Save → it just
takes effect within one cycle." The implementation honours it everywhere
because `get_schedule(job_key)` is dirt cheap (one indexed PK lookup) so
calling it every iteration of every daemon is fine.

## Why a separate `system_schedules` table

The §10.2 mode selector lives in `system_settings` (single key/value pair).
That table is fine for one-knob settings but wrong for schedules — schedules
have structured columns (start/end times, days, intervals) that we want to
constrain at the schema level (`CHECK (start_hour BETWEEN 0 AND 23)`).
Forcing schedule rows into a flat key/value table would mean either lots
of small rows per job (`overnight_window.start_hour`,
`overnight_window.start_minute`, …) or JSON-in-text with no DB-level
validation. A purpose-built table is cleaner and the schema is small (1
table, 12 columns).

## Why fail open everywhere

Same reasoning as §10.2: defaulting to "stop running" on any error
silently halts the fleet. Defaulting to in-code defaults preserves the
pre-§10.7 behaviour exactly. Logged as warnings, never silenced.

## Why no `interval_seconds` enforcement of `enabled=False`

Interval daemons don't have a clean "not running" state — they're either
in their loop or they're not running at all. Disabling the schedule row
would mean the interval drops to None, which the daemon then has to
interpret as "use default" or "halt." Either way, the operator hasn't
actually stopped the daemon — it still polls at *some* rate. The honest
answer is: to stop these daemons, `launchctl unload` is required. The
toggle is preserved for forward compatibility (e.g., a future scheduler
might honour it) and documented as a no-op.

## Files

| File | Status | What it does |
|---|---|---|
| `migrations/005_system_schedules.sql` | NEW | `system_schedules` table + 4-row seed. Idempotent. |
| `api/system_schedules.py` | NEW | DB layer + `get_schedule`, `is_in_window`, `should_run_today`, `get_interval_seconds`, `update_schedule`. Fails open. |
| `api/approval_api.py` | MODIFIED | + `GET /schedules`, `POST /schedules/{job_key}`. |
| `api/static/approval_ui.html` | MODIFIED | + Schedules section: time pickers, day chips, save button per card. |
| `core/overnight_automation.py` | MODIFIED | `is_overnight_window()` consults schedule first, falls back to constants. |
| `api/intelligence_report_api.py` | MODIFIED | catalog auto-refresh thread reads interval from schedule. |
| `api/ams_alert_listener.py` | MODIFIED | poll loop reads `ams_alert_poll.interval_seconds` each cycle. |
| `api/slack_approval_listener.py` | MODIFIED | run loop reads `slack_listener_poll.interval_seconds` each cycle. |
| `tests/test_system_schedules.py` | NEW | 23 tests, fully mocked. |
| `docs/OPERATOR_SCHEDULES.md` | NEW | Full operator guide: jobs, types, DB schema, endpoints, failure modes, ship steps. |
| `docs/MG_UNIFIED_TODO_LIST.md` | MODIFIED | Adds §10.7 row, marks ✅ DONE 2026-04-29 PM. |

## Test results

```
PYTHONPATH=. python3 -m pytest -xvs tests/test_system_schedules.py
============================== 23 passed in 0.06s ==============================
```

Plus regression check on §10.1/§10.2 — 10 passed. No regression.

## How to ship

After merge, on the Mac Mini:

```bash
cd ~/Documents/GitHub/Mining-Guardian
git pull --ff-only
psql -U guardian_app -d mining_guardian -f migrations/005_system_schedules.sql
sudo launchctl kickstart -k system/com.miningguardian.approvalapi
sudo launchctl kickstart -k system/com.miningguardian.overnight-automation
sudo launchctl kickstart -k system/com.miningguardian.alerts
sudo launchctl kickstart -k system/com.miningguardian.slack-listener
sudo launchctl kickstart -k system/com.miningguardian.intelligence-report
```

Browser at `http://localhost:8686/ui` → new Schedules section with four cards.

## Backward compatibility

- Existing `WINDOW_START_HOUR / WINDOW_END_HOUR` constants in
  `core/overnight_automation.py` are still read as the fallback when the
  schedule helper is unavailable — they will never silently disappear.
- Existing `POLL_INTERVAL` and `self.poll_interval` constants are still
  honoured when `system_schedules` is unavailable.
- Pre-migration deployments behave exactly like the pre-§10.7 codebase.

## Cross-references

- §10.7 in `docs/MG_UNIFIED_TODO_LIST.md`
- §10.1 / §10.2 already shipped in PR #88 (unmerged at time of writing)
- `docs/OPERATOR_SCHEDULES.md` for the full operator-facing guide
- `docs/CRON_RECONCILIATION.md` lists the VPS cron jobs deferred to a future PR
