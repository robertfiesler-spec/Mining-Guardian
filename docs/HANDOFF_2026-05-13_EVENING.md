# HANDOFF — 2026-05-13 (Wednesday evening)

> **For the next session.** This is the durable record of what happened today. The state of the world is in this file plus the artifacts it points at. Read this AFTER `docs/MORNING_BRIEFING_2026-05-14.md` — the morning briefing is the orientation; this file is the deep history.

---

## E0. The actual TL;DR

Today was one of the heaviest execution days in the project's recent history. **11 PRs merged** (#201 through #211), spanning two distinct chapters separated by a deploy gap.

**Morning chapter (06:48–11:00 CDT) — Infrastructure surgery (5 PRs).**
W14 (two-Postgres-instance split) executed live against the Mini in a 22-minute maintenance window, followed by W14b convention lock + Step 9 daily backup pipeline + a db_maintenance.sh fix. The morning closed with the new topology fully smoke-verified, all 10 always-on services healthy on fresh PIDs in cluster 66707-66788.

**Afternoon chapter (13:00–17:00 CDT) — Cohort cleanups + Grafana restoration (6 PRs).**
The P-038 cohort got a second pass (timestamptz `[:N]` slice sites in HTML rendering — surfaced by Grafana panel inspection), a 91-file dead-code sweep removed archive/ + fixes/ legacy dirs, then three Grafana-related W-items closed: W25 dashboard_api bind, W25b `/fleet/board_stats` Postgres GROUP BY fix, W26a Intelligence Catalog dashboard rendering on Grafana 13.

**End-of-day state on Mini:** Two Postgres containers (`mining-guardian-db` port 5432, `mg-catalog-db` port 5433). All 10 always-on services healthy on the W14 topology. Grafana 13.0.1 serving 9 dashboards (8 VPS-restored + 1 new catalog) over Tailscale at `http://100.69.66.32:3000`. dashboard_api binding `0.0.0.0:8585` (W25), `/fleet/board_stats` Postgres-strict (W25b), Intelligence Catalog populating all 5 panels (W26a).

**Main HEAD at end of day:** `5cf154f` (PR #211 merge).

---

## E1. PR ledger for today

| # | PR | Branch | Summary |
|---|---|---|---|
| 1 | #201 | `docs/w14-closed-2026-05-13` | W14 close-out: status updated to `[X]`, post-mortem doc landed |
| 2 | #202 | `tests/w14-password-quote-consistency` | Cohort guard test #2 — `.env` password quote-stripping convention |
| 3 | #203 | `docs/w14b-convention-lock` | W14b convention lock — CLAUDE.md two-target rule + `.env.example` + install_colima.sh docstring |
| 4 | #204 | `feat/w14-step9-postgres-daily-backup` | W14 Step 9 (D6) — per-instance pg_dump scripts + wrapper + 02:00 plist; 3 legacy VPS scripts retired |
| 5 | #205 | `fix/w14-db-maintenance-two-instance-colima-socket` | db_maintenance.sh — Colima socket path under launchd context + two-instance awareness |
| 6 | #206 | `fix/p038-timestamptz-slice-cohort-2026-05-13` | P-038 v2: 19 timestamptz `[:N]` slice sites in production code + cohort guard test |
| 7 | #207 | `fix/p038-dashboard-html-timestamp-slices-2026-05-13` | P-038 v2 HTML rendering: 14 `[:19]` sites → `fmt_dt()` |
| 8 | #208 | `chore/p038-archive-fixes-deadcode-sweep-2026-05-13` | Dead-code sweep: `archive/` + `fixes/` removed (91 files, -15,898 LOC) |
| 9 | #209 | `w25-dashboard-api-bind-host` | W25: dashboard_api host/port configurable via env (was hardcoded 127.0.0.1) |
| 10 | #210 | `w25b-fleet-board-stats-postgres-group-by` | W25b: `/fleet/board_stats` SQLite-isms → Postgres-strict `DISTINCT ON (ip)` + outer GROUP BY |
| 11 | #211 | `w26a-catalog-dashboard-grafana13-compat` | W26a: Intelligence Catalog dashboard renders on Grafana 13 (3 distinct fixes) |

Plus this evening's handoff PR which lands a 12th merge.

---

## E2. Morning chapter — W14 ship + convention lock + backups (PRs #201–#205)

### E2.1. W14 the actual ship (06:48–07:10 CDT)

Two-Postgres-instance split executed live following [`strategy/W14_PREP.md`](strategy/W14_PREP.md) steps 0–10. 22-minute total wall time. Sequence:

1. **Step 1** — unloaded 12 scheduled launchd jobs. 10 always-on kept running through entire window.
2. **Step 2** — spun up `mg-catalog-db` (postgres:16-bookworm, port 5433, bind-mounted `/Library/Application Support/MiningGuardian/pgdata-catalog`).
3. **Step 3** — dropped empty bootstrap DB, `pg_restore` from `pre-w14-catalog-20260512-121154.dump`. Row counts matched baseline exactly: 324/17/6/22/0.
4. **Step 4** — backed up live `db_targets.py` + `.env`, scp'd new resolver code from laptop, appended `GUARDIAN_PG_CATALOG_HOST=127.0.0.1` and `GUARDIAN_PG_CATALOG_PORT=5433` to `.env`.
5. **Step 5** — bootout/bootstrap of all 10 always-on services. All came back on fresh PIDs cluster 66707-66788.
6. **Step 6** — smoke gate (3 sub-checks): fresh Python resolver verified, `ai.catalog_context.get_catalog_context()` returned valid result for ANTMINER S19j Pro, `daily_deep_dive --dry-run` enumerated 72 online miners with correct model lookups. **Bug surfaced here** (see E2.2).
7. **Step 7** — `DROP DATABASE mining_guardian_catalog` on `mining-guardian-db` (irreversible gate, passed).
8. **Step 8** — reload 12 scheduled jobs (back to 22 total).
9. **Step 9** (deferred 30 min) — landed in PR #204 (see E2.3).
10. **Step 10** — installer-side provisioning postponed pending postinstall.sh redesign.

### E2.2. The mid-flight password bug (good outcome — smoke gate worked)

Step 6 smoke caught a Postgres password-authentication failure on `mg-catalog-db`. **Root cause:** `cut -d= -f2-` in the Step 2 `docker run` script preserved literal single quotes around the password value from `.env`, leaving the new container's `mg` role with a 66-char quoted password while applications send the 64-char unquoted value.

**Fix:** `ALTER USER mg WITH PASSWORD '<unquoted>'` inside the container.

**Why this matters:** the smoke gate did its job. Bug surfaced **before** Step 7 (irreversible DROP). The pattern is now locked into [`strategy/W14_POSTMORTEM_2026-05-13.md`](strategy/W14_POSTMORTEM_2026-05-13.md) + the cohort guard test in PR #202 + the convention block in CLAUDE.md from PR #203.

### E2.3. W14 Step 9 (D6) — daily backup pipeline

Replaced the legacy VPS-era scripts with two-instance-aware pipeline:

- `scripts/backup_operational.sh` — pg_dump from inside `mining-guardian-db`, verify with `pg_restore --list`, apply retention (default 7 dumps, env-tunable via `MG_BACKUP_RETAIN_COUNT`).
- `scripts/backup_catalog.sh` — same shape, targets `mg-catalog-db`.
- `scripts/daily_backup.sh` — wrapper; returns non-zero if either fails.
- New launchd plist `com.miningguardian.scheduled.daily-backup.plist` at 02:00 CDT (operator-tunable).
- 3 legacy VPS-era scripts (`backup_db.sh`, `backup_mining_guardian.sh`, original `daily_backup.sh`) renamed to `*.legacy-vps-decommissioned`.

Pre-W14 dumps deliberately not matched by the prune pattern → they remain on disk indefinitely.

**Pre-existing bug fixed as part of this:** Colima socket path resolution under launchd context. Setting `DOCKER_HOST="unix:///Users/miningguardian/.colima/default/docker.sock"` explicitly in backup scripts bypasses broken default-context resolution that had been failing `db_maintenance.sh` for days. PR #205 propagated the same fix to `db_maintenance.sh`.

End-to-end smoke: `sudo /bin/bash scheduled_job_launcher.sh scripts/daily_backup.sh daily_backup` → exit 0, both dumps written + verified, 2-second wall time.

### E2.4. W14b convention lock (PR #203)

The durable artifact. `CLAUDE.md` `## Coding Conventions` section added with two binding rules:

1. **All Postgres access through `core.db_targets`.** Cohort guard test `tests/test_w14a_no_direct_pg_env_reads.py` enforces.
2. **`.env` values sourced via `xargs` (strips quotes) before downstream use.** Cohort guard test `tests/test_w14_password_quote_consistency.py` enforces.

Plus `.env.example` rewritten with two-instance topology defaults + quote-handling note, and `installer/macos-pkg/scripts/lib/install_colima.sh` docstring documents the two-container provisioning requirement.

The full installer code changes (postinstall.sh provisioning of the second container) ship later, with W14 Step 10.

---

## E3. Afternoon chapter — P-038 v2 + dead-code sweep + Grafana restoration (PRs #206–#211)

### E3.1. P-038 v2 cohort (PRs #206 + #207)

P-038 was previously thought closed (PR #178 ran through ai/core/api/scripts/ tests/ and removed the bug pattern). Grafana panel inspection during W25 setup surfaced 19 surviving sites in production code (`api/dashboard_api.py`, `api/ai_dashboard_api.py`, intel-report rendering) where `timestamp[:N]` slicing on `datetime` objects produced TypeError at render time. Plus 14 HTML-rendering sites using `[:19]` for display formatting that were brittle to the timestamptz return type from Postgres.

- **PR #206** — 19 slice sites converted to `fmt_dt(...)` from `core.tz_utils`; cohort guard test added.
- **PR #207** — 14 HTML-render sites converted to `fmt_dt(...)` for consistency.

P-038 v2 cohort guard now: 4 tests, all pass.

### E3.2. Dead-code sweep (PR #208)

Removed `archive/` (legacy SQLite-era code, ~50 files) and `fixes/` (one-shot migration scripts from May 2025, ~41 files). 91 files total, -15,898 lines of code. None imported by any current code path (verified via static analysis). Repository is now substantially smaller and contributors stop wandering into dead corridors.

### E3.3. Grafana restoration — W25 + W25b + W26a (PRs #209 + #210 + #211)

#### W25 — dashboard_api bind (PR #209)

dashboard_api was hardcoded to `uvicorn.run(host="127.0.0.1", port=8585)`. Tailscale clients couldn't reach it for iframe rendering. **Fix:** read `MG_DASHBOARD_HOST` + `MG_DASHBOARD_PORT` env vars, default to `0.0.0.0:8585`. `.env` updated on Mini. dashboard_api restarted. Curl from 100.69.66.32 returns 200.

Cohort guard test: 7 tests verifying env-derived bind, no other uvicorn.run hardcodes loopback:8585, `.env.example` documents the vars.

#### W25b — /fleet/board_stats Postgres-strict GROUP BY (PR #210)

`fleet_board_stats` in `api/dashboard_api.py` had two SQLite-isms that Postgres 16 strictly rejects:
1. Subqueries: `SELECT ip, model FROM miner_readings WHERE scan_id=%s GROUP BY ip` — Postgres requires `model` either in GROUP BY or aggregated.
2. Outer queries grouping only by `p.ip`/`c.ip` while selecting `m.model`.

**Fix:** `DISTINCT ON (ip)` in subqueries (preserves "exactly one row per ip" defensive intent); `m.model` added to outer GROUP BY; `HAVING total_hw > 0` → `HAVING SUM(c.hw_errors) > 0` for alias-free clarity. Live-Mini verified: 127.0.0.1 HTTP 200 / 70ms / 3896B, 100.69.66.32 HTTP 200 / 31ms / 3896B. Top offender: `192.168.188.86` at 4.819% rejection rate.

Cohort guard: 5 tests.

#### W26a — Intelligence Catalog dashboard works on Grafana 13 (PR #211)

Three distinct breakage modes diagnosed via Safari Web Inspector:

1. **Markdown text panel** had literal `\n` escape sequences (double-escaped JSON) → rendered as run-on paragraph.
2. **Four data panels** returned "No data" with console error: `runRequest.catchError: You do not currently have a default database configured for this data source`. **Root cause:** Grafana 12.2+ bug [#112418](https://github.com/grafana/grafana/issues/112418) — the frontend stopped reading the top-level `database` field at panel-query time, reads only `jsonData.database`. Datasources provisioned with the legacy top-level form pass Save-and-Test but fail every query.
3. **Dashboard JSON** used `schemaVersion: 16` (Grafana 6.x era). Grafana 13's auto-migrator handles this inconsistently and drops target-level datasource refs.

**Fixes shipped:**
- `mining_guardian.yml` — `database: <name>` duplicated into `jsonData` for all 3 Postgres datasources. Top-level kept for backward compat (defence-in-depth).
- `intelligence_catalog_live_queries.json` — `\n` → real newlines, `schemaVersion` 16→39, `datasource` pushed onto every SQL target.
- **Yaml hardening:** while sanitizing the Mini's live yaml for the repo, found the password was a literal 64-char hex string instead of `${GUARDIAN_PG_PASSWORD}`. Repo keeps the env-var form. Password rotation tracked separately (still open — see E5).

Cohort guard: 6 tests, including a Failure Mode 9 sibling sweep verifying no other installer dashboard has the same old-schema + missing-target-ds combination.

Live-Mini after deploy + Grafana restart: all 5 panels populate (10 schemas, 98 tables, full firmware table list, formatted markdown documentation).

---

## E4. End-of-day production state

### Mini at `miningguardian@100.69.66.32` (Tailscale)
- macOS 26.4.1, M4, 16GB RAM
- Install root: `/Library/Application Support/MiningGuardian/` (NOT git-managed; manual scp delivery)
- Colima Docker, CLI at `/usr/local/bin/docker`

### Postgres topology (post-W14)
- Container `mining-guardian-db` (postgres:16-bookworm, port 5432:5432, bind-mounted `pgdata/`) — operational DB only
- Container `mg-catalog-db` (postgres:16-bookworm, port 5433:5432, bind-mounted `pgdata-catalog/`) — catalog DB only

### Baseline row counts (must match after any rollback)
| Database | Table | Rows |
|---|---|---|
| catalog | hardware.miner_models | 324 |
| catalog | hardware.manufacturers | 17 |
| catalog | firmware.firmware_releases | 6 |
| catalog | market.war_stories | 22 |
| catalog | ops.failure_patterns | 0 |
| operational | miner_readings | 17,856+ (growing) |
| operational | action_audit_log | 19+ |
| operational | miner_restarts | 8+ |
| operational | llm_analysis | 98+ |

### launchd services
- 10 always-on services (`ProcessType=Standard`), healthy in cluster 66707-66788
- 22 scheduled jobs registered (12 cron + 10 always-on)
- New: `com.miningguardian.scheduled.daily-backup.plist` at 02:00 CDT

### Grafana 13.0.1
- Served on port 3000, reachable at `http://100.69.66.32:3000` over Tailscale
- 4 datasources (1 operational PG + 2 catalog PG + 1 Prometheus)
- 9 dashboards rendering: 1 in repo's installer + 8 VPS-restored only on Mini (W26b will close this drift)
- Admin: `admin / W25test` (still needs proper rotation)

### dashboard_api
- Bound to `0.0.0.0:8585` (W25)
- `/fleet/board_stats` Postgres-strict (W25b)
- All P-038 slice sites converted to `fmt_dt(...)` (PRs #206 #207)

### Backup pipeline
- Daily pg_dump of both instances at 02:00 CDT
- 7-dump retention, env-tunable
- Pre-W14 dumps preserved indefinitely

---

## E5. Open items at end of day

### Resolved today (moved off the open list)
- ~~W14 split~~ ✅ Done (PRs #197 #201)
- ~~W14b convention lock~~ ✅ Done (PR #203)
- ~~W14 Step 9 (D6 backup pipeline)~~ ✅ Done (PRs #204 #205)
- ~~P-038 v2 cohort (19 + 14 slice sites)~~ ✅ Done (PRs #206 #207)
- ~~Dead-code sweep (archive/ + fixes/)~~ ✅ Done (PR #208)
- ~~W25 dashboard_api bind~~ ✅ Done (PR #209)
- ~~W25b /fleet/board_stats GROUP BY~~ ✅ Done (PR #210)
- ~~W26a Intelligence Catalog dashboard~~ ✅ Done (PR #211)

### Still open

**Tomorrow's priority (W26b):**
- **W26b — installer dashboard catch-up.** The Mini runs 9 dashboards; the repo's installer ships only 4 (3 legacy May-2 + 1 new catalog from W26a). The 8 missing dashboards (`mining_guardian_*.json` from VPS restore) need to land in the repo so the installer ships parity with production. **5 of the 8 contain hardcoded `100.69.66.32` references** in iframe URLs and other panel content — this is Bobby's specific Tailscale IP and would not work on a customer install. Two paths: ship as-is in a clearly-labeled `reference-mini/` subfolder, OR template the IP. Default per evening discussion: **ship as-is with reference-mini/ label, defer templating to a future W27**. See [`strategy/W26b_PREP.md`](strategy/W26b_PREP.md) for the runbook.

**Open security:**
- **🔐 Postgres password rotation** — Mini's deployed Grafana yaml still has the password as a literal 64-char hex hash; the same value was visible in chat today during W26a sanitization. Bobby decided "we will handle the passwords later" — should not slide past this week. Rotation requires: `ALTER USER mg WITH PASSWORD '<new>'` on **both** containers (5432 + 5433), update `.env` on Mini, update Grafana's deployed yaml on Mini (env-var form ideal but Grafana service has issues with `brew services` regenerating plist), restart all services that read `GUARDIAN_PG_PASSWORD`. ~30-60 min careful work.
- **🔐 Grafana admin password rotation** — currently `W25test`. Should be real before customer ship.
- **🔐 Anthropic API key** — rotated May 12 evening (E5 was leaked in chat May 11), but new key was also briefly visible in chat today during `.env` updates. Consider rotation cadence.

**Deferred technical debt:**
- **W17** — 151 naked `datetime.now()` calls to convert to UTC-aware. Reconciliation receipt unchanged from yesterday.
- **W24** — Grafana password secret management (proper). Currently inlined in deployed yaml.
- **db_maintenance.sh** had a Colima socket fix today (PR #205) — same pattern may exist in other helper scripts; spot-check during W26b prep.
- **catalog_import permissions** — pre-existing bug surfaced during W14 verification, tracked separately.
- **`daily_deep_dive` stale last-run-date tracking** — pre-existing bug surfaced during W14 verification, tracked separately.
- **feedback-loop-daemon** — not writing to catalog since 2026-05-09; tracked but not in W26b scope.
- **`.claude/settings.json`** plugin marketplace migration — clean drift in working tree, not committed.
- **3 untracked PNG files** at `installer/macos-pkg/resources/grafana/mining_guardian_{icon,primary,wordmark}.png` — wordmarks restored during W25; commit to repo in W26b or its own micro-PR.

---

## E6. Where the plan stands after today

| Phase | Items | Status after 2026-05-13 |
|---|---|---|
| Phase 1 — Foundation | W01, W02, W03, W04, W05 | W01 closed. W05 closed. W02/W03/W04 still in line per D5. |
| **Phase 1.5 — Architectural restoration** | W14a → W14 → W14b | **All three closed today + yesterday.** |
| Phase 2 — Closing the integration gap | W06, W07, W08, W09 | Unblocked by W14. Order TBD. |
| Phase 2b — Operator surfaces | W10 → W11 | Unblocked by W14. |
| Phase 3 — Catalog completeness | W26, W27, W30 | W26 closed. W27 + W30 open. |
| Phase 3b — Grafana intelligence dashboard | W23, W24, W25, W25b, W26a, W26b, W12 | W23/W25/W25b/W26a closed today. **W26b queued for tomorrow.** W24 open. W12 not started. |
| Phase 4 — Federation v1 | W28, W29 | July. |
| Phase 5 — Customer ship preparation | .pkg build, notarization | Late July / early August. |
| Phase 6 (post-ship) — Performance polish | W15, W17, W18-W22 | Post-August. |

---

## E7. Tomorrow's job in one paragraph

**W26b** — pull the 8 VPS-restored dashboards from the Mini into the repo's installer bundle so the installer ships parity with production. Drop them in `installer/macos-pkg/resources/grafana/dashboards/reference-mini/` to clearly label them as Mini-specific (5 of 8 have hardcoded Tailscale IP). Verify all 8 load on Mini's Grafana (regression check). Add a sibling-sweep cohort test in the spirit of W26a S6. Update the installer README to explain the reference-mini/ folder. **Estimated wall time: 60-90 min**, plus testing buffer.

Full runbook in [`strategy/W26b_PREP.md`](strategy/W26b_PREP.md).

---

## E8. Notes to tomorrow's Claude

- **Read MORNING_BRIEFING_2026-05-14.md first.** It points you to the right ordered reading.
- **Do not re-litigate W26b path.** Bobby's evening decision: ship dashboards as-is in `reference-mini/`, defer templating to a separate W item. If you want to challenge this, do it explicitly and concisely; do not silently choose a different path.
- **The Mini's live yaml has a hardcoded password.** Don't accidentally re-copy that into the repo. The repo version uses `${GUARDIAN_PG_PASSWORD}` env-var form — preserve this.
- **The naming collision:** repo has `fleet_overview.json` (7.5K, May-2 era); Mini has `mining_guardian_fleet_overview.json` (11.8K, VPS-era). They are **different files**. W26b ships the new one with its `mining_guardian_` prefix; leave the old one alone unless explicitly decided otherwise.
- **dashboard_api now has `MG_ANTHROPIC_LINKED=1`** in `.env` on Mini — this is operational, not bug-shaped. Don't reset.
- **Memory bias:** the morning of 2026-05-13 was W14 ship + post-W14 cleanup. The afternoon was Grafana restoration. Both were productive but distinct chapters; tomorrow's W26b is the natural continuation of the afternoon.

---

## E9. Quick verification commands for tomorrow

```bash
# Are we where we think we are?
ssh miningguardian@100.69.66.32 'sudo launchctl list | grep com.miningguardian | wc -l'
# Expected: 22 (12 cron + 10 always-on)

# Grafana healthy?
curl -s http://100.69.66.32:3000/api/health
# Expected: {"database":"ok","version":"13.0.1-0",...}

# dashboard_api reachable from Tailscale?
curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" http://100.69.66.32:8585/fleet/board_stats
# Expected: 200 0.0xxs

# Both Postgres instances responding?
ssh miningguardian@100.69.66.32 'docker exec mining-guardian-db psql -U mg -d mining_guardian -c "SELECT count(*) FROM miner_readings"'
ssh miningguardian@100.69.66.32 'docker exec mg-catalog-db psql -U mg -d mining_guardian_catalog -c "SELECT count(*) FROM hardware.miner_models"'
# Expected: operational has 17856+, catalog has 324

# Repo green?
cd /Users/BigBobby/Documents/GitHub/Mining-Guardian
git status                                              # main clean
git log --oneline -1                                    # 5cf154f or later
.venv-p018-tests/bin/python -m pytest tests/ 2>&1 | tail -3
# Expected: all pass
```

---

*End of evening handoff. See [`MORNING_BRIEFING_2026-05-14.md`](MORNING_BRIEFING_2026-05-14.md) for tomorrow's orientation, [`strategy/W26b_PREP.md`](strategy/W26b_PREP.md) for the runbook.*
