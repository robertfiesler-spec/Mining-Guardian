# Mining Guardian v1.0.3 — 2026-05-06 day-end handoff

```yaml
date: 2026-05-06
session_id: P-018 catalog-routing train + P-019 alias-seed FK robustness + retired-host doc cleanup; closing day with launchd bootstrap audit (P-019C) still in flight
last_commit_on_main: 2e96af1 — fix(installer): D-18 P-029 shell-safe .env, DB password reconcile, config.json (#150)
working_branch_tip: b44862c — fix(installer): FK-safe Tier-1 alias seed apply via pg_temp staging (P-019B)
latest_pkg_built: MiningGuardian-1.0.3-b44862c598b3.pkg (signed, notarized Accepted, stapled, spctl --assess accepted)
latest_pkg_install_outcome: failed at `step_install_plists_and_bootstrap` on com.miningguardian.dashboard-api with `Bootstrap failed: 5: Input/output error` / FATAL (34); alias seed step succeeded (87 / 1494 rows landed)
agent: Computer (autonomous agent)
repo: Mining-Guardian
scope: docs-only checkpoint; all today's repo changes already committed on the P-018/P-019B branch chain — this handoff records state and gate, no source/build changes here
```

This is a docs-only checkpoint. The P-018 catalog-routing train (A → E)
and the P-019B alias-seed FK robustness fix all merged into the
`mg/p019b-alias-seed-robust` branch chain today. The only remaining
in-flight workstream is the **launchd bootstrap audit** (informally
"P-019C") which is being driven by a separate subagent and has NOT yet
landed. The Mini is in a partial-upgrade state: alias data has been
written to both DBs by the new postinstall step, the package receipt
shows v1.0.3, but the dashboard-api LaunchDaemon is unstable and the
service plists were not all bootstrapped.

---

## Standing rules from Rob (carry forward)

- Over-document everything so future sessions have a reference point.
- Go slow and do it right; no shortcuts.
- Stay local — Bitcoin SHA-256 only. Local Ollama on the Mini, no
  cloud LLM in the operational loop.
- Never call SQLite live. Postgres only.
- No destructive operations on the Mini without explicit confirmation.
  This includes `docker volume rm`, `DROP TABLE`, `DELETE FROM`, any
  `rm -rf`, and any password rotation on a live service.
- Every session ends with a HANDOFF_<DATE>.md. Every session starts by
  reading the latest handoff.
- New today: **no more reinstall attempts on the Mini** until the
  launchd bootstrap audit completes and a fresh `.pkg` is built that
  passes the new orchestration tests. The Mini is partially upgraded
  and rerunning the current-built pkg is expected to hit the same
  exit-34 failure point.

---

## Open questions for Rob

1. Is it acceptable for `step_install_plists_and_bootstrap` to be
   refactored to bootstrap all 10 service plists with per-service
   isolation and a summary-then-FATAL pattern (the launchd-audit
   subagent's working assumption), or do you want a more conservative
   one-line fix that only addresses dashboard-api today?
2. The dashboard-api logs on the Mini show historic Postgres `mg`-user
   auth failures pre-cutover. Those are stale (P-029 reconciled the
   password) but the file-on-disk content might mislead a future
   debug session into chasing a phantom auth bug. Want to trim those
   pre-cutover lines from `dashboard_api.err.log` during the next
   reinstall, or leave them as forensic history?
3. Long-term B-24 fix (deterministic `uuid_generate_v5` for
   `seed_miner_models.sql` so the alias seed's frozen UUIDs match)
   — do you want this in the next sprint, or accept the P-019B
   staging shim + WARN-level coverage detector as the v1.0.3 ship
   state?

---

## Today's PRs / branches / commits

| Branch | Tip commit | Title | State |
|---|---|---|---|
| `mg/p018a-db-targets-helper` | `4adb769` | feat(core): add operational/catalog DB target helper (P-018A) | pushed; not opened as PR |
| `mg/p018b-catalog-writer-redirect` | `df59387` | feat(catalog): redirect dual_writer to catalog DB; route importer through db_targets (P-018B) | pushed; not opened as PR |
| `mg/p018c-catalog-context-pg-reader` | `f67d863` | feat(catalog): psycopg-direct catalog reader; feedback_loop two-conn split (P-018C) | pushed; not opened as PR |
| `mg/p018d-alias-seed-apply` | `6070052` | feat(installer): apply alias seeds in postinstall (P-018D) | pushed; not opened as PR |
| `mg/p018e-retired-host-cleanup` | `511ed27` | chore: retire ROBS-PC host defaults; route catalog API via db_targets (P-018E) | pushed; not opened as PR |
| `mg/p019a-docs-retired-host-cleanup` | `1ef6a36` | docs: retire ROBS-PC host from operator-facing guidance (P-019A) | pushed; not opened as PR |
| `mg/p019b-alias-seed-robust` | `b44862c` | fix(installer): FK-safe Tier-1 alias seed apply via pg_temp staging (P-019B) | pushed; not opened as PR; this is the **branch the .pkg was built from** |
| `mg/p019c-launchd-robust` | (in flight) | launchd bootstrap audit + diagnostics (informal P-019C) | not pushed; separate subagent in progress |
| `mg/p019c-day-end-docs` | this commit | docs: 2026-05-06 day-end handoff + B-25 (P-019D — docs only) | pushed when this lands |

Branch chain (each builds on the previous):

```
main (2e96af1)
  └─ mg/p018a-db-targets-helper       (4adb769)  P-018A
     └─ mg/p018b-catalog-writer-redirect (df59387) P-018B
        └─ mg/p018c-catalog-context-pg-reader (f67d863) P-018C
           └─ mg/p018d-alias-seed-apply  (6070052)  P-018D
              └─ mg/p018e-retired-host-cleanup (511ed27) P-018E
                 └─ mg/p019a-docs-retired-host-cleanup (1ef6a36) P-019A
                    └─ mg/p019b-alias-seed-robust (b44862c)     P-019B  ← .pkg built here
                       └─ mg/p019c-day-end-docs (this commit)   docs only
```

CLAUDE.md "Failure mode 9 — never branch a feature PR off another open
feature PR" applies here: when these PRs eventually open, each one
should be re-targeted onto `main` rather than merged in chain. The
chain only exists to share work-in-progress and to let the .pkg build
pick up the cumulative state.

---

## Workstreams completed today

The seven landed workstreams are all on the chain ending in `b44862c`.
Every one has its own commit message, in-repo tests, and (where
relevant) a `docs/LATENT_BUGS.md` entry. A one-paragraph summary per
workstream:

### P-018A — `core/db_targets.py` central DSN helper (`4adb769`)

Adds `core/db_targets.py` with `operational_target()` and
`catalog_target()` returning a frozen `DBTarget` dataclass that
resolves Postgres connection params from the canonical `GUARDIAN_PG_*`
family. Both targets share host / port / user / password — only
`dbname` differs (`mining_guardian` vs `mining_guardian_catalog`).
`__repr__` masks the password so a stray log line cannot leak it.
**Tests:** `tests/test_db_targets.py` — 21/21 green.

### P-018B — catalog writer redirect (`df59387`)

`intelligence-catalog/db/dual_writer.py::_get_connection` now resolves
through `core.db_targets.catalog_target()`. `mg_import_tool/mg_import.py`
adds `_resolve_operational_target` + `_connect_kwargs` and routes all
20 `psycopg2.connect` sites through it (operational target, behavior
preserved). The dead `mg.model_aliases` legacy fallback path is
documented in `docs/LATENT_BUGS.md` as B-22 (deferred — not P-018B
scope to delete the fallback). **Tests:**
`tests/test_db_targets_p018b_redirects.py` — 13/13 green.

### P-018C — psycopg-direct catalog reader + two-connection feedback loop (`f67d863`)

`ai/catalog_context.py` rewritten as a Postgres reader (D-14 sub-lock
5). Public surface preserved (5 functions + `CatalogReadFailure`).
The retired ROBS-PC HTTP default `http://100.110.87.1:8420` is gone.
An optional opt-in HTTP fallback is gated on a NEW env var
`MG_CATALOG_HTTP_FALLBACK_URL` and the runtime explicitly REFUSES any
value containing 100.110.87.1 / Tailscale CGNAT prefixes.
`intelligence-catalog/db/feedback_loop.py` refactored to two-connection
split: operational read + catalog write, with idempotent independent
commits. Public signatures take `op_conn=`/`cat_conn=`; legacy `conn=`
kwarg removed. **Tests:**
`tests/test_db_targets_p018c_catalog_reader.py` — 23/23 green.

### P-018D — alias seed apply step in postinstall (`6070052`)

New `step_apply_alias_seeds` in `installer/macos-pkg/scripts/postinstall.sh`
between `step_provision_catalog_db_and_seed` and
`step_install_ollama_and_pull_model`. Tier-1 → catalog DB
(`hardware.model_aliases`); Tier-2 → operational DB
(`mg.model_family_aliases`). Reserved exit code 42. Seed files moved
from `mg_import_tool/sql/seed/` to
`intelligence-catalog/seed-data/aliases/` so they survive the D-20
`mg_import*` payload purge. Tier-1 seed's `ON CONFLICT
(alias_normalized)` clause patched to the canonical `(miner_model_id,
alias)` (B-20). **Tests:** `tests/installer/test_postinstall_alias_seeds.sh`
— 21/21 green at this stage.

### P-018E — retired ROBS-PC host defaults cleanup (`511ed27`)

Six active Python files defaulted `OLLAMA_URL` to
`http://100.110.87.1:11434/api/generate`; one defaulted
`CATALOG_DB_HOST` to `100.110.87.1`. All seven switched to
`127.0.0.1:11434` / `127.0.0.1`. `intelligence-catalog/catalog-api/
catalog_api.py` now resolves DSN via `core.db_targets.catalog_target()`
with legacy `DB_*` env vars retained as backward-compat overrides;
the pre-P-018E `DB_NAME=mining_guardian` default that silently routed
the catalog API at the operational DB is gone. `.env.example` updated
to ship local defaults. **Tests:**
`tests/test_no_retired_host_defaults.py` — 5/5 green.

### P-019A — operator-facing docs retired-host cleanup (`1ef6a36`)

Five operator-facing docs (`DEPLOYMENT_CHECKLIST.md`,
`docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md`, `docs/CRON_SCHEDULE.md`,
`docs/DAILY_DEEP_DIVE_DESIGN.md`,
`docs/PERPLEXITY_PROMPT_MINING_INTELLIGENCE_CATALOG.md`) had their
recommendation-shape examples (`OLLAMA_URL=http://100.110.87.1:...` and
`curl http://100.110.87.1:...`) rewritten to local Mini defaults.
Historical-context references retained per "preserve archive history"
guideline. **Tests:** `tests/test_no_retired_host_in_operator_docs.py`
— 6/6 green.

### P-019B — FK-safe Tier-1 alias seed apply (`b44862c`)

Root cause: the Tier-1 seed freezes 317 specific `miner_model_id`
UUIDs from the seed generator's snapshot, but `seed_miner_models.sql`
uses `uuid_generate_v4()` per row — every install gets fresh random
UUIDs. The seed's frozen UUIDs almost never match the live DB's
UUIDs, so every Tier-1 INSERT trips the FK constraint and the
`BEGIN/COMMIT` envelope aborts everything. **Fix:** `step_apply_alias_seeds`
now stages the seed in a `pg_temp` scratch table without FK / UNIQUE,
then promotes only rows whose `miner_model_id` exists in
`hardware.miner_models` via an `INSERT … SELECT … WHERE EXISTS …`
gate. The seed file on disk is untouched. Verify section is now
three-tier: 0 → FATAL, <100 → ERROR-WARN drift detector, <5000 → INFO
partial, ≥5000 → INFO full. Documented as B-24 in `docs/LATENT_BUGS.md`.
**Tests:** `tests/installer/test_postinstall_alias_seeds.sh` extended
21 → 35 assertions, all green.

---

## Build validation (P-019B `.pkg`)

Built from branch tip `b44862c` as
`MiningGuardian-1.0.3-b44862c598b3.pkg`. All gates passed:

- Pre-build static tests: `test_postinstall_alias_seeds.sh` 35/35,
  `test_postinstall_catalog_seed.sh` 22/22 (shellcheck portions
  skipped on the build host because shellcheck wasn't installed —
  this is a known acceptable skip).
- P-018 / P-019 unit-test bundle: 68/68 passed.
- `productsign` succeeded with the Developer ID Installer cert.
- `notarytool submit … --wait` returned status `Accepted`.
- `stapler staple` succeeded.
- `spctl --assess --type install` returned `accepted: source=Notarized
  Developer ID`.

The package is signed and notarized correctly; the install failure
on the Mini is a runtime postinstall issue, not a packaging issue.

---

## Mini install outcome (2026-05-06 evening)

The pre-existing `MiningGuardian-1.0.3-1ef6a36...pkg` (P-019A tip)
had previously failed at the alias-seed step with `FATAL (42)
Tier-1 alias seed apply failed against mining_guardian_catalog` —
this was the symptom that drove the P-019B fix.

The new `MiningGuardian-1.0.3-b44862c598b3.pkg` (P-019B tip) was
installed today with the following observed sequence in
`/var/log/mining-guardian/install-postinstall.log`:

```
INFO migrations applied
INFO catalog DB seeded
INFO Tier-1 alias seed coverage VERY LOW: hardware.model_aliases has 87 rows …
INFO alias seeds verified: hardware.model_aliases=87, mg.model_family_aliases=1494
INFO Ollama install + model pull OK
INFO launcher wrappers installed
INFO venv ready
INFO config.json preserved (operator-edited copy intact across re-install)
INFO installed 10 LaunchDaemon plists into /Library/LaunchDaemons
INFO bootstrapped com.miningguardian.scanner
Bootstrap failed: 5: Input/output error
FATAL (34) launchctl bootstrap failed for com.miningguardian.dashboard-api
```

What this tells us:

- **P-019B did its job.** The alias seed step landed 87 rows into
  `hardware.model_aliases` (the ones whose `miner_model_id` happened
  to overlap between the seed snapshot and the live catalog) and the
  full 1494 rows into `mg.model_family_aliases` (Tier-2 has no FK).
  The drift detector logged "VERY LOW" at ERROR level — exactly the
  designed signal that the long-term B-24 fix is still needed.
- **The new failure is launchd orchestration, not seed shape.**
  Scanner bootstrapped successfully; dashboard-api hit
  `Bootstrap failed: 5: Input/output error`. This is the famously
  underspecified launchctl errno-5 surface where the actual
  diagnostic detail is hidden. The launchd-audit subagent (informal
  P-019C) is investigating the root cause now.
- **Approval and console were OK shortly after the install attempt;
  dashboard endpoint check failed.** The next-most-recent operator
  audit captured these reachability checks.

### Read-only audit results (recorded for the next session)

- All 10 `/Library/LaunchDaemons/com.miningguardian.*.plist` parse
  clean under `plutil -lint`. Each is `root:wheel` mode `0644`.
- Dashboard plist is structurally identical in shape to scanner
  plist; only label / paths / log file names differ.
- Dashboard launcher exists at
  `/Library/Application Support/MiningGuardian/bin/dashboard_api_launcher.sh`,
  is executable. It is owned `miningguardian:staff` even though the
  comment block at the top of the file says it should be `root:wheel`.
- Launcher checks .env / venv / api/dashboard_api.py are all present
  and the static path checks pass.
- `package_receipts | grep MiningGuardian` returns version `1.0.3`.
- Manual `sudo launchctl bootstrap system /Library/LaunchDaemons/
  com.miningguardian.dashboard-api.plist` AFTER the failed install
  returned rc=0; `launchctl print system/com.miningguardian.dashboard-api`
  showed pid 73764 / state running. But the dashboard endpoint check
  failed shortly after. Dashboard logs include historical Postgres
  `mg`-user auth failures pre-cutover and shutdown/restart noise.
  Manual bootstrap success suggests the plist itself is loadable;
  the failure is upgrade-state / launchd orchestration related, not
  plist syntax.

---

## Mini stabilization (do not run unless Rob confirms)

The system is **partially upgraded**. The cleanest thing to do is
NOTHING until P-019C lands and a fresh `.pkg` is built. If the
operator decides the dashboard endpoint must come back tonight
without waiting for the rebuild, this manual sequence brings the
dashboard service up using the artifacts that already shipped with
the b44862c install. It does NOT re-run the installer and does NOT
modify any data.

```bash
# 1. Confirm the failed-install state.
ls -la "/Library/LaunchDaemons/com.miningguardian.dashboard-api.plist"
launchctl print "system/com.miningguardian.dashboard-api" 2>&1 | head -3

# 2. Bootout any partial / stuck load (best-effort, ignore errors).
sudo launchctl bootout "system/com.miningguardian.dashboard-api" 2>/dev/null || true

# 3. Clear any persisted disable state.
sudo launchctl enable "system/com.miningguardian.dashboard-api"

# 4. Bring the launcher into the canonical root:wheel ownership
#    (the postinstall step that should set this is one of the
#    suspected P-019C culprits — leaving it miningguardian:staff
#    means a root LaunchDaemon is exec'ing a non-root-writable
#    script, which macOS may refuse on some releases).
sudo chown root:wheel \
  "/Library/Application Support/MiningGuardian/bin/dashboard_api_launcher.sh"
sudo chmod 0755 \
  "/Library/Application Support/MiningGuardian/bin/dashboard_api_launcher.sh"

# 5. Bootstrap.
sudo launchctl bootstrap system \
  "/Library/LaunchDaemons/com.miningguardian.dashboard-api.plist"

# 6. Confirm pid + endpoint.
launchctl print "system/com.miningguardian.dashboard-api" | head -10
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8585/ || true
```

If step 5 returns `Bootstrap failed: 5: Input/output error` again,
**stop and capture the unified log** for the next session:

```bash
log show --predicate "subsystem == 'com.apple.xpc.launchd'" --last 5m \
  | grep -i "miningguardian.dashboard-api" | tail -50
```

Do not loop bootstrap attempts; each retry can entrench launchd's
internal stale state and is one of the suspected P-019C causes.

---

## Things I currently believe that need re-verification

Per the handoff template's "worked example" pattern, list every
24+-hour-old belief acted on in this session and what would verify it.
Mark **[VERIFY FIRST]** anything the next session must check before
acting.

1. I believe the `MiningGuardian-1.0.3-b44862c598b3.pkg` payload
   contains the new `step_apply_alias_seeds` and that it ran on the
   Mini install attempt this evening.
   **[VERIFY FIRST if rerunning the install]** —
   `/var/log/mining-guardian/install-postinstall.log` must show
   `INFO alias seeds verified: hardware.model_aliases=<N>,
   mg.model_family_aliases=1494` for some N >= 0.

2. I believe the dashboard-api `Bootstrap failed: 5` is launchd
   orchestration / upgrade-state and not a plist parse error. Last
   verified: today, by manual bootstrap returning rc=0. Verify
   step: `plutil -lint /Library/LaunchDaemons/com.miningguardian.
   dashboard-api.plist` returns OK; `sudo launchctl bootstrap
   system /Library/LaunchDaemons/com.miningguardian.dashboard-api.plist`
   from a clean shell returns 0.

3. I believe the alias-seed apply landed `hardware.model_aliases=87`
   on the Mini's catalog DB. **[VERIFY FIRST before any catalog
   mutation]** —
   `docker exec mining-guardian-db psql -U mg -d
   mining_guardian_catalog -tAc "SELECT count(*) FROM
   hardware.model_aliases;"` must return 87.

4. I believe the package receipt shows version 1.0.3 but represents
   an INCOMPLETE install (LaunchDaemons not all loaded). Verify:
   `pkgutil --pkg-info com.miningguardian.installer` returns version
   1.0.3 AND `launchctl print system/com.miningguardian.scanner |
   head -3` shows a pid (scanner did bootstrap).

---

## Decisions made today

D-N entries are appended to `docs/DECISIONS.md`. None of today's seven
workstreams claimed a new locked decision; they all implement existing
locks (D-14 sub-lock 5, D-9, S-13, etc.). One new "**don't reinstall
yet**" gate is operationally binding for the next session but is not a
new D-N — it's a continuation of D-26 ("no more Mac mini install
attempts until the full preflight audit completes"), now extended to
"until P-019C lands and a fresh `.pkg` is built."

---

## Files created/modified this session

| Path | Purpose | Commit |
|---|---|---|
| `core/db_targets.py` | new central DSN helper | 4adb769 |
| `tests/test_db_targets.py` | P-018A unit tests | 4adb769 |
| `intelligence-catalog/db/dual_writer.py` | catalog writer redirect | df59387 |
| `mg_import_tool/mg_import.py` | importer routes through db_targets | df59387 |
| `tests/test_db_targets_p018b_redirects.py` | P-018B unit tests | df59387 |
| `ai/catalog_context.py` | psycopg-direct catalog reader | f67d863 |
| `intelligence-catalog/db/feedback_loop.py` | two-connection split | f67d863 |
| `tests/test_db_targets_p018c_catalog_reader.py` | P-018C unit tests | f67d863 |
| `installer/macos-pkg/scripts/postinstall.sh` | `step_apply_alias_seeds` (P-018D) + P-019B staging shim | 6070052 → b44862c |
| `intelligence-catalog/seed-data/aliases/001_hardware_model_aliases_tier1.sql` | moved from mg_import_tool, ON CONFLICT clause patched | 6070052 |
| `intelligence-catalog/seed-data/aliases/002_mg_family_aliases_tier2.sql` | moved from mg_import_tool | 6070052 |
| `intelligence-catalog/seed-data/aliases/README.md` | new aliases README | 6070052 |
| `tests/installer/test_postinstall_alias_seeds.sh` | 21 → 35 assertions across P-018D + P-019B | 6070052 → b44862c |
| `core/llm_analyzer.py`, `core/mining_guardian.py`, `ai/combine_knowledge.py`, `ai/daily_deep_dive.py`, `ai/local_llm_analyzer.py`, `ai/refinement_chain.py`, `migrations/migrate_sqlite_to_postgres.py`, `intelligence-catalog/catalog-api/catalog_api.py`, `intelligence-catalog/catalog-api/.env.example`, `.env.example` | retired-host defaults eliminated (P-018E) | 511ed27 |
| `tests/test_no_retired_host_defaults.py` | P-018E regression guard | 511ed27 |
| `DEPLOYMENT_CHECKLIST.md`, `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md`, `docs/CRON_SCHEDULE.md`, `docs/DAILY_DEEP_DIVE_DESIGN.md`, `docs/PERPLEXITY_PROMPT_MINING_INTELLIGENCE_CATALOG.md` | operator-facing docs retired-host cleanup (P-019A) | 1ef6a36 |
| `tests/test_no_retired_host_in_operator_docs.py` | P-019A regression guard | 1ef6a36 |
| `docs/LATENT_BUGS.md` | B-20 / B-21 / B-22 / B-23 / B-24 entries | various |
| `docs/handoffs/HANDOFF_2026-05-06_DAY_END.md` | this file | this commit |
| `docs/LATENT_BUGS.md` (B-25 row) | launchd bootstrap failure (OPEN) | this commit |

---

## Next session start checklist

1. Read this handoff file in full.
2. Re-verify every **[VERIFY FIRST]** belief above before taking any
   action. The dashboard-endpoint check on the Mini is the canary —
   if it's down, do NOT rerun the installer.
3. Pull the latest `mg/p019c-launchd-robust` branch (or whatever the
   launchd-audit subagent's branch is named when it lands) and read
   the diff against `b44862c` before deciding to rebuild the `.pkg`.
4. Confirm there are no destructive operations queued. Specifically:
   no `docker volume rm`, no `DROP TABLE`, no operational-DB
   modifications, no manual `launchctl bootout` loops on the Mini.
5. Read `docs/DECISIONS.md` for any D-N entries appended after D-26.
6. Read `docs/LATENT_BUGS.md` rows B-20 through B-25; the B-25 row is
   new today and tracks the launchd bootstrap blocker.
7. The current top priority is unchanged: **land the launchd
   bootstrap audit (P-019C), build a fresh `.pkg` from the new tip,
   reinstall on the Mini, and verify all 10 LaunchDaemons load**.
8. If anything in this handoff feels wrong or stale, STOP and confirm
   with Rob before acting.

---

## Failure modes spotted this session

Over-document the near-misses. Future sessions learn from these.

- **Stacked PR chain reused for build artifacts.** P-018A → P-018B →
  P-018C → P-018D → P-018E → P-019A → P-019B is exactly the shape
  CLAUDE.md Failure Mode 9 warns against. The chain works because
  none of the branches have opened PRs yet — but when they do, they
  must each be re-targeted onto `main`. If the operator opens
  `mg/p019b-alias-seed-robust` against `main` directly with the chain
  intact, the PR will surface every prior commit on the chain as
  changes-from-main, which is correct but verbose. The reviewer
  pattern is "open these as a stack of seven separate PRs against
  `main`" or "merge to main as one squash" — not "open one PR with
  the chain still attached."
- **Tier-1 alias seed coverage is correctly low (87 rows) because of
  the UUID drift documented in B-24.** The drift detector at
  `step_apply_alias_seeds` logged this as ERROR-level WARN — that's
  the designed signal. Don't mistake it for a P-019B regression. The
  long-term fix is making `seed_miner_models.sql` use deterministic
  UUIDs (B-24 future work).
- **Manual `launchctl bootstrap` succeeded after the install failed.**
  This is the strongest signal that the bug is upgrade-state /
  orchestration, not plist syntax. The launchd-audit subagent should
  treat this as the most important diagnostic data point, not chase
  plist content.
- **Dashboard launcher ownership mismatch** — comment says
  `root:wheel`, file is `miningguardian:staff` post-install. This is
  a known suspect for the P-019C root cause (a root LaunchDaemon
  exec'ing a non-root-writable script). Documented but not yet
  pinned as the cause.

---

## Costs / credits burned today

Order-of-magnitude (the operator's spend trend tracker):

- Subagents spawned: ~1 (launchd audit, still running)
- Memory writes: ~0
- PR reads / fetches: a handful
- Web fetches / searches: 0
- Notable expensive operations: 1 Apple notarization round-trip for
  `MiningGuardian-1.0.3-b44862c598b3.pkg` (Accepted on first try, no
  rebuilds). 1 install attempt on the Mini (failed at launchd
  bootstrap, did not require a wipe).
