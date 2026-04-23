"""
Mining Guardian Database Layer
Extracted from mining_guardian.py on April 21, 2026

This module handles all SQLite database operations for Mining Guardian.
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# Import the database router for split database support
from core.database_router import get_router, get_connection, TABLE_ROUTING

# Import hashrate evaluation utilities
try:
    from hashrate_evaluation import parse_bixbit_profile
except ImportError:
    def parse_bixbit_profile(profile_str):
        return None  # Fallback if not available

logger = logging.getLogger(__name__)

class GuardianDB:

    def __init__(self, db_path: str = "guardian.db"):
        self.db_path = db_path
        self._router = get_router()
        self._init_db()

    def _connect(self, table_name: str = "scans") -> sqlite3.Connection:
        """Return a connection to the legacy monolithic guardian.db.
        
        TEMPORARY: Router-based split-DB routing disabled on 2026-04-22 because
        several extracted methods (e.g. count_outcome_failures, _count_pdu_cycles)
        issue cross-table queries that cannot span SQLite databases. Falling back
        to the single legacy guardian.db keeps all joins working. The split DBs
        remain as point-in-time snapshots for future Postgres migration work.
        The `table_name` argument is accepted but ignored."""
        from contextlib import contextmanager
        @contextmanager
        def _cm():
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA busy_timeout=30000')
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()
        return _cm()
    
    def _connect_legacy(self) -> sqlite3.Connection:
        """Legacy connection method - connects to guardian.db directly."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=30000')
        conn.row_factory = sqlite3.Row
        return conn

    def _latest_scan_id(self) -> Optional[int]:
        """Get the latest scan ID. Returns None if no scans exist."""
        with self._connect('scans') as conn:
            row = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
            return row["id"] if row else None

    def _init_db(self) -> None:
        """Create tables if they don't exist.

        Schemas are partitioned across four split SQLite DBs via the router
        (see core/database_router.TABLE_ROUTING). Each partition runs in its
        own _connect() block because SQLite executescript cannot cross DBs.

        Note on foreign keys: several tables declare REFERENCES scans(id) or
        similar. Under the split-DB architecture these references cross
        databases and are therefore NOT enforced by SQLite — they remain as
        informational schema documentation only. This was true before this
        method was split as well; the split doesn't change enforcement.
        """
        # ── operational.db: scans + pending_approvals + miner_restarts +
        #    known_dead_boards + miner_hardware + discovery_log ──
        with self._connect('scans') as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS scans (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    scanned_at    TEXT    NOT NULL,
                    total_miners  INTEGER NOT NULL,
                    online        INTEGER NOT NULL,
                    offline       INTEGER NOT NULL,
                    issues        INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pending_approvals (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at    TEXT    NOT NULL,
                    scan_id       INTEGER,
                    thread_ts     TEXT    NOT NULL,
                    miner_id      TEXT    NOT NULL,
                    ip            TEXT    NOT NULL,
                    model         TEXT,
                    action_type   TEXT    NOT NULL,
                    problem       TEXT,
                    pdu_id        INTEGER,
                    outlet        INTEGER,
                    status        TEXT    DEFAULT 'PENDING',
                    responded_at  TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_pending_thread
                    ON pending_approvals(thread_ts, status);

                CREATE TABLE IF NOT EXISTS miner_restarts (
                    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                    restarted_at          TEXT    NOT NULL,
                    miner_id              TEXT    NOT NULL,
                    ip                    TEXT,
                    model                 TEXT,
                    restart_type          TEXT,
                    elevated_until        TEXT,
                    outcome               TEXT,
                    outcome_checked_at    TEXT,
                    hashrate_before       REAL,
                    hashrate_after        REAL,
                    recovery_time_scans   INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_restarts_miner
                    ON miner_restarts(miner_id, restarted_at);

                CREATE TABLE IF NOT EXISTS known_dead_boards (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    miner_id        TEXT    NOT NULL,
                    ip              TEXT,
                    model           TEXT,
                    board_indices   TEXT    NOT NULL,
                    first_seen      TEXT    NOT NULL,
                    restart_attempted TEXT,
                    restart_result  TEXT,
                    ticket_created  TEXT,
                    ticket_noticed_at TEXT,
                    resolved_at     TEXT,
                    notes           TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_dead_boards_miner
                    ON known_dead_boards(miner_id)
                    WHERE resolved_at IS NULL;

                CREATE TABLE IF NOT EXISTS miner_hardware (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    miner_id            TEXT    NOT NULL,
                    ip                  TEXT,
                    mac                 TEXT,
                    board_index         INTEGER NOT NULL,
                    board_name          TEXT,
                    serial_number       TEXT,
                    chip_die            TEXT,
                    chip_marking        TEXT,
                    chip_technology     TEXT,
                    pcb_version         TEXT,
                    bom_version         TEXT,
                    chip_bin            TEXT,
                    chip_ft_ver         TEXT,
                    ideal_hashrate      INTEGER,
                    control_board       TEXT,
                    psu_version         TEXT,
                    bixminer_version    TEXT,
                    topol_machine       TEXT,
                    device_name         TEXT,
                    asic_count          INTEGER,
                    bad_chips_count     INTEGER,
                    pic_version         TEXT,
                    first_seen          TEXT    NOT NULL,
                    last_updated        TEXT    NOT NULL,
                    log_source          TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_hardware_miner_board
                    ON miner_hardware(miner_id, board_index);

                CREATE TABLE IF NOT EXISTS discovery_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discovery_type TEXT NOT NULL,
                    device_name TEXT,
                    normalized_name TEXT,
                    firmware_version TEXT,
                    miner_id TEXT,
                    ip TEXT,
                    hashrate REAL,
                    temp_chip REAL,
                    consumption REAL,
                    board_count INTEGER,
                    chip_count INTEGER,
                    raw_data TEXT,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    acknowledged INTEGER DEFAULT 0,
                    notes TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_discovery_type_name
                    ON discovery_log(discovery_type, normalized_name);

                CREATE INDEX IF NOT EXISTS idx_discovery_ack
                    ON discovery_log(acknowledged);
            """)

            # ── Schema migration: add outcome feedback columns to miner_restarts
            # (miner_restarts lives in operational.db, so this stays in this block)
            existing = [r[1] for r in conn.execute(
                "PRAGMA table_info(miner_restarts)").fetchall()]
            for col, typedef in [
                ("outcome",             "TEXT"),
                ("outcome_checked_at",  "TEXT"),
                ("hashrate_before",     "REAL"),
                ("hashrate_after",      "REAL"),
                ("recovery_time_scans", "INTEGER"),
            ]:
                if col not in existing:
                    conn.execute(
                        f"ALTER TABLE miner_restarts ADD COLUMN {col} {typedef}")
                    logger.info("Migration: added miner_restarts.%s", col)

            # ── Schema migration: add confidence columns to pending_approvals
            # These columns were added to the live DB via ad-hoc ALTER TABLE at some
            # point and save_pending_approvals() writes to them, but the CREATE TABLE
            # above doesn't include them. Without this migration a fresh install
            # crashes on first pending-approval save. Discovered by the scratch-router
            # test on 2026-04-23.
            existing = [r[1] for r in conn.execute(
                "PRAGMA table_info(pending_approvals)").fetchall()]
            for col, typedef in [
                ("confidence_score", "INTEGER"),
                ("confidence_gate",  "TEXT"),
            ]:
                if col not in existing:
                    conn.execute(
                        f"ALTER TABLE pending_approvals ADD COLUMN {col} {typedef}")
                    logger.info("Migration: added pending_approvals.%s", col)
            conn.commit()

        # ── timeseries.db: miner_readings + chain_readings + pool_readings +
        #    chip_readings + miner_state_readings + miner_ams_extended +
        #    hvac_readings + weather_readings ──
        with self._connect('miner_readings') as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS miner_readings (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id             INTEGER NOT NULL REFERENCES scans(id),
                    scanned_at          TEXT    NOT NULL,
                    miner_id            TEXT    NOT NULL,
                    ip                  TEXT,
                    mac                 TEXT,
                    model               TEXT,
                    status              TEXT,
                    hashrate            REAL,
                    max_hashrate        REAL,
                    hashrate_pct        REAL,
                    temp_chip           REAL,
                    temp_board          REAL,
                    cooling_mode        INTEGER,
                    current_profile     TEXT,
                    firmware_manufacturer TEXT,
                    firmware_version    TEXT,
                    uptime              TEXT,
                    consumption         REAL,
                    max_consumption     REAL,
                    pdu_power           REAL,
                    map_location        TEXT,
                    error_codes         TEXT,
                    issue               TEXT,
                    action              TEXT,
                    pdu_id              INTEGER,
                    outlet              INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_readings_miner
                    ON miner_readings(miner_id, scanned_at);

                CREATE TABLE IF NOT EXISTS chain_readings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id         INTEGER NOT NULL REFERENCES scans(id),
                    scanned_at      TEXT    NOT NULL,
                    miner_id        TEXT    NOT NULL,
                    ip              TEXT,
                    board_index     INTEGER NOT NULL,
                    rate_mhs        REAL,
                    voltage         REAL,
                    freq_mhz        REAL,
                    consumption_w   REAL,
                    hw_errors       INTEGER,
                    temp_board      REAL,
                    temp_chip       REAL
                );

                CREATE INDEX IF NOT EXISTS idx_chain_miner
                    ON chain_readings(miner_id, scanned_at);

                CREATE TABLE IF NOT EXISTS pool_readings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id         INTEGER NOT NULL REFERENCES scans(id),
                    scanned_at      TEXT    NOT NULL,
                    miner_id        TEXT    NOT NULL,
                    ip              TEXT,
                    pool_priority   INTEGER,
                    pool_url        TEXT,
                    pool_user       TEXT,
                    pool_type       TEXT,
                    status          TEXT,
                    accepted        INTEGER,
                    rejected        INTEGER,
                    accepted_diff   REAL,
                    rejected_diff   REAL,
                    difficulty      TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_pool_miner
                    ON pool_readings(miner_id, scanned_at);

                CREATE TABLE IF NOT EXISTS chip_readings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id         INTEGER NOT NULL REFERENCES scans(id),
                    scanned_at      TEXT    NOT NULL,
                    miner_id        TEXT    NOT NULL,
                    ip              TEXT,
                    board_index     INTEGER NOT NULL,
                    chip_index      INTEGER NOT NULL,
                    freq_mhz        REAL,
                    voltage_mv      REAL,
                    temp_c          REAL,
                    source          TEXT    DEFAULT 'direct_api'
                );

                CREATE INDEX IF NOT EXISTS idx_chip_miner
                    ON chip_readings(miner_id, scanned_at);

                CREATE TABLE IF NOT EXISTS miner_state_readings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id         INTEGER NOT NULL REFERENCES scans(id),
                    scanned_at      TEXT    NOT NULL,
                    miner_id        TEXT    NOT NULL,
                    ip              TEXT,
                    hashrate_medium REAL,
                    hashrate_low    REAL,
                    max_hashrate    REAL,
                    max_consumption REAL,
                    max_temp_board  REAL,
                    max_temp_chip   REAL,
                    temp_chip_low   REAL,
                    temp_chip_medium REAL,
                    miner_status    INTEGER,
                    cooling_mode    INTEGER,
                    worker_version  TEXT,
                    active_pool_user TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_state_miner
                    ON miner_state_readings(miner_id, scanned_at);

                CREATE TABLE IF NOT EXISTS miner_ams_extended (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id             INTEGER NOT NULL REFERENCES scans(id),
                    scanned_at          TEXT    NOT NULL,
                    miner_id            TEXT    NOT NULL,
                    ip                  TEXT,
                    ams_timestamp       TEXT,
                    map_location_id     INTEGER,
                    map_x               REAL,
                    map_y               REAL,
                    pdu_counter         REAL,
                    stratum_url         TEXT,
                    favorite            INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_ams_ext_miner
                    ON miner_ams_extended(miner_id, scanned_at);

                CREATE TABLE IF NOT EXISTS hvac_readings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at     TEXT    NOT NULL,
                    supply_temp_f   REAL,
                    return_temp_f   REAL,
                    delta_t_f       REAL,
                    diff_pressure   REAL,
                    spray_pump_on   INTEGER,
                    cwp1_vfd_pct    REAL,
                    cwp2_vfd_pct    REAL,
                    ct1_vfd_pct     REAL,
                    ct2_vfd_pct     REAL,
                    leak_alarm      INTEGER DEFAULT 0,
                    ct1_fault       INTEGER DEFAULT 0,
                    ct2_fault       INTEGER DEFAULT 0,
                    pump_fault      INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS weather_readings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at     TEXT    NOT NULL,
                    temp_f          REAL,
                    humidity_pct    REAL,
                    feels_like_f    REAL,
                    temp_high_f     REAL,
                    temp_low_f      REAL,
                    humidity_max    REAL,
                    humidity_min    REAL
                );
            """)

            # ── Schema migration: add dual-system HVAC columns to hvac_readings.
            # When the s19jpro container HVAC came online, api/dashboard_api.py
            # started writing a 17-column form of hvac_readings including
            # system_id, outside_air_f, container_temp_f. The live DB got these
            # via ad-hoc ALTER TABLE but _init_db didn't. Without this migration,
            # a fresh install would crash the dashboard API HVAC POST and every
            # AI pipeline query that references those columns (deep_dive,
            # local_llm_analyzer, predictor, action_diversity, hvac_correlator).
            # Discovered by the column-drift audit on 2026-04-23.
            existing = [r[1] for r in conn.execute(
                "PRAGMA table_info(hvac_readings)").fetchall()]
            for col, typedef in [
                ("system_id",        "TEXT DEFAULT 'warehouse'"),
                ("outside_air_f",    "REAL"),
                ("container_temp_f", "REAL"),
            ]:
                if col not in existing:
                    conn.execute(
                        f"ALTER TABLE hvac_readings ADD COLUMN {col} {typedef}")
                    logger.info("Migration: added hvac_readings.%s", col)
            conn.commit()

        # ── audit.db: action_audit_log + ams_notifications + miner_logs ──
        with self._connect('action_audit_log') as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS action_audit_log (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp     TEXT    NOT NULL,
                    date          TEXT    NOT NULL,
                    scan_id       INTEGER,
                    miner_id      TEXT    NOT NULL,
                    ip            TEXT    NOT NULL,
                    model         TEXT,
                    problem       TEXT    NOT NULL,
                    action_taken  TEXT    NOT NULL,
                    decision      TEXT    NOT NULL,
                    approved_by   TEXT,
                    slack_user_id TEXT,
                    notes         TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_audit_date
                    ON action_audit_log(date);

                CREATE INDEX IF NOT EXISTS idx_audit_miner
                    ON action_audit_log(miner_id);

                CREATE TABLE IF NOT EXISTS ams_notifications (
                    row_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at     TEXT    NOT NULL,
                    notification_id INTEGER,
                    device_id       TEXT,
                    type            TEXT,
                    key             TEXT,
                    alert_level     TEXT,
                    miner_ip        TEXT,
                    raw             TEXT
                );

                CREATE TABLE IF NOT EXISTS miner_logs (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    collected_at  TEXT    NOT NULL,
                    miner_id      TEXT    NOT NULL,
                    model         TEXT,
                    health_status TEXT,
                    log_file      TEXT    NOT NULL,
                    content       TEXT    NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_logs_miner
                    ON miner_logs(miner_id, collected_at);
            """)

        logger.info("Database ready at %s", self.db_path)

    def save_pending_approvals(self, thread_ts: str, scan_id: int,
                               issues: List[Dict]) -> None:
        """Save actionable issues as pending approvals linked to a Slack thread.

        Rules:
          - Only RESTART / PDU_CYCLE / RESTART_CHECK_BOARDS ever need approval
          - Known dead boards are skipped (need physical inspection)
          - One pending approval per miner — if one already exists, update it
            so the thread_ts and problem stay current without creating duplicates
        """
        now  = datetime.now().isoformat()
        with self._connect('pending_approvals') as conn:
            for i in issues:
                if i["action"] not in ("PDU_CYCLE", "RESTART", "RESTART_CHECK_BOARDS", "POWER_PROFILE_UP", "PREEMPTIVE_RESTART", "ECO_MODE", "MONITOR_CLOSE"):
                    continue
                if self.has_known_dead_boards(str(i["id"])):
                    logger.info("Skipping pending approval for miner %s (%s) — known dead boards",
                                i["id"], i.get("ip"))
                    continue

                problem = " | ".join(i.get("issues", []))

                # Check if a PENDING approval already exists for this miner
                existing = conn.execute(
                    "SELECT id FROM pending_approvals "
                    "WHERE miner_id=? AND status='PENDING' LIMIT 1",
                    (str(i["id"]),)
                ).fetchone()

                if existing:
                    # Update existing row — keep it current without spamming new rows
                    conn.execute("""
                        UPDATE pending_approvals
                        SET thread_ts=?, scan_id=?, action_type=?,
                            problem=?, pdu_id=?, outlet=?, created_at=?
                        WHERE id=?
                    """, (thread_ts, scan_id, i["action"],
                          problem, i.get("pdu_id"), i.get("outlet"),
                          now, existing["id"]))
                    logger.debug("Updated existing pending approval for miner %s", i["id"])
                else:
                    # New pending approval
                    # DG-1 FIX
                    try:
                        from ai.confidence_scorer import get_confidence, get_gate
                        conf_score, _ = get_confidence(str(i["id"]), i["ip"], i["action"], hashrate_pct=i.get("hashrate_pct"))
                        conf_gate = get_gate(conf_score)
                        if conf_gate == "HOLD":
                            logger.warning("HOLD conf %d%% for %s - suppressed", conf_score, i["ip"])
                            continue
                    except Exception:
                        conf_score, conf_gate = 50, "ASK"

                    conn.execute("""
                        INSERT INTO pending_approvals
                        (created_at, scan_id, thread_ts, miner_id, ip, model,
                         action_type, problem, pdu_id, outlet, confidence_score, confidence_gate)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (now, scan_id, thread_ts,
                          i["id"], i["ip"], i["model"],
                          i["action"], problem,
                          i.get("pdu_id"), i.get("outlet"),
                          conf_score, conf_gate))
                    logger.info("New pending approval for miner %s (%s) → %s",
                                i["id"], i["ip"], i["action"])

    def expire_old_pending_approvals(self, max_age_minutes: int = 30) -> int:
        """Auto-deny pending approvals older than max_age_minutes.

        Called at the start of each scan cycle. If you didn't respond in
        30 minutes, the approval is auto-denied and cleared from the queue.
        This prevents the queue from growing unboundedly across scans.
        """
        cutoff = (datetime.now() - timedelta(minutes=max_age_minutes)).isoformat()
        # First block: read + update pending_approvals (operational.db).
        with self._connect('pending_approvals') as conn:
            expired = conn.execute(
                "SELECT id, miner_id, ip, action_type FROM pending_approvals "
                "WHERE status='PENDING' AND created_at < ?",
                (cutoff,)
            ).fetchall()

            if expired:
                conn.execute("""
                    UPDATE pending_approvals
                    SET status='DENIED', responded_at=?
                    WHERE status='PENDING' AND created_at < ?
                """, (datetime.now().isoformat(), cutoff))

        # Second block: write one audit-log row per expiry (audit.db).
        # Separate connection because action_audit_log lives in audit.db
        # while pending_approvals lives in operational.db — SQLite cannot
        # span two databases on one connection. Note: the UPDATE above has
        # already committed by the time we get here, so if this audit
        # write fails the denials remain in place with no audit entry.
        # That is an acceptable tradeoff of the split-DB architecture.
        if expired:
            with self._connect('action_audit_log') as conn:
                for row in expired:
                    conn.execute("""
                        INSERT INTO action_audit_log
                        (timestamp, date, miner_id, ip, model, problem,
                         action_taken, decision, approved_by, notes)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                    """, (datetime.now().isoformat(),
                          datetime.now().strftime("%Y-%m-%d"),
                          row["miner_id"], row["ip"], "", "",
                          row["action_type"], "DENIED",
                          "Mining Guardian (Auto-Expired)",
                          f"No response within {max_age_minutes} minutes — auto-denied"))

            logger.info("Auto-expired %d pending approvals older than %d min",
                        len(expired), max_age_minutes)
        return len(expired) if expired else 0

    def log_action(self, miner_id: str, ip: str, model: str,
                   problem: str, action_taken: str, decision: str,
                   approved_by: str = None, slack_user_id: str = None,
                   scan_id: int = None, notes: str = None) -> None:
        """Log every approval or denial to the permanent action audit log.

        Never expires. Grouped by date for easy review.
        approved_by should be the Slack display name of the person who responded.
        decision should be 'APPROVED' or 'DENIED'.
        """
        now  = datetime.now()
        with self._connect('action_audit_log') as conn:
            conn.execute(
                "INSERT INTO action_audit_log "
                "(timestamp, date, scan_id, miner_id, ip, model, "
                " problem, action_taken, decision, approved_by, "
                " slack_user_id, notes) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (now.isoformat(), now.strftime("%Y-%m-%d"), scan_id,
                 miner_id, ip, model, problem, action_taken,
                 decision, approved_by, slack_user_id, notes)
            )
        logger.info("Audit log: %s %s on %s (%s) by %s",
                    decision, action_taken, ip, model, approved_by or "unknown")

    def get_audit_log(self, days: int = None, miner_id: str = None,
                      limit: int = 100) -> List[Dict]:
        """Retrieve audit log entries, optionally filtered by date range or miner."""
        query  = "SELECT * FROM action_audit_log WHERE 1=1"
        params = []
        if days:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            query += " AND date >= ?"
            params.append(cutoff)
        if miner_id:
            query += " AND miner_id = ?"
            params.append(miner_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with self._connect('action_audit_log') as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def save_notifications(self, notifications: List[Dict]) -> None:
        """Store AMS notifications in the database."""
        if not notifications:
            return
        now = datetime.now().isoformat()
        rows = []
        for n in notifications:
            params = n.get("params", {})
            rows.append((
                now,
                n.get("id"),
                str(n.get("deviceID", "")),
                n.get("type"),
                n.get("key"),
                params.get("alertLevel"),
                params.get("minerIp"),
                json.dumps(n),
            ))
        with self._connect('ams_notifications') as conn:
            conn.executemany(
                "INSERT INTO ams_notifications "
                "(recorded_at, notification_id, device_id, type, key, "
                " alert_level, miner_ip, raw) VALUES (?,?,?,?,?,?,?,?)",
                rows
            )
        logger.info("Saved %s AMS notifications", len(rows))

    def save_weather(self, weather: Dict[str, Any]) -> None:
        """Store a weather reading alongside scan data."""
        now = datetime.now().isoformat()
        with self._connect('weather_readings') as conn:
            conn.execute(
                "INSERT INTO weather_readings "
                "(recorded_at, temp_f, humidity_pct, feels_like_f, "
                " temp_high_f, temp_low_f, humidity_max, humidity_min) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (now,
                 weather.get("temp_f"),
                 weather.get("humidity_pct"),
                 weather.get("feels_like_f"),
                 weather.get("temp_high_f"),
                 weather.get("temp_low_f"),
                 weather.get("humidity_max"),
                 weather.get("humidity_min"))
            )

    def save_hvac(self, hvac) -> None:
        """Store an HVAC snapshot alongside scan data."""
        if hvac is None:
            return
        now = datetime.now().isoformat()
        with self._connect('hvac_readings') as conn:
            conn.execute(
                "INSERT INTO hvac_readings "
                "(recorded_at, supply_temp_f, return_temp_f, delta_t_f, "
                " diff_pressure, spray_pump_on, cwp1_vfd_pct, cwp2_vfd_pct, "
                " ct1_vfd_pct, ct2_vfd_pct, leak_alarm, ct1_fault, ct2_fault, pump_fault) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (now,
                 hvac.supply_temp_f,
                 hvac.return_temp_f,
                 hvac.delta_t_f,
                 hvac.diff_pressure_psi,
                 1 if hvac.spray_pump_on else 0,
                 hvac.cwp1_vfd_pct,
                 hvac.cwp2_vfd_pct,
                 hvac.ct1_vfd_pct,
                 hvac.ct2_vfd_pct,
                 1 if hvac.leak_alarm else 0,
                 1 if hvac.ct1_fault else 0,
                 1 if hvac.ct2_fault else 0,
                 1 if hvac.pump_fault else 0)
            )

    # ── Auto-discovery ───────────────────────────────────────────

    def load_known_models(self, catalog_path: str) -> set:
        """Load known model names from the Intelligence Catalog JSON.

        Returns a set of normalized device names for fast lookup.
        Normalization: lowercase, strip spaces/hyphens, keep plus signs
        and trailing 's' variants as distinct (m63 != m63s != m63+ != m63s+).
        """
        known = set()
        try:
            with open(catalog_path, "r") as f:
                catalog = json.load(f)
            for key, entry in catalog.items():
                # Add the slug key itself (e.g. "antminer-s21-pro")
                known.add(self._normalize_model_name(key))
                # Add the display_name (e.g. "Antminer S21 Pro (234 TH)")
                display = entry.get("display_name", "")
                if display:
                    # Strip hashrate/parenthetical from display_name
                    base = display.split("(")[0].strip()
                    known.add(self._normalize_model_name(base))
            logger.info("Loaded %d known models from Intelligence Catalog", len(known))
        except FileNotFoundError:
            logger.warning("Intelligence Catalog not found: %s — discovery will flag all models", catalog_path)
        except Exception as e:
            logger.error("Failed to load Intelligence Catalog: %s", e)
        return known

    @staticmethod
    def _normalize_model_name(name: str) -> str:
        """Normalize a model name for comparison.

        Lowercase, strip manufacturer prefixes, remove spaces and hyphens.
        Preserves plus signs and 's' suffixes so m63/m63s/m63+/m63s+ stay distinct.
        """
        n = name.lower().strip()
        # Remove known manufacturer prefixes
        for prefix in ("antminer", "whatsminer", "avalon", "canaan", "bitmain",
                        "microbt", "innosilicon", "ebang", "strongu", "goldshell",
                        "iceriver", "jasminer", "bombax", "bixbit"):
            if n.startswith(prefix):
                n = n[len(prefix):]
        # Strip spaces and hyphens (but keep + for plus variants)
        n = n.replace(" ", "").replace("-", "").replace("_", "")
        return n

    def load_known_firmware(self) -> set:
        """Load known firmware versions from discovery_log.

        Returns a set of firmware version strings already seen.
        """
        known = set()
        try:
            with self._connect('discovery_log') as conn:
                rows = conn.execute(
                    "SELECT DISTINCT firmware_version FROM discovery_log "
                    "WHERE discovery_type = 'new_firmware' AND firmware_version IS NOT NULL"
                ).fetchall()
                for row in rows:
                    known.add(row["firmware_version"])
            # Also load firmware from existing miner_readings to bootstrap.
            # Separate connection because miner_readings lives in timeseries.db
            # while discovery_log lives in operational.db — SQLite cannot span
            # two databases on one connection.
            with self._connect('miner_readings') as conn:
                rows2 = conn.execute(
                    "SELECT DISTINCT firmware_version FROM miner_readings "
                    "WHERE firmware_version IS NOT NULL AND firmware_version != ''"
                ).fetchall()
                for row in rows2:
                    known.add(row["firmware_version"])
        except Exception as e:
            logger.warning("Failed to load known firmware: %s", e)
        return known

    def save_discovery(self, discovery_type: str, miner_data: Dict,
                       normalized_name: str, device_name: str) -> None:
        """Insert or update a discovery_log entry.

        If an entry with the same discovery_type + normalized_name already exists,
        update last_seen and raw_data. Otherwise, insert a new row.
        """
        now = datetime.now().isoformat()
        raw_json = json.dumps(miner_data, default=str)
        chains = miner_data.get("chains") or []
        board_count = len(chains)
        chip_count = chains[0].get("chips", 0) if chains else None

        with self._connect('discovery_log') as conn:
            if discovery_type == "new_model":
                existing = conn.execute(
                    "SELECT id FROM discovery_log "
                    "WHERE discovery_type = 'new_model' AND normalized_name = ?",
                    (normalized_name,)
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT id FROM discovery_log "
                    "WHERE discovery_type = 'new_firmware' AND firmware_version = ? AND normalized_name = ?",
                    (miner_data.get("firmwareVersion", ""), normalized_name)
                ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE discovery_log SET last_seen = ?, raw_data = ?, "
                    "hashrate = ?, temp_chip = ?, consumption = ?, board_count = ? "
                    "WHERE id = ?",
                    (now, raw_json,
                     miner_data.get("hashrate") or 0,
                     miner_data.get("tempChip") or 0,
                     miner_data.get("consumption") or 0,
                     board_count,
                     existing["id"])
                )
            else:
                conn.execute(
                    "INSERT INTO discovery_log "
                    "(discovery_type, device_name, normalized_name, firmware_version, "
                    " miner_id, ip, hashrate, temp_chip, consumption, board_count, "
                    " chip_count, raw_data, first_seen, last_seen) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (discovery_type,
                     device_name,
                     normalized_name,
                     miner_data.get("firmwareVersion"),
                     str(miner_data.get("id", "")),
                     miner_data.get("ip"),
                     miner_data.get("hashrate") or 0,
                     miner_data.get("tempChip") or 0,
                     miner_data.get("consumption") or 0,
                     board_count,
                     chip_count,
                     raw_json,
                     now, now)
                )

    def get_discoveries(self, acknowledged: Optional[int] = None) -> List[Dict]:
        """Return discovery_log entries, optionally filtered by acknowledged status."""
        with self._connect('discovery_log') as conn:
            if acknowledged is not None:
                rows = conn.execute(
                    "SELECT * FROM discovery_log WHERE acknowledged = ? "
                    "ORDER BY last_seen DESC", (acknowledged,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM discovery_log ORDER BY last_seen DESC"
                ).fetchall()
            return [dict(r) for r in rows]

    def acknowledge_discovery(self, discovery_id: int, level: int = 1,
                              notes: Optional[str] = None) -> bool:
        """Mark a discovery as reviewed (1) or added-to-catalog (2).

        Returns True if a row was updated, False if id not found.
        """
        with self._connect('discovery_log') as conn:
            params = [level, discovery_id]
            sql = "UPDATE discovery_log SET acknowledged = ?"
            if notes is not None:
                sql += ", notes = ?"
                params = [level, notes, discovery_id]
            sql += " WHERE id = ?"
            updated = conn.execute(sql, params).rowcount
            return updated > 0

    def save_scan(self, miners: List[Dict], issues: List[Dict]) -> int:
        """Write scan summary and all miner readings. Returns scan_id."""
        now      = datetime.now().isoformat()
        online   = sum(1 for m in miners if m.get("status") == "online")
        offline  = len(miners) - online

        # First block: write the scan header row (scans table, operational.db).
        with self._connect('scans') as conn:
            cur = conn.execute(
                "INSERT INTO scans (scanned_at, total_miners, online, offline, issues) "
                "VALUES (?, ?, ?, ?, ?)",
                (now, len(miners), online, offline, len(issues))
            )
            scan_id = cur.lastrowid

        # Second block: build per-miner rows and bulk-insert into miner_readings
        # (timeseries.db). Uses a separate connection because miner_readings lives
        # in a different split DB than scans. The firmware-fallback SELECT inside
        # the loop also reads from miner_readings, so it belongs on this
        # connection, not on the scans-block connection.
        # Tradeoff: the scans INSERT has already committed when this block runs.
        # If this block crashes, we'd have a scans row with no miner_readings.
        # Acceptable — the scan header is a durable record of "a scan happened";
        # a retry can re-populate miner_readings from AMS if needed.
        with self._connect('miner_readings') as conn:
            # Build a quick lookup of issues by miner id
            issue_map = {i["id"]: i for i in issues}

            rows = []
            for m in miners:
                miner_id  = str(m.get("id", ""))
                max_hr    = m.get("maxHashrate") or 0
                hashrate  = m.get("hashrate") or 0
                # Use BiXBiT profile parser for accurate rated TH/s, fall back to AMS maxHashrate
                _profile_str = m.get("currentProfile", "") or ""
                _profile_rated = parse_bixbit_profile(_profile_str)
                if _profile_rated:
                    # Profile gives us TH/s, hashrate from AMS is MH/s
                    pct = round((hashrate / 1000.0 / _profile_rated) * 100, 1) if _profile_rated > 0 else 0.0
                elif max_hr > 0:
                    pct = round((hashrate / max_hr) * 100, 1)
                else:
                    pct = 0.0
                temp_raw  = m.get("tempChip") or 0
                temp      = temp_raw if temp_raw >= 0 else None
                temp_board = m.get("tempBoard") or 0
                pdu_power  = (m.get("pduOutlet") or {}).get("power") or 0
                map_loc   = (m.get("mapLocation") or {}).get("title") or None
                err_codes = str(m.get("errorCodes") or []) if m.get("errorCodes") else None
                issue     = issue_map.get(miner_id)

                # Firmware fallback: if AMS returns empty firmware, use last known value
                fw_mfr = m.get("firmwareManufacturer") or ""
                fw_ver = m.get("firmwareVersion") or ""
                if not fw_mfr and miner_id:
                    try:
                        _fw_row = conn.execute(
                            "SELECT firmware_manufacturer, firmware_version FROM miner_readings "
                            "WHERE miner_id = ? AND firmware_manufacturer != '' "
                            "AND firmware_manufacturer IS NOT NULL "
                            "ORDER BY id DESC LIMIT 1", (miner_id,)
                        ).fetchone()
                        if _fw_row:
                            fw_mfr = _fw_row["firmware_manufacturer"] or ""
                            fw_ver = _fw_row["firmware_version"] or ""
                    except Exception:
                        pass  # Keep empty if lookup fails

                # Use 'name' when profile confirms BiXBiT firmware and shortModel is wrong
                raw_model = m.get("shortModel", m.get("name", "unknown"))
                profile_str = m.get("currentProfile", "")
                if "TH/s" in profile_str and m.get("name") and m.get("name") != raw_model:
                    raw_model = m["name"]
                rows.append((
                    scan_id,
                    now,
                    miner_id,
                    m.get("ip"),
                    m.get("mac"),
                    raw_model,
                    m.get("status"),
                    hashrate,
                    max_hr,
                    pct,
                    temp,
                    temp_board if temp_board >= 0 else None,
                    m.get("coolingMode"),
                    m.get("currentProfile"),
                    fw_mfr,
                    fw_ver,
                    m.get("uptime"),
                    m.get("consumption") or 0,
                    m.get("maxConsumption") or 0,
                    round(pdu_power / 1000, 2) if pdu_power else 0,
                    map_loc,
                    err_codes,
                    " | ".join(issue["issues"]) if issue else None,
                    issue["action"] if issue else None,
                    issue.get("pdu_id") if issue else None,
                    issue.get("outlet") if issue else None,
                ))

            conn.executemany(
                "INSERT INTO miner_readings "
                "(scan_id, scanned_at, miner_id, ip, mac, model, status, hashrate, "
                " max_hashrate, hashrate_pct, temp_chip, temp_board, cooling_mode, "
                " current_profile, firmware_manufacturer, firmware_version, uptime, "
                " consumption, max_consumption, pdu_power, map_location, error_codes, "
                " issue, action, pdu_id, outlet) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows
            )

        logger.info("Scan #%s saved to database (%s miners)", scan_id, len(miners))
        return scan_id

    def save_logs(self, miner_id: str, model: str, health_status: str,
                  log_files: Dict[str, str]) -> None:
        """Store extracted log file contents and parse all structured data from miner.log.

        Deduplicates by (miner_id, log_file) — same file is never stored twice.
        Hardware identity is parsed and upserted permanently.
        Per-chip hashrate, PSU voltage, system health parsed into structured tables.
        """
        now = datetime.now().isoformat()
        saved = 0
        with self._connect('miner_logs') as conn:
            for filename, content in log_files.items():
                # Dedup check — skip if this exact file was already stored
                # under the SAME health_status label. The same physical log file
                # may legitimately be stored under multiple labels (e.g. once as
                # 'healthy' from a routine scan and again as 'pre-restart' when
                # the operator approves a restart action) — those are distinct
                # observations of the system state and both have value.
                # Bug fix (Apr 8 2026): previously dedup was on (miner_id,
                # log_file) only, which silently dropped pre/post-restart saves
                # of files already captured under 'healthy'.
                existing = conn.execute(
                    "SELECT id FROM miner_logs WHERE miner_id=? AND log_file=? AND health_status=?",
                    (miner_id, filename, health_status)
                ).fetchone()
                if existing:
                    logger.debug("[%s] Log already stored under %s: %s — skipping",
                                 miner_id, health_status, filename)
                    continue
                conn.execute(
                    "INSERT INTO miner_logs "
                    "(collected_at, miner_id, model, health_status, log_file, content) "
                    "VALUES (?,?,?,?,?,?)",
                    (now, miner_id, model, health_status, filename, content)
                )
                saved += 1

        if saved:
            logger.info("Saved %s new log files for miner %s (%s)", saved, miner_id, health_status)

        # Parse hardware identity and structured data from miner.log automatically
        for filename, content in log_files.items():
            if "miner.log" in filename and content:
                try:
                    # miner_readings lives in timeseries.db, not audit.db where
                    # miner_logs lives — open a connection to the right split DB
                    # so this lookup doesn't crash under an active router.
                    with self._connect('miner_readings') as conn:
                        row = conn.execute(
                            "SELECT ip, mac FROM miner_readings WHERE miner_id=? ORDER BY id DESC LIMIT 1",
                            (miner_id,)
                        ).fetchone()
                    ip  = row["ip"] if row else ""
                    mac = row["mac"] if row else ""
                    # Hardware identity — parse once, upsert permanently
                    self.parse_and_save_hardware(miner_id, ip, mac, content, filename)
                    # Parse per-chip data and other structured log data
                    self.parse_log_metrics(miner_id, ip, content, filename)
                except Exception as e:
                    logger.warning("[%s] Log parse failed: %s", miner_id, e)

    def purge_old_logs(self, days: int = 7) -> int:
        """Delete miner log entries older than N days. Returns count deleted.

        Only purges the miner_logs table (raw log content).
        Scan history and miner_readings are kept permanently for trending.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._connect('miner_logs') as conn:
            cur = conn.execute(
                "DELETE FROM miner_logs WHERE collected_at < ?", (cutoff,)
            )
            deleted = cur.rowcount
        if deleted:
            logger.info("Purged %s log entries older than %s days", deleted, days)
        return deleted

    def has_known_dead_boards(self, miner_id: str) -> bool:
        """Check if this miner has unresolved known dead boards (already attempted restart)."""
        with self._connect('known_dead_boards') as conn:
            row = conn.execute(
                "SELECT id FROM known_dead_boards WHERE miner_id = ? AND resolved_at IS NULL AND restart_attempted IS NOT NULL",
                (miner_id,)
            ).fetchone()
            return row is not None

    def register_dead_boards(self, miner_id: str, ip: str, model: str,
                             board_indices: list, restart_result: str = None):
        """Register or update known dead boards for a miner.
        Sets ticket_created=None so the next scan knows to create an AMS ticket.
        """
        now = datetime.now().isoformat()
        with self._connect('known_dead_boards') as conn:
            existing = conn.execute(
                "SELECT id FROM known_dead_boards WHERE miner_id = ? AND resolved_at IS NULL",
                (miner_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE known_dead_boards SET board_indices=?, restart_attempted=?, restart_result=? WHERE id=?",
                    (str(board_indices), now, restart_result, existing[0])
                )
            else:
                conn.execute(
                    "INSERT INTO known_dead_boards "
                    "(miner_id, ip, model, board_indices, first_seen, restart_attempted, restart_result, ticket_created) "
                    "VALUES (?,?,?,?,?,?,?,NULL)",
                    (miner_id, ip, model, str(board_indices), now,
                     now if restart_result else None, restart_result)
                )
        logger.info("[%s] Registered known dead boards %s — result: %s", miner_id, board_indices, restart_result)

    def needs_ticket(self, miner_id: str) -> Optional[dict]:
        """Return dead board record if it needs an AMS ticket created (ticket_created IS NULL)."""
        with self._connect('known_dead_boards') as conn:
            row = conn.execute(
                "SELECT miner_id, ip, model, board_indices, first_seen, restart_result "
                "FROM known_dead_boards "
                "WHERE miner_id=? AND resolved_at IS NULL AND ticket_created IS NULL "
                "AND restart_attempted IS NOT NULL",
                (miner_id,)
            ).fetchone()
        return dict(row) if row else None

    def mark_ticket_created(self, miner_id: str, ticket_id: str = None) -> None:
        """Record that an AMS ticket has been created for this dead board miner."""
        now = datetime.now().isoformat()
        with self._connect('known_dead_boards') as conn:
            conn.execute(
                "UPDATE known_dead_boards SET ticket_created=? "
                "WHERE miner_id=? AND resolved_at IS NULL",
                (ticket_id or now, miner_id)
            )
        conn.commit() if hasattr(conn, 'commit') else None
        logger.info("[%s] AMS ticket recorded: %s", miner_id, ticket_id or now)

    def get_newly_ticketed(self) -> list:
        """Return dead board miners whose ticket was created but not yet noticed in Slack.

        Bug fix: ticket_created stores the ticket ID string (e.g. '2661'), not a
        timestamp — comparing it against a datetime cutoff always matched because
        '2661' > '2026-...' alphabetically, so the notice showed every scan forever.
        Now we track ticket_noticed_at separately. Only rows where ticket_noticed_at
        IS NULL are returned — marking them noticed happens immediately after posting.
        """
        with self._connect('known_dead_boards') as conn:
            rows = conn.execute(
                "SELECT miner_id, ip, model, board_indices, ticket_created "
                "FROM known_dead_boards "
                "WHERE resolved_at IS NULL AND ticket_created IS NOT NULL "
                "AND ticket_noticed_at IS NULL"
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_ticket_noticed(self, miner_ids: list) -> None:
        """Mark tickets as noticed in Slack — won't appear in future reports."""
        if not miner_ids:
            return
        now = datetime.now().isoformat()
        with self._connect('known_dead_boards') as conn:
            for miner_id in miner_ids:
                conn.execute(
                    "UPDATE known_dead_boards SET ticket_noticed_at=? "
                    "WHERE miner_id=? AND resolved_at IS NULL",
                    (now, miner_id)
                )

    def resolve_dead_boards(self, miner_id: str):
        """Mark dead boards as resolved (boards recovered after restart or repair)."""
        now = datetime.now().isoformat()
        with self._connect('known_dead_boards') as conn:
            conn.execute(
                "UPDATE known_dead_boards SET resolved_at = ? WHERE miner_id = ? AND resolved_at IS NULL",
                (now, miner_id)
            )

    def save_chain_readings(self, scan_id: int, scanned_at: str, miners: List[Dict]) -> None:
        """Store per-board chain data every scan: rate, voltage, freq, consumption, HW errors, temps."""
        rows = []
        for m in miners:
            miner_id = str(m.get("id", ""))
            ip = m.get("ip", "")
            for chain in (m.get("chains", []) or []):
                rows.append((
                    scan_id, scanned_at, miner_id, ip,
                    chain.get("index", 0), chain.get("rate", 0),
                    chain.get("voltage"), chain.get("freq"),
                    chain.get("consumption"), chain.get("HWErrors", 0),
                    chain.get("tempBoard"), chain.get("tempChip"),
                ))
        if not rows:
            return
        with self._connect('chain_readings') as conn:
            conn.executemany("""
                INSERT INTO chain_readings
                (scan_id, scanned_at, miner_id, ip, board_index,
                 rate_mhs, voltage, freq_mhz, consumption_w,
                 hw_errors, temp_board, temp_chip)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, rows)

    def save_pool_readings(self, scan_id: int, scanned_at: str, miners: List[Dict]) -> None:
        """Store per-pool stats every scan: accepted/rejected shares, diff, pool status."""
        rows = []
        for m in miners:
            miner_id = str(m.get("id", ""))
            ip = m.get("ip", "")
            for pool in (m.get("pools", []) or []):
                rows.append((
                    scan_id, scanned_at, miner_id, ip,
                    pool.get("priority", 0), pool.get("url", ""),
                    pool.get("user", ""), pool.get("poolType", ""),
                    pool.get("status", ""),
                    int(pool.get("accepted", 0) or 0),
                    int(pool.get("rejected", 0) or 0),
                    float(pool.get("acceptedDiff", 0) or 0),
                    float(pool.get("rejectedDiff", 0) or 0),
                    pool.get("diff", ""),
                ))
        if not rows:
            return
        with self._connect('pool_readings') as conn:
            conn.executemany("""
                INSERT INTO pool_readings
                (scan_id, scanned_at, miner_id, ip, pool_priority,
                 pool_url, pool_user, pool_type, status,
                 accepted, rejected, accepted_diff, rejected_diff, difficulty)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, rows)

    def save_miner_state_readings(self, scan_id: int, scanned_at: str, miners: List[Dict]) -> None:
        """Store extended state fields from AMS miner list: hashrate tiers, limits, status codes."""
        rows = []
        for m in miners:
            rows.append((
                scan_id, scanned_at, str(m.get("id", "")), m.get("ip", ""),
                m.get("hashrateMedium"), m.get("hashrateLow"),
                m.get("maxHashrate"), m.get("maxConsumption"),
                m.get("maxTempBoard"), m.get("maxTempChip"),
                m.get("tempChipLow"), m.get("tempChipMedium"),
                m.get("minerStatus"), m.get("coolingMode"),
                m.get("workerVersion", ""), m.get("activePoolUser", ""),
            ))
        if not rows:
            return
        with self._connect('miner_state_readings') as conn:
            conn.executemany("""
                INSERT INTO miner_state_readings
                (scan_id, scanned_at, miner_id, ip,
                 hashrate_medium, hashrate_low, max_hashrate, max_consumption,
                 max_temp_board, max_temp_chip, temp_chip_low, temp_chip_medium,
                 miner_status, cooling_mode, worker_version, active_pool_user)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, rows)

    def save_ams_extended(self, scan_id: int, scanned_at: str, miners: List[Dict]) -> None:
        """Store AMS fields not captured elsewhere: timestamp, map coords, pdu counter, stratum URL."""
        rows = []
        for m in miners:
            map_loc = m.get("mapLocation") or {}
            pdu_out = m.get("pduOutlet") or {}
            # Get stratum URL from primary pool
            pools = m.get("pools") or []
            stratum_url = pools[0].get("stratumURL", "") if pools else ""
            rows.append((
                scan_id, scanned_at, str(m.get("id", "")), m.get("ip", ""),
                m.get("timestamp", ""),
                map_loc.get("id"),
                map_loc.get("x"),
                map_loc.get("y"),
                pdu_out.get("counter"),
                stratum_url,
                1 if m.get("favorite") else 0,
            ))
        if not rows:
            return
        with self._connect('miner_ams_extended') as conn:
            conn.executemany("""
                INSERT INTO miner_ams_extended
                (scan_id, scanned_at, miner_id, ip,
                 ams_timestamp, map_location_id, map_x, map_y,
                 pdu_counter, stratum_url, favorite)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, rows)

    def parse_and_save_hardware(self, miner_id: str, ip: str, mac: str,
                                 log_content: str, log_source: str) -> int:
        """Parse CGMiner/BixMiner miner.log and extract hardware identity.

        Extracts from EEPROM lines per board:
          board_name, serial_number, chip_die, chip_marking, chip_technology,
          pcb_version, bom_version, chip_bin, chip_ft_ver, ideal_hashrate

        Extracts from device detection lines:
          control_board, psu_version, bixminer_version, topol_machine,
          device_name, asic_count, bad_chips_count, pic_version

        Returns count of boards parsed.
        """
        import re
        now = datetime.now().isoformat()

        # Per-board EEPROM data
        eeprom_pattern = re.compile(
            r'Eeprom chain \[(\d+)\] '
            r'board_name: (\S+), '
            r'sn_oom: (\S+), '
            r'chip_die_oom: (\S+), '
            r'chip_marking_oom: (\S+), '
            r'chip_technology_oom: (\S+).*?'
            r'chip_bin (\S+).*?'
            r'chip_ft_ver (\S+).*?'
            r'pcb_version (\S+).*?'
            r'bom_version (\S+).*?'
            r'voltage \d+.*?'
            r'freq \d+.*?'
            r'ideal_hashrate (\d+)',
            re.MULTILINE
        )

        # Device-level fields
        control_board  = re.search(r'Control board: (\S+)', log_content)
        psu_version    = re.search(r'Detected psu version: (\S+)', log_content)
        bixminer_ver   = re.search(r'BixMiner ver: ([\S]+),', log_content)
        topol_machine  = re.search(r'Topol machine: (\S+)', log_content)
        device_name    = re.search(r'Device name: (.+)', log_content)

        ctrl_board_val  = control_board.group(1) if control_board else None
        psu_ver_val     = psu_version.group(1) if psu_version else None
        bixminer_val    = bixminer_ver.group(1) if bixminer_ver else None
        topol_val       = topol_machine.group(1) if topol_machine else None
        device_val      = device_name.group(1).strip() if device_name else None

        # Per-board asic counts
        asic_pattern = re.compile(r'Chain\[(\d+)\]: found (\d+) asic, bad chips (\d+)')
        asic_map = {}
        for match in asic_pattern.finditer(log_content):
            idx = int(match.group(1))
            asic_map[idx] = {"asic_count": int(match.group(2)), "bad_chips": int(match.group(3))}

        # PIC versions (one per board)
        pic_pattern = re.compile(r'Pic \[(\d+)\] version (\d+)')
        pic_map = {}
        for match in pic_pattern.finditer(log_content):
            pic_map[int(match.group(1))] = match.group(2)

        boards_parsed = 0
        with self._connect('miner_hardware') as conn:
            for match in eeprom_pattern.finditer(log_content):
                board_idx = int(match.group(1))
                asic_info = asic_map.get(board_idx, {})
                pic_ver   = pic_map.get(board_idx)

                conn.execute("""
                    INSERT INTO miner_hardware
                    (miner_id, ip, mac, board_index, board_name, serial_number,
                     chip_die, chip_marking, chip_technology,
                     pcb_version, bom_version, chip_bin, chip_ft_ver, ideal_hashrate,
                     control_board, psu_version, bixminer_version, topol_machine,
                     device_name, asic_count, bad_chips_count, pic_version,
                     first_seen, last_updated, log_source)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(miner_id, board_index) DO UPDATE SET
                        board_name=excluded.board_name,
                        serial_number=excluded.serial_number,
                        chip_die=excluded.chip_die,
                        chip_marking=excluded.chip_marking,
                        chip_technology=excluded.chip_technology,
                        pcb_version=excluded.pcb_version,
                        bom_version=excluded.bom_version,
                        chip_bin=excluded.chip_bin,
                        chip_ft_ver=excluded.chip_ft_ver,
                        ideal_hashrate=excluded.ideal_hashrate,
                        control_board=excluded.control_board,
                        psu_version=excluded.psu_version,
                        bixminer_version=excluded.bixminer_version,
                        topol_machine=excluded.topol_machine,
                        device_name=excluded.device_name,
                        asic_count=excluded.asic_count,
                        bad_chips_count=excluded.bad_chips_count,
                        pic_version=excluded.pic_version,
                        last_updated=excluded.last_updated,
                        log_source=excluded.log_source
                """, (
                    miner_id, ip, mac, board_idx,
                    match.group(2),   # board_name
                    match.group(3),   # serial_number
                    match.group(4),   # chip_die
                    match.group(5),   # chip_marking
                    match.group(6),   # chip_technology
                    match.group(9),   # pcb_version
                    match.group(10),  # bom_version
                    match.group(7),   # chip_bin
                    match.group(8),   # chip_ft_ver
                    int(match.group(11)),  # ideal_hashrate
                    ctrl_board_val, psu_ver_val, bixminer_val,
                    topol_val, device_val,
                    asic_info.get("asic_count"),
                    asic_info.get("bad_chips"),
                    pic_ver,
                    now, now, log_source
                ))
                boards_parsed += 1

        if boards_parsed:
            logger.info("[%s] Hardware identity parsed: %s boards from %s",
                        miner_id, boards_parsed, log_source)
        return boards_parsed

    def get_hardware_identity(self, miner_id: str) -> List[Dict]:
        """Return hardware identity records for a miner (one per board)."""
        with self._connect('miner_hardware') as conn:
            rows = conn.execute(
                "SELECT * FROM miner_hardware WHERE miner_id=? ORDER BY board_index",
                (miner_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def parse_log_metrics(self, miner_id: str, ip: str,
                          log_content: str, log_source: str) -> None:
        """Parse structured metrics from miner.log that aren't available via AMS.

        Extracts and stores:
        1. Per-chip hashrate vs target (the [chip_idx  actual  target] lines)
           - 126 chips per miner, logged every ~30 seconds
           - Key for detecting individual failing chips before board dies
        2. PSU voltage and estimated power over time
        3. CPU/memory system health over time
        4. Chain attach/detach events with timestamps

        All data is stored in log_metrics table for trending and AI analysis.
        """
        import re

        now = datetime.now().isoformat()
        rows = []

        # Per-chip hashrate lines: [chip_idx  actual  target] format
        # Example: [  0  97.69 121.47][  1  98.62 121.47]...
        chip_line_pattern = re.compile(
            r'\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] INFO: '
            r'((?:\[\s*\d+\s+[\d.]+\s+[\d.]+\]\s*)+)'
        )

        # PSU voltage line: "Psu current voltage 14.70V, sample voltage 14.57V, power estimated 4632W"
        psu_pattern = re.compile(
            r'\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] INFO: '
            r'Psu current voltage ([\d.]+)V, sample voltage ([\d.]+)V, power estimated (\d+)W'
        )

        # System health: "Total cpu: 79.65%, miner cpu: 44.16%, free mem: 158 MB, miner mem: 30 MB"
        sys_pattern = re.compile(
            r'\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] INFO: '
            r'Total cpu: ([\d.]+)%, miner cpu: ([\d.]+)%, free mem: (\d+) MB, miner mem: (\d+) MB'
        )

        # Chain attach/detach events
        chain_event_pattern = re.compile(
            r'\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] '
            r'(INFO|WARN): Chain\[(\d+)\] (attached|detached)'
        )

        # Ensure log_metrics table exists
        with self._connect('log_metrics') as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS log_metrics (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    miner_id        TEXT    NOT NULL,
                    ip              TEXT,
                    log_timestamp   TEXT,
                    metric_type     TEXT    NOT NULL,
                    board_index     INTEGER,
                    chip_index      INTEGER,
                    value_1         REAL,
                    value_2         REAL,
                    value_3         REAL,
                    value_4         REAL,
                    text_value      TEXT,
                    log_source      TEXT,
                    recorded_at     TEXT    NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_log_metrics_miner
                    ON log_metrics(miner_id, log_timestamp)
            """)

        # Parse PSU readings
        psu_rows = []
        for m in psu_pattern.finditer(log_content):
            psu_rows.append((
                miner_id, ip, m.group(1), "psu_voltage",
                None, None,
                float(m.group(2)),   # current voltage
                float(m.group(3)),   # sample voltage
                float(m.group(4)),   # power watts
                None, None,
                log_source, now
            ))

        # Parse system health readings
        sys_rows = []
        for m in sys_pattern.finditer(log_content):
            sys_rows.append((
                miner_id, ip, m.group(1), "system_health",
                None, None,
                float(m.group(2)),   # total cpu %
                float(m.group(3)),   # miner cpu %
                float(m.group(4)),   # free mem MB
                float(m.group(5)),   # miner mem MB
                None,
                log_source, now
            ))

        # Parse chain events
        event_rows = []
        for m in chain_event_pattern.finditer(log_content):
            event_rows.append((
                miner_id, ip, m.group(1), "chain_event",
                int(m.group(3)), None,
                None, None, None, None,
                m.group(4),  # "attached" or "detached"
                log_source, now
            ))

        # Parse per-chip hashrate (sample every 10th occurrence to avoid DB explosion)
        # Full 5MB log has thousands of these — we sample to keep DB manageable
        chip_rows = []
        chip_line_count = 0
        chip_entry_pattern = re.compile(r'\[\s*(\d+)\s+([\d.]+)\s+([\d.]+)\]')

        for m in chip_line_pattern.finditer(log_content):
            chip_line_count += 1
            if chip_line_count % 10 != 0:  # sample every 10th timestamp
                continue
            timestamp = m.group(1)
            line_data = m.group(2)
            for chip_m in chip_entry_pattern.finditer(line_data):
                chip_rows.append((
                    miner_id, ip, timestamp, "chip_hashrate",
                    None, int(chip_m.group(1)),
                    float(chip_m.group(2)),   # actual TH/s
                    float(chip_m.group(3)),   # target TH/s
                    None, None, None,
                    log_source, now
                ))

        all_rows = psu_rows + sys_rows + event_rows + chip_rows
        if not all_rows:
            return

        with self._connect('log_metrics') as conn:
            conn.executemany("""
                INSERT INTO log_metrics
                (miner_id, ip, log_timestamp, metric_type,
                 board_index, chip_index,
                 value_1, value_2, value_3, value_4, text_value,
                 log_source, recorded_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, all_rows)

        logger.info("[%s] Log metrics parsed: %d PSU + %d sys + %d events + %d chip samples",
                    miner_id, len(psu_rows), len(sys_rows),
                    len(event_rows), len(chip_rows))

    def record_restart(self, miner_id: str, ip: str, model: str,
                       restart_type: str, elevated_hours: int = 3,
                       hashrate_before: float = None) -> None:
        """Record a restart event, set elevated monitoring window, and mark outcome as PENDING.
        hashrate_before captures the miner's hashrate_pct at time of restart so the
        outcome checker knows what 'before' looked like without a separate lookup.
        """
        now            = datetime.now()
        elevated_until = (now + timedelta(hours=elevated_hours)).isoformat()
        with self._connect('miner_restarts') as conn:
            conn.execute(
                "INSERT INTO miner_restarts "
                "(restarted_at, miner_id, ip, model, restart_type, elevated_until, "
                " outcome, hashrate_before) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (now.isoformat(), miner_id, ip, model, restart_type,
                 elevated_until, "PENDING", hashrate_before)
            )
        logger.info("Restart recorded for miner %s (%s) — elevated monitoring for %sh",
                    miner_id, restart_type, elevated_hours)

    def is_elevated_monitoring(self, miner_id: str) -> bool:
        """Return True if this miner is within its post-restart elevated monitoring window."""
        now = datetime.now().isoformat()
        with self._connect('miner_restarts') as conn:
            row = conn.execute(
                "SELECT elevated_until FROM miner_restarts "
                "WHERE miner_id=? AND elevated_until > ? "
                "ORDER BY id DESC LIMIT 1",
                (miner_id, now)
            ).fetchone()
        return row is not None

    def get_failed_restart_count(self, miner_id: str, days: int = 7) -> int:
        """Count restarts in the last N days where the miner did not recover."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._connect('miner_restarts') as conn:
            row = conn.execute("""
                SELECT COUNT(*) as cnt FROM miner_restarts
                WHERE miner_id=? AND restarted_at >= ?
            """, (miner_id, cutoff)).fetchone()
        return row["cnt"] if row else 0

    def count_outcome_failures(self, miner_id: str) -> int:
        """Count restarts labeled FAILURE by the outcome feedback loop (Feature 1)."""
        with self._connect('miner_restarts') as conn:
            row = conn.execute("""
                SELECT COUNT(*) as cnt FROM miner_restarts
                WHERE miner_id=? AND outcome='FAILURE'
            """, (miner_id,)).fetchone()
        return row["cnt"] if row else 0

    def _count_pdu_cycles(self, miner_id: str, days: int = 1) -> int:
        """Count PDU power cycles attempted for this miner in the last N days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._connect('action_audit_log') as conn:
            row = conn.execute("""
                SELECT COUNT(*) as cnt FROM action_audit_log
                WHERE miner_id=? AND action_taken='PDU_CYCLE'
                  AND timestamp >= ?
            """, (miner_id, cutoff)).fetchone()
        return row["cnt"] if row else 0

    def last_log_collected(self, miner_id: str) -> Optional[datetime]:
        """Return datetime of last log collection for this miner, or None."""
        with self._connect('miner_logs') as conn:
            row = conn.execute(
                "SELECT collected_at FROM miner_logs WHERE miner_id=? "
                "ORDER BY id DESC LIMIT 1",
                (miner_id,)
            ).fetchone()
        if row:
            try:
                return datetime.fromisoformat(row[0])
            except Exception:
                return None
        return None
