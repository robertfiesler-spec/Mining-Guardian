# Reconciliation — 2026-05-12

> **Purpose.** Yesterday's handoff (`HANDOFF_2026-05-11_EVENING.md` §5 step 2) instructs the next session to *re-grep main, not trust chat assertions*. The prior chat had asserted W16 was "50–70% done" and W17 was "20–30% done", then corrected itself. This file captures the actual grep output so the question is never re-litigated.
>
> **The rule.** If a future Claude session reads this file and is tempted to disagree with it based on memory or context, **re-run the commands**. Do not argue from priors. The commands are deterministic; the chat history is not.

**Repo:** `robertfiesler-spec/Mining-Guardian`
**Branch / HEAD at reconciliation time:** `main` @ `9d2e1178362c4e1f70879365c28989f98c46c1b3` (Merge PR #182 — P-038 #6 db_maintenance macOS-portable)
**Date:** 2026-05-12

---

## W16 — TO_CHAR cast cleanup

**Master Plan §W16 expected post-fix state:** zero `TO_CHAR(NOW(` patterns in production code paths.

### Command 1: production paths
```bash
grep -rn 'TO_CHAR(NOW(' ai/ core/ api/ scripts/ --include='*.py'
```

**Output:** *(empty)*

**Count:** `0`

**Verdict:** ✅ Clean. PR #178 (P-038 #2+#3+bonus) closed this in production paths.

### Command 2: repo-wide (sanity check that test guards exist)
```bash
grep -rn 'TO_CHAR(NOW(' --include='*.py'
```

**Output:** 7 hits, all in `tests/test_p038_timestamptz_vs_text_sql_casts.py`:

```
tests/test_p038_timestamptz_vs_text_sql_casts.py:20:in `::text` (`daily_log_failure_report.py`) or `TO_CHAR(NOW() - INTERVAL
tests/test_p038_timestamptz_vs_text_sql_casts.py:51:  S2. Source-level negative regression — no `TO_CHAR(NOW() - INTERVAL`
tests/test_p038_timestamptz_vs_text_sql_casts.py:105:# S2. daily_deep_dive.py - no TO_CHAR(NOW() - INTERVAL ...) wrapper
tests/test_p038_timestamptz_vs_text_sql_casts.py:110:    """The `TO_CHAR(NOW() - INTERVAL '...', 'YYYY-MM-DD"T"HH24:MI:SS.US')`
tests/test_p038_timestamptz_vs_text_sql_casts.py:127:        f"ai/daily_deep_dive.py still contains `TO_CHAR(NOW() - "
tests/test_p038_timestamptz_vs_text_sql_casts.py:207:    """The `TO_CHAR(NOW() - INTERVAL '...')` shape
tests/test_p038_timestamptz_vs_text_sql_casts.py:224:        "Sibling files share the `TO_CHAR(NOW() - INTERVAL '...')` \"
```

**Verdict:** ✅ Expected. These are intentional regression-guard strings — the test file checks that the pattern does not reappear in production files. They are not bugs.

**W16 status: DONE (Phase 4 → completed in Phase 1 timeframe).**

---

## W17 — Time zone discipline (`datetime.now()` → `datetime.now(timezone.utc)`)

**Master Plan §W17 expected end-state:** zero naive `datetime.now()` calls in `ai/core/api/scripts/`. Schema is already TIMESTAMPTZ; only Python side needs the sweep.

### Command 1: naive calls
```bash
grep -rnE 'datetime\.now\(\)' ai/ core/ api/ scripts/ --include='*.py' | wc -l
```

**Count:** `151`

### Command 2: tz-aware calls (baseline)
```bash
grep -rnE 'datetime\.now\(timezone' ai/ core/ api/ scripts/ --include='*.py' | wc -l
```

**Count:** `18`

**Ratio:** 18 tz-aware / 169 total = ~10.7% tz-aware. The sweep is ~89% outstanding.

**Verdict:** ⚠️ Essentially untouched. PR #180 (P-038 #5) was a different change — it added `core/dt_format.py` for datetime *formatting/slicing*, not for `datetime.now()` → `datetime.now(timezone.utc)` conversion.

**W17 status: NOT STARTED.**

### Why the prior chat got this wrong

The prior session conflated PR #180 ("datetime slicing fix via `fmt_dt`") with W17 ("tz-aware datetimes"). They are different problems:

- **#180 / `fmt_dt`** — Handles `s.get('last_seen', '')[:16]` style bugs where Python code assumed datetime values were strings (because text-typed Postgres columns) and used slice syntax. The fix gives one helper that accepts either a string or a datetime and returns the formatted form. This was P-038's actual problem.
- **W17** — A categorically different fix: switching `datetime.now()` to `datetime.now(timezone.utc)` everywhere so the Python side is timezone-aware to match the TIMESTAMPTZ schema. This is sweep work, mechanical, not yet started.

Both touch datetime, both are real, but completing one does not close the other. Yesterday's handoff §4.1 caught this and called it out explicitly — that flag was right.

---

## W05 — ProcessType for always-on services

**Master Plan §W05 lists 6 plists:** `scanner`, `alerts`, `approval-api`, `dashboard-api`, `slack-listener`, `slack-commands`.

### Command
```bash
for f in installer/macos-pkg/resources/launchd/com.miningguardian.*.plist; do
  name=$(basename "$f" .plist | sed 's/com.miningguardian.//')
  pt=$(grep -A1 '<key>ProcessType</key>' "$f" | tail -1 | tr -d '[:space:]')
  echo "  $name : $pt"
done
```

**Output:**

```
  alerts               : <string>Background</string>
  approval-api         : <string>Background</string>
  console              : <string>Background</string>
  dashboard-api        : <string>Background</string>
  intelligence-report  : <string>Background</string>
  overnight-automation : <string>Background</string>
  scanner              : <string>Background</string>
  slack-commands       : <string>Background</string>
  slack-listener       : <string>Background</string>
```

**Count:** `9` always-on plists, all `Background`.

**Verdict:** ⚠️ Plan §W05 is incomplete. There are 9 always-on plists, not 6. The 3 not in the Plan list:

| Service | Verdict | Reason |
|---|---|---|
| `console` | Operator-facing → **Standard** | Web UI on `127.0.0.1:8787`; renders task panel for operator |
| `intelligence-report` | Interactive HTTP → **Standard** | Flask API on `localhost:8590`; serves Grafana iframes and `/api/discoveries`; will be hit by W11's `/intel` |
| `overnight-automation` | Time-sensitive long-running → **Standard** | Service that during 10pm–6am window auto-executes LOW-RISK actions (firmware restart, PDU cycle). Latency throttling could delay AUTO actions when miners need them |

Full inspection confirming "service-shaped, not batch-shaped" in [`AMENDMENTS_2026-05-12.md`](AMENDMENTS_2026-05-12.md) §W05.

**W05 status: NOT STARTED. Scope: 9 plists, not 6.**

---

## W03 — Postgres connection pool (refined status)

**Plan §W03 expected:** `psycopg2.pool.ThreadedConnectionPool` in `core/database_pg.py`.

### Command 1: any pool usage in repo
```bash
grep -rln "ThreadedConnectionPool\|psycopg2.pool" --include='*.py'
```

**Output:**

```
intelligence-catalog/catalog-api/catalog_api.py
```

### Command 2: read the operational adapter's own status
```bash
head -50 core/database_pg.py
```

Confirmed lines 22–24 still read:

> `- conn is checked out per-call (no pool today — simple for correctness)`

And lines 27–29:

> Non-goals:
> - Connection pooling (add when we deploy)

**Verdict:** ⚠️ Half-done.

| Component | Status | Notes |
|---|---|---|
| `intelligence-catalog/catalog-api/catalog_api.py` | ✅ Pooled | Already uses `ThreadedConnectionPool` |
| `core/database_pg.py` (operational adapter) | ❌ Per-call connect | The high-call-volume side. Report 1 §2.1 estimates ~500 calls/scan land here |

**W03 status: PARTIAL. Operational adapter is the remaining work and is the higher-volume side.**

---

## W02 — pg_stat_statements

### Command
```bash
grep -rln "pg_stat_statements\|shared_preload_libraries" --include='*.py' --include='*.sql' --include='*.md' --include='*.sh'
```

**Output:** *(empty)*

**Verdict:** ❌ Not started. No references anywhere in repo.

---

## How to re-run this reconciliation

Drop this snippet into `scripts/run_reconciliation_greps.sh` and run from repo root. Output should match this file exactly until status changes are made.

```bash
#!/usr/bin/env bash
set -u

echo "Reconciliation against: $(git log -1 --oneline)"
echo

echo "W16 (production TO_CHAR — expect 0):"
grep -rn 'TO_CHAR(NOW(' ai/ core/ api/ scripts/ --include='*.py' | wc -l

echo "W16 (test guards — expect 7):"
grep -rn 'TO_CHAR(NOW(' --include='*.py' | grep -c '^tests/'

echo "W17 (naive datetime.now — expect ~151):"
grep -rnE 'datetime\.now\(\)' ai/ core/ api/ scripts/ --include='*.py' | wc -l

echo "W17 (tz-aware datetime.now baseline — expect 18+):"
grep -rnE 'datetime\.now\(timezone' ai/ core/ api/ scripts/ --include='*.py' | wc -l

echo "W05 (ProcessType in always-on plists — expect 9× Background):"
for f in installer/macos-pkg/resources/launchd/com.miningguardian.*.plist; do
  name=$(basename "$f" .plist | sed 's/com.miningguardian.//')
  pt=$(grep -A1 '<key>ProcessType</key>' "$f" | tail -1 | tr -d '[:space:]')
  echo "  $name : $pt"
done

echo "W03 (pool usage in repo — expect 1 file, catalog-api):"
grep -rln "ThreadedConnectionPool\|psycopg2.pool" --include='*.py'

echo "W02 (pg_stat_statements references — expect empty):"
grep -rln "pg_stat_statements\|shared_preload_libraries" --include='*.py' --include='*.sql' --include='*.md' --include='*.sh' 2>/dev/null
```

A copy is staged at `/scripts/run_reconciliation_greps.sh`.
