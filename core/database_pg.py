"""
PostgreSQL adapter for GuardianDB.

This is a parallel implementation of core/database.py::GuardianDB backed by
PostgreSQL instead of SQLite. It exposes the same method names and signatures
so the rest of the Mining Guardian codebase can import either backend
interchangeably.

Scope (as of 2026-04-23):
  - _init_db, _connect are fully implemented
  - The 7 methods exercised by /tmp/scratch_router_test.py are ported:
      save_scan, save_logs, expire_old_pending_approvals,
      load_known_firmware, count_outcome_failures, _count_pdu_cycles,
      save_pending_approvals
  - Other methods from GuardianDB are NOT yet ported. Adding them is a
    straightforward extension when needed.

Design notes:
  - Uses psycopg2 (not psycopg3) to match scripts/migrate_to_postgres.py
  - SQL placeholders are %s (not ? like SQLite)
  - INSERT ... RETURNING id is used instead of cur.lastrowid
  - conn is checked out per-call (no pool today — simple for correctness)
  - _init_db runs migrations/001_initial_schema.sql which is idempotent

Non-goals:
  - Connection pooling (add when we deploy)
  - Async variant
  - Multi-schema / per-table routing (the SQLite split-DB router concept
    doesn't apply — all tables live in the public schema)
"""
from contextlib import contextmanager
from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch

logger = logging.getLogger(__name__)

# Schema file that defines the Postgres tables. Idempotent (uses IF NOT EXISTS).
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMA_SQL = REPO_ROOT / "migrations" / "001_initial_schema.sql"


def _profile_parse_ths(profile_str: str) -> Optional[float]:
    """Parse TH/s value from a BiXBiT profile string.

    Duplicated from core/database.py to avoid importing the SQLite module.
    """
    if not profile_str:
        return None
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*TH/s", profile_str)
    return float(m.group(1)) if m else None


class GuardianPGDB:
    """PostgreSQL-backed GuardianDB. API-compatible parallel implementation."""

    def __init__(
        self,
        dsn: Optional[str] = None,
        *,
        host: str = "localhost",
        port: int = 5432,
        dbname: str = "mining_guardian",
        user: str = "guardian_app",
        password: Optional[str] = None,
        schema_sql_path: Optional[Path] = None,
    ) -> None:
        """Connect to Postgres and ensure the schema is loaded.

        Either pass a full DSN or individual host/port/dbname/user/password.
        If password is None, reads from env var GUARDIAN_PG_PASSWORD.
        """
        if dsn is not None:
            self._dsn = dsn
        else:
            pw = password if password is not None else os.environ.get("GUARDIAN_PG_PASSWORD", "")
            self._dsn = f"host={host} port={port} dbname={dbname} user={user} password={pw}"
        self._schema_sql_path = Path(schema_sql_path) if schema_sql_path else DEFAULT_SCHEMA_SQL
        # Ping the DB to fail fast if credentials are wrong.
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        self._init_db()

    # ── Connection management ──────────────────────────────────────────
    @contextmanager
    def _connect(self, table_name: str = None):
        """Open a Postgres connection.

        table_name is accepted for API compatibility with the SQLite backend's
        router hint, but it is ignored — all tables live in public.

        Uses RealDictCursor so rows behave like dicts (parallel to SQLite
        Row factory on the SQLite side).
        """
        conn = psycopg2.connect(self._dsn, cursor_factory=RealDictCursor)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Schema bootstrap ───────────────────────────────────────────────
    def _init_db(self) -> None:
        """Apply the Postgres schema migration. Idempotent.

        Runs migrations/001_initial_schema.sql which uses IF NOT EXISTS
        everywhere, so repeated runs are no-ops.
        """
        if not self._schema_sql_path.exists():
            logger.warning(
                "Schema SQL not found at %s — assuming tables already exist",
                self._schema_sql_path,
            )
            return
        schema_sql = self._schema_sql_path.read_text()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(schema_sql)
        logger.info("Postgres schema bootstrapped from %s", self._schema_sql_path)

    # ── save_scan (Bug 4 in the SQLite audit) ──────────────────────────
    def save_scan(self, miners: List[Dict], issues: List[Dict]) -> int:
        """Write scan summary and all miner readings. Returns scan_id."""
        now = datetime.now().isoformat()
        online = sum(1 for m in miners if m.get("status") == "online")
        offline = len(miners) - online

        with self._connect() as conn:
            # Insert scan header, get scan_id back via RETURNING
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO scans (scanned_at, total_miners, online, offline, issues) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (now, len(miners), online, offline, len(issues)),
                )
                scan_id = cur.fetchone()["id"]

            issue_map = {i["id"]: i for i in issues}

            rows = []
            for m in miners:
                miner_id = str(m.get("id", ""))
                max_hr = m.get("maxHashrate") or 0
                hashrate = m.get("hashrate") or 0
                _profile_str = m.get("currentProfile", "") or ""
                _profile_rated = _profile_parse_ths(_profile_str)
                if _profile_rated:
                    pct = round((hashrate / 1000.0 / _profile_rated) * 100, 1) if _profile_rated > 0 else 0.0
                elif max_hr > 0:
                    pct = round((hashrate / max_hr) * 100, 1)
                else:
                    pct = 0.0
                temp_raw = m.get("tempChip") or 0
                temp = temp_raw if temp_raw >= 0 else None
                temp_board = m.get("tempBoard") or 0
                pdu_power = (m.get("pduOutlet") or {}).get("power") or 0
                map_loc = (m.get("mapLocation") or {}).get("title") or None
                err_codes = str(m.get("errorCodes") or []) if m.get("errorCodes") else None
                issue = issue_map.get(miner_id)

                # Firmware fallback — look up last known firmware if AMS returned blank
                fw_mfr = m.get("firmwareManufacturer") or ""
                fw_ver = m.get("firmwareVersion") or ""
                if not fw_mfr and miner_id:
                    try:
                        with conn.cursor() as cur:
                            cur.execute(
                                "SELECT firmware_manufacturer, firmware_version FROM miner_readings "
                                "WHERE miner_id = %s AND firmware_manufacturer != '' "
                                "AND firmware_manufacturer IS NOT NULL "
                                "ORDER BY id DESC LIMIT 1",
                                (miner_id,),
                            )
                            _fw_row = cur.fetchone()
                        if _fw_row:
                            fw_mfr = _fw_row["firmware_manufacturer"] or ""
                            fw_ver = _fw_row["firmware_version"] or ""
                    except Exception:
                        pass

                raw_model = m.get("shortModel", m.get("name", "unknown"))
                profile_str = m.get("currentProfile", "")
                if "TH/s" in profile_str and m.get("name") and m.get("name") != raw_model:
                    raw_model = m["name"]

                rows.append((
                    scan_id, now, miner_id, m.get("ip"), m.get("mac"),
                    raw_model, m.get("status"), hashrate, max_hr, pct,
                    temp, temp_board if temp_board >= 0 else None,
                    m.get("coolingMode"), m.get("currentProfile"),
                    fw_mfr, fw_ver, m.get("uptime"),
                    m.get("consumption") or 0, m.get("maxConsumption") or 0,
                    round(pdu_power / 1000, 2) if pdu_power else 0,
                    map_loc, err_codes,
                    " | ".join(issue["issues"]) if issue else None,
                    issue["action"] if issue else None,
                    issue.get("pdu_id") if issue else None,
                    issue.get("outlet") if issue else None,
                ))

            with conn.cursor() as cur:
                execute_batch(
                    cur,
                    "INSERT INTO miner_readings "
                    "(scan_id, scanned_at, miner_id, ip, mac, model, status, hashrate, "
                    " max_hashrate, hashrate_pct, temp_chip, temp_board, cooling_mode, "
                    " current_profile, firmware_manufacturer, firmware_version, uptime, "
                    " consumption, max_consumption, pdu_power, map_location, error_codes, "
                    " issue, action, pdu_id, outlet) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    rows,
                    page_size=100,
                )

        logger.info("Scan #%s saved to Postgres (%s miners)", scan_id, len(miners))
        return scan_id

    # ── save_logs (Bug 5) ──────────────────────────────────────────────
    def save_logs(self, miner_id: str, model: str, health_status: str, logs: Dict[str, str]) -> None:
        """Store log snapshots for a miner. Looks up IP from miner_readings."""
        if not logs:
            return
        now = datetime.now().isoformat()

        # Look up the most recent IP for this miner_id
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ip FROM miner_readings WHERE miner_id = %s "
                    "ORDER BY id DESC LIMIT 1",
                    (miner_id,),
                )
                ip_row = cur.fetchone()
            ip = ip_row["ip"] if ip_row else None
            # (We don't actually use ip in the insert because the miner_logs
            # schema doesn't have an ip column — the lookup is inherited from
            # the SQLite implementation. Kept here for parity.)
            _ = ip

            rows = [
                (now, miner_id, model, health_status, filename, content)
                for filename, content in logs.items()
            ]
            with conn.cursor() as cur:
                execute_batch(
                    cur,
                    "INSERT INTO miner_logs "
                    "(collected_at, miner_id, model, health_status, log_file, content) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    rows,
                )

    # ── expire_old_pending_approvals (Bug 2) ───────────────────────────
    def expire_old_pending_approvals(self, max_age_minutes: int = 30) -> int:
        """Auto-deny pending approvals older than max_age_minutes."""
        cutoff = (datetime.now() - timedelta(minutes=max_age_minutes)).isoformat()

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, miner_id, ip, action_type FROM pending_approvals "
                    "WHERE status='PENDING' AND created_at < %s",
                    (cutoff,),
                )
                expired = cur.fetchall()

                if expired:
                    cur.execute(
                        "UPDATE pending_approvals SET status='DENIED', responded_at=%s "
                        "WHERE status='PENDING' AND created_at < %s",
                        (datetime.now().isoformat(), cutoff),
                    )

            # Postgres supports cross-table writes in one transaction, so the
            # SQLite split-DB dance isn't needed here.
            if expired:
                audit_rows = [
                    (datetime.now().isoformat(),
                     datetime.now().strftime("%Y-%m-%d"),
                     row["miner_id"], row["ip"], "", "",
                     row["action_type"], "DENIED",
                     "Mining Guardian (Auto-Expired)",
                     f"No response within {max_age_minutes} minutes — auto-denied")
                    for row in expired
                ]
                with conn.cursor() as cur:
                    execute_batch(
                        cur,
                        "INSERT INTO action_audit_log "
                        "(timestamp, date, miner_id, ip, model, problem, "
                        " action_taken, decision, approved_by, notes) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        audit_rows,
                    )
                logger.info(
                    "Auto-expired %d pending approvals older than %d min",
                    len(expired), max_age_minutes,
                )
        return len(expired) if expired else 0

    # ── load_known_firmware (Bug 3) ────────────────────────────────────
    def load_known_firmware(self) -> set:
        """Return the set of known firmware (manufacturer, version) pairs."""
        known: set = set()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT firmware_manufacturer, firmware_version "
                    "FROM miner_readings "
                    "WHERE firmware_manufacturer IS NOT NULL "
                    "AND firmware_manufacturer != ''"
                )
                for row in cur.fetchall():
                    known.add((row["firmware_manufacturer"], row["firmware_version"]))
        return known

    # ── count_outcome_failures (Bug 6) ─────────────────────────────────
    def count_outcome_failures(self, miner_id: str, since_days: int = 7) -> int:
        """Count FAILURE outcomes for a miner in the last N days."""
        since = (datetime.now() - timedelta(days=since_days)).isoformat()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM miner_restarts "
                    "WHERE miner_id = %s AND outcome = 'FAILURE' AND restarted_at > %s",
                    (miner_id, since),
                )
                row = cur.fetchone()
        return row["cnt"] if row else 0

    # ── _count_pdu_cycles (Bug 7) ──────────────────────────────────────
    def _count_pdu_cycles(self, miner_id: str, since_hours: int = 24) -> int:
        """Count PDU cycles performed on a miner in the last N hours."""
        since = (datetime.now() - timedelta(hours=since_hours)).isoformat()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM action_audit_log "
                    "WHERE miner_id = %s AND action_taken = 'PDU_CYCLE' "
                    "AND timestamp > %s",
                    (miner_id, since),
                )
                row = cur.fetchone()
        return row["cnt"] if row else 0

    # ── save_pending_approvals (support for Bug 2 test) ────────────────
    def save_pending_approvals(self, thread_ts: str, scan_id: int, issues: List[Dict]) -> None:
        """Save actionable issues as pending approvals linked to a Slack thread."""
        if not issues:
            return
        now = datetime.now().isoformat()
        rows = []
        for i in issues:
            problem = " | ".join(i.get("issues", [])) if i.get("issues") else None
            rows.append((
                now, scan_id, thread_ts,
                i["id"], i["ip"], i.get("model"),
                i["action"], problem,
                i.get("pdu_id"), i.get("outlet"),
                i.get("confidence_score"), i.get("confidence_gate"),
            ))
        with self._connect() as conn:
            with conn.cursor() as cur:
                execute_batch(
                    cur,
                    "INSERT INTO pending_approvals "
                    "(created_at, scan_id, thread_ts, miner_id, ip, model, "
                    " action_type, problem, pdu_id, outlet, "
                    " confidence_score, confidence_gate) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    rows,
                )

    # ── Phase 3: trivial methods (Postgres-translated from core/database.py) ─────

    def _latest_scan_id(self) -> Optional[int]:
        """Get the latest scan ID. Returns None if no scans exist."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1")
                row = cur.fetchone()
        return row["id"] if row else None

    def has_known_dead_boards(self, miner_id: str) -> bool:
        """Check if this miner has unresolved known dead boards (already attempted restart)."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM known_dead_boards "
                    "WHERE miner_id = %s AND resolved_at IS NULL AND restart_attempted IS NOT NULL",
                    (miner_id,),
                )
                row = cur.fetchone()
        return row is not None

    def mark_ticket_created(self, miner_id: str, ticket_id: str = None) -> None:
        """Record that an AMS ticket has been created for this dead board miner."""
        now = datetime.now().isoformat()
        value = ticket_id or now
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE known_dead_boards SET ticket_created=%s "
                    "WHERE miner_id=%s AND resolved_at IS NULL",
                    (value, miner_id),
                )
        logger.info("[%s] AMS ticket recorded: %s", miner_id, value)

    def mark_ticket_noticed(self, miner_ids: list) -> None:
        """Mark tickets as noticed in Slack — won't appear in future reports."""
        if not miner_ids:
            return
        now = datetime.now().isoformat()
        with self._connect() as conn:
            with conn.cursor() as cur:
                for miner_id in miner_ids:
                    cur.execute(
                        "UPDATE known_dead_boards SET ticket_noticed_at=%s "
                        "WHERE miner_id=%s AND resolved_at IS NULL",
                        (now, miner_id),
                    )

    def get_newly_ticketed(self) -> list:
        """Return dead board miners whose ticket was created but not yet noticed in Slack.

        Matches the SQLite implementation — only rows where ticket_noticed_at IS NULL
        are returned. Marking them noticed happens immediately after posting via
        mark_ticket_noticed().
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT miner_id, ip, model, board_indices, ticket_created "
                    "FROM known_dead_boards "
                    "WHERE resolved_at IS NULL AND ticket_created IS NOT NULL "
                    "AND ticket_noticed_at IS NULL"
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def is_elevated_monitoring(self, miner_id: str) -> bool:
        """Return True if this miner is within its post-restart elevated monitoring window."""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT elevated_until FROM miner_restarts "
                    "WHERE miner_id=%s AND elevated_until > %s "
                    "ORDER BY id DESC LIMIT 1",
                    (miner_id, now),
                )
                row = cur.fetchone()
        return row is not None

    def get_failed_restart_count(self, miner_id: str, days: int = 7) -> int:
        """Count restarts in the last N days. Matches SQLite semantics — this is a
        total-restart counter, not filtered by outcome (despite the name).
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM miner_restarts "
                    "WHERE miner_id=%s AND restarted_at >= %s",
                    (miner_id, cutoff),
                )
                row = cur.fetchone()
        return row["cnt"] if row else 0

    def close(self, force: bool = False) -> None:
        """No-op for Postgres — connections are per-call and auto-close on context exit.

        Kept for API compatibility with the SQLite backend which maintained persistent
        connections.
        """
        pass
