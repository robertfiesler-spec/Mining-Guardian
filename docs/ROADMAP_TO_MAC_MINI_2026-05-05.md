# Roadmap to Mac Mini Install — 2026-05-05

**Status:** SUPERSEDED — historical plan-of-record
**Created:** 2026-04-26
**Install date originally locked for:** Monday 2026-05-05
**Install date as of 2026-04-29:** Thursday **2026-04-30** — the operator pulled the install in once the cutover gate criteria went green (OpenClaw removed in PR #69 superseded by sweep, web GUI shipped in PR #88, operator schedules shipped in PR #90, catalog populated, installer .pkg ready in PR #79). The day-by-day plan below ran ahead of schedule.
**Cutover gate:** Customer-grade — all 8 exit criteria green as of 2026-04-29 EOD.
**Working style:** Slow and steady, step by step, late-and-perfect over early-and-wrong

> **Reading this on or after 2026-04-30?** This file is preserved for the audit trail. For the actual install runbook see `DEPLOYMENT_CHECKLIST.md` and `installer/macos-pkg/README.md`. For what shipped and when, see `docs/MG_UNIFIED_TODO_LIST.md`.

---

## Why May 5 (operator decision, 2026-04-26)

Original plan was Mac Mini install on Tuesday 2026-04-28 or Wednesday 2026-04-29 with a Monday "build day" cramming installer rewrite + security fixes + catalog database work into eight hours. After Sunday's audit consolidation made the full scope visible — installer rebuild, OpenClaw removal, 14 security findings, 5 critical catalog/database items, orphan code cleanup, customer documentation — the operator chose to push the install rather than ship a half-baked customer experience:

> "I would like everything done before we install on the Mac Mini. I truly want this to be a 100% representative of what customer would receive and load. All patches all fixes done. Paper written. I want to be our first customer. So if we push loading on the mini out that is fine. We were planing on May 5 anyway. I did not realize how far out we were. Remember slow and steady. I would rather be late and perfect than early and wrong."

The operator is customer #1. The install must be exactly what a paying customer would receive.

---

## Exit criteria (the cutover gate)

The Mac Mini install does NOT happen until all 8 of these are green:

| # | Criterion | How we verify |
|---|---|---|
| 1 | No leaked secrets in repo | S-2 PAT revoked at GitHub; `git log -p \| grep -E "(ghp_\|ghs_\|password\|MiningGuardian2026!)"` returns 0 hits in current tree |
| 2 | No hardcoded passwords or default API keys | CRIT-1 + CRIT-3 + CRIT-6 closed; new `MG_DB_PASSWORD` and `CATALOG_API_KEY` generated at install time |
| 3 | No dead code shipping to customer | OpenClaw fully removed (10 active source files clean); orphan tables dropped or wired (`chip_readings`, `log_collection_failures`, empty `guardian.db` stub, `databases/*.db`) |
| 4 | One canonical catalog schema | N6 done — 4 schema versions consolidated to 1, others archived |
| 5 | AI actually has data | C4 seed executed (313-row baseline) + C1/C3 dual-write live so catalog Postgres has real rows the API can read |
| 6 | Installer is real | `scripts/setup.sh` v2 produces a working system from a blank Mac in one pass: Postgres, Ollama (qwen2.5:14b), 8 LaunchAgents, 9 cron jobs, Grafana, Tailscale, secrets generation, masked credential prompts, idempotent re-runs |
| 7 | Daily paper trail | Every working day from now through 05-05 has a `SESSION_LOG_YYYY-MM-DD.md` committed |
| 8 | Customer-facing docs done | Setup Manual + Program Instructions + Product Brochure (8–10 pages with images) — all written and reviewed |

---

## Day-by-day plan (working days only — no weekend installs)

### Sunday 2026-04-26 (today) — ✅ DONE
- PR #5 merged (CR-5 Phase 1B GROUP BY fix)
- Audit consolidated into `docs/MG_UNIFIED_TODO_LIST.md`
- Mac Mini hardware decisions locked (16 GB Apple Silicon, qwen2.5:14b, Tailscale remote-only)
- Install date moved to 2026-05-05
- This roadmap + session log committed

**Tonight (within 1 hour):**
- ✅ **S-2 — Revoked leaked GitHub PAT** at `docs/SECURITY.md:80` (token `<REDACTED — revoked 2026-04-24>`). Confirmed `Never used` in GitHub settings on 2026-04-27. New PAT "3rd" issued.

---

### Monday 2026-04-27 — Build Day #1: code cleanup

**Goal:** OpenClaw out, hardcoded passwords out, mg_import locked down. End the day with the codebase showing no dead notifier code and no embedded credentials.

| Block | Item | Effort | Section ref |
|---|---|---|---|
| AM | OpenClaw surgical removal — all 12 sites in 10 active files | 1.5–2 hrs | UNIFIED §5 |
| AM | Run tests after each removal step (pytest) | included | UNIFIED §5.2 step 10 |
| AM | Commit + PR: `refactor: remove dead OpenClaw integration` | 15 min | |
| Mid | CRIT-1 — purge `MiningGuardian2026!` from 29 source locations + apply locked `MG_DB_PASSWORD` | 2 hrs | UNIFIED §2.2 |
| Mid | CRIT-3 — `mg_import` Flask app: add auth + 8-hour session TTL + bind to 127.0.0.1 | 2 hrs | UNIFIED §2.3 |
| PM | CRIT-6 — Catalog API hardening: generate API key at install, fix `!=` token compare to `hmac.compare_digest`, error handler stops leaking `str(exc)` | 2 hrs | UNIFIED §2.5, §3.5, §3.7 |
| EOD | `docs/SESSION_LOG_2026-04-27.md` committed | 20 min | |

---

### Tuesday 2026-04-28 — Build Day #2: catalog database

**Goal:** AI stops starving. C4 + N6 done in the morning, C1 dual-write architecture decided and started in the afternoon.

| Block | Item | Effort | Section ref |
|---|---|---|---|
| AM | C4 — Run `seed-data/seed_miner_models.sql` against catalog Postgres | 30 sec | UNIFIED §4.1 |
| AM | N6 — Pick canonical catalog schema, archive the other 3, document why | 2 hrs | UNIFIED §8.2 |
| AM | Drop orphan tables: `chip_readings`, `log_collection_failures`, `s19jpro_overheat_tracking` (or wire — recommend drop) | 30 min | UNIFIED §8.1 |
| AM | Delete `guardian.db` 0-byte stub + `databases/*.db` empty SQLite files | 10 min | UNIFIED §8.1 |
| PM | C1 path A (dual-write) — design + first watcher converted (Manufacturer 920d0231) | 2 hrs | UNIFIED §4.2 |
| PM | C3 — Manufacturer watcher UPSERT to catalog Postgres, end-to-end verified | 1.5 hrs | UNIFIED §4.3 |
| EOD | `docs/SESSION_LOG_2026-04-28.md` | 20 min | |

---

### Wednesday 2026-04-29 — Build Day #3: catalog finish

**Goal:** All 5 watchers writing to Postgres, feedback loop wired, AI is now reading from a populated catalog.

| Block | Item | Effort | Section ref |
|---|---|---|---|
| AM | C3 — Firmware watcher (aa676933) UPSERT | 1 hr | |
| AM | C3 — Community watcher (c8c4678d) UPSERT | 1 hr | |
| AM | C3 — Aggregator watcher (4cc981c0) UPSERT | 1 hr | |
| PM | C3 — Deep enrichment watcher (ebb3af70) UPSERT | 1 hr | |
| PM | C5 — Operational→catalog feedback loop (action_audit_log → ops.failure_patterns, llm_analysis → market.war_stories, miner_restarts → hardware.model_known_issues) | 2–3 hrs | UNIFIED §4.4 |
| PM | Verify catalog API now returns real rows for all 21 query types | 30 min | |
| EOD | `docs/SESSION_LOG_2026-04-29.md` | 20 min | |

---

### Thursday 2026-04-30 — Build Day #4: installer rewrite

**Goal:** New `scripts/setup.sh` exists and runs end-to-end on a sandbox.

| Block | Item | Effort | Section ref |
|---|---|---|---|
| AM | Inventory `setup.sh` v1 vs production reality — write gap doc | 30 min | UNIFIED §7.1, Track I-1 |
| AM | Write 8 plist templates in `deploy/launchd/` (one per service) | 1 hr | UNIFIED §7.3 7b |
| AM/PM | Rewrite `setup.sh` v2 — all 15 phases (pre-flight, customer info, brew, Postgres, seed, repo, secrets, Ollama, LaunchAgents, cron, Grafana, Tailscale, smoke test, post-install, optional restore) | 4–5 hrs | UNIFIED §7.2, Track I-2 |
| PM | Build `scripts/restore_from_snapshot.sh` (separate script the installer optionally calls) | 1.5 hrs | Track I-4 |
| EOD | `docs/SESSION_LOG_2026-04-30.md` | 20 min | |

---

### Friday 2026-05-01 — Build Day #5: installer test + remaining security

**Goal:** Installer survives sandbox test. Remaining security findings closed.

| Block | Item | Effort | Section ref |
|---|---|---|---|
| AM | Sandbox test on fresh user account / macOS VM — paper-cut log | 1.5 hrs | Track I-5 |
| AM | Fix paper cuts surfaced by sandbox | 1–2 hrs | |
| Mid | S-7 — services run under dedicated `guardian` user, not root | 1 hr | UNIFIED §3.2 |
| Mid | S-8 — `intelligence_report_api.py` wildcard CORS + 0.0.0.0 binding fixed | 30 min | UNIFIED §3.3 |
| PM | S-9 — Auradine client: remove `admin/admin` defaults, default `verify=True` | 30 min | UNIFIED §3.4 |
| PM | S-10 — Catalog API global exception handler stops leaking `str(exc)` | 30 min | UNIFIED §3.5 |
| PM | S-11 — Path traversal in `/reports/{filename}` — sanitize | 30 min | UNIFIED §3.6 |
| PM | S-12 — Token compare `!=` → `hmac.compare_digest` (covered by CRIT-6 if scoped) | 15 min | UNIFIED §3.7 |
| PM | S-13 — Hardcoded Tailscale IP fallbacks (12 sites) replaced with config | 1 hr | UNIFIED §3.8 |
| PM | S-14 — `setup.sh` masked AMS password input via `read -s` (folded into installer rewrite) | covered | UNIFIED §3.9 |
| EOD | `docs/SESSION_LOG_2026-05-01.md` | 20 min | |

---

### Weekend 2026-05-02 / 05-03 — Customer documentation + housekeeping (operator's call to work or rest)

**Goal if working:** Customer-facing docs done.

| Item | Effort | Section ref |
|---|---|---|
| Customer Setup Manual (beginner-friendly, with images) | 4 hrs | UNIFIED §10.4 |
| Program Instructions (beginner-friendly) | 3 hrs | UNIFIED §10.5 |
| Product Brochure 8–10 pages with images | 4 hrs | UNIFIED §10.6 |

If operator chooses rest, these slide to Monday 05-04.

---

### Monday 2026-05-04 — Final hardening + repo housekeeping

**Goal:** Repo is polished. Final dry run passes. Operator's housekeeping wish granted.

| Block | Item | Effort |
|---|---|---|
| AM | Full sandbox install dry-run with snapshot restore | 2 hrs |
| AM | `DEPLOYMENT_CHECKLIST.md` rewritten to match installer v2 | 30 min |
| AM | Grafana provisioning yaml (datasource + dashboards) | 1.5 hrs |
| PM | **Repo housekeeping pass** (operator request 2026-04-26): consolidate `docs/`, edit for polish, delete unrelated files, clean folders | 3–4 hrs |
| PM | Final tag pre-cutover: `v1.0.0-rc1` | 15 min |
| EOD | `docs/SESSION_LOG_2026-05-04.md` | 20 min |

---

### Tuesday 2026-05-05 — INSTALL DAY

**Goal:** Real install on Mac Mini. Document every step in real time.

| Block | Item |
|---|---|
| AM | Pre-flight: VPS snapshot taken, snapshot tarball copied to Mac, Mac on miner LAN, Mac has Apple ID + admin user |
| AM | Run `scripts/setup.sh` on Mac (interactive, real customer creds) |
| AM | Run `scripts/restore_from_snapshot.sh --tarball=<...>` |
| Mid | Smoke tests: scan loop, AMS reach, all 8 services, Slack ping, Grafana datasource, Ollama smoke |
| Mid | Switch DNS / VPS to cold-backup mode |
| PM | 30-minute burn-in observation |
| PM | If green: tag `v1.0.0`, write `docs/SESSION_LOG_2026-05-05.md`, write `docs/INSTALL_REPORT_2026-05-05.md` |
| PM | If red: pre-defined rollback (VPS comes back hot, snapshot restore on Mac re-attempted next day) |

---

## Decision points still open

| # | Question | When it must be answered |
|---|---|---|
| D1 | C1 path A vs B vs C | Tuesday morning before C1 work starts |
| D2 | N6 — which of the 4 catalog schemas is canonical | Tuesday morning |
| D3 | Customer brochure tone/visual style | Saturday 05-02 |
| D4 | Whether to migrate Slack to Bolt/Socket Mode pre-cutover or defer | Recommended defer; revisit Friday 05-01 |

For D1 and D2, recommend agent picks based on least-risk; operator confirmed "your recomendations always this is above me now, just go" earlier in the project.

---

## Tracking

- Daily session logs: `docs/SESSION_LOG_YYYY-MM-DD.md`
- Daily PR per day where there's commits, on a date-stamped branch
- This roadmap gets updated end-of-day if scope shifts; changes appear in that day's session log

---

## Out of scope (do NOT touch before 05-05) — outcome as of 2026-04-29

- ~~OpenClaw branch experimental work~~ — moot. OpenClaw is fully removed from the codebase as of the 2026-04-29 doc sweep.
- ~~Web GUI for `approval_api.py:8686` (operator backlog, post-cutover)~~ — shipped in PR #88 (§10.1, §10.2).
- ~~Mode selector (Full Auto / Semi Auto / Manual) GUI (operator backlog, post-cutover)~~ — shipped in PR #88.
- Operator-controlled schedules (§10.7) — shipped in PR #90.
- Bolt/Socket Mode Slack migration — still deferred.
- `migrate_to_postgres.py` deletion — still deferred (guarded by `MG_ALLOW_MIGRATION=1`, see D-6).

---

*Last meaningful update of the day-by-day plan: 2026-04-26. Historical-status header refreshed: 2026-04-29.*
