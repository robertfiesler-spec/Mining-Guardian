# W14 Postmortem — 2026-05-13

> **One-line summary:** W14 (two-Postgres-instance split) landed cleanly, but
> Step 2's `docker run` command preserved literal single quotes from `.env`
> when injecting `POSTGRES_PASSWORD`, leaving the new container's `mg` role
> with a quoted password that no application could authenticate against. The
> bug surfaced in the Step 6 smoke gate before any irreversible operation;
> remediated by `ALTER USER mg WITH PASSWORD '<unquoted>'` inside the
> container. No data loss, no rollback required, ~3 minutes added to the
> maintenance window.
>
> **Why this doc exists:** the bug is in a class that will recur if the
> installer's `docker run` provisioning copies the same shell pattern. This
> postmortem captures the root cause, the fix, and a permanent prevention
> rule so neither happens again on a customer .pkg build (per D7).

---

## 1 · Timeline

All times CDT 2026-05-13.

| Time | Step | Event | Outcome |
|---|---|---|---|
| 06:48 | 0 | Pre-flight sanity checks (6 boxes) | All green |
| 06:49 | 1 | `sudo launchctl bootout` 12 scheduled plists | 22 → 10 entries, clean |
| 06:51 | 2a | `sudo mkdir + chown` `pgdata-catalog/` | OK, 755 miningguardian:staff |
| 06:51 | 2b | `docker run mg-catalog-db` on port 5433 | Container up in 1s, `pg_isready` OK |
| 06:52 | 3 | Drop empty bootstrap DB, `pg_restore` from pre-W14 dump | Row counts match baseline (324/17/6/22/0) |
| 06:53 | 4a | scp `core/db_targets.py` laptop→Mini, md5 match | OK |
| 06:53 | 4b | Append `GUARDIAN_PG_CATALOG_{HOST,PORT}` to `.env` | OK, 3290 → 3420 bytes |
| 06:54 | (verify) | Fresh-process resolver test: catalog → 5433 | OK |
| ~06:58 | 5 | Bootout/bootstrap 10 always-on services | All 10 came up, PIDs 66707-66788 |
| **07:02** | **6a** | **Smoke gate: psycopg2 connect via `catalog_target()`** | **🔴 `password authentication failed for user "mg"` against 127.0.0.1:5433** |
| 07:02-07:08 | (triage) | Three hypotheses tested and falsified; fourth confirmed | Root cause: literal quotes in `POSTGRES_PASSWORD` from Step 2b |
| 07:08 | (fix) | `ALTER USER mg WITH PASSWORD '<unquoted>'` inside `mg-catalog-db` | OK, `ALTER ROLE` |
| 07:08 | 6a re-run | Same smoke gate | ✅ AUTH OK, both targets resolve to correct ports/DBs |
| 07:09 | 6b | `ai.catalog_context.get_catalog_context("ANTMINER S19j Pro")` | Returns valid string result |
| 07:09 | 6c | `daily_deep_dive --dry-run` end-to-end | 72 miners enumerated with correct model lookups |
| 07:09 | **7** | **`DROP DATABASE mining_guardian_catalog` on old container** | OK, irreversible step crossed |
| 07:09 | (verify) | Re-run `daily_deep_dive --dry-run` post-DROP | Identical clean output (72 miners) |
| 07:10 | 8 | `sudo launchctl bootstrap` 12 scheduled plists | 10 → 22 entries, same 10 PIDs held |

**Window duration: 22 minutes.** ~3 minutes added by the bug-investigation pause
between 07:02 and 07:08. No always-on service crashed at any point; PID cluster
held from 66707-66788 from Step 5 through Step 8.

---

## 2 · Root cause

### What I did wrong

Step 2b's `docker run` command sourced the password from `.env` like this:

```bash
export MG_DB_PASSWORD=$(grep "^MG_DB_PASSWORD=" \
    "/Library/Application Support/MiningGuardian/.env" | cut -d= -f2-)
# ...
/usr/local/bin/docker run -d \
    --name mg-catalog-db \
    ...
    -e POSTGRES_PASSWORD="$MG_DB_PASSWORD" \
    ...
```

The `.env` file on the Mini stores the password in single-quoted form:

```
MG_DB_PASSWORD='6264c33180bfb64de457b998...'
```

`cut -d= -f2-` returns everything after the first `=`, including the
surrounding single quotes. So `$MG_DB_PASSWORD` was set to a 66-character
string: a literal `'`, then the 64-character actual password, then another
literal `'`. Docker dutifully passed that 66-character string to the
container's entrypoint, which provisioned the `mg` role with that quoted
password as its actual credential.

### Why the smoke gate caught it

Mining Guardian application code loads `.env` via Python's standard env-var
handling (via the `export $(grep ... | xargs)` idiom in the launchctl wrapper
scripts), and `xargs` strips surrounding quotes from values. So Python's
`os.environ.get("GUARDIAN_PG_PASSWORD")` returned the 64-character unquoted
form. When `core.db_targets.catalog_target()` called
`psycopg2.connect(password="64charvalue", ...)`, the server checked against
the role's stored `'64charvalue'` (with literal quotes) and rejected.

The operational container (`mining-guardian-db`) is unaffected because it was
provisioned long ago by the installer's `step_reconcile_postgres_password`
flow in `installer/macos-pkg/scripts/postinstall.sh`, which uses a different
password-injection mechanism that does strip quotes correctly.

### Why I didn't catch it sooner

Three earlier sanity checks all *appeared* to confirm the password matched:

1. **Step 2b length check** — `"password loaded (length: ${#MG_DB_PASSWORD} chars)"` returned 66. I read 66 as "normal length for this kind of secret" without noticing the password I'd seen documented elsewhere was 64.
2. **`.env` consistency check (during triage hypothesis 1)** — `${#gp}` and `${#mp}` both returned 66; md5 of both matched. Both sides of the comparison were the quoted form, so the equality held.
3. **`docker inspect` env check (hypothesis 2)** — md5 of container's
   `POSTGRES_PASSWORD` matched md5 of `.env`'s `MG_DB_PASSWORD`. Again, both
   sides quoted; equality held.

Hypothesis 4 — *"what if the container's actual stored role password differs
from what we *think* `POSTGRES_PASSWORD` was?"* — would have surfaced the bug
in one comparison: extract the password the application actually sends
(`os.environ["GUARDIAN_PG_PASSWORD"]`, post-`xargs` unquoting) and compare its
length to the container's stored value. The two would have differed by 2.

The diagnostic that finally revealed the bug printed lengths from both
contexts:

```
GUARDIAN_PG_PASSWORD set: True, len=64    ← what Python sees, what apps send
MG_DB_PASSWORD       set: True, len=64    ← same
```

vs. the earlier zsh shell check:

```
GUARDIAN_PG_PASSWORD length: 66           ← shell, $cut output, what was sent to Docker
```

The **66 vs 64 discrepancy in the same variable** was the smoking gun. Once
that was visible, an `xxd` on the `.env` line showed the literal `'` byte
sitting where the password should have started.

---

## 3 · Fix

### What was done in the maintenance window

```sql
-- inside mg-catalog-db container, with password sourced unquoted via sed
ALTER USER mg WITH PASSWORD '<the 64-char unquoted value>';
```

The `ALTER USER` was generated by an SSH command that pulled the value via:

```bash
PW=$(grep "^MG_DB_PASSWORD=" .env | cut -d= -f2- \
     | sed -E "s/^'(.*)'\$/\1/")
```

The `sed` here strips a leading-and-trailing pair of single quotes (and
nothing else). Length was verified to be 64 before the `ALTER USER` ran.

Verification: the same Python diagnostic from triage re-run and now shows
AUTH OK for the unquoted password and FAIL for the quoted one (mirror flip
of the original failure mode).

No data was touched. No restart was required. Application code continued
working through the change.

---

## 4 · Permanent prevention

There are two places where this same bug class can recur. Both need fixing
before the customer .pkg ships (per D7).

### 4.1 Installer must use a quote-safe password injection

`installer/macos-pkg/scripts/lib/install_colima.sh` will (per W14 Step 10)
gain a second `docker run` block for `mg-catalog-db`. That block **must
not** copy the shell pattern that just broke. Two acceptable approaches:

**Option A — stdin via `--env-file`.** Write the password to a temporary
env file (mode 0600), use `--env-file=/path/to/temp.env`, then shred the
temp file. Docker reads env files in `KEY=VALUE` form without quote
interpretation — surrounding quotes in the value are preserved as part of
the value, which is what we want when the value naturally contains quotes,
but for our case we generate the file ourselves so we control quoting.

**Option B — explicit unquoting before the `docker run`.** Strip surrounding
quotes with `sed -E "s/^'(.*)'\$/\1/"` (or `sed -E 's/^"(.*)"\$/\1/'` for
double quotes; or both via two sed passes). This is what the in-window fix
did. Pattern is documented and reusable.

**Recommended: Option A**, because it generalizes to all secrets, not just
the password. The installer should follow the same pattern for the
Anthropic API key, the Tailscale auth key, etc. — never inline a secret in
a shell command that could mishandle quoting.

### 4.2 Cohort guard test for password consistency

Land a new test in W14b's PR:

```python
# tests/test_w14_password_quote_consistency.py
"""W14 cohort guard — the password the application sends to Postgres must
   match what the container's mg role was provisioned with.

   Bug class captured: literal quotes in `.env` values can be interpreted
   inconsistently by `cut -d=` vs `xargs` vs Python's `os.environ`. If the
   container is provisioned with a quoted password and apps send the
   unquoted form (or vice versa), every catalog read fails with
   "password authentication failed for user mg".

   See: docs/strategy/W14_POSTMORTEM_2026-05-13.md §2 (root cause).
"""
import os
import psycopg2
import pytest


@pytest.mark.live_mini
def test_application_password_matches_container_for_both_targets():
    """Connecting via operational_target() and catalog_target() with the
       password resolved from .env must both succeed."""
    from core.db_targets import operational_target, catalog_target

    for label, target in [("operational", operational_target()),
                          ("catalog", catalog_target())]:
        conn = psycopg2.connect(**target.connect_kwargs())
        cur = conn.cursor()
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,), f"{label}: trivial query failed"
        conn.close()
```

This test is marked `live_mini` and runs only against the live Mini DB. It
fails closed: any future regression that mis-injects a password (whether by
copying our buggy pattern, or by env-var format drift) trips the test
before any deploy step.

### 4.3 Documentation update — quote-handling in `.env`

The W14b convention block in `CLAUDE.md` should add a short rule:

> **`.env` values:** when sourcing a value from `.env` in a shell script,
> always pipe through `xargs` (which strips surrounding quotes) before use,
> or strip quotes explicitly. Do not pass `cut -d= -f2-` output directly to
> a downstream command. This bug shipped W14 by 3 minutes (see
> `docs/strategy/W14_POSTMORTEM_2026-05-13.md`).

Combined with the cohort guard test, this gives us belt + suspenders +
buckle.

---

## 5 · What the smoke gate did right

Per the working convention (CLAUDE.md "evidence-before-fix, live-Mini smoke
before commit"), Step 6 was designed as a hard gate before Step 7's
irreversible `DROP DATABASE`. The gate had three sub-checks:

- **6a:** fresh Python resolves correctly + connects + reads correct rows on 5433
- **6b:** W14a-refactored production code path (`ai.catalog_context`) returns valid data
- **6c:** end-to-end `daily_deep_dive --dry-run` enumerates 72 miners

The bug surfaced **at 6a**. None of the sub-checks were skipped or downgraded
under time pressure. The runbook explicitly built in this pause; honoring
the pause was the right call.

The post-mortem lesson is not "the smoke gate was lucky." The lesson is "the
smoke gate worked as designed, and the next iteration of the runbook needs to
fold the bug class itself into a permanent guard so we don't rely on smoke to
catch it next time."

---

## 6 · Related risks I want to flag while context is hot

These came up during the W14 window but are not the post-mortem subject.
Captured here so they're not lost:

1. **`postgres-data/` vs `pgdata-catalog/` naming asymmetry.** The
   pre-existing operational container uses `/Library/Application Support/MiningGuardian/postgres-data/`. I created the new container's volume at
   `/Library/Application Support/MiningGuardian/pgdata-catalog/`. Both are
   bind-mounts. Cosmetic; should be standardized before customer ship —
   either both `postgres-data-{operational,catalog}/` or both `pgdata-{operational,catalog}/`. **No urgency.** Add to W14b PR if scope fits, otherwise its own PR.

2. **Colima bind-mount opacity from the host.** `ls -lh` against either
   pgdata directory returns "total 0" from the macOS host even though Postgres
   has tens or hundreds of MB written. Reason: Colima runs an ARM Linux VM with
   its own filesystem, and VirtIO-fs bind-mounts present these paths in a way
   that's only fully visible from inside the container. **Implication for the
   backup story:** `tar` from the host won't capture pgdata content. The
   `docker exec pg_dump` pattern (which is what Step 0 used) is the right
   approach. Should be documented in W14_PREP.md.

3. **Stale `daily_deep_dive` last-run date.** During smoke 6c, the log
   showed *"yesterday's deep dive: 2026-04-27"* — 16 days stale. Either the
   scheduled job has been failing silently, or that field tracks something
   other than what I think. Not a W14 issue, but worth investigating before
   trusting any recent deep-dive output for production decisions.

---

## 7 · Items added to today's post-W14 work

- ✅ This post-mortem doc + execution status update (this PR)
- ⏭ Rotate Anthropic API key (EOD)
- ⏭ W14b — once 16:00 daily deep dive completes cleanly
- ⏭ W14 Step 9 — `scripts/daily_backup.sh` rewrite per D6 (two scripts + wrapper). Must use the quote-safe pattern from §4.1.
- ⏭ W14 Step 10 — installer updates (`install_colima.sh`, `postinstall.sh`). Must use Option A (`--env-file`) from §4.1.
- ⏭ Cohort guard test from §4.2 (lands with W14b or Step 10, whichever ships first)

---

*Captured 2026-05-13 ~07:30 CDT, while context was hot.*
