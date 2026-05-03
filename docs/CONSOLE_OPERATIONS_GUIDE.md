# Mining Guardian — Console Operations Guide (D-19, P-006)

Authoritative source for the customer operator console — the 10th
LaunchDaemon shipped in v1.0.3. Locked: 2026-05-03 by D-19; foundation
PR: P-006.

## Purpose (one paragraph)

Grafana is the **visibility surface** — dashboards for time-series
metrics, fleet health, model behavior over time. The console is the
**control surface** — accept jobs, toggle automation, edit task
schedules, review pending approvals, and inspect read-only system
state. The two are deliberately separate. This PR does not touch any
Grafana dashboard or Grafana provisioning JSON.

## Tech stack

- **Backend:** FastAPI in `console/` (Python). Reuses
  `api/system_settings.py`, `api/system_schedules.py`, `core/`, and the
  existing `pending_approvals` Postgres table.
- **Frontend:** Server-rendered Jinja2 + HTMX (CDN). No React, no node,
  no build step. Static CSS at `console/static/console.css`.
- **Bind:** `127.0.0.1:8787`. Never `0.0.0.0`. Tested.

## Port allocation note (IMPORTANT)

D-19 originally requested binding the console to **8686**. That port is
already owned by `api/approval_api.py` (the Slack approve/deny webhook
plus the existing `/ui` Web GUI from Bucket 9 §10.1). Two services
cannot share a port. The console binds to **8787** instead.

Updated port table for v1.0.3 customer Mac Mini:

| Port | Service |
|---|---|
| 5432 | PostgreSQL (`mining-guardian-db` container) |
| 8585 | Dashboard API (`api/dashboard_api.py`) |
| 8686 | Approval API (`api/approval_api.py`) |
| 8787 | **Operator Console (`console/main.py`) — D-19 / P-006** |
| 11434 | Ollama |
| 3000 | Grafana |

`docs/INSTALL_PATHS_2026-05-03.md` and `welcome.html` / `conclusion.html`
should reference `:8787` for the console once Gap 1 (welcome/conclusion
copy) is updated. Until then, the console is reachable at
`http://localhost:8787` from the Mini itself, via Cloudflare Access at
`mg.fieslerfamily.com` (production), and via Tailscale at
`http://<mini-ts-name>:8787` (operator/dev path).

## Access paths

The console is local-only. It is reached three ways:

1. **From the Mini itself** — `http://localhost:8787`. The 10th
   launchd daemon binds to localhost only.
2. **Cloudflare Access** — production customer-facing path per D-19.
   Cloudflare Tunnel + Access front the console at the customer's
   hostname (operator-controlled domain). Access auth is email-based.
   Tunnel + Access wiring lands in a follow-up postinstall step (D-19
   item 5); the v1.0.3 .pkg ships the daemon ready, the operator runs
   `cloudflared service install` once with the token.
3. **Tailscale** — operator/dev path. Tailscale gives a clean private
   route to `localhost:8787` without exposing the port at all. This
   keeps the data plane local (Vision Anchor 6) — Tailscale only
   carries the operator's personal traffic, not customer data.

No public ingress is added by this PR. There is no `0.0.0.0` bind, no
inbound port-forward, no UPnP request, no firewall rule punched.

## Routes

| Method | Path | What it does |
|---|---|---|
| GET | `/` | 302 to `/tasks` |
| GET | `/healthz` | Liveness — always 200 |
| GET | `/tasks` | Task registry view (the 9 services + 11 scheduled jobs) |
| GET | `/tasks/htmx` | HTMX partial — refreshed every 15 s |
| POST | `/tasks/{key}/pause` | `launchctl bootout system/<label>` |
| POST | `/tasks/{key}/resume` | `launchctl bootstrap system <plist>` |
| POST | `/tasks/{key}/schedule` | Edit schedule via `system_schedules` |
| GET | `/automation` | Automation mode pill + form |
| POST | `/automation/mode` | Set `automation_mode` in `system_settings` |
| GET | `/approvals` | PENDING rows from `pending_approvals` |
| POST | `/approvals/{id}/approve` | Mark APPROVED |
| POST | `/approvals/{id}/deny` | Mark DENIED |
| POST | `/approvals/{id}/snooze` | Push wake time (in `system_settings`) |
| GET | `/system` | Read-only state panel |

OpenAPI / Redoc / `/openapi.json` are intentionally disabled
(`docs_url=None` etc.) — the console is not a public API surface and
exposing the schema adds attack surface without adding operator value.

## Approval queue — important behaviors

In v1, the console's Approve / Deny buttons **update the
`pending_approvals` row directly** (status flip + `responded_by`
audit). They do **NOT** trigger remediation execution (RESTART /
PDU_CYCLE). The existing Slack approval flow remains the side-effect
driver for now. Rationale:

- The Slack flow already executes remediation cleanly via
  `core/overnight_automation.py` and `api/approval_api.py`. Adding a
  second execution path means two places to keep in sync.
- v1 console scope (per D-19) is queue management, not remediation
  orchestration. A unified execution library is a follow-up workstream.
- This means: until the unified execution library lands, an operator
  who Approves a row in the console will see the row flip to APPROVED
  but the miner restart will only fire if/when the existing approval
  flow picks it up. Acceptable for v1.0.3 — documented prominently here
  so it isn't a surprise.

Snooze records a wake time in `system_settings` under
`console_snooze:<id>`. It does **not** hide the row in v1; the
operator sees both the row and its snooze label. A future patch can
wire a real "snoozed → re-pending" transition.

## INTERNAL_API_SECRET — never leaked

`INTERNAL_API_SECRET` is read from `.env` server-side and is never
rendered into any HTML response. It is not used for outbound calls in
v1 (approvals are written directly to Postgres). The
`test_internal_secret_never_appears_in_html` unit test verifies this
by setting a sentinel value into the env and walking every public GET
route to confirm absence.

## Pause / Resume semantics

Pause = `launchctl bootout system/<label>`. The plist stays on disk;
the daemon stops. Resume = `launchctl bootstrap system /Library/LaunchDaemons/<label>.plist`.
Same mechanism `installer/macos-pkg/scripts/postinstall.sh` uses for
its idempotent re-install path. No new privilege escalation vector.

The console runs as **root** (it is the 10th LaunchDaemon, same as
every other service). `launchctl` commands targeting `system/...`
work without sudo. No `sudo` shells out from the console.

## Schedule editing

Schedule edits write to the `system_schedules` table via
`api.system_schedules.update_schedule(...)`. Daemons that already read
this table (overnight automation, AMS alert poll, slack listener
poll, catalog auto-refresh) pick up changes within one loop iteration.

For tasks that aren't yet wired into `system_schedules` (the cron-replacement
plists from Gap 4 — DB maintenance, knowledge backup, morning briefing,
etc.), the console writes the requested schedule into `system_settings`
under `console_pending_schedule:<key>` and shows the operator a
"queued" flash. Gap 4's plist generator will read these pending values
when it runs.

## System state probes

Each probe is bounded by a short timeout (≤ 0.6 s) and never raises.
Failed probes return `status: "unknown"` rather than 500-ing the page.

| Probe | Source |
|---|---|
| `postgres` | TCP probe to `GUARDIAN_PG_HOST:GUARDIAN_PG_PORT` |
| `ollama` | HTTP GET `OLLAMA_HOST/api/tags` |
| `grafana` | HTTP GET `GRAFANA_URL/api/health` |
| `tailscale` | TCP probe to `localhost:41112` (best-effort) |
| `last_scan` | `MAX(scanned_at)` from `scans` |
| `miner_reach` | online/total from latest `miner_readings` per miner |

The Tailscale probe is best-effort; absence on the local API port
does not mean Tailscale is unhealthy. Operators relying on Tailscale
should check `tailscale status` from a terminal.

## Deferred / out-of-scope for the foundation PR (P-006)

These are explicitly NOT in this PR. They are documented here so the
follow-up workstream tables stay accurate:

| Item | Why deferred | Where it lands |
|---|---|---|
| Cloudflare Tunnel + Access auto-provisioning | Needs operator's CF API token in `MiningGuardian.conf`; gated postinstall step | D-19 step 5 — separate PR |
| Plist generators for the 11 scheduled tasks | Gap 4 of D-18 — generates `installer/macos-pkg/resources/launchd/scheduled/*.plist` from the registry | Gap 4 PR |
| Welcome/Conclusion copy update (`:8787`, "ten background services") | Bug #7 from MG_UNIFIED_TODO_LIST | Separate copy PR |
| Real `bin/uninstall.sh` covering 10 services | Bug #3 from MG_UNIFIED_TODO_LIST | Separate uninstall PR |
| Phone-app retirement | Console is explicitly temporary scaffolding (D-19) | Phone-app project, post-cutover |
| Unified remediation execution library | Today the Slack flow is the executor; console v1 is queue-management only | Post-cutover |
| Real-time WebSocket push (currently HTMX 15-s polling) | 15-s polling is good enough for an internal control surface | Optional follow-up |
| Grafana UI changes | OUT OF SCOPE — Grafana is the visibility surface; this PR is the control surface only | N/A |

## Smoke test (for the operator on the Mini)

After `make pkg` produces a v1.0.3 `.pkg`, install on a clean macOS
VM and verify:

```sh
# 1. Console daemon is loaded
sudo launchctl print system/com.miningguardian.console | head

# 2. Console is reachable on localhost only
curl -sf http://127.0.0.1:8787/healthz   # -> {"ok": true, "service": "mg-console"}
curl -sf http://0.0.0.0:8787/healthz     # -> connection refused (must NOT bind)

# 3. Tasks page renders (200 + HTML)
curl -sI http://127.0.0.1:8787/tasks | head -1   # -> HTTP/1.1 200 OK

# 4. The 10th plist is installed
ls -1 /Library/LaunchDaemons/com.miningguardian.console.plist
```

Full clean-VM smoke is the v1.0.3 D-18 verification gate (already
locked) — the console gets exercised there alongside the other 9
services.
