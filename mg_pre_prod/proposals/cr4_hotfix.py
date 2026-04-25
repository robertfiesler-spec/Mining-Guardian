#!/usr/bin/env python3
"""
CR-4 Hotfix Patch Script — main branch (b28c8a7)
=================================================

Targets:
  core/database_pg.py        — Layer 1: _PgConnWrapper shim in _connect()
  core/mining_guardian.py    — Layer 2: 8 SQL conversion sites

Bug summary:
  GuardianPGDB._connect() yields a raw psycopg2.connection which has no
  .execute() method. 8 of 9 callers in mining_guardian.py invoke
  conn.execute(...) directly (SQLite-style) — every call raises
  AttributeError. Production VPS logs show 68 hits in 7 days from a
  single function (_auto_create_missing_tickets). Other 7 sites likely
  also fire silently inside try/except blocks.

Fix:
  Layer 1: Replace _connect() with a context-managed wrapper that
           exposes BOTH .execute() (SQLite-style shortcut) AND
           .cursor() (passthrough — preserves existing 30+ internal
           callers in database_pg.py).

  Layer 2: Convert SQLite-only SQL syntax in mining_guardian.py:
           - "?"  param markers     -> "%s"  (8 sites)
           - datetime('now', '...') -> NOW() - INTERVAL '...'  (1 site)
           - datetime('now')        -> NOW()  (1 site)
           - datetime(col)          -> col    (2 sites in same statement)
             (Postgres timestamp columns don't need wrapper)

Usage:
    python cr4_hotfix.py --dry-run   # show planned edits, write nothing
    python cr4_hotfix.py --apply     # apply edits + write .pre_cr4_backup files

Run from repo root.
"""
from __future__ import annotations
import argparse
import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DB_PG = REPO / "core" / "database_pg.py"
MG    = REPO / "core" / "mining_guardian.py"

# Expected sha256 of clean origin/main files (refuse to patch if mismatched)
EXPECTED_MG_SHA  = "dbc873b9336773ef5052fa08a4aa3e6ac1eac82061d04b48626e393f9cb2fbea"
# database_pg.py sha — computed at runtime, not pinned (less critical, smaller surface)


# ──────────────────────────────────────────────────────────────────────
# Layer 1 — _PgConnWrapper shim in core/database_pg.py
# ──────────────────────────────────────────────────────────────────────

DB_PG_OLD = '''    # ── Connection management ──────────────────────────────────────────
    @contextmanager
    def _connect(self, table_name: str = None):
        """Open a Postgres connection.

        table_name is accepted for API compatibility with the SQLite backend's
        router hint, but it is ignored — all tables live in public.

        Uses DictCursor so rows behave like dicts (parallel to SQLite
        Row factory on the SQLite side).
        """
        conn = psycopg2.connect(self._dsn, cursor_factory=DictCursor)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
'''

DB_PG_NEW = '''    # ── Connection management ──────────────────────────────────────────
    @contextmanager
    def _connect(self, table_name: str = None):
        """Open a Postgres connection wrapped in a SQLite-compatible shim.

        table_name is accepted for API compatibility with the SQLite backend's
        router hint, but it is ignored — all tables live in public.

        Returns a _PgConnShim that exposes BOTH:
          - .execute(sql, params) -> cursor with .fetchone/.fetchall/.rowcount
            (SQLite-style shortcut — used by mining_guardian.py callers)
          - .cursor()             -> raw psycopg2 DictCursor
            (used by database_pg.py's own internal methods)
          - .commit() / .rollback() / context manager protocol

        Wraps a per-connection DictCursor so rows behave like dicts (parallel
        to SQLite Row factory on the SQLite side).
        """
        raw = psycopg2.connect(self._dsn, cursor_factory=DictCursor)
        shim = _PgConnShim(raw)
        try:
            yield shim
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()
'''

# New class definition — inserted just before "class GuardianPGDB:"
PG_SHIM_CLASS = '''
class _PgConnShim:
    """SQLite-compatible shim over a psycopg2 connection.

    Added 2026-04-25 as part of CR-4 hotfix. The codebase contains a mix of
    callers — some written for SQLite (conn.execute(...).fetchall()) and
    some written for psycopg2 (with conn.cursor() as cur). Rather than
    rewrite every caller, this shim exposes both surfaces.

    .execute(sql, params=()) returns a cursor (so .fetchone/.fetchall/
    .rowcount/iteration all work just like SQLite). .cursor() passes
    through unchanged so existing psycopg2-style callers in database_pg.py
    keep working without modification.
    """

    __slots__ = ("_conn",)

    def __init__(self, conn):
        self._conn = conn

    # SQLite-style shortcut used by mining_guardian.py
    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur

    # Passthrough used by database_pg.py's own methods
    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    # Some callers do `with self.db._connect() as conn: with conn:` — be safe.
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Don't close here — outer @contextmanager owns the lifecycle.
        return False


'''

PG_SHIM_ANCHOR = "class GuardianPGDB:"


# ──────────────────────────────────────────────────────────────────────
# Layer 2 — SQL conversions in core/mining_guardian.py
# ──────────────────────────────────────────────────────────────────────
# Each entry: (label, old_block, new_block)
# old_block must be unique in the file. We include enough context lines
# to guarantee uniqueness.

MG_EDITS = [
    # ─────────────────────────────────────────────────────────
    # Site 1 — line ~285 (AMS SYNC suppression)
    # ─────────────────────────────────────────────────────────
    (
        "site_1_ams_sync_lookup",
        '''                    with self.db._connect() as conn:
                        rows = conn.execute("""
                            SELECT issue FROM miner_readings
                            WHERE miner_id=? ORDER BY id DESC LIMIT 20
                        """, (miner_id,)).fetchall()''',
        '''                    with self.db._connect() as conn:
                        rows = conn.execute("""
                            SELECT issue FROM miner_readings
                            WHERE miner_id=%s ORDER BY id DESC LIMIT 20
                        """, (miner_id,)).fetchall()''',
    ),

    # ─────────────────────────────────────────────────────────
    # Site 2 — line ~1033 (_auto_create_missing_tickets candidates)
    # This is THE function logging 68 errors/week.
    # Three sub-queries inside one with-block. Convert all three.
    # ─────────────────────────────────────────────────────────
    (
        "site_2a_auto_ticket_failures",
        '''            candidates_failures = conn.execute("""
                SELECT miner_id, ip, model,
                       COUNT(*) as failure_count, 'failure_outcomes' as reason
                FROM miner_restarts
                WHERE outcome = 'FAILURE'
                  AND restarted_at < datetime('now', '-30 minutes')
                GROUP BY miner_id
                HAVING failure_count >= ?
            """, (FAILURE_THRESHOLD,)).fetchall()''',
        '''            candidates_failures = conn.execute("""
                SELECT miner_id, ip, model,
                       COUNT(*) as failure_count, 'failure_outcomes' as reason
                FROM miner_restarts
                WHERE outcome = 'FAILURE'
                  AND restarted_at < NOW() - INTERVAL '30 minutes'
                GROUP BY miner_id
                HAVING COUNT(*) >= %s
            """, (FAILURE_THRESHOLD,)).fetchall()''',
    ),
    (
        "site_2b_auto_ticket_escalated",
        '''            candidates_escalated = conn.execute("""
                SELECT miner_id, ip, model,
                       COUNT(*) as failure_count, 'escalated_restarts' as reason
                FROM miner_restarts
                WHERE restart_type LIKE '%Dead board%'
                   OR restart_type LIKE '%board%'
                GROUP BY miner_id
                HAVING failure_count >= ?
            """, (ESCALATION_THRESHOLD,)).fetchall()''',
        '''            candidates_escalated = conn.execute("""
                SELECT miner_id, ip, model,
                       COUNT(*) as failure_count, 'escalated_restarts' as reason
                FROM miner_restarts
                WHERE restart_type LIKE %s
                   OR restart_type LIKE %s
                GROUP BY miner_id
                HAVING COUNT(*) >= %s
            """, ('%Dead board%', '%board%', ESCALATION_THRESHOLD)).fetchall()''',
    ),

    # ─────────────────────────────────────────────────────────
    # Site 3 — line ~1102 (known_dead_boards check)
    # ─────────────────────────────────────────────────────────
    (
        "site_3_known_dead_boards_check",
        '''            with self.db._connect() as conn:
                existing = conn.execute("""
                    SELECT ticket_created FROM known_dead_boards
                    WHERE miner_id=? AND resolved_at IS NULL
                """, (miner_id,)).fetchone()''',
        '''            with self.db._connect() as conn:
                existing = conn.execute("""
                    SELECT ticket_created FROM known_dead_boards
                    WHERE miner_id=%s AND resolved_at IS NULL
                """, (miner_id,)).fetchone()''',
    ),

    # ─────────────────────────────────────────────────────────
    # Site 4 — line ~1418 (LLM log comparison pre/post fetch)
    # Two queries in one with-block. datetime(collected_at) wrapper not
    # needed in Postgres — column is already timestamp; remove wrapper.
    # ─────────────────────────────────────────────────────────
    (
        "site_4a_llm_pre_log",
        '''            with self.db._connect() as conn:
                pre_row = conn.execute(
                    "SELECT content, datetime(collected_at) FROM miner_logs "
                    "WHERE miner_id=? AND health_status=? AND log_file LIKE ?"
                    " ORDER BY collected_at DESC LIMIT 1",
                    (miner_id, pre_label, '%miner.log')
                ).fetchone()
                post_row = conn.execute(
                    "SELECT content, datetime(collected_at) FROM miner_logs "
                    "WHERE miner_id=? AND health_status=? AND log_file LIKE ?"
                    " ORDER BY collected_at DESC LIMIT 1",
                    (miner_id, post_label, '%miner.log')
                ).fetchone()''',
        '''            with self.db._connect() as conn:
                pre_row = conn.execute(
                    "SELECT content, collected_at FROM miner_logs "
                    "WHERE miner_id=%s AND health_status=%s AND log_file LIKE %s"
                    " ORDER BY collected_at DESC LIMIT 1",
                    (miner_id, pre_label, '%miner.log')
                ).fetchone()
                post_row = conn.execute(
                    "SELECT content, collected_at FROM miner_logs "
                    "WHERE miner_id=%s AND health_status=%s AND log_file LIKE %s"
                    " ORDER BY collected_at DESC LIMIT 1",
                    (miner_id, post_label, '%miner.log')
                ).fetchone()''',
    ),

    # ─────────────────────────────────────────────────────────
    # Site 5 — line ~1909 (log collection failure enrichment)
    # ─────────────────────────────────────────────────────────
    (
        "site_5_log_failure_enrichment",
        '''                    row = conn.execute(
                        "SELECT MAX(collected_at) FROM miner_logs WHERE miner_id = ?",
                        (miner_id,)
                    ).fetchone()''',
        '''                    row = conn.execute(
                        "SELECT MAX(collected_at) FROM miner_logs WHERE miner_id = %s",
                        (miner_id,)
                    ).fetchone()''',
    ),

    # ─────────────────────────────────────────────────────────
    # Site 6 — line ~2066 (cancel pending approvals for ticketed miners)
    # Dynamic IN clause with "?" placeholders — convert to "%s" array.
    # Plus datetime('now') -> NOW().
    # ─────────────────────────────────────────────────────────
    (
        "site_6_cancel_ticketed_pending",
        '''            with self.db._connect() as conn:
                ticketed_ids = [r["miner_id"] for r in conn.execute(
                    "SELECT miner_id FROM known_dead_boards WHERE resolved_at IS NULL"
                ).fetchall()]
                if ticketed_ids:
                    placeholders = ",".join("?" for _ in ticketed_ids)
                    cancelled = conn.execute(f"""
                        UPDATE pending_approvals
                        SET status='CANCELLED', responded_at=datetime('now')
                        WHERE miner_id IN ({placeholders}) AND status='PENDING'
                    """, ticketed_ids).rowcount''',
        '''            with self.db._connect() as conn:
                ticketed_ids = [r["miner_id"] for r in conn.execute(
                    "SELECT miner_id FROM known_dead_boards WHERE resolved_at IS NULL"
                ).fetchall()]
                if ticketed_ids:
                    placeholders = ",".join("%s" for _ in ticketed_ids)
                    cancelled = conn.execute(f"""
                        UPDATE pending_approvals
                        SET status='CANCELLED', responded_at=NOW()
                        WHERE miner_id IN ({placeholders}) AND status='PENDING'
                    """, ticketed_ids).rowcount''',
    ),

    # ─────────────────────────────────────────────────────────
    # Site 7 — line ~2285 (Auradine firmware lookup in prediction loop)
    # ─────────────────────────────────────────────────────────
    (
        "site_7_auradine_firmware_lookup",
        '''                                with self.db._connect() as _c:
                                    _fw = _c.execute(
                                        "SELECT firmware_manufacturer FROM miner_readings "
                                        "WHERE miner_id=? ORDER BY id DESC LIMIT 1", (pred["miner_id"],)
                                    ).fetchone()''',
        '''                                with self.db._connect() as _c:
                                    _fw = _c.execute(
                                        "SELECT firmware_manufacturer FROM miner_readings "
                                        "WHERE miner_id=%s ORDER BY id DESC LIMIT 1", (pred["miner_id"],)
                                    ).fetchone()''',
    ),

    # ─────────────────────────────────────────────────────────
    # Site 8 — line ~609 — already correct (uses cur.execute with %s).
    # No change needed.
    # ─────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────
    # Site 9 — line ~2393 — no params, just .execute("SELECT id FROM scans...")
    # No SQL change needed; the wrapper handles .execute() correctly.
    # No change needed.
    # ─────────────────────────────────────────────────────────
]


# ──────────────────────────────────────────────────────────────────────
# Patch engine
# ──────────────────────────────────────────────────────────────────────

def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_db_pg(content: str) -> tuple[str, list[str]]:
    """Apply Layer 1 edits to database_pg.py source. Returns (new, log)."""
    log = []
    new = content

    # Idempotence check
    if "_PgConnShim" in new:
        log.append("[skip] _PgConnShim class already present (idempotent re-run?)")
        return new, log

    if DB_PG_OLD not in new:
        raise RuntimeError("database_pg.py: DB_PG_OLD anchor not found — file may have drifted from origin/main b28c8a7")
    new = new.replace(DB_PG_OLD, DB_PG_NEW, 1)
    log.append("[ok] replaced _connect() body with shim-yielding version")

    # Insert _PgConnShim class definition just before "class GuardianPGDB:"
    if PG_SHIM_ANCHOR not in new:
        raise RuntimeError("database_pg.py: GuardianPGDB class anchor not found")
    new = new.replace(PG_SHIM_ANCHOR, PG_SHIM_CLASS + PG_SHIM_ANCHOR, 1)
    log.append("[ok] inserted _PgConnShim class definition above GuardianPGDB")

    return new, log


def patch_mg(content: str) -> tuple[str, list[str]]:
    """Apply Layer 2 edits to mining_guardian.py source. Returns (new, log)."""
    log = []
    new = content
    for label, old, new_block in MG_EDITS:
        if new_block in new and old not in new:
            log.append(f"[skip] {label}: already patched")
            continue
        if old not in new:
            raise RuntimeError(f"mining_guardian.py: anchor not found for edit '{label}'")
        new = new.replace(old, new_block, 1)
        log.append(f"[ok] {label}")
    return new, log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print planned edits, write nothing")
    ap.add_argument("--apply", action="store_true", help="write changes to disk + .pre_cr4_backup files")
    args = ap.parse_args()

    if not args.dry_run and not args.apply:
        ap.error("must specify --dry-run or --apply")

    if not DB_PG.exists():
        print(f"FATAL: {DB_PG} not found", file=sys.stderr)
        return 2
    if not MG.exists():
        print(f"FATAL: {MG} not found", file=sys.stderr)
        return 2

    # Verify mining_guardian.py is the expected origin/main b28c8a7 version
    actual_mg_sha = sha256_of(MG)
    if actual_mg_sha != EXPECTED_MG_SHA:
        print(f"FATAL: core/mining_guardian.py sha256 mismatch", file=sys.stderr)
        print(f"  expected: {EXPECTED_MG_SHA}", file=sys.stderr)
        print(f"  actual:   {actual_mg_sha}", file=sys.stderr)
        print(f"  This script expects origin/main HEAD b28c8a7. Refusing to patch.", file=sys.stderr)
        return 3

    db_pg_src = DB_PG.read_text()
    mg_src    = MG.read_text()

    new_db_pg, db_log = patch_db_pg(db_pg_src)
    new_mg,    mg_log = patch_mg(mg_src)

    print("=" * 64)
    print("Layer 1: core/database_pg.py")
    print("=" * 64)
    for line in db_log:
        print(f"  {line}")
    print(f"  before: {len(db_pg_src):>7} chars / {len(db_pg_src.splitlines()):>5} lines")
    print(f"  after:  {len(new_db_pg):>7} chars / {len(new_db_pg.splitlines()):>5} lines")

    print()
    print("=" * 64)
    print("Layer 2: core/mining_guardian.py")
    print("=" * 64)
    for line in mg_log:
        print(f"  {line}")
    print(f"  before: {len(mg_src):>7} chars / {len(mg_src.splitlines()):>5} lines")
    print(f"  after:  {len(new_mg):>7} chars / {len(new_mg.splitlines()):>5} lines")

    if args.dry_run:
        print()
        print("DRY-RUN — no files written. Re-run with --apply to persist.")
        return 0

    # Apply: write backups + new content
    DB_PG.with_suffix(DB_PG.suffix + ".pre_cr4_backup").write_text(db_pg_src)
    MG.with_suffix(MG.suffix + ".pre_cr4_backup").write_text(mg_src)
    DB_PG.write_text(new_db_pg)
    MG.write_text(new_mg)

    print()
    print(f"APPLIED. Backups: {DB_PG.name}.pre_cr4_backup, {MG.name}.pre_cr4_backup")
    return 0


if __name__ == "__main__":
    sys.exit(main())
