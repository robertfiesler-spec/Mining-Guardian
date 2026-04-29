# Session Note 2026-04-29 — Web GUI + Mode Selector (Bucket 9 §10.1/§10.2)

**Filed:** 2026-04-29 PM, second session of the day after PRs #85 / #86 / #87 shipped.

## What this PR does

Closes Bucket 9 §10.1 (Web GUI for approve/deny with explanation) and §10.2 (Full Auto / Semi Auto / Manual mode selector) — both previously tagged "Backlog (not for build day)" but unblocked once the three earlier PRs were ready for Bobby's review.

## Why now

Bobby chose this path explicitly when offered (a) Web GUI + mode selector, (b) customer doc refresh, (c) pause for his review, (d) other. Reasoning: pure code work, no operator-side dependencies, can ship while he's away from the keyboard. Customer docs need a running dashboard for screenshot refresh — that's blocked on §15.6.2.

## Architecture overview

Two independent features, one PR because they share the same surface (`approval_api.py:8686`):

1. **Mode selector** — global setting, layered on top of the per-action AUTO/HOLD/MANUAL classifier. Stored in a new `system_settings (key, value, updated_at, updated_by)` table. `run_overnight_cycle` reads it each cycle and uses it as a ceiling: `MANUAL` forces everything to manual, `SEMI_AUTO` demotes AUTO → HOLD, `FULL_AUTO` is the existing behavior. Fails open to `FULL_AUTO` on any DB error so a transient outage never silently halts automation.

2. **Web GUI** — single-file vanilla HTML/CSS/JS at `api/static/approval_ui.html`, served by `approval_api.py` at `GET /ui`. Three new endpoints: `GET/POST /mode`, `POST /gui/approve`, `POST /gui/deny`. Per-row explanation textarea writes verbatim to `action_audit_log.notes` and feeds the existing `KnowledgeManager.store_operator_rule` rule-extractor (same heuristics as the Slack `/deny` path).

## Why a generic `system_settings` table

`automation_mode` is the first operator-controllable knob, but it won't be the last. Future GUI knobs (approval timeout, slack-mute window, etc.) slot into the same key/value table without a new migration each time. Application layer enforces the value space.

## Why fail open instead of fail closed

If the DB is unreachable, defaulting to `MANUAL` would silently halt all automation — and operators wouldn't notice for hours. Defaulting to `FULL_AUTO` is what the system has always done. Logged as a warning, not silenced.

## Why per-miner endpoints instead of reusing `/approve`

The existing `/approve` is keyed on `thread_ts` because Slack's UX bundles all of a thread's miners into a single approve/deny. The GUI shows each miner as its own card with its own explanation field — so it needs a `miner_id`-keyed action. The `/gui/*` endpoints share all the underlying logic (DB updates, audit log, MiningGuardian execution) but accept the row-level scope. The Slack listener path is untouched.

## Files

| File | Status | What it does |
|---|---|---|
| `migrations/004_system_settings.sql` | NEW | `system_settings` table + default-mode seed. Idempotent. |
| `api/system_settings.py` | NEW | Read/write helpers. Fails open. Validates allowed mode values. |
| `api/static/approval_ui.html` | NEW | Single-file operator console. Vanilla JS, no deps. Nexus palette inline. |
| `api/approval_api.py` | MODIFIED | + `/ui`, `/mode` GET/POST, `/gui/approve`, `/gui/deny`. |
| `core/overnight_automation.py` | MODIFIED | `run_overnight_cycle` reads mode and applies it as a ceiling on classifier output. |
| `tests/test_system_settings_and_mode_gating.py` | NEW | 10 tests, fully mocked, no live DB. |
| `docs/WEB_GUI_OPERATOR_CONSOLE.md` | NEW | Setup, endpoints, security, testing, limitations. |
| `docs/MG_UNIFIED_TODO_LIST.md` | MODIFIED | Flips §10.1 and §10.2 to ✅ DONE per todo_sync convention. |

## Test results

```
============================== 10 passed in 0.15s ==============================
```

Coverage:
- system_settings constants and allowed values
- `get_setting` returns default on DB error (never raises)
- `get_automation_mode` fails open to `FULL_AUTO` (None / unknown values both rejected)
- `set_automation_mode` validates input — rejects values outside the allowed set
- `run_overnight_cycle` in `FULL_AUTO` — AUTO auto-executes, HOLD held, MANUAL skipped
- `run_overnight_cycle` in `SEMI_AUTO` — AUTO demoted to HOLD with `semi-auto mode` reason, HOLD/MANUAL untouched
- `run_overnight_cycle` in `MANUAL` — every action becomes MANUAL with `manual mode` reason
- Empty pending list returns clean summary including `mode` key

## How to ship

This is a code-only PR — no operator action needed before merge. After merge, on the Mac Mini / VPS:

```bash
cd ~/Documents/GitHub/Mining-Guardian
git pull --ff-only
psql -U guardian_app -d mining_guardian -f migrations/004_system_settings.sql
sudo launchctl kickstart -k system/com.miningguardian.approvalapi  # restart approval_api
```

Then in the browser at `http://localhost:8686/ui`, open devtools console and run:

```javascript
localStorage.setItem('mg_operator', 'bobby');
localStorage.setItem('mg_internal_secret', '<paste from .env INTERNAL_API_SECRET>');
```

Reload — the GUI loads, current mode displays, pending approvals populate, auto-refresh every 30s.

## Backward compatibility

- Slack path unchanged — `slack_approval_listener.py` and the existing `/approve` / `/deny` / `/approve_selected` endpoints are untouched.
- `automation_mode = FULL_AUTO` is seeded by the migration, so existing behavior is preserved on first deploy. Operator must explicitly flip it to see the new modes take effect.
- If `system_settings` is missing (pre-migration), `run_overnight_cycle` defaults to `FULL_AUTO` and `GET /mode` returns the in-code default. GUI is fully usable, just can't persist mode changes.

## Cross-references

- §10.1 / §10.2 in `docs/MG_UNIFIED_TODO_LIST.md`
- §3.3 S-8 hardening: `approval_api` already binds to `127.0.0.1` only
- DG-2 fix: rule-extraction logic mirrored from `/deny` to `/gui/deny`
- §15.6.2: dashboard deep-links from approval cards deferred until dashboards-as-code lands
