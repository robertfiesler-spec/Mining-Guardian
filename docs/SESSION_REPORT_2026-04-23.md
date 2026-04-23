# Session Report — April 21 through April 23, 2026

**Subject:** What happened with the database split, and how it was cleaned up
**Audience:** Bobby and anyone picking up this work later
**Length:** ~2 pages of plain English

## The short version

On April 21, the Mining Guardian codebase was reorganized to split the single
6.6 GB SQLite database into four smaller databases. The split landed in the
repo, but the code that was supposed to route reads and writes to the right
database had bugs that nobody caught until the system crashed in production.
Over April 22-23, those crashes were stopped, the system was pulled back to
the original monolithic database, and the codebase was cleaned up so that
when we eventually do split the database for real (probably alongside the
Mac Mini migration in May), we'll have a clear playbook instead of surprise
crashes.

The system is stable. Nothing important was lost. Here's the story.

## What happened

### April 21 — the split landed

Someone did a big refactor: the single `guardian.db` file (everything
Mining Guardian writes — scans, miner telemetry, logs, audit trail,
approvals) was logically split into four smaller databases by category:
`operational.db` (live state), `timeseries.db` (historical readings),
`audit.db` (who did what when), `ai_knowledge.db` (AI outputs). A new
file `core/database_router.py` was added to figure out which database a
given query should go to.

On paper, this was a good move. The timeseries data was 5.4 GB by itself
and growing, and splitting it out would make backups and future Postgres
migrations easier. The smaller operational DB would also be faster for
hot queries.

But the split required every method in `core/database.py` to respect the
new rule: **one database connection, one database at a time, no cross-DB
queries.** And seven methods in that file didn't respect the rule. They
were written when everything lived in one file, and they did things like
"open the connection for the audit table, then run a query against the
restarts table on that same connection." Under one database, fine. Under
the split, that crashes with `no such table: miner_restarts` because
SQLite can't look across separate database files.

### April 22 — production crashed, then was stabilized

The split went live and mining-guardian immediately started crashing. The
first crash was a trivial missing `import json` that turned into a
`NameError` at line 601. Fixed in about 30 seconds. But fixing that
unblocked a deeper crash in `count_outcome_failures` — one of the seven
methods that tried to query across databases. Fixing that would unblock
another one, and another.

The right call in the moment was to not play whack-a-mole. Instead, the
`_connect()` function (which the router uses to hand out database
connections) was rewritten to ignore the requested database and always
hand back a connection to the original monolithic `guardian.db` file.
All 38 places in the code that call `_connect()` kept working, the
cross-database bug disappeared because there was only one database again,
and mining-guardian came back up in about 90 minutes total from first
crash to verified recovery.

The four split databases were left alone on disk as cold snapshots —
useful as rollback points, harmless as long as nothing was writing to them.

### April 23 — the cleanup (this session)

Came back to the same system and worked through the mess systematically:

**First, sorted out the reality.** There turned out to be *three*
databases in play, not just the two mentioned yesterday: the monolithic
`guardian.db` on the VPS (live), the four frozen split-SQLite files on
the VPS (cold snapshots), an empty-schema Postgres on the VPS waiting to
be the migration target, and a completely separate Postgres running in a
Docker container on Bobby's PC that holds the Field Intelligence catalog
data. The PC-side docs had conflated "the VPS Postgres" and "the PC
Postgres" because both happened to be named `mining_guardian`. Wrote
`docs/DB_STATE_2026-04-23.md` as the canonical source of truth going
forward.

**Next, cleaned up the git tree.** Nine files had half-finished
refactoring work in them (an import that was added but never used).
Reverted those back to their committed state — better to have "no
refactor yet" than "refactor in progress, waiting for who knows how
long." Committed the real stabilization fixes from yesterday with a
clear explanation of what broke, what was done, and what's still
outstanding. Tagged the Postgres migration script as WIP. Added
`reports/` to `.gitignore` since it's just generated PDFs.

**Then, audited every database method in `core/database.py`.** Using a
parser, walked every one of the 38 places in the file that calls
`_connect()`, checked what SQL each one runs, and cross-referenced
against the routing table to identify which ones would crash under an
active router. Found seven bugs. Four of them were single-line fixes
(wrong database hint for a single query). Three were structural (code
that needed to be split into two database connections with the data
passed in Python between them). One was large (the schema-creation
function needed to be partitioned across three connection blocks, one
per target database). Wrote `docs/CORE_DATABASE_AUDIT_2026-04-23.md`
to catalog everything before fixing anything.

**Then, fixed all seven bugs.** One commit per bug, each with a clear
message explaining what the bug was and what the fix did. Tests passed
at every commit (48 tests, all green). Each fix was a no-op under the
current monolithic setup (since `_connect()` ignores the hint and
returns the monolithic DB anyway), so there was no production risk —
but the fixes are there, ready to work correctly if and when the
router is ever re-enabled.

**Finally, restarted mining-guardian to load the new code into memory
and let it run one full scan cycle.** Scan 1691 completed cleanly at
05:37 — the production write path works with all seven fixes in place.
No errors, no regressions.

Pushed 12 commits to origin/main.

## What's next

The audit and the fixes together are the prerequisite work for
re-enabling the router, which is the prerequisite for migrating to
Postgres. None of that happens today — the next logical step is a
scratch-copy test where we make copies of the four split databases,
flip the router back on against the copies, and verify the seven
fixes actually work end-to-end. That's tomorrow's (or next week's)
focused experiment.

When the Mac Mini arrives in May, the decision will probably be:
skip the split-SQLite experiment entirely, migrate the monolithic
database straight to Postgres as part of the Mac Mini cutover. The
router work done today won't be wasted — the bug fixes are correct
regardless of target — but the split-SQLite state is likely a stepping
stone we end up not using.

## What's durable

- 12 commits on origin/main tell the full story in git history
- The three key docs (`DB_STATE_2026-04-23.md`, `CORE_DATABASE_AUDIT_2026-04-23.md`,
  and this one) explain the reasoning and the current reality
- A 1.8 GB safety-snapshot tarball at `/root/mg_safety_snapshot_2026-04-23.tar.gz`
  captures the VPS working tree from 04:24 CDT this morning as a rollback point
- Mining-guardian is running clean on the new code, with 0 restarts since
  05:35 CDT, writing to the same `guardian.db` it has been writing to
  since 2026-04-22 16:37

Sleep is still a good idea. The system doesn't need anything else from
us right now.
