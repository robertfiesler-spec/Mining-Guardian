> ## ⚠️ Status as of 2026-04-29 PM
>
> This document is preserved as a historical planning record (written 2026-04-28 morning). Key deltas since then:
>
> - **Mac Mini install date** moved to **2026-04-30** (was May 5–9 in this doc). Operator quote 2026-04-28 is still accurate: “rather be late and perfect than early and wrong” — date moved forward, not back.
> - **VPS decommissioned for MG** as of 2026-04-30 install. The Hostinger VPS (`root@srv1549463` / 187.124.247.182 / Tailscale 100.106.123.83) is historical for MG; Bobby still uses it for his own facility.
> - **Bucket 1 D-14 items** (drop cache, scan consults catalog, loud failure, C5 daemon, retire HTTP catalog) have been addressed in the 2026-04-29 doc sweep and subsequent PRs. Check `docs/MG_UNIFIED_TODO_LIST.md` for current status.
> - **VPS GitHub PAT rotation** (Bucket 2) — completed 2026-04-29 per `docs/SESSION_LOG_2026-04-27.md` CRIT-1.
>
> The body below is preserved verbatim as the historical 2026-04-28 snapshot.

# Remaining Work — 2026-04-28

**Created:** 2026-04-28 (Tuesday, 8:15 AM CDT)
**Status:** Active — this is the canonical "what's next" pointer until superseded.
**Supersedes:** `NEXT_SESSION.md` (banner-superseded 2026-04-28 in PR #31).
**Read-order rule:** At the start of every Mining Guardian session, read this file
**before** proposing any plan, then verify against current GitHub state via
`gh` CLI per the standing rule in `docs/OPERATOR_RULES.md`.

This doc is the single redirect point for "what is still left to do." It groups
the work into four buckets in priority order, points at the existing canonical
documents for each item (so nothing is duplicated), and records the locked
sequence the next session should follow.

---

## State of the repo on 2026-04-28 morning

- **`main` HEAD:** `d0e8b01` — *"docs(decisions): D-14 operational/catalog live-reference architecture (#33)"*
- **Open PRs:** none
- **Open branches on origin:** none (Option β cadence — branch deleted on squash-merge)
- **Last archive tag:** `archive/installer-build-20260428` → `ec7d359`

### Today's PRs (2026-04-28)

| PR | Subject | Squash SHA |
|---|---|---|
| #25 | bulk import tools + live DB re-import | `6f0b5a2` |
| #26 | docs(decisions): D-13 Ollama RAM auto-detect | `04ae080` |
| #27 | docs(claude.md): comprehensive refresh | `3248bde` |
| #29 | docs(branding): restore brand system | `4313ba9` |
| #30 | docs(latent-bugs): 5 bugs from PR #25 | `121dcd4` |
| #31 | docs(next-session): superseded banner | `5e4f1ee` |
| #32 | feat(installer): scaffold macOS Hybrid `.pkg` | `ffc687c` |
| #33 | docs(decisions): D-14 live-reference architecture | `d0e8b01` |

PR #28 was closed without merge (terminal-wizard contamination caught in
review).

### Locked decisions (this session)

| ID | Subject | Where it lives |
|---|---|---|
| D-13 | Ollama RAM auto-detect (supersedes D-8) — 16 GB→`llama3.2:3b`, 24 GB+→`qwen2.5:14b-instruct-q4_K_M` | `docs/DECISIONS.md` |
| D-14 | Operational ↔ catalog live-reference architecture (no scheduled refresh) | `docs/DECISIONS.md` |
| Q1 | Installer shape: Hybrid ~500 MB `.pkg` (double-click) | `docs/DECISIONS.md` |
| Cutover scope γ | Mac Mini replaces **both** the Hostinger VPS **and** the ROBS-PC catalog | `docs/DECISIONS.md` |
| Branch cadence | Option β — one narrow branch per PR, deleted on squash-merge | this doc + `docs/CLAUDE.md` |

---

## Bucket 1 — 🔴 Critical before May 5 (D-14 implementation + High-severity bugs)

This is the work that must land in `main` before the Mac Mini install window
(May 5 – 9). All five D-14 implementation PRs and all three High-severity
LATENT_BUGS items go here. Each bullet has its canonical pointer.

### D-14 implementation — five PRs in this exact order

Per Option β, each is its own narrow branch and deleted on squash-merge.
The architectural lock and the code-grounded findings that motivated each
step are in `docs/DECISIONS.md` under D-14.

1. **Drop the 5-minute cache.** `ai/catalog_context.py` — set `_CACHE_TTL = 0`
   and remove the cache plumbing. One-file PR. Branch: `feat/d14-1-drop-cache`.
2. **Wire `core/mining_guardian.py` to consult the catalog.** Verified
   2026-04-28 on `ffc687c` to have **zero** catalog references; the scan
   daemon must read `hardware.miner_models`, `ops.failure_patterns`,
   `hardware.model_known_issues`, and `market.war_stories` before evaluating
   any miner. Branch: `feat/d14-2-scan-consults-catalog`.
3. **Make catalog read failure loud.** Replace the silent circuit breaker in
   `ai/catalog_context.py` (silently returns `""` after 3 failures — a
   B-4-class silent-failure mode) with raise-and-log-at-ERROR. Branch:
   `feat/d14-3-loud-failure`.
4. **Build the C5 daemon.** Postgres `NOTIFY catalog_feedback` triggers on
   `public.action_audit_log`, `public.miner_restarts`, and
   `public.llm_analysis`; new `feedback_loop_daemon.py` that `LISTEN`s and
   invokes the existing C5 sync logic in
   `intelligence-catalog/db/feedback_loop.py` (PR #22, 30 KB, on `main`,
   not currently invoked); launchd plist for the Mini. Branch:
   `feat/d14-4-c5-daemon`.
5. **Retire HTTP `catalog-api` on the Mini.** Post-cutover, AI consumers on
   the Mini talk psycopg-direct to the catalog DB instead of HTTP to
   `100.110.87.1:8420` on ROBS-PC. Branch: `feat/d14-5-retire-http-catalog`.

### LATENT_BUGS — High-severity items (canonical entries in `docs/LATENT_BUGS.md`)

- **B-3 (High)** — `000_bootstrap_field_log_tables.sql` non-partitioned shape
  trap. Documented in PR #25, not fixed. Re-running it on a fresh Postgres
  install will leave the partitioned tables in a non-partitioned shape.
- **B-4 (High)** — `mg_import.insert_raw_json` silently swallows ingestion
  errors. **124 of 127 raw_json rows lost** during the live-DB re-import
  (PR #25). Fix-and-backfill is required: B-4 fix changes the ingestion
  helper to raise; backfill is a one-time re-import of the missing rows
  from the original archive set.
- **B-5 (Medium, but coupled to B-3)** — `mg_import.py` raw_json index targets
  a nonexistent column; was patched out as part of PR #25 to unblock import.
  The fix is "uncomment-and-correct" once B-3 is resolved, not before.

### Mac Mini install fundamentals (track in `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md`)

- Mini is sealed in box, 16 GB RAM, target install window 2026-05-05 → 2026-05-09.
- D-13 `qwen2.5:14b-instruct-q4_K_M` requires the 24 GB tier — Mini is on
  the 16 GB tier, so install path uses `llama3.2:3b`. Confirm runbook reads.
- Operator quote 2026-04-28: *"i am not going to go slow to hit a may 5
  install date lets roll"* — May 5 is **not** a hard deadline. Slip is
  preferred over wrong.

---

## Bucket 2 — 🟡 Cleanup this week

These are not blockers, but they should land before the Mini install so
the install does not import stale paths or expired credentials.

### B-6 typo cleanup — bigger blast radius than originally documented

The `docs/LATENT_BUGS.md` entry for B-6 currently lists only `docs/CRON_SCHEDULE.md`.
Verified 2026-04-28 on `d0e8b01`, the `Mining-Gaurdian` typo (missing the `r`)
appears in **far more** locations than the entry covers. The next session
should expand B-6 and fix the live-impact files.

**Current verified counts of `Mining-Gaurdian` (2026-04-28 on `d0e8b01`):**

| Scope | Files | Hits | Action |
|---|---|---|---|
| `deploy/*.service` (all 8 systemd units) | 8 | 29 | **Fix** — these are still copied onto fresh hosts |
| `docs/CRON_SCHEDULE.md` | 1 | 10 | **Fix** — the doc B-6 already names |
| `docs/CLAUDE.md`, `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md`, `docs/SECURITY.md`, `docs/TESTING.md`, `docs/MORNING_KICKOFF_PROMPT.md`, `docs/MG_UNIFIED_TODO_LIST.md`, `docs/LATENT_BUGS.md`, `docs/DAILY_DEEP_DIVE_DESIGN.md`, `docs/LOG_COLLECTION_ARCHITECTURE.md`, `docs/DIRECT_LOG_COLLECTION.md` | 10 | 25 | **Fix** — currently-active docs |
| Root: `README.md`, `CLAUDE.md`, `DEPLOYMENT_CHECKLIST.md`, `REPAIR_LOG.md` | 4 | 17 | **Fix** — top-level docs |
| `docs/SESSION_LOG_*` and historical handoff files | 8 | ~30 | **Leave** — historical record per "comprehensive + over-document" lock |
| `NEXT_SESSION.md` body (post-banner) | 1 | 5 | **Leave** — preserved verbatim by PR #31 |
| `archive/**` and `fixes/**` (frozen scripts) | 41 | 100+ | **Leave** — frozen by design |
| `.coverage` (binary build artifact) | 1 | 27 | **Leave** — regenerated on next test run |

**B-6 fix sequence:**
1. **First PR** — expand the B-6 entry in `docs/LATENT_BUGS.md` to list every
   "Fix" row above with its grep counts as evidence. This makes the bug entry
   match the verified blast radius. Branch: `docs/b6-expand-blast-radius`.
2. **Second PR** — actually fix every "Fix" row. Single sed-replace across
   `deploy/*.service` + the named docs, no script changes. Branch:
   `docs/b6-typo-cleanup`. Verify the operator runs `gh actions` (none
   currently) and that no `.service` file is referenced by an active
   ProcMon-style watcher before mass-rename.

### Other Bucket 2 cleanup

- **B-7 (Medium)** — migrations `002_layer2` + `*_staging` are not committed
  to the repo. They were applied directly to the live container in this
  session per `docs/SESSION_LOG_2026-04-27.md`. Add them to
  `migrations/` so a fresh install can reproduce the live schema.
- **VPS GitHub PAT rotation** — confirm rotation per
  `docs/SESSION_LOG_2026-04-27.md` CRIT-1.
- **Delete OLD Mac clone** Wed 2026-04-29 —
  `/Users/BigBobby/Documents/GitHub/Mining Gaurdian.OLD-20260428/`.
- **Delete `scripts/cleanup_ams_logs.py`** — flagged in PR #25 as orphaned.

---

## Bucket 3 — 🟢 Installer build (scaffolding done, content not started)

PR #32 landed the directory scaffold for the macOS Hybrid `.pkg` (Q1).
What remains is the actual content of each file. Track in
`docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md` and the installer scaffold
itself.

- `installer/scripts/preinstall.sh` — currently a stub. Must check macOS
  version, free disk space, and whether a previous Mining Guardian install
  exists. Bail loudly on any failure.
- `installer/scripts/postinstall.sh` — currently a stub. Must run the
  RAM-detect path per D-13, install the launchd plists, run initial
  `db init` against the bundled Postgres, and start the C5 daemon
  (Bucket 1 D-14 step 4) on first boot.
- `installer/Distribution.xml` — currently a stub. Must declare the
  bundle metadata, the minimum macOS version, and the pre/post script
  hookups.
- `installer/Makefile` — `make pkg` pipeline that calls `pkgbuild`,
  `productbuild`, then notarization with team `ARJZ5FYU94` /
  notarization key `FPZJ87B3QF`. Apple Dev login is
  `robfiesler25@gmail.com`. Private key values are local-only at
  `/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt`.

The installer-build branch history is preserved at tag
`archive/installer-build-20260428` → `ec7d359`.

---

## Bucket 4 — 🟢 Per-customer ops (not D-14, not blocking)

These are normal operations against the live fleet. They live here so a
new session sees them without losing them, but they do not block the
Mini install.

- **Miner 53476** — power cycle.
- **Miner 53494** — inspect (failure mode pending operator).
- **Miner 53521** — hashboards (pending inspection result).
- **Miner 53482** — underperforming, monitor and re-evaluate.
- **HVAC** — re-enable after `hvac_work_apr2026` window closes.
  Remove the `hvac_work_apr2026` hardware fact from the catalog when
  re-enabled.

---

## How to use this doc next session

1. **First action of any new MG session:** read this file, top to bottom.
2. **Second action:** verify state on GitHub via `gh` CLI:
   ```bash
   gh api repos/robertfiesler-spec/Mining-Guardian/commits/main --jq '.sha'
   gh pr list --repo robertfiesler-spec/Mining-Guardian --state open
   ```
   If `main` HEAD is not `d0e8b01`, this doc is **stale** — find the most
   recent `docs/REMAINING_WORK_*.md` and use that one instead.
3. **Third action:** propose a plan rooted in this doc's bucket order
   (Bucket 1 → 2 → 3 → 4). Never jump buckets without operator approval.
4. **When this doc is itself superseded:** replace this file in-place with
   the new dated version (e.g. `docs/REMAINING_WORK_2026-05-02.md`) and
   add a banner here pointing at the new file, in the same pattern as
   `NEXT_SESSION.md` was banner-superseded in PR #31.

---

## What is intentionally NOT in this doc

- **Locked decisions** — all locked decisions live in `docs/DECISIONS.md`.
  This doc only references them.
- **Open bug entries** — all open bugs live in `docs/LATENT_BUGS.md`. This
  doc only references the IDs.
- **Per-session diff records** — those live in `docs/SESSION_LOG_<date>.md`.
  This doc is forward-looking only.
- **Architecture description** — that lives in `docs/CLAUDE.md`. This doc
  assumes the reader has read `CLAUDE.md` already.
- **Brand system** — that lives in `branding/BRANDING.md`.

---

*End of REMAINING_WORK_2026-04-28.md*
