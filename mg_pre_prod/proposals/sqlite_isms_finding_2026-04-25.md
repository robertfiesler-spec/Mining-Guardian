# SQLite-ism Findings on `main` — 2026-04-25 Bonus Sprint

**Branch audited:** `origin/main` @ `b28c8a7`
**Audit method:** Pattern scan across 29 files using `psycopg2.connect`
**Status:** Catalog only. **Not bundled into CR-4 PR.** Separate hotfix recommended.

## Scope rationale

CR-4's shim (`_PgConnShim` in `core/database_pg.py`) intercepts the `.execute()` API
mismatch — it does NOT translate SQLite-specific SQL (`datetime('now', ...)`, `strftime()`,
`date('now')`) into Postgres syntax. Each finding below is a real psycopg2 syntax
error that fires when the code path executes.

## Findings

### Tier A — User-facing failures (not wrapped in try/except)

These hit on every dashboard/UI request that reaches them. **Currently broken in production
unless these endpoints are simply never called.**

| File | Line | Snippet | Endpoint / caller | Postgres equivalent |
|---|---|---|---|---|
| `api/dashboard_api.py` | 1317-1318, 1337-1338 | `strftime('%Y-%m-%dT', recorded_at)`, `strftime('%H', recorded_at)` | `GET /facility/environment_history` | `to_char(recorded_at, 'YYYY-MM-DD"T"')`, `EXTRACT(HOUR FROM recorded_at)` |
| `api/dashboard_api.py` | 2113 | `datetime('now', %s \|\| ' hours')` | `GET /miner/{ip}/history` (presumed) | `NOW() + (%s \|\| ' hours')::interval` |
| `api/dashboard_api.py` | 2159 | `datetime('now', %s \|\| ' hours')` | `GET /actions` audit log | same as above |
| `api/dashboard_api.py` | 2599 | `datetime('now', %s \|\| ' hours')` | `/ask` NL query — miner history branch | same as above |
| `api/dashboard_api.py` | 2793 | `datetime('now', %s \|\| ' hours')` | `/ask` NL query — actions branch | same as above |

### Tier B — Silent degradation (wrapped in try/except)

These don't crash the process but the feature stops working. No logs, no alerts —
caller gets `None`/`0.0`/empty list and behaves as if there's "no data."

| File | Line | Function | Effect when it fires |
|---|---|---|---|
| `ai/predictor.py` | 585 | `_check_chip_degradation` | Signal 13 always returns `(0.0, None)`. Chip-deviation detection effectively dead. |
| `api/slack_approval_listener.py` | 120 | `build_miner_context` | Slack approval messages show no 7-day history per miner. |
| `api/slack_approval_listener.py` | 384 | denial-reason update path | Denial reasons may not stamp onto recent audit rows. (`date('now')`) |
| `ai/local_llm_analyzer.py` | 155, 165, 174, 184 | `_get_scan_context` | LLM scan analysis aborts before building prompt → no LLM commentary in scan reports. |

## Hot-vs-cold assessment

- **predictor.py L585**: HOT path (predictor runs on every scan) — but failure is silent.
  68 AttributeError hits over 7 days from `_auto_create_missing_tickets` strongly suggest
  the predictor IS executing; if it threw psycopg2 errors here we'd see them in journal.
  Action: confirm by grepping VPS journal for `syntax error at or near "'now'"`.
- **dashboard_api.py Tier A**: HOT but binary — either Rob's been hitting these endpoints
  (and seeing 500s / blank charts) or hasn't (cold in practice). Worth asking him.
- **local_llm_analyzer.py**: HOT (every scan) but silent. If LLM commentary has been
  missing from scan reports lately, this is why.
- **slack_approval_listener.py**: COLD-ish — only fires on Slack interactions.

## Recommendation

**Do NOT extend CR-4 PR.** Reasons:
1. CR-4 is already a shim + 8 SQL conversion sites — it's the minimum viable patch
   to unbreak `mining_guardian.py` core scan loop.
2. Each Tier A site needs Postgres-specific SQL rewriting and per-endpoint testing,
   not a mechanical sed.
3. Bundling adds risk to a patch Rob hasn't reviewed line-by-line.

**Instead:**
1. Land CR-4 first (Sunday after rename).
2. Verify VPS journal for `syntax error at or near "'now'"` → confirms which Tier A
   endpoints are actually being hit. Cmd: `journalctl -u dashboard-api --since "7 days ago" | grep -i "syntax error"`
3. Open follow-up hotfix `hotfix/cr-5-sqlite-sql-rewrites` for Tier A first
   (user-visible), Tier B second (silent degradation).

## Pattern reference: psycopg2 equivalents

| SQLite | Postgres |
|---|---|
| `datetime('now')` | `NOW()` or `CURRENT_TIMESTAMP` |
| `datetime('now', '-7 days')` | `NOW() - INTERVAL '7 days'` |
| `datetime('now', %s \|\| ' hours')` | `NOW() + (%s \|\| ' hours')::interval` (negative seconds OK as bound param) |
| `date('now')` | `CURRENT_DATE` |
| `strftime('%Y-%m-%d', col)` | `to_char(col, 'YYYY-MM-DD')` |
| `strftime('%H', col)` | `EXTRACT(HOUR FROM col)::int` |
| `LENGTH(blob)` | `octet_length(blob)` (text) or `length(blob)` (bytea) — verify by column type |
| `SUBSTR(s, 1, n)` | `substring(s FROM 1 FOR n)` or `substr(s, 1, n)` (works in PG too) |

## Files inspected (29) — clean (no SQLite-isms found)

`api/healthz.py`, `api/intelligence_api.py`, `api/intelligence_report.py`,
`api/approval_api.py`, `api/slack_commands.py`, `api/fleet_comparison.py`,
`core/mining_guardian.py` (handled by CR-4), `core/hashrate_evaluation.py`,
`core/database_pg.py` (handled by CR-4), `core/maintenance_db.py`,
`core/migrations.py`, `core/ticket_manager.py`, `core/knowledge_manager.py`,
`ai/anomaly_detector.py`, `ai/log_collector.py`, `ai/log_analyzer.py`,
`ai/predictive_eta.py`, plus 8 misc scripts.
(Full clean list: scan output saved to `/tmp/main_audit/clean_files.txt` if needed.)

## Open question for Rob

> Have you noticed any of these recently?
> - Dashboard "Environment History" chart blank or 500-erroring
> - "Ask" panel returning empty for "history of <ip>" or "actions today"
> - LLM commentary missing from intelligence reports
> - Slack approval messages showing no 7-day history block per miner
>
> If yes → confirms hot path → bumps to Tier A priority.
> If no → these endpoints aren't being hit much; queue for non-urgent CR-5.
