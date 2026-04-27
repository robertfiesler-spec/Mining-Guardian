# OpenClaw audit — 2026-04-23

## TL;DR

OpenClaw is running on the VPS (Docker container, 43+ hours uptime) but is
**effectively dead code** for Mining Guardian. It can be removed without
breaking anything. Bobby's instinct was correct.

## What I found

### 1. Mining-guardian agent inside OpenClaw

- Session directory: `/docker/openclaw-5b5o/data/.openclaw/agents/mining-guardian/`
- Most recent activity: April 23, 2026 at 04:03 UTC (today's HEARTBEAT ping)
- Content of that session: OpenClaw sent "Read HEARTBEAT.md if anything needs
  attention. Otherwise reply HEARTBEAT_OK." The agent replied "HEARTBEAT_OK"
  and that was the entire interaction.
- No user-initiated sessions in weeks. No events routed to the agent.

### 2. OpenClaw Socket Mode for Slack

- Container holds an active Slack Socket Mode connection.
- Logs show only health-monitor reconnect cycles every 35 minutes
  ("stale-socket" → reconnect). Zero evidence of real Slack events being
  received and routed to the mining-guardian agent or to any Python service.

### 3. Python codebase integrations

File: `notifiers/openclaw_notifier.py`
- `OpenClawNotifier` class with `send_scan(miners, issues)` method
- POSTs to `http://127.0.0.1:18789/hooks` (OpenClaw webhook gateway)
- **Port 18789 is not listening** — only 58910 (OpenClaw's current port) is.
- When `webhook_url` is `None` or unset, the method returns silently:
  `if not self.webhook_url: return`

File: `config.json` (live production config)
- **No `openclaw_webhook_url` key present.**
- `OpenClawNotifier` is instantiated with `webhook_url=None` every time.
- Every `send_scan()` call is therefore a silent no-op.

File: `core/overnight_automation.py`
- `notify_openclaw(summary)` POSTs to the same webhook URL.
- Same outcome — silent no-op because config has no URL.

File: `api/slack_approval_listener.py`
- Docstring: "Socket Mode is owned by OpenClaw — we use polling instead of
  Bolt to avoid conflicts."
- This is historically true but the polling workaround is no longer needed
  if OpenClaw is removed. Could switch to Bolt/Socket Mode as a follow-up.

## Effective behavior

Mining Guardian currently:
- Does NOT send scan summaries to OpenClaw (silent no-op)
- Does NOT send overnight summaries to OpenClaw (silent no-op)
- Does NOT receive Slack events through OpenClaw
- Does NOT invoke the mining-guardian agent except through OpenClaw's
  own daily internal HEARTBEAT_OK self-check

OpenClaw is burning Docker resources and a daily Qwen inference for
essentially nothing.

## Safe removal checklist (for a future session, NOT today)

1. `cd /docker/openclaw-5b5o && docker compose down`
2. Optional: `docker volume rm` on the openclaw volumes if sure we don't
   want session history
3. Edit `core/mining_guardian.py`:
   - Remove `from notifiers.openclaw_notifier import OpenClawNotifier` (line 74)
   - Remove `self.notifier = OpenClawNotifier(config.openclaw_webhook_url)` (line 84)
   - Remove `openclaw_webhook_url` key from the example config template (line 2608)
4. Edit `core/overnight_automation.py`:
   - Remove `notify_openclaw()` function (lines 375-405)
   - Remove the call site at line 477
5. Delete `notifiers/openclaw_notifier.py`
6. Edit `core/models.py`:
   - Remove `openclaw_webhook_url` field from config dataclass (lines 63, 95)
7. Delete `tests/test_openclaw_notifier.py`
8. Update `tests/conftest.py` if it references OpenClaw
9. Run tests (should still pass since nothing real used the notifier)
10. Commit: `refactor: remove dead OpenClaw integration`

**Bigger optional follow-up**: once OpenClaw is out, switch
`slack_approval_listener.py` and `slack_command_handler.py` from REST
polling to Bolt/Socket Mode for Slack. More efficient. Not required.

## Why not do this today

Mid-Postgres-migration. Services stopped. Don't pile a second operational
change on top of an in-flight one. Finish Phase 7, restart services on
Postgres, verify everything works, THEN come back to OpenClaw removal
as a fresh focused task.
