# Session Log — 2026-04-27 (Monday)

**Operator:** Bobby Fiesler (BigBobby)
**Agent:** Perplexity Computer
**Session duration:** ~6:00 am CDT through ~8:15 am CDT (security track block)
**Commits shipped:** 4 PRs merged to main (`#7` OpenClaw removal, `#8` CRIT-1 password purge, `#9` CRIT-3 mg_import auth, `#10` CRIT-6 catalog API hardening). PR `#6` (Sunday docs) was merged earlier in the day.
**Context:** First day of the 9-day customer-grade hardening sprint to the **2026-05-05** Mac Mini install. Today closed out the **entire security track from CRITICAL findings** plus the OpenClaw dead-code purge, in a single uninterrupted block per operator instruction "no need to review the pr just keep going" / "straight in the same way".

---

## TL;DR

The security track is **done**. Every CRITICAL audit finding that gates the customer install is now landed on `main`:

- **CRIT-1** (hardcoded DB passwords across 13 files / 26 sites) → purged. Single source of truth is `MG_DB_PASSWORD` env. Process refuses to start without it.
- **CRIT-3** (mg_import was an unauth Flask app on `0.0.0.0`) → login flow + 8h session TTL (locked decision **D-4**) + bind to `127.0.0.1` by default. All 17 routes now gated by `@require_login`. 25/25 auth tests pass.
- **CRIT-6** (catalog API accepted placeholder API keys, used `==` for token compare, no rate limits, no input caps, listened on `0.0.0.0`) → placeholder rejection (≥32-char real secret required), `hmac.compare_digest`, slowapi rate limits, Pydantic input caps, loopback default. 16/16 hardening tests pass.

Three of the eight customer-grade exit criteria now flip green:
- ✅ #1 No leaked secrets
- ✅ #2 No hardcoded passwords
- ✅ #3 No dead code shipping

Plus one moves materially closer:
- ⏳ #7 Daily paper trail — **this file** ticks today's box.

The remaining five (#4 catalog schema, #5 AI has data, #6 installer rewrite, #7 ongoing logs, #8 customer docs) are this week's roadmap.

---

## Opening state (2026-04-27 ~6 am CDT)

- **VPS:** srv1549463 healthy. 4 am backup ran clean — 68 miners, 50 insights, 7 patterns; knowledge backup commit `d782ddf`.
- **Origin HEAD:** `fc1fffe` — PR #6 (Sunday docs) merged.
- **PAT status:** Friday's revoke-and-rotate confirmed clean. Only the new "3rd" token is Active and showed "Never used" on the GitHub settings page — that was the verification the operator asked for first thing this morning ("it says never used").
- **Audit gate:** All 4 CRITICAL findings still open from Sunday's audit (CRIT-1, CRIT-3, CRIT-6, plus OpenClaw dead code as a structural prerequisite for clean diffs).
- **Operator framing:** "no need to review the pr just keep going" — single uninterrupted block, no pauses between PRs.

---

## Commits shipped this session (chronological)

### 1. `0620ef3` — PR #7: chore(cleanup): remove OpenClaw dead code

**Why first:** OpenClaw was a vestigial notifier path that never shipped — keeping it in the tree meant every subsequent security PR would have to reason about whether the notifier was a real attack surface. Removing it first kept the CRIT-* diffs surgical.

**What landed (17 files, +25 / −266):**
- Deleted: `tests/test_openclaw_notifier.py`
- Stripped: OpenClaw branches in `notifiers/slack_notifier.py`, `scripts/deep_status.py`, `tests/conftest.py`, plus 13 other call sites
- Net: −241 lines, no behavior change

**Verification:** `grep -ri "openclaw" .` returns 0 hits in code (matches only docs referencing the historical removal).

---

### 2. `a3cbe57` — PR #8: security(crit-1): purge hardcoded DB passwords → MG_DB_PASSWORD env

**Problem:** Sunday's audit found the production DB password literal in 26 places across 13 files — `mg_import.py` (multiple sites), `catalog_api.py`, `migrate_to_postgres.py`, `.env.example`, `docker-compose.yml`, `deploy.ps1`, `README.md`, plus the SESSION_HANDOFF forensic doc.

**Fix:**
- Single helper `_db_password()` in `mg_import_tool/mg_import.py` reads `MG_DB_PASSWORD` and exits with a clear error if missing. All 26 mg_import sites route through this helper.
- `catalog_api.py`, `scripts/migrate_to_postgres.py`: same pattern.
- `intelligence-catalog/.env.example`, `docker-compose.yml`, `deploy.ps1`, `mg_import_tool/README.md`: replaced literals with `${MG_DB_PASSWORD}` references and explanatory comments.
- `docs/SECURITY.md`: PAT mentions redacted (literal token replaced with `[REVOKED 2026-04-24]` banner per locked decision **D-5b**).
- `docs/SESSION_HANDOFF_2026-04-24.md`: forensic doc kept literal for audit fidelity but gained a top banner "ROTATED — see SECURITY.md".

**Stats:** 13 files, +118 / −52.

**Verification:** `grep -rn "tX-fhG" .` returns 0 in code (only matches the forensic SESSION_HANDOFF, which is intentional and banner-marked).

**Locked decision applied:** **D-1** — `MG_DB_PASSWORD=tX-fhG#iJdm{V?>uuZ35G-Y)O5<UeN=5` (192-bit) lives only in operator-managed `secrets.bat` / VPS env, never in repo.

---

### 3. `5afb75c` — PR #9: security(crit-3): require login on mg_import + 8h session TTL + bind 127.0.0.1

**Problem:** `mg_import_tool/mg_import.py` was a Flask app exposing 17 routes (database imports, deletes, miner manipulation) bound to `0.0.0.0` with **no authentication of any kind**. On a Mac Mini sitting on the customer's LAN, that's a wormhole.

**Fix:**

**Imports added:** `hmac`, `secrets`, `wraps` from functools, `flask.session as flask_session`.

**Required env vars (process exits 2 if missing):**
- `MG_IMPORT_PASSWORD` — operator login password
- `MG_IMPORT_SECRET_KEY` — must be ≥32 chars, used to sign Flask session cookie

**Optional env vars:**
- `MG_IMPORT_SESSION_TTL_SECONDS` — default `28800` (8 hours, **D-4**)
- `MG_IMPORT_BIND` — default `127.0.0.1` (legacy `HOST` honored as fallback)

**Helper functions (all module-level, all unit-tested):**
- `_import_password()` / `_import_secret_key()` / `_import_session_ttl()` — env readers with validation
- `_ensure_secret_key()` — validates length on import
- `_is_session_authed()` — returns True iff session has authed=True AND `time.time() - authed_at < ttl`

**Decorator:** `@require_login` applied to all 17 existing routes. Unauth GET → 302 to `/login`. Unauth API → 401 JSON.

**New routes:**
- `GET /login` — HTML form (input `value=""` per locked decision **D-5a** — never echo password back)
- `POST /login` — verifies with `hmac.compare_digest(submitted, _import_password())`, sets session
- `POST /logout` — clears session
- `GET /healthz` — unauthenticated, returns `{"status":"ok"}` so monitors don't need creds

**Cookie:** `HttpOnly`, `SameSite=Lax`, name `mg_import_session`.

**Bind change:** `app.run(host='0.0.0.0', ...)` → `app.run(host=os.environ.get('MG_IMPORT_BIND', os.environ.get('HOST', '127.0.0.1')), ...)`.

**Launcher:** `mg_import_tool/launch_mg_import.bat` now sources `%USERPROFILE%\.mining-guardian\secrets.bat` if present, so the operator drops one secrets file in the home dir and the launcher picks it up.

**Tests:** `mg_import_tool/tests/test_crit3_auth.py` — 25 tests, all pass. Coverage:
- Unauth redirect to /login (GET)
- Unauth 401 (API)
- Login success → session set
- Login wrong password → no session, generic error
- Logout → session cleared, next call redirects
- /healthz unauth-accessible
- TTL expiration boundary (`time.time` monkeypatched forward by `ttl + 1`)
- Missing env vars cause clean process exit
- Source-level assertion that `hmac.compare_digest` is what's called (not `==`)

**Stats:** 4 files, +530 / −7.

**Pre-existing test caveat:** The mg_import_tool suite has 7 unrelated failures (`test_layer2_unmatched`, `test_resolver`, `test_unknown_field`) confirmed pre-existing via `git stash` before branching. Tracked separately, not blockers.

**README:** New "Authentication & network exposure (CRIT-3)" section with the full env var table.

---

### 4. `735efff` — PR #10: security(crit-6): catalog API hardening

**Problem:** `intelligence-catalog/catalog-api/catalog_api.py` had four independent attack surfaces:
1. It would happily run with `CATALOG_API_KEY` unset, empty, or set to placeholder values like `CHANGE_ME_TO_A_REAL_SECRET` / `__GENERATE_AT_INSTALL_TIME__` / `__SET_BY_INSTALLER__`.
2. Token comparison used Python `==` (timing-leaky).
3. Zero rate limits — anyone reaching the port could hammer the LLM-fronted endpoints.
4. Input objects were Pydantic but had no length caps. `include_sections` was free-form `List[str]`.
5. Bind was `0.0.0.0`.

**Fix on the API (`intelligence-catalog/catalog-api/catalog_api.py`):**

- Added `_FORBIDDEN_API_KEYS = {None, "", "CHANGE_ME_TO_A_REAL_SECRET", "__GENERATE_AT_INSTALL_TIME__", "__SET_BY_INSTALLER__"}`. Module load checks `CATALOG_API_KEY`: rejects if in forbidden set or `len < 32`. Process refuses to start.
- `verify_token`: replaced `==` with `hmac.compare_digest`.
- `API_HOST` default `0.0.0.0` → `127.0.0.1`.
- Rate limits via slowapi, all env-overridable:
  - `CATALOG_RATE_LIMIT_SCAN_BUNDLE` (default `60/minute`)
  - `CATALOG_RATE_LIMIT_MINER` (default `120/minute`)
  - `CATALOG_RATE_LIMIT_HEALTH` (default `600/minute`)
- `ScanBundleRequest`: `include_sections: List[str]` → `include_sections: List[Literal["models","issues","chips","firmware","all"]]`. Per-list caps in `model_post_init`: 200 models, 100 issues, 100 chips, 100 firmware. Per-string caps via `Field(max_length=256)`.
- `scan_bundle` route: parameter renamed `request: ScanBundleRequest` → `body: ScanBundleRequest` because slowapi needs the FastAPI `Request` object as `request`. All inner references updated `request.x` → `body.x`.
- `get_miner_knowledge`: `include` query param gets `max_length=256`.

**Fix on the client (`ai/catalog_context.py`):**

- `CATALOG_API_KEY` reads env, no default placeholder.
- `_CATALOG_KEY_PLACEHOLDERS` mirrors the API's forbidden set.
- `_headers()` returns `Optional[dict]` — `None` when key is missing or placeholder. Three call sites short-circuit on `None` (return empty / log degraded mode).
- `is_catalog_available()` no longer attaches auth (health endpoint is unauth).

**Config files:**
- `intelligence-catalog/catalog-api/.env.example`: `API_HOST=127.0.0.1` + new `CATALOG_RATE_LIMIT_*` lines + comment explaining the placeholder rejection.
- `intelligence-catalog/catalog-api/requirements.txt`: `+ slowapi==0.1.9`.
- `intelligence-catalog/catalog-api/test_api.py`: `DEFAULT_API_KEY = os.environ.get("CATALOG_API_KEY", "")` (no hardcoded default).

**Tests:** `intelligence-catalog/catalog-api/test_crit6_hardening.py` — 16 tests, all pass. Pattern uses `pytest.importorskip("psycopg2")` / fastapi / slowapi so the suite no-ops cleanly when deps are missing. Each test reloads the module via `sys.modules.pop("catalog_api", None)` + `importlib.import_module` to test env-var-time behavior. Coverage:
- Missing / empty / short / each placeholder value of `CATALOG_API_KEY` → import fails
- Real key → import succeeds, route accessible
- Wrong token → 401 via constant-time compare
- Source-level assertion `hmac.compare_digest` is used (not `==`)
- Rate limit triggers 429 after threshold
- `include_sections` with invalid literal → 422
- Per-list cap exceeded → 422
- Per-string cap exceeded → 422
- `/healthz` unauth-accessible
- Default bind is `127.0.0.1` when `API_HOST` unset

**Stats:** 6 files, +412 / −30.

---

## Locked decisions reaffirmed today

- **D-1** `MG_DB_PASSWORD` is the canonical DB credential. Never committed.
- **D-4** mg_import session TTL = 28800 seconds (8 hours). Implemented.
- **D-5a** mg_import login form input `value=""` — never echo. Implemented.
- **D-5b** `SESSION_HANDOFF_2026-04-24.md` keeps literal PAT for forensic record but carries top banner stating it's been rotated. Verified.

No new decisions taken today. Today was pure execution against Sunday's locked plan.

---

## Cutover gate (8 customer-grade exit criteria) — end of Monday

| # | Criterion | Status | Notes |
|---|-----------|--------|-------|
| 1 | No leaked secrets | ✅ done | PAT revoked Friday, scrubbed today in PR #8 |
| 2 | No hardcoded passwords | ✅ done | CRIT-1 / PR #8 |
| 3 | No dead code shipping | ✅ done | OpenClaw / PR #7 |
| 4 | One canonical catalog schema (N6) | ⏳ Tuesday | Data track starts tomorrow |
| 5 | AI has data | ⏳ Tue/Wed | Path is now hardened — CRIT-6 unblocks safe seeding |
| 6 | Installer rewrite (15 phases + 8 plists) | ⏳ Thursday | |
| 7 | Daily paper trail | ✅ today's log written | This file |
| 8 | Customer docs (manual + brochure) | ⏳ weekend | |

**Three flipped green today. Five remain. Eight days to install.**

---

## Patterns that worked (record for future sessions)

- `gh pr create --repo robertfiesler-spec/Mining-Guardian --base main --head <branch> --body-file /tmp/prN_body.md` with `api_credentials=["github"]` — never hits the rate-limited interactive editor path.
- `gh pr merge N --repo robertfiesler-spec/Mining-Guardian --merge --delete-branch` immediately after — branch is gone before the next branch is cut, so `git branch -a` stays clean.
- `git push -u origin <branch>` with `api_credentials=["github"]` refreshes the GH_ENTERPRISE_TOKEN without operator intervention.
- Multi `-m` flags on commits keep PowerShell-safe quoting on the operator's side and round-trip cleanly.
- `git stash` / `git stash pop` to confirm pre-existing test failures pre-date the current branch — used today on the 7 mg_import_tool failures, confirmed pre-CRIT-3.
- Always exclude stowaways from staging: `core/database_pg.py.pre_cr4_backup`, `core/mining_guardian.py.pre_cr4_backup`, `mg_pre_prod/` — caught two of these today.
- Module-reload pattern for env-var-time tests: `sys.modules.pop("catalog_api", None); importlib.import_module("catalog_api")` — required for CRIT-6 because the API key check runs at import time.

---

## Session counts

- PRs opened: 4
- PRs merged: 4
- PRs reverted or rolled back: 0
- Files touched: 40 (deduped across PRs)
- Net diff: +1085 / −355
- New tests: 41 (25 CRIT-3 + 16 CRIT-6) — all passing
- Production incidents: 0
- VPS state at end of day: identical to start of day (none of today's PRs need to deploy until installer rewrite Thursday)

---

## Tomorrow (Tuesday 2026-04-28) — data track begins

Per the locked roadmap:

1. **C4** — execute the 313-row baseline seed (`seed-data/seed_miner_models.sql`) into the catalog DB.
2. **N6** — schema consolidation pass: 165 tables / 1712 columns → one canonical surface. Identify orphan tables, mark for drop or migrate.
3. **C1** — start dual-write from the live mining-guardian path into the catalog so the AI stops reading a dead database.
4. **C3** — bring up the manufacturer watcher (first of five) writing into Postgres instead of `cron_tracking/*.json`.

Operator's framing for the week, restated for the record:

> "I would like everything done before we install on the Mac Mini... 100% representative of what customer would receive... All patches all fixes done. I want to be our first customer."
> "Remember slow and steady. I would rather be late and perfect than early and wrong."

Eight days. Slow and steady.

---

## Addendum — Tuesday data track pulled into Monday afternoon

Operator direction at the start of the afternoon:

> "lets keep going and knock off tuesdays as well, this is my only job for the day, so lets go"

The full Tuesday data track was executed in the same session. All five PRs merged to `main` before end of day. D-10 to install. Cutover gate row 5 ("AI has data") moves from ⏳ to ✅ on the C4, C1, and C3 sub-rows.

### PRs merged this afternoon

| # | Title | Commit | What it does |
|---|---|---|---|
| 12 | N6 schema consolidation | `833bc95` | Deletes duplicate `deploy_schema.sql`, promotes canonical `apply_schema.sql`, adds `seed-data/README.md`, fixes 7 latent bugs surfaced during review |
| 13 | C4 seed runner | `d9aca73` | `scripts/seed_catalog.sh` with idempotency guard, enum prerequisite block, 6-test suite |
| 14 | Orphan tables audit | _PR #14_ | `docs/CATALOG_ORPHAN_TABLES_2026-04-28.md` — drop / defer / wire-up disposition for every orphan table; `intelligence/` deprecated in favor of `intelligence-catalog/` |
| 15 | C1 dual-write | _PR #15_ | `staging.*` schema (3 tables + view + enum) + `intelligence-catalog/db/dual_writer.py` + `catalog_updater.py` wiring. Watchers UPSERT to `staging.*` then promote to `hardware.*`; JSON becomes debug export only |
| 16 | C3 manufacturer watcher | `8c6dc94` | `intelligence-catalog/watchers/` — 388-line framework, Bitmain parser (10 SHA-256 SKUs), 23 unit tests, cross-model alias collision detection (closes N6 review feedback) |

Combined with the morning's security batch (PRs #6–#11), today's total is **11 merged PRs** plus this addendum.

### Decisions locked during the afternoon

- **D-12 — Postgres-as-truth for spec/observation split.** The two-sets-of-numbers question (factory specs vs. real-world readings) was raised again. Ruling: factory specs live in `hardware.*` (one canonical row per model), real-world numbers live in `market.war_stories` and `ops.failure_patterns` (many rows per model, time-stamped, source-tagged). Watchers write to `staging.*` first; promotion into `hardware.*` is a deliberate human / C5 step. The JSON files (`unified_miner_index.json` etc.) become debug exports, not the source of truth.
- **C3 watcher source — fresh in repo, ignore VPS.** The VPS-only watcher script is abandoned. Mac Mini will be 100% repo-controlled, which is the only way the install date promise ("100% representative of what customer would receive") holds.
- **Drop list confirmed for May 4.** 13 tables and the entire `intelligence/` directory will be removed during the housekeeping pass: `hardware.{psu,control_board,board}_serial_batches`, `hardware.connector_pinouts`, `hardware.signal_chain_reference`, `facility.container_*` (3), `regulatory.*` (entire schema). PR #14 documents the rationale per table.

### Latent bugs surfaced and fixed mid-flight

1. **PR #12** — apply_schema.sql had 7 small but real defects (duplicated CHECK constraints, missing trigger function reference, etc.). All fixed.
2. **PR #14** — `intelligence/database/*.sql` files differed from canonical (still had the 7 latent bugs). Confirmed they are abandoned, not just duplicates.
3. **PR #14** — 16 manufacturers seeded but only 13 brand enums declared. Three (`jasminer`, `iceriver`, `goldshell`) had been silently re-introduced from a second `INSERT` block. Documented in the audit; will be reconciled before the May 4 housekeeping cut.
4. **PR #16** — `dual_writer.py` from PR #15 never registered the psycopg2 UUID adapter. PR #15 unit tests passed because they used `None` for `source_run_id`; the C3 watcher always passes a UUID, which exposed the gap. Fixed with a 21-line idempotent `_ensure_uuid_adapter()` helper. PR #15's full test suite still passes after the patch.

Finding #4 is the kind of bug you can only surface by running the next layer end-to-end — a small but useful argument for stacking the data-track PRs in one session rather than across two days.

### Sandbox state at end of afternoon

Postgres 17 sandbox at `/tmp:5433` against `mining_guardian`:

- **98 tables** (95 catalog + 3 staging from PR #15)
- **317 miner_models** in `hardware.miner_models`
- **16 manufacturers**
- **23 sources** in `knowledge.sources`
- C3 live watcher run produced 10 model proposals, 42 alias proposals, 1 manufacturer proposal in `staging.*` (status=pending). Idempotent re-run produced zero new rows. Test rows cleaned up post-validation; only the pre-existing PR #15 test rows remain.

### Cutover gate progress (end of Monday)

| # | Criterion | Status |
|---|---|---|
| 1 | No leaked secrets | ✅ |
| 2 | No hardcoded passwords | ✅ |
| 3 | No dead code | ✅ |
| 4 | One canonical catalog schema | ✅ |
| 5 | AI has data (C1, C3, C4 done; C5 + remaining watchers Wed) | ⏳ |
| 6 | Installer rewrite | ⏳ (Thu) |
| 7 | Daily paper trail | ✅ |
| 8 | Customer docs | ⏳ (weekend) |

Four rows green, two rows partially green, two rows pending. On schedule for D-Day.

### Wednesday roadmap (now reduced)

With the Tuesday data track done, Wednesday's work shrinks to:

1. C3 remaining manufacturer parsers — MicroBT, Canaan, Auradine, Bitdeer (all stubbed in `PARSER_MODULES`, just need `parsers/<brand>.py` + fixture each)
2. C5 feedback loop — auto-validation of `staging.*` rows that match existing `hardware.*` data, status flip from `pending` → `validated`
3. Wire writes for the DEFER tables that have parser sources: `firmware.*`, `market.*`, `repair.*`, `pool.*`, `facility.*`

Thursday's installer rewrite is unaffected.

---

*— end of 2026-04-27 log (addendum closed end-of-day)*
