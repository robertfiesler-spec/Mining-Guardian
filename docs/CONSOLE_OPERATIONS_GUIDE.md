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
- **Frontend:** Server-rendered Jinja2 + HTMX. No React, no node, no
  build step. HTMX is **vendored locally** at
  `console/static/vendor/htmx-1.9.12.min.js` (served from
  `/static/vendor/…`). There is **no CDN dependency at runtime** — the
  browser loads every asset from the Mac Mini. Static CSS at
  `console/static/console.css`. See `console/static/vendor/README.md`
  for the upstream source, license, size, and SHA-256.
- **Bind:** `127.0.0.1:8787`. Never `0.0.0.0`. Tested.

### Local-first asset rule (enforced by tests)

The console runs on an appliance with no public ingress, and customers
may restrict outbound internet. No template may load a script or
stylesheet from `unpkg.com`, `cdn.jsdelivr.net`, `cdnjs.cloudflare.com`,
`ajax.googleapis.com`, or `code.jquery.com`. This is enforced by
`test_no_cdn_dependencies_in_any_template`, which walks every public
GET route and greps the response body. To bump HTMX, replace the file,
update the SHA-256 in `console/static/vendor/README.md`, update the
`<script>` tag in `console/templates/_base.html`, and re-run the
console test suite.

### Surface boundaries (operator-facing rule)

- **Grafana = visibility.** Time-series dashboards, fleet health,
  model behavior over time. Read-only.
- **Console = controls.** Accept jobs, toggle automation, edit
  schedules, review the approval queue, inspect read-only system
  state.
- **Tailscale = clean private operator/dev path.** Personal routing
  layer only. No customer data plane on it.
- **Cloudflare Access = customer-facing path when appropriate.** Used
  when the customer wants an email-gated HTTPS door to the console
  from off-site.

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

### Queue-only in v1 (customer-experience guard)

The console's approval-page buttons are **labelled and styled as
queue-only** so the customer cannot mistake them for "execute
remediation now":

- Buttons read **"Mark Approved (queue only)"** and **"Mark Denied
  (queue only)"** — never the bare verbs "Approve" / "Deny".
- The page renders a yellow callout above the table that spells out
  the limitation: marking a row updates `pending_approvals.status` +
  `responded_by`; it does **not** restart a miner, it does **not**
  PDU-cycle anything, and it does **not** call `api/approval_api.py`.
- The queue-only buttons are styled with a dashed border and muted
  colour so they read as a record-keeping action rather than a
  primary "go" button.
- Title attributes on the buttons repeat the rule on hover.
- A unit test (`test_approvals_page_shows_queue_only_callout`) fails
  the build if either the label or the callout is removed.

Until the unified execution library lands, an operator who needs the
remediation to actually run must approve in the Slack
`#mg-approvals` thread — that path keeps executing remediation via
`api/approval_api.py` + `INTERNAL_API_SECRET` exactly as before.

### Why the console does not call approval_api in this PR

`api/approval_api.py` `/approve` is keyed by Slack `thread_ts` and
approves *every* PENDING row in that thread at once. The console
addresses approvals by integer `id`. Wiring the console through the
existing endpoint would either (a) approve more rows than the
operator clicked on, or (b) require a new `/approve_by_id` endpoint
plus a remediation-execution refactor, both of which are out of
scope for the foundation PR.

### Pre-customer-ready follow-up (BLOCKER for full execution path)

If/when the customer requires that the console buttons execute
remediation:

1. Add an id-keyed endpoint to `api/approval_api.py` (e.g. `POST
   /approve_by_id` with `X-Internal-Secret` auth) that mirrors the
   Slack `/approve` execution path for a single approval id. The new
   endpoint must also write to `action_audit_log` so the audit trail
   stays single-sourced.
2. Have `console/approvals.py` POST to `http://127.0.0.1:8686/approve_by_id`
   with the loopback-only `INTERNAL_API_SECRET` from `.env`. The
   secret stays server-side; the browser only ever sends an opaque
   approval id. This preserves the
   `test_internal_secret_never_appears_in_html` guarantee.
3. Update the labels back to "Approve" / "Deny" and remove the
   queue-only callout. Keep the test that asserts the callout
   matches the wording — flip its expected text.

Tracked as a pre-v1.0.3-customer-ready follow-up. The queue-only
posture in this PR is the safe default until that follow-up lands.

### Snooze

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
| Unified remediation execution library + console-button execution path | Today the Slack flow is the executor; console v1 is queue-management only. **Required pre-v1.0.3-customer-ready** if customers expect console buttons to execute remediation. See "Pre-customer-ready follow-up" above. | Post-cutover (or pre-customer-ready, see above) |
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
