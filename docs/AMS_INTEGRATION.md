# AMS Integration

**Last updated:** 2026-04-24
**Scope:** evergreen reference. Defines what Mining Guardian DOES and DOES NOT use AMS for.
**See also:** `AMS_API.md` (endpoint reference), `LOG_COLLECTION_ARCHITECTURE.md`, `SESSION_LOG_2026-04-24.md`

---

## AMS summary

**AMS** = BiXBiT's miner management system. Hosted at `api-staging.dev.bixbit.io` (staging) and accessed via:
- REST API over HTTPS for fleet state, notifications, tickets, log archives (server-side only), reboots, PDU control
- WebSocket for real-time miner state feeds (`/miners/list_ws`) and alerts

AMS talks to each miner via a local hub (the Raspberry Pi at `192.168.188.30`) that relays commands and streams state updates back to the cloud. When the hub is down, AMS appears to show all miners offline.

Mining Guardian authenticates once at startup, caches a bearer token, and reuses it across requests.

---

## What we USE AMS for

### 1. Fleet state (primary)

- `ams.get_miners(filters)` — returns the full fleet list via the `/miners/list_ws` WebSocket endpoint with pagination at 50 miners per page. This is the source of truth for the hourly scan loop.
- Each miner record includes: id, ip, mac, model, status, hashrate, maxHashrate, currentProfile, tempChip, tempBoard, mapLocation, firmwareManufacturer, firmwareVersion, errorCodes, pduOutlet info, minerStatus (internal state code).
- Called by `mining_guardian.py::run_once()` once per scan cycle.

### 2. Notifications / alerts (primary)

- `ams.get_notifications("miner")` — pulls AMS alert history (offline-threshold breaches, temp warnings, overheats)
- `ams.get_ticket_list()` / `ams.create_ticket()` — maintenance ticket lifecycle for dead boards and hardware failures
- The mining-guardian-alerts service holds a persistent WebSocket to `/alerts` for 15-second-cadence push notifications on urgent state changes

### 3. Remediation actions (primary)

- `ams.reboot_miner(ids)` — firmware-level restart via AMS control path
- `ams.pdu_power_cycle(outlet_id, off_delay)` — PDU power cycle via AMS (the PDU itself is polled directly for power draw, but the switching goes through AMS)
- `ams.set_miner_profile(miner_id, profile)` — power-profile change (e.g. "120 TH/s - 3400 W")

### 4. Per-miner state polling during restarts

- `ams.get_miner_state(miner_id)` — used by `_wait_for_stable()` during pre/post restart flows to watch for `status=online` and `minerStatus=0` (mining)

### 5. Authentication and session management

- `ams.login()` / `ams._ensure_token()` — OAuth-style bearer token refresh
- Workspace selection: each miner is scoped to an AMS workspace. Mining Guardian authenticates into workspace `USA 188` (workspace id 119).

---

## What we DO NOT use AMS for

### Log collection — explicitly replaced

**This is a hard rule as of 2026-04-24 (commit 8191aa6).** Do NOT call any of these methods in new code:

- `ams.collect_fresh_miner_logs(miner_id)`
- `ams.collect_miner_logs(miner_id)`
- `ams.trigger_log_export(miner_id)`
- `ams.get_log_list(miner_id)`
- `ams.download_log(...)`

The AMS log export path was unreliable in production — 4-hour stuck exports, 5-of-55 success rates, queue overflow. **All log collection goes through direct HTTP to each miner** — see `LOG_COLLECTION_ARCHITECTURE.md` and `DIRECT_LOG_COLLECTION.md`.

The AMSClient methods still exist in `clients/ams_client.py` because `scripts/cleanup_ams_logs.py` uses `get_log_list` + `/log/delete` to clean up stale log archives on the AMS server. That script is operational maintenance (server-side cleanup), not runtime collection. Do not confuse the two.

### Direct miner device APIs — sparingly

Mining Guardian generally does NOT talk to miners directly via their cgminer/WhatsMiner APIs on port 4028 because AMS is the stable abstraction. The exceptions are:

- **Log collection** — direct HTTP Digest to `/cgi-bin/create_log_backup.cgi` (covered above)
- **Emergency rescue paths** that haven't been built yet — if AMS becomes unavailable long-term, we would need fallback device APIs. Currently not implemented.

The rationale: AMS handles the auth negotiation, connection pooling, and hub-relay details. Talking directly to miners on port 4028 means knowing per-firmware auth (Bitmain root/root, WhatsMiner admin/admin, BiXBiT root/root, Auradine custom) and maintaining three or four parallel code paths. Not worth it for control operations when AMS works.

---

## Gotcha: AMS session staleness

**First observed and documented: 2026-04-24 during the "6 miners back online" investigation.**

**Symptom:** AMS UI shows N miners in the workspace; Mining Guardian's scan shows fewer.

**Cause:** Long-running `AMSClient` instances hold a cached bearer token and WebSocket session that includes a workspace snapshot. When miners are added to the workspace, brought back online after extended downtime, or otherwise re-surfaced, the existing session does NOT automatically re-fetch the workspace list. The pagination logic sees `totalCount=56` from the stale session while a fresh login would see `totalCount=62`.

**Confirmation test:** fire up a one-shot Python process that does a fresh `AMSClient().get_miners()` and compare the count to what the running service logs.

**Fix:** restart the service. `systemctl restart mining-guardian` forces a fresh login, fresh token, fresh workspace fetch.

**All six services that hold AMS sessions:**
- `mining-guardian` — the scan loop
- `mining-guardian-alerts` — persistent WebSocket alert listener
- `slack-listener` — picks up /commands
- `slack-commands` — slash command handler
- `overnight-automation` — 8pm-6am auto-exec
- `approval-api` — Slack approval webhook (doesn't poll miners but uses AMS for remediation actions)

If the workspace changes significantly (miners added/removed, workspace re-org), restart all six.

**Design note for future:** we could add periodic automatic session refresh (e.g. force a re-login every 4 hours) but so far we have not because workspace changes are rare and an operator-triggered restart is cheap. If this stops being rare, revisit.

---

## Gotcha: AMS apparent-downtime

**Symptom:** every miner in a scan shows `status="offline"`.

**First check:** is this AMS itself, or the hub?

- If AMS UI shows miners online → the hub is up, but Mining Guardian's scan is talking to a stale/broken AMS session. Restart the service (see above).
- If AMS UI also shows everything offline → the hub at 192.168.188.30 is probably down. `ssh bixbit@192.168.188.30 'tmux ls'` to check. If the `hub` tmux session is missing or the binary has died, restart it manually: `tmux attach -t hub`, restart the ams.hub.*.linux.arm binary, `Ctrl+B d` to detach.

Mining Guardian has an "AMS appears down" code path (`mining_guardian.py::run_once`) that detects `online_count == 0` and short-circuits the normal scan flow, just saving weather + HVAC + a minimal scan header. This prevents a degenerate scan from creating 55 false restart recommendations.

**Locked behavior:** when AMS appears down, mining-guardian posts to Slack at most once per hour (throttled). Do not change this to post more often — the operator explicitly rate-limited this because AMS can be down for 10+ minutes during hub restarts and repeated "AMS down" Slack noise is worse than silence.

---

## Credentials and configuration

- `AMS_USER` / `AMS_PASS` in `.env` — login credentials
- `AMS_BASE_URL` in `config.json` under `ams_base_url` — default `https://api-staging.dev.bixbit.io/api/v1`
- No AMS credentials in code or git. All via env.

Workspace is auto-selected as the first workspace the authenticated user has access to. Today that is always USA 188 (id 119). If the operator ever gains access to a second workspace and we need to pick between them, `AMSClient._select_workspace` would need updating.

---

## Summary table — when you read code and see something AMS-related

| You see…                                    | Is it OK?                                  |
|---------------------------------------------|--------------------------------------------|
| `ams.get_miners`                            | YES. Primary fleet fetch.                  |
| `ams.get_notifications`                     | YES. Alert history.                        |
| `ams.reboot_miner`                          | YES. Restart control.                      |
| `ams.pdu_power_cycle`                       | YES. PDU control.                          |
| `ams.set_miner_profile`                     | YES. Profile changes.                      |
| `ams.get_miner_state`                       | YES. Used in _wait_for_stable.             |
| `ams.collect_fresh_miner_logs`              | **NO**. Regression. See commit 8191aa6.    |
| `ams.collect_miner_logs`                    | **NO**. Regression.                        |
| `ams.trigger_log_export`                    | **NO**. Regression.                        |
| `ams.get_log_list`                          | Only in `scripts/cleanup_ams_logs.py` for server-side archive maintenance. Nowhere else. |

If a PR or edit reintroduces any of the three "NO" methods in runtime code, block it and reference this document.
