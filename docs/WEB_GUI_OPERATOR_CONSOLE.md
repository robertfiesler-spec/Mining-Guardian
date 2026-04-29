# Web GUI Operator Console

**Purpose:** Non-terminal, browser-based approve/deny interface for Mining Guardian with a global automation mode selector. Served by `approval_api.py` on port 8686 at `/ui`. Delivers Bucket 9 §10.1 (Web GUI) and §10.2 (mode selector).

**Scope:** Operator-side — runs on the Mac Mini that hosts `approval_api.py`. No new services, no new ports. Zero JavaScript dependencies, single static HTML file, works offline. (Historical: also ran on the VPS; VPS decommissioned for MG as of 2026-04-30.)

---

## What it does

Two features on one page:

1. **Automation mode selector.** Three tiles — Full Auto / Semi Auto / Manual — that flip the global `automation_mode` setting in the `system_settings` table. `overnight_automation.run_overnight_cycle()` reads this setting every cycle (~5 min) and applies it as a ceiling over the per-action risk classifier:

    | Mode | AUTO-classified action | HOLD / MANUAL action |
    |---|---|---|
    | `FULL_AUTO` | auto-executes | unchanged (HOLD skips, MANUAL skips) |
    | `SEMI_AUTO` | demoted to HOLD — queues for approval | unchanged |
    | `MANUAL`    | demoted to MANUAL — queues for approval | demoted to MANUAL (nothing auto-runs) |

2. **Per-miner approve / deny with explanation field.** Each pending approval row has its own explanation textarea. The free-form text is written verbatim to `action_audit_log.notes` and — when substantive (>10 chars and containing an imperative like "should", "must", "never", "always") — also flows through the existing `KnowledgeManager.store_operator_rule(category, ...)` path so future decisions learn from it. Same rule-extraction heuristics as the Slack `/deny` endpoint.

---

## Setup — operator-side

The GUI lives at `http://localhost:8686/ui`. One-time setup in your browser devtools console:

```javascript
localStorage.setItem('mg_operator', 'bobby');
localStorage.setItem('mg_internal_secret', '<paste the INTERNAL_API_SECRET from .env>');
```

Both values persist in the browser and never leave the machine. `mg_operator` is used in audit log `approved_by` and `updated_by` fields. `mg_internal_secret` is sent as the `X-Internal-Secret` header on every API call.

Then reload `http://localhost:8686/ui` — the page loads the current mode and pending approvals, and auto-refreshes approvals every 30 seconds.

---

## Endpoints (all require `X-Internal-Secret`)

| Method | Path | What it does |
|---|---|---|
| `GET`  | `/ui` | Serves the single-page HTML (no auth — the page itself contains no data) |
| `GET`  | `/mode` | Returns `{key, value, updated_at, updated_by}` for `automation_mode` |
| `POST` | `/mode` | Sets automation mode. Body: `{"mode": "FULL_AUTO\|SEMI_AUTO\|MANUAL", "operator": "<name>"}` |
| `GET`  | `/pending` | Existing endpoint — lists all `PENDING` approvals |
| `POST` | `/gui/approve` | Per-miner approve. Body: `{"miner_id": "...", "user": "...", "user_id": "web_gui", "explanation": "..."}` |
| `POST` | `/gui/deny`    | Per-miner deny. Same body shape as `/gui/approve`. |

The existing `/approve` / `/deny` / `/approve_selected` endpoints are untouched — the Slack approval listener continues to use them.

---

## Database migration

`migrations/004_system_settings.sql` creates `public.system_settings (key, value, updated_at, updated_by)` and seeds `automation_mode = 'FULL_AUTO'`. Idempotent — re-running is safe.

Apply on the Mac Mini (historical: also applied on the VPS):

```bash
psql -U guardian_app -d mining_guardian -f migrations/004_system_settings.sql
```

Verify:

```sql
SELECT * FROM system_settings WHERE key = 'automation_mode';
-- expect: 1 row, value='FULL_AUTO'
```

Before the migration runs, `GET /mode` still returns `FULL_AUTO` via the in-code default — the GUI is usable even pre-migration, just can't persist changes.

---

## How the mode ceiling works

`core/overnight_automation.py :: run_overnight_cycle` reads the mode at the top of every cycle:

```python
mode = _get_automation_mode_safe()   # defaults to FULL_AUTO on any DB error
```

For each pending action, `classify_risk(action)` still returns AUTO / HOLD / MANUAL per the existing rules (action type, miner history, restart counts tonight, etc.). The mode is then layered on top:

```python
if mode == "MANUAL":
    effective_risk = "MANUAL"
elif mode == "SEMI_AUTO" and risk == "AUTO":
    effective_risk = "HOLD"
else:
    effective_risk = risk
```

The summary dict returned from the cycle now includes `mode`, so morning briefings can surface "last night ran in SEMI_AUTO — N actions were held for you to review" instead of just reporting executed counts.

The gate **fails open** — if `system_settings` is unreachable, the function logs a warning and treats the mode as `FULL_AUTO`. A DB outage must never silently halt legitimate automation.

---

## Security

- **Auth:** all data endpoints require the `X-Internal-Secret` header matching `INTERNAL_API_SECRET` from `.env`. This is the same header the Slack approval listener uses — no new secret to rotate.
- **CORS:** unchanged — historically restricted to `slack.fieslerfamily.com`, `dashboard.fieslerfamily.com`, `localhost:8585` (VPS-era allowed origins). The GUI at `localhost:8686/ui` is same-origin with the API on Mac Mini (loopback-only), so CORS doesn't apply to it. The fieslerfamily origins are historical; see `docs/CORS_LOCKDOWN_PLAN.md` for current lockdown state.
- **Binding:** `approval_api.py` binds to `127.0.0.1:8686` only (per §3.3 S-8 hardening work). The GUI is reachable from the host machine only — not exposed to the local network.
- **Audit trail:** every mode change and every approve/deny writes to `system_settings.updated_by` and `action_audit_log.notes` respectively, with the operator name captured from `localStorage`.

---

## Testing

`tests/test_system_settings_and_mode_gating.py` covers:

- `system_settings` fails open to `FULL_AUTO` on any DB error
- `system_settings.set_automation_mode` rejects values outside the allowed set
- `run_overnight_cycle` in `FULL_AUTO` mode auto-executes AUTO-classified actions
- `run_overnight_cycle` in `SEMI_AUTO` mode demotes AUTO → HOLD with a mode-specific reason, leaves HOLD/MANUAL untouched
- `run_overnight_cycle` in `MANUAL` mode forces everything to MANUAL, no auto-execution at all
- Empty pending-list produces a clean summary including the current mode

Run:

```bash
cd ~/Documents/GitHub/Mining-Guardian
PYTHONPATH=. python3 -m pytest -xvs tests/test_system_settings_and_mode_gating.py
# 10 passed
```

All mocks — no live DB or browser needed.

---

## Limitations (deferred)

- **No rate limiting on the GUI endpoints.** The Slack path is protected by Slack's signing + replay protection; the GUI path relies solely on `X-Internal-Secret`. A slow-request rate limiter would reduce blast radius if the secret ever leaked. Filed as a follow-up if needed.
- **No multi-operator session awareness.** If two operators have the GUI open and both click Approve on the same miner, the second request returns `no_pending`. This is correct (first writer wins), but a toast notification explaining "already handled by someone else" would be nicer.
- **No dashboard links from the approval cards.** The miner IP is a clickable link (opens `http://<ip>`), but there's no direct Grafana panel deep-link yet. Blocked on §15.6.2 (dashboards-as-code) so the panel URIs stabilize.
- **LocalStorage for the secret.** Acceptable because the Mac Mini is a single-operator kiosk. Not acceptable on shared machines — use a different path or migrate to a cookie-based session if that ever changes.

---

## Cross-references

- Approval flow: `api/approval_api.py` (this file adds `/ui`, `/mode`, `/gui/*`)
- Automation cycle: `core/overnight_automation.py :: run_overnight_cycle`
- Setting store: `api/system_settings.py` + `migrations/004_system_settings.sql`
- Front end: `api/static/approval_ui.html` (single file, vanilla JS, Nexus palette inline)
- Existing Slack path: `notifiers/slack_approval_listener.py` (untouched)
