# VPS Journal Audit Script — Usage

**Purpose:** Inventory all error signatures across the 8 production services
over the last 7 days. Confirms whether CR-4 + CR-5 cover everything that's
actually firing, or if there are AttributeError / psycopg2 patterns we
haven't seen yet.

## When to run

**Recommended timing:**
1. **Sunday 2026-04-26 ~8:50 AM CDT** — BEFORE the typo rename. Captures the
   "before CR-4" baseline. Save the output.
2. **After CR-4 PR merge** (later Sunday) — captures "after CR-4". Diff against
   the baseline to confirm the AttributeError volume drops.
3. **Tuesday or Wednesday next week** — confirms no new patterns emerged.

## How to run on VPS

```bash
# After typo rename, path is /root/Mining-Guardian/. Before rename it is /root/Mining-Gaurdian/.
cd /root/Mining-Guardian   # adjust path if pre-rename
bash mg_pre_prod/proposals/vps_journal_audit.sh > /tmp/mg_journal_$(date +%Y%m%d_%H%M).txt 2>&1

# Then:
cat /tmp/mg_journal_*.txt
# ...and paste output back to chat for triage.
```

If the file isn't in the VPS clone yet (audit branch not pulled there):

```bash
# One-liner: download script straight from audit branch
curl -fsSL https://raw.githubusercontent.com/robertfiesler-spec/Mining-Guardian/pre-prod-audit-2026-04-25/mg_pre_prod/proposals/vps_journal_audit.sh \
  | bash > /tmp/mg_journal_$(date +%Y%m%d_%H%M).txt 2>&1
```

## What the script reports

For each of the 8 services:
- Total error/traceback lines (7d)
- Top 15 unique `AttributeError` signatures
- Top 15 unique `psycopg2.*Error` signatures
- Top 10 `syntax error at or near` occurrences (= Postgres rejecting SQLite SQL)
- Top 10 traceback origin files (file:line)
- Top 10 `function ... does not exist` errors

Then cross-service summary:
- Top 20 unique AttributeError patterns across all services
- Top 20 unique psycopg2 errors across all services

## What I expect to see

**Before CR-4 (baseline):**
- `mining-guardian` service:
  - ~68 hits of `AttributeError: '_PgConn' object has no attribute 'execute'` (or similar — exact wording depends on raw psycopg2 conn class) traced to `core/mining_guardian.py:1040` in `_auto_create_missing_tickets`.
  - Likely also hits at lines 285, 1102, 1418, 1911, 2068, 2285 (the other CR-4 conversion sites) IF those code paths fired.
- `dashboard-api` service:
  - Possible `psycopg2.errors.SyntaxError: syntax error at or near "'now'"` from the 5 CR-5 Tier A sites (env history, miner history, actions, /ask).
- Other services: likely much smaller error counts.

**After CR-4 merge:**
- The `_auto_create_missing_tickets` AttributeError should drop to zero on `mining-guardian`.
- If `dashboard-api` syntax errors persist → confirms CR-5 Tier A is hot and worth prioritizing.
- Any *new* AttributeError or psycopg2 signatures that show up here that we haven't seen → that's our gap.

## Decision tree on the output

| What you see | Action |
|---|---|
| Only the known `_auto_create_missing_tickets` AttributeError + maybe CR-5 Tier A syntax errors | All accounted for. Land CR-4, then schedule CR-5. |
| New AttributeError on `core/mining_guardian.py` at lines we converted (285/1102/1418/1911/2068/2285) | CR-4 didn't reach these — re-verify the patch landed correctly on disk. |
| AttributeError on a file outside `core/mining_guardian.py` (e.g. `core/hashrate_evaluation.py`) | New finding — file it as CR-6 candidate. |
| psycopg2 OperationalError (connection drops, pool exhaustion) | NOT a CR-4 issue — infra/db sizing problem. Separate ticket. |
| `function datetime(unknown, unknown) does not exist` | Confirms a CR-5 site is being hit. Note which service. |

## Privacy note

The output may contain miner IPs and miner IDs. Safe to share back to chat — no
secrets or credentials are dumped (journalctl strips environment variables).
