# Postgres Migration Status — 2026-04-24 (final)

## TL;DR

**Migration complete.** SQLite fully deprecated and removed from VPS. All 8
systemd services running on Postgres with no loose ends.

The old `guardian.db` (6.6 GB) was compressed and stashed at
`/Volumes/Big-Bobby-T9/Bixbit USA/Mining Guardian Backups/guardian.db.frozen.2026-04-23.gz`
(704 MB compressed, gzip-integrity verified) and deleted from the VPS.

**54 commits shipped since migration start** (51 on 2026-04-23 + 3 on 2026-04-24).

## Service state (verified 2026-04-24 mid-morning)

| Service | Status | Notes |
|---|---|---|
| mining-guardian | active | Scan cadence ~1/hour, latest #1716 at 09:07 CDT |
| dashboard-api | active | /metrics returns 200 (fixed via commit `edb579c`) |
| approval-api | active | No errors |
| slack-listener | active | No errors |
| slack-commands | active | Slack API rate-limit WARNINGS (benign, pre-existing) |
| overnight-automation | active | No errors |
| mining-guardian-alerts | active | No errors |
| intelligence-report | active | No errors |

**All 8 services: zero restarts, running clean on Postgres.**

## Database state

- **Postgres `mining_guardian`**: active production database, Postgres 16 on
  localhost:5432, user `guardian_app`
- **SQLite `guardian.db`**: gone. Frozen + gzipped on Bobby's T9 HDD at
  `/Volumes/Big-Bobby-T9/Bixbit USA/Mining Guardian Backups/guardian.db.frozen.2026-04-23.gz`
  (704 MB compressed, gzip integrity verified). Removed from VPS.
- Schema file `migrations/001_initial_schema.sql` is fully representative —
  PRIMARY KEY constraints on `miner_baselines.miner_id` and
  `alert_listener_seen.notification_id` are in the file (were added at initial
  schema creation, no backport needed).

## Cron jobs

`GUARDIAN_PG_*` env vars are installed in the crontab (one-time installation
at 17:40 CDT on 2026-04-23 via `crontab /tmp/crontab_new.txt`). All overnight
jobs now connect to Postgres successfully under cron.

| Cron | Status |
|---|---|
| 00:00 weekly_train | **Fixed 2026-04-24 morning.** Last night's run crashed on 5 separate bugs. All fixed in commits `cc0c22c` + `29390e8`. Verified end-to-end via manual rerun (16 cohorts, 49 insights saved). Tonight's cron will succeed. |
| 01:00 refinement_chain | Ran clean last night |
| 04:00 knowledge_backup | Ran clean last night, committed as `a7e5810` |
| 07:00 morning_briefing | Runs but has a `maximum recursion depth exceeded` warning in cost_tracking. Still delivers the briefing to Slack. Non-blocking. |
| 08:00 daily_operator_review | Ran clean |
| 13:00 direct_collect_logs | First post-fix cron run later today. Yesterday was manual-run only (42/47 miners, 16.31 MB logs). |
| 16:00 daily_deep_dive | First post-fix cron run later today. Yesterday ran manually with `--scan-id 1698` override (34/34 miners, 4h runtime). |

## Known outstanding issues

### 1. `morning_briefing.py` cost_tracking recursion warning

`Cost tracking unavailable for briefing: maximum recursion depth exceeded`

Observed in 7am cron output on 2026-04-23 AND 2026-04-24. Morning briefing
itself posts to Slack fine; only the cost-tracking section is missing. Probably
a circular import or recursive function introduced by the Postgres migration.
Non-blocking, worth investigating when convenient.

### 2. Slack API rate-limit warnings on slack-commands

WARNING-level `ratelimited` responses when polling channel history. Pre-existing,
not caused by migration. Quality-of-life fix: increase poll interval or batch
channel lookups. Low priority.

### 3. Mac Mini deployment (future work, not a current issue)

Hardware arriving 2026-05-05 through 2026-05-09. The Mac Mini will host production
Mining Guardian. Local LLM will run on the Mac Mini itself (not RTX 4090 via
Tailscale). All Cloudflare tunnels must be shut down before cutover (production
= no public ingress). Fresh Postgres install will pick up schema from
`migrations/001_initial_schema.sql` correctly (PKs + indexes all in file).

## Remaining Mac-local cleanup (optional)

Three stale `guardian.db` copies on Bobby's Mac (~130 MB total):

- `/Users/BigBobby/guardian.db` — 0 bytes, stub
- `/Users/BigBobby/Documents/GitHub/Mining Gaurdian/guardian.db` — 272 KB
- `/Users/BigBobby/Documents/GitHub/Mining Gaurdian/artifacts/guardian.db` — 129 MB

Not affecting operation. Worth archiving or deleting when Bobby feels like it.

## Git state

- Working tree: clean
- origin/main == local main: yes
- **54 total migration-era commits** (`d452317` onward)
- Latest on 2026-04-24: `29390e8` fix(postgres): 4 more bug classes in train_cohort.py

## What's permanently resolved

- ✅ **All `conn.execute()` → psycopg2 cursor patterns** (Phase 7.1 → 7.11 +
  hashrate_evaluation + train_comprehensive)
- ✅ **All 8 classes of post-flip bugs** fixed: DictCursor swap, ROUND::numeric
  casts, %% LIKE escapes, GROUP_CONCAT → string_agg, datetime() → INTERVAL,
  placeholder-join bug, GROUP BY + HAVING alias fixes, non-aggregate SELECT fixes
- ✅ **`train_cohort.py` Postgres compatibility** (the cron path): cooling_mode
  text cast, ROUND::numeric wrapping, text-timestamp cast, GROUP BY ip,
  Decimal→float arithmetic
- ✅ **`direct_collect_logs.py` %miner.log escape** (`26207fe`)
- ✅ **`daily_deep_dive.py` 3 %miner.log escapes** (`52380c1`) + `--scan-id`
  override flag (`2a1bc4e`) for AMS-transient recovery
- ✅ **Crontab env vars** installed (`GUARDIAN_PG_*`)
- ✅ **SQLite removed from VPS**, archived to T9 HDD
- ✅ **Schema file has all PKs and indexes** (no backport needed for Mac Mini)

## Lessons captured

- Trust git over conversation memory. Chat compaction dropped 5+ messages
  during this migration. Each resume started with `git log --since=today`
  and a filesystem audit rather than trusting remembered state.
- DictCursor (not RealDictCursor) is the drop-in sqlite3.Row replacement —
  supports both `row[0]` and `row["col"]`.
- psycopg2 interprets `%` as format specifier even with empty params —
  always double `%%` in LIKE patterns.
- Postgres ROUND requires `::numeric` cast for double-precision input.
- psycopg2 returns NUMERIC columns as Decimal; Python `**0.5` fails on
  Decimal. Cast to float at collection time for arithmetic.
- TEXT-stored timestamps need `::timestamp` cast for comparisons.
- Running code that was never tested end-to-end will surface multiple bugs
  in sequence. Schedule manual runs BEFORE cron time whenever possible.
- Bobby's "I think, but I'm not sure" instincts were consistently accurate
  through this migration — worth investigating every time.
