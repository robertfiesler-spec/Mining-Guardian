# core/database.py — Cross-Table-Join Audit

**Date:** 2026-04-23
**Status:** Catalog only — no fixes yet
**Prerequisite for:** re-enabling the split-DB router (currently disabled per commit 215c453)

## How this audit was run

Every method in `GuardianDB` was parsed via `ast`. For each method:

1. Extract literal string arguments to `self._connect(...)` calls
2. Extract SQL-bearing string literals
3. Cross-reference each table name found in SQL against `TABLE_ROUTING` in `core/database_router.py`
4. Flag any method where the `_connect()` hint's DB doesn't match one or more tables referenced in the SQL

**Bug rule:** A method is buggy if, with the router active, its `_connect()` opens DB A but its SQL references tables in DB B, because SQLite cannot span databases without `ATTACH DATABASE`.

## Bugs Found

### 🔴 Bug 1 — `_init_db` (line 70)

**Severity:** High (silent data corruption)
**Hint:** `_connect('scans')` → `operational.db`
**Issue:** Uses `conn.executescript(...)` with CREATE TABLE statements for tables from **all four split DBs**: `scans`, `miner_readings`, `pending_approvals`, `action_audit_log`, `ams_notifications`, `weather_readings`, `hvac_readings`, `miner_logs`, `miner_restarts`, `known_dead_boards`, `chain_readings`, `pool_readings`, etc.

Under the router, all tables get created in `operational.db` regardless of intended home. This doesn't crash but silently pollutes one DB with schemas that should live elsewhere. First `save_weather()` call would then fail (`weather_readings` doesn't exist in `timeseries.db` because `_init_db` created it in the wrong DB).

**Fix approach:** Split the executescript into multiple blocks, one per target DB, each inside its own `with self._connect(<a_table_in_that_db>)` context. Or just call `_init_db` once per DB with the appropriate subset of schemas.

---

### 🔴 Bug 2 — `expire_old_pending_approvals` (line 522)

**Severity:** High (crash under router)
**Hint:** `_connect('pending_approvals')` → `operational.db`
**Issue:** Inside the connection, does:

- `UPDATE pending_approvals ...` ✅ operational.db
- `SELECT id, miner_id, ip, action_type FROM pending_approvals ...` ✅ operational.db
- `INSERT INTO action_audit_log ...` 🔴 belongs in `audit.db`

The audit-log insert uses the `operational.db` connection, which has no `action_audit_log` table.

**Fix approach:** Split into two connection blocks, or use a single audit method that opens its own connection.

---

### 🔴 Bug 3 — `load_known_firmware` (line 726)

**Severity:** Medium (read-only, but returns wrong/partial data)
**Hint:** `_connect('discovery_log')` → `operational.db`
**Issue:**

- `SELECT DISTINCT firmware_version FROM discovery_log ...` ✅ operational.db
- `SELECT DISTINCT firmware_version FROM miner_readings ...` 🔴 `miner_readings` lives in `timeseries.db`

Second query crashes. Method silently returns only the firmware versions known from `discovery_log`, missing anything observed only in `miner_readings`.

**Fix approach:** Two separate connection blocks, merge results in Python.

---

### 🔴 Bug 4 — `save_scan` (line 842)

**Severity:** Critical (this is the production write path on every scan)
**Hint:** `_connect('scans')` → `operational.db`
**Issue:** Inside one connection:

- `INSERT INTO scans ...` ✅ operational.db
- `SELECT firmware_manufacturer, firmware_version FROM miner_readings ...` 🔴 timeseries.db (inline firmware-fallback lookup)
- `executemany INSERT INTO miner_readings ...` 🔴 timeseries.db (the main batch insert)

All three are attempted on the same `operational.db` connection. Under the router, this would crash on every scan cycle.

**Fix approach:** Open two connections sequentially — one for `scans` (operational.db) to get scan_id and commit; then a second for `miner_readings` (timeseries.db) for the firmware lookup and batch insert. The `scan_id` passes between them by value.

**Alternative with less refactor risk:** Split into two methods (`_insert_scan_row` returning scan_id, `_insert_miner_readings` taking scan_id).

---

### 🔴 Bug 5 — `save_logs` (line 947)

**Severity:** High (crash on log save)
**Hint:** `_connect('miner_logs')` → `audit.db` (called twice in the method)
**Issue:** Inside the second `_connect('miner_logs')` block:

- `INSERT INTO miner_logs ...` ✅ audit.db
- `SELECT ip, mac FROM miner_readings WHERE miner_id=? ORDER BY id DESC LIMIT 1` 🔴 timeseries.db

The cross-DB select is a lookup to enrich the log row with the miner's latest IP/MAC.

**Fix approach:** Do the `miner_readings` lookup with its own connection before opening the `miner_logs` connection for the insert.

---

### 🔴 Bug 6 — `count_outcome_failures` (line 1552)

**Severity:** Medium (crashes on every `_analyze_miner` call)
**Hint:** `_connect('action_audit_log')` → `audit.db`
**Issue:** SQL is `SELECT COUNT(*) FROM miner_restarts WHERE miner_id=? AND outcome='FAILURE'`. But `miner_restarts` lives in `operational.db`, not `audit.db`.

**Fix approach:** Change hint to `_connect('miner_restarts')` (correct single-DB query). The method is mis-named historically — it reads restart outcomes, not audit log entries.

**Note:** This was one of the bugs that surfaced yesterday and triggered the router revert. Already documented in `DB_STATE_2026-04-23.md`.

---

### 🔴 Bug 7 — `_count_pdu_cycles` (line 1561)

**Severity:** Medium
**Hint:** `_connect('miner_restarts')` → `operational.db`
**Issue:** Mirror of Bug 6 — SQL is `SELECT COUNT(*) FROM action_audit_log WHERE miner_id=? AND action_taken='PDU_CYCLE' AND timestamp >= ?`. But `action_audit_log` lives in `audit.db`, not `operational.db`.

**Fix approach:** Change hint to `_connect('action_audit_log')`. The method reads audit log rows to count PDU cycles — hint should match.

**Note:** Second of the bugs that triggered yesterday's router revert.

## Methods Verified Clean (31)

These methods were inspected and every table they touch matches their `_connect()` hint's DB. No cross-DB access.

- `_latest_scan_id` (L64) — scans
- `save_pending_approvals` (L456) — pending_approvals
- `log_action` (L562) — action_audit_log
- `get_audit_log` (L587) — action_audit_log
- `save_notifications` (L605) — ams_notifications
- `save_weather` (L632) — weather_readings
- `save_hvac` (L651) — hvac_readings
- `save_discovery` (L751) — discovery_log
- `get_discoveries` (L812) — discovery_log
- `acknowledge_discovery` (L826) — discovery_log
- `purge_old_logs` (L1005) — miner_logs
- `has_known_dead_boards` (L1021) — known_dead_boards
- `register_dead_boards` (L1030) — known_dead_boards
- `needs_ticket` (L1056) — known_dead_boards
- `mark_ticket_created` (L1068) — known_dead_boards
- `get_newly_ticketed` (L1080) — known_dead_boards
- `mark_ticket_noticed` (L1098) — known_dead_boards
- `resolve_dead_boards` (L1111) — known_dead_boards
- `save_chain_readings` (L1120) — chain_readings
- `save_pool_readings` (L1145) — pool_readings
- `save_miner_state_readings` (L1174) — miner_state_readings
- `save_ams_extended` (L1199) — miner_ams_extended
- `parse_and_save_hardware` (L1229) — miner_hardware
- `get_hardware_identity` (L1353) — miner_hardware
- `parse_log_metrics` (L1362) — log_metrics
- `record_restart` (L1509) — miner_restarts
- `is_elevated_monitoring` (L1530) — miner_restarts
- `get_failed_restart_count` (L1542) — miner_restarts
- `last_log_collected` (L1572) — miner_logs

## Summary

- **7 bugs** requiring code changes before router re-enable
- **31 methods** verified clean
- **38 total `_connect()` call sites** audited
- **Most severe bugs:** `_init_db` (silent schema pollution) and `save_scan` (write path used on every scan)

All 7 bugs are structural — they all violate the same rule (one connection, one DB) — and the fixes follow the same pattern: split into separate connection blocks, one per target DB, passing values in Python between them.

## Recommended fix order for Step 6

1. `count_outcome_failures` and `_count_pdu_cycles` — smallest, simplest, well-understood. Each is a single-line hint change.
2. `last_log_collected` was clean — confirm no similar mismatches.
3. `load_known_firmware` — split into two reads, merge in Python.
4. `save_logs` — split miner_readings lookup from miner_logs insert.
5. `expire_old_pending_approvals` — split pending_approvals update from audit_log insert.
6. `save_scan` — largest refactor, most write traffic, save for when others are validated.
7. `_init_db` — schema creation split across four DBs. Touch once all data-path methods are fixed, since this only matters on first-run or new-DB bootstrap.

Each fix should be its own commit with a dedicated test. Running `pytest tests/test_database.py` must stay green between commits.
