# CR-4-EXT — Per-Line Inventory of SQLite execute() Statements in `core/mining_guardian.py`

**Generated:** 2026-04-25 (break-time prep, mid-CR-4-EXT)
**Source:** `repo_snapshot/core/mining_guardian.py` (5862 lines, pre-CRIT-1; CRIT-1 did not touch this file so live-branch line numbers are identical)
**Scope:** All `conn.execute(...)` / `conn.executemany(...)` calls inside the inline `class GuardianDB` (line 1390) that contain SQLite-specific syntax — qmark placeholders (`?`) or `datetime('now', ...)` literals.
**Total flagged:** **47 statements** across **16 tables**.

> **NOT INCLUDED** in the 47 (intentionally — these are SQLite-only DDL and have no `?` placeholders, so they are not part of the qmark→%s translation surface):
> - `L1742` — `conn.execute("PRAGMA table_info(miner_restarts)")` (PRAGMA is SQLite-only, must be replaced with Postgres `information_schema.columns` lookup)
> - `L1752` — `conn.execute(f"ALTER TABLE miner_restarts ADD COLUMN ...")` (works on both, but DDL belongs in a migration script, not runtime)
> - All `_init_db()` `CREATE TABLE` DDL inside the inline class (lines ~1410–1740) — type-mapping needed (`INTEGER PRIMARY KEY AUTOINCREMENT` → `SERIAL` / `BIGSERIAL`, `REAL` → `DOUBLE PRECISION`, `TEXT` for ISO timestamps stays `TEXT` only if we keep the wire format)
>
> These are tracked separately under **Phase 0 — Schema migration** below.

---

## Strategic recommendation

The inline `class GuardianDB` at `core/mining_guardian.py:1390` is the entire SQLite footprint inside the daemon. Two options to neutralize it:

| | **Option A — Surgical translation (in place)** | **Option B — Replace class entirely** |
|---|---|---|
| Approach | Keep `class GuardianDB`, swap `sqlite3.connect()` → `psycopg2.connect()`, translate each of the 47 execute() bodies | Delete inline class, change `self.db = GuardianDB(...)` to `from core.database_pg import GuardianPGDB; self.db = GuardianPGDB()` |
| Diff size | ~150–200 lines changed (mostly mechanical) | ~350 lines deleted, ~5 lines added (import + constructor swap) |
| Risk | Low — each statement is locally verifiable; same call surface on both sides | Higher — `GuardianPGDB` may not implement every method `core/mining_guardian.py` calls (need full method-by-method audit first) |
| Rollback | Trivial (revert one file) | Requires re-introducing the SQLite class |
| **Recommendation** | **✅ Pick this for CR-4-EXT** — surgical, contained, reviewable | Defer to a post-cutover cleanup pass |

**This document is built for Option A.** If we choose Option B later, the GROUP BY / dynamic-placeholder / datetime callouts below still apply because `GuardianPGDB` would need the same SQL bodies refactored.

---

## Phase 0 — Schema migration (must run before code patch)

Before any execute() body becomes `%s`-flavored, the inline class's `_init_db()` `CREATE TABLE` DDL needs to be replicated against the live `mining_guardian` Postgres database. Two sub-tasks:

1. **One-shot DDL migration script** — translate `INTEGER PRIMARY KEY AUTOINCREMENT` → `BIGSERIAL PRIMARY KEY`, `REAL` → `DOUBLE PRECISION`, keep `TEXT` and `INTEGER` as-is, add explicit `CREATE TABLE IF NOT EXISTS` for the 16 tables below if they don't already exist in the catalog DB.
2. **Replace the runtime `_init_db()`** — once the DDL is migrated, the in-process `_init_db()` should be replaced with a no-op (or a "verify expected columns exist" check using `information_schema.columns`).

The **PRAGMA table_info** call at `L1742` becomes:

```python
existing = [r[0] for r in conn.execute(
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_name = %s", ("miner_restarts",)).fetchall()]
```

Or, with the `GuardianPGDB._connect()` pattern (DictCursor):

```python
with self._connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s", ("miner_restarts",))
        existing = [r["column_name"] for r in cur.fetchall()]
```

The `f"ALTER TABLE miner_restarts ADD COLUMN ..."` at `L1752` is portable as written — Postgres accepts it — but should still be moved to a one-shot migration rather than running on daemon startup.

---

## Phase 1 — Mechanical translation rules (apply to all 47 statements)

Apply these in order to each body:

| # | Rule | SQLite | Postgres |
|---|------|--------|----------|
| R1 | Placeholders | `?` | `%s` |
| R2 | Now literal in SQL | `datetime('now')` | `NOW()` (or omit and pass `datetime.utcnow().isoformat()` from Python) |
| R3 | Now-with-offset | `datetime('now', '-30 minutes')` | `NOW() - INTERVAL '30 minutes'` |
| R4 | Cast-to-timestamp | `datetime(collected_at)` (no-op formatter) | drop the wrapper — `collected_at` already TIMESTAMP |
| R5 | UPSERT excluded | `ON CONFLICT(...) DO UPDATE SET col=excluded.col` | identical syntax in Postgres ≥ 9.5 — no change |
| R6 | HAVING with alias | `HAVING failure_count >= ?` (where `failure_count` is `COUNT(*) AS failure_count`) | Postgres rejects aliases in HAVING — rewrite as `HAVING COUNT(*) >= %s` |
| R7 | GROUP BY non-aggregated cols | implicit OK in SQLite | Postgres requires every selected non-aggregate column in `GROUP BY` — see CR-4 callouts below |
| R8 | Connection / cursor pattern | `conn.execute(sql, params).fetchall()` | `with conn.cursor() as cur: cur.execute(sql, params); rows = cur.fetchall()` (per `GuardianPGDB._connect`) |
| R9 | Row access | `row["col"]` (sqlite3.Row) | `row["col"]` (DictCursor) — **identical**, no code change needed |
| R10 | conn.commit() inside `with` | manual commit needed in SQLite | auto-commit on `with` exit in `GuardianPGDB._connect` — **remove** explicit `conn.commit()` lines |

**R8 is the largest source of churn.** Every `conn.execute(sql, params).fetchone()`/`.fetchall()`/`.rowcount` call in the inline class needs to become a two-step `with conn.cursor() as cur: cur.execute(...); cur.fetchone()` pattern, OR we add a thin shim method to the patched class that wraps `cursor.execute` and returns the cursor (preserving the `.fetchone()` chain). Recommend the **shim** approach to minimize diff:

```python
class GuardianDB:
    def _connect(self):
        # New body — replaces sqlite3.connect()
        return _PGConnWrapper(psycopg2.connect(self._dsn, cursor_factory=DictCursor))

class _PGConnWrapper:
    """Adapter that makes psycopg2 conn behave like sqlite3 conn for our use."""
    def __init__(self, raw): self._raw = raw
    def __enter__(self): return self
    def __exit__(self, et, ev, tb):
        if et: self._raw.rollback()
        else:  self._raw.commit()
        self._raw.close()
    def execute(self, sql, params=()):
        cur = self._raw.cursor()
        cur.execute(sql, params)
        return _CurResult(cur)
    def commit(self): self._raw.commit()  # tolerate explicit calls
    def rollback(self): self._raw.rollback()

class _CurResult:
    def __init__(self, cur): self._cur = cur
    def fetchone(self): return self._cur.fetchone()
    def fetchall(self): return self._cur.fetchall()
    @property
    def rowcount(self): return self._cur.rowcount
    @property
    def lastrowid(self): return self._cur.fetchone()[0]  # only valid w/ RETURNING id
```

With this shim in place, **R8 becomes a no-op** for almost all 47 statements — they keep their `.fetchall()`/`.fetchone()`/`.rowcount` chains and only need R1/R2/R3/R6/R7 applied to the SQL text.

---

## Phase 2 — Per-statement inventory

Legend:
- **Op** = SELECT / INSERT / UPDATE / DELETE
- **Flags** = SQLite-isms the extractor flagged (`?` = qmark placeholders; `datetime('now'` = NOW literal in SQL)
- **GB?** = contains `GROUP BY`
- **HV?** = contains `HAVING`
- **OC?** = contains `ON CONFLICT`
- **DYN?** = builds SQL with f-string `{placeholders}` (needs build-IN logic)

| # | Line | Op | Table | Flags | GB? | HV? | OC? | DYN? | Translation notes |
|---|------|----|-------|-------|-----|-----|-----|------|-------------------|
| 1 | L1782–1786 | SELECT | pending_approvals | ? | | | | | R1 only — `WHERE miner_id=%s AND status='PENDING'` |
| 2 | L1790–1797 | UPDATE | pending_approvals | ? | | | | | R1 only |
| 3 | L1801–1809 | INSERT | pending_approvals | ? | | | | | R1 only — 10 `?` → 10 `%s` |
| 4 | L1822–1826 | SELECT | pending_approvals | ? | | | | | R1 only — `created_at < %s` (cutoff is ISO string from Python) |
| 5 | L1829–1833 | UPDATE | pending_approvals | ? | | | | | R1 only |
| 6 | L1837–1847 | INSERT | action_audit_log | ? | | | | | R1 only |
| 7 | L1865–1874 | INSERT | action_audit_log | ? | | | | | R1 only |
| 8 | L1915–1920 | INSERT | ams_notifications | ? | | | | | R1 only |
| 9 | L1927–1940 | INSERT | weather_readings | ? | | | | | R1 only |
| 10 | L1948–1968 | INSERT | hvac_readings | ? | | | | | R1 only — large column list, verify column count matches values |
| 11 | L1977–1981 | INSERT | scans | ? | | | | | R1 only — **needs `RETURNING id`** if calling `.lastrowid` (verify caller usage) |
| 12 | L2044–2053 | INSERT | miner_readings | ? | | | | | R1 only |
| 13 | L2079–2082 | SELECT | miner_logs | ? | | | | | R1 only |
| 14 | L2087–2092 | INSERT | miner_logs | ? | | | | | R1 only |
| 15 | L2103–2106 | SELECT | miner_readings | ? | | | | | R1 only |
| 16 | L2124–2126 | DELETE | miner_logs | ? | | | | | R1 only — only DELETE in the file |
| 17 | L2135–2139 | SELECT | miner_logs | ? | | | | | R1 only |
| 18 | L2150–2153 | SELECT | known_dead_boards | ? | | | | | R1 only |
| 19 | L2163–2166 | SELECT | known_dead_boards | ? | | | | | R1 only |
| 20 | L2168–2171 | UPDATE | known_dead_boards | ? | | | | | R1 only |
| 21 | L2173–2179 | INSERT | known_dead_boards | ? | | | | | R1 only |
| 22 | L2185–2191 | SELECT | known_dead_boards | ? | | | | | R1 only |
| 23 | L2198–2202 | UPDATE | known_dead_boards | ? | | | | | R1 only |
| 24 | L2231–2235 | UPDATE | known_dead_boards | ? | | | | | R1 only |
| 25 | L2241–2244 | UPDATE | known_dead_boards | ? | | | | | R1 only |
| 26 | L2263–2269 | INSERT | chain_readings | ? | | | | | R1 only |
| 27 | L2292–2298 | INSERT | pool_readings | ? | | | | | R1 only |
| 28 | L2316–2323 | INSERT | miner_state_readings | ? | | | | | R1 only |
| 29 | L2347–2353 | INSERT | miner_ams_extended | ? | | | | | R1 only |
| 30 | **L2423–2471** | INSERT | miner_hardware | ? | | | **✅** | | R1 + R5 (`ON CONFLICT(miner_id, board_index) DO UPDATE SET ... excluded.col`) — Postgres syntax is identical. **Verify** the unique constraint `UNIQUE(miner_id, board_index)` exists on the Postgres table; if not, add via migration. |
| 31 | L2482–2485 | SELECT | miner_hardware | ? | | | | | R1 only |
| 32 | L2622–2629 | INSERT | log_metrics | ? | | | | | R1 only |
| 33 | L2638–2642 | SELECT | miner_logs | ? | | | | | R1 only |
| 34 | L2660–2667 | INSERT | miner_restarts | ? | | | | | R1 only |
| 35 | L2675–2680 | SELECT | miner_restarts | ? | | | | | R1 only |
| 36 | L2687–2690 | SELECT | miner_restarts | ? | | | | | R1 only |
| 37 | L2696–2699 | SELECT | miner_restarts | ? | | | | | R1 only |
| 38 | L2706–2710 | SELECT | action_audit_log | ? | | | | | R1 only |
| 39 | L2716–2720 | SELECT | miner_logs | ? | | | | | R1 only |
| 40 | L3514–3517 | SELECT | miner_readings | ? | | | | | R1 only |
| 41 | **L4196–4204** | SELECT | miner_restarts | ?+datetime('now' | **✅** | **✅** | | | **CR-4 #1** — see callout below |
| 42 | **L4206–4214** | SELECT | miner_restarts | ? | **✅** | **✅** | | | **CR-4 #2** — see callout below |
| 43 | L4260–4263 | SELECT | known_dead_boards | ? | | | | | R1 only — `WHERE miner_id=%s AND resolved_at IS NULL` |
| 44 | L4576–4581 | SELECT | miner_logs | ? | | | | | R1 only — **CR-5 area** |
| 45 | L4582–4587 | SELECT | miner_logs | ? | | | | | R1 only — **CR-5 area**; **verify whether body wraps a column with `datetime(collected_at)` and drop wrapper if so** (R4) |
| 46 | L5070–5073 | SELECT | miner_logs | ? | | | | | R1 only |
| 47 | **L5471–5475** | UPDATE | pending_approvals | datetime('now' | | | | **✅** | **Dynamic IN** — see callout below |

---

## Callout — CR-4 candidates (statements 41 & 42)

Body of statement 41 (`L4196–4204`) currently:

```sql
SELECT miner_id, ip, model,
       COUNT(*) as failure_count, 'failure_outcomes' as reason
FROM miner_restarts
WHERE outcome = 'FAILURE'
  AND restarted_at < datetime('now', '-30 minutes')
GROUP BY miner_id
HAVING failure_count >= ?
```

**Two Postgres problems:**

1. **R7 (GROUP BY non-aggregated cols)** — Postgres requires `ip` and `model` in `GROUP BY` because they are selected and not aggregated. If the data model guarantees one (ip, model) per miner_id, the simplest fix is to add them to the GROUP BY:
   ```sql
   GROUP BY miner_id, ip, model
   ```
   **❓ Question for Rob:** is `(miner_id) → (ip, model)` truly 1:1 in `miner_restarts`, or could a single miner_id have multiple ip/model rows in the table (e.g. after IP reassignment)? If 1:1, GROUP BY all three is safe. If not, we need `MAX(ip)` / `MAX(model)` (or `(SELECT ip FROM miner_restarts WHERE miner_id=outer.miner_id ORDER BY restarted_at DESC LIMIT 1)`).

2. **R6 (HAVING alias)** — Postgres won't accept `HAVING failure_count >= ?` because `failure_count` is a SELECT-list alias. Rewrite as:
   ```sql
   HAVING COUNT(*) >= %s
   ```

3. **R3 (datetime offset)** — `datetime('now', '-30 minutes')` becomes `NOW() - INTERVAL '30 minutes'`.

**Final translated form for #41:**
```sql
SELECT miner_id, ip, model,
       COUNT(*) as failure_count, 'failure_outcomes' as reason
FROM miner_restarts
WHERE outcome = 'FAILURE'
  AND restarted_at < NOW() - INTERVAL '30 minutes'
GROUP BY miner_id, ip, model
HAVING COUNT(*) >= %s
```

Statement 42 (`L4206–4214`) is the same shape minus the datetime literal — apply R6 + R7 the same way.

---

## Callout — CR-5 datetime-wrapper drop (statement 45 area)

Need to **read** the actual body of statements 44/45 from the snapshot to confirm whether they invoke `datetime(collected_at)` as a no-op formatter. The extractor only flagged the qmark, not the wrapper — but the manifest mentions wrapper-drop work in this area. **TODO during application:** open the snapshot at L4576–4587 and apply R4 if the wrapper is present. (Not blocking — purely a cleanup applied while we're already in the body.)

---

## Callout — Dynamic placeholder build (statement 47)

Body of statement 47 (`L5471–5475`):

```python
cancelled = conn.execute(f"""
    UPDATE pending_approvals
    SET status='CANCELLED', responded_at=datetime('now')
    WHERE miner_id IN ({placeholders}) AND status='PENDING'
""", ticketed_ids).rowcount
```

`{placeholders}` is built upstream as a comma-joined string of `?` markers — likely `",".join("?" * len(ticketed_ids))`. Postgres translation:

```python
placeholders = ",".join(["%s"] * len(ticketed_ids))
cancelled = conn.execute(f"""
    UPDATE pending_approvals
    SET status='CANCELLED', responded_at=NOW()
    WHERE miner_id IN ({placeholders}) AND status='PENDING'
""", tuple(ticketed_ids)).rowcount
```

**Verify upstream code at the line where `placeholders` is computed** — change `"?"` → `"%s"` there. Also note `ticketed_ids` may be a list; psycopg2 accepts list or tuple for IN clauses.

---

## Phase 3 — Application plan

**Recommendation:** translate via a **patch script** in the same all-or-nothing exact-match style as `cr2_patch.py` and CRIT-1a-2, applied in **three commits**:

1. **Commit A — Schema migration script** — adds CREATE TABLE IF NOT EXISTS for any of the 16 tables missing from Postgres + the unique constraint check on `miner_hardware(miner_id, board_index)`. No code changes.
2. **Commit B — Inline class shim + mechanical R1/R2/R3/R10 translation** — covers statements 1–40, 43, 44, 46 (the 43 "R1 only" rows). Patch script writes ~80 exact-match replacements (one per `?` cluster + one per `datetime('now'`).
3. **Commit C — Targeted rewrites** — covers statements 41, 42, 45, 47 (CR-4 GROUP BY/HAVING fixes, CR-5 wrapper drop if present, dynamic-IN rewrite). Hand-written, reviewed sentence by sentence before commit.

Per-commit verification:
- After Commit A: run `python -c "import core.mining_guardian"` (still imports cleanly) + spot-check `\d+ miner_hardware` in psql shows the unique constraint.
- After Commit B: import + start daemon in **dry-run mode** (no scan loop), exercise one of each of the 4 op types via REPL, confirm no `psycopg2.errors.SyntaxError`.
- After Commit C: full smoke test of `_auto_create_missing_tickets` (CR-4) and `_run_post_action_log_comparison` (CR-5) paths.

---

## Phase 4 — Open questions for Rob (need answers before Commit C)

1. **GROUP BY question (CR-4):** Is `(miner_id) → (ip, model)` 1:1 in `miner_restarts`, or do we need `MAX(ip), MAX(model)` (or a lateral-join lookup of latest)? Drives whether statements 41/42 use `GROUP BY miner_id, ip, model` or aggregate ip/model.
2. **`L1977 scans` INSERT — does the caller use `.lastrowid`?** If yes, body needs `RETURNING id` + caller adapted to call `.fetchone()[0]`. If no, R1 alone is enough.
3. **Surgical (Option A) vs class replacement (Option B)?** Recommendation is A; confirming before writing the patch script.
4. **`datetime(collected_at)` wrapper — does it actually appear at L4576–4587?** Need 30 seconds with the snapshot to confirm; not blocking inventory acceptance.
5. **CRIT-3/5/6 line shifts:** CRIT-3 inserted a session-TTL helper into `mg_import.py`; CRIT-6 added `CATALOG_API_KEY`; neither touched `core/mining_guardian.py`, so the line numbers in this inventory remain correct after those manifests ship. **Reconfirm if CRIT-2/CR-2 ships first** (CR-2 inserts `_parse_hashrate_pct` near line 49 of `core/mining_guardian.py` → +6 lines → all line numbers in this file shift by +6 below the helper). The patch script for Commit B should therefore be **regenerated against the post-CR-2 file** if CR-2 ships first.

---

## Footprint summary

- **47** execute() statements
- **43** are R1-only mechanical (~80 single-token replacements: `?` → `%s`, plus 1 × `datetime('now'` → `NOW()`, plus 1 × `datetime('now', '-30 minutes')` → `NOW() - INTERVAL '30 minutes'`)
- **4** require hand-written rewrites (CR-4 ×2, dynamic-IN ×1, possible CR-5 wrapper-drop ×1)
- **1** UPSERT (miner_hardware) — Postgres-compatible, only needs R1
- **0** `INSERT OR REPLACE` / `INSERT OR IGNORE` (good — no SQLite-only conflict idioms)
- **16** tables touched (largest: miner_logs ×9, known_dead_boards ×9, pending_approvals ×6, miner_restarts ×6)

**Status:** ready for Phase 3 patch-script generation pending answers to Phase 4 questions.
