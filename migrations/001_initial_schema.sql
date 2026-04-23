-- Mining Guardian PostgreSQL Schema
-- Migration 001: Initial schema from SQLite
-- Created: 2026-04-21

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- For text search

-- ============================================
-- CORE TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS scans (
    id            SERIAL PRIMARY KEY,
    scanned_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    total_miners  INTEGER NOT NULL,
    online        INTEGER NOT NULL,
    offline       INTEGER NOT NULL,
    issues        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS miner_readings (
    id                    SERIAL PRIMARY KEY,
    scan_id               INTEGER NOT NULL REFERENCES scans(id),
    scanned_at            TIMESTAMP WITH TIME ZONE NOT NULL,
    miner_id              TEXT NOT NULL,
    ip                    TEXT,
    model                 TEXT,
    status                TEXT,
    hashrate              REAL,
    max_hashrate          REAL,
    hashrate_pct          REAL,
    temp_chip             REAL,
    issue                 TEXT,
    action                TEXT,
    pdu_id                INTEGER,
    outlet                INTEGER,
    mac                   TEXT,
    temp_board            REAL,
    cooling_mode          INTEGER,
    current_profile       TEXT,
    firmware_manufacturer TEXT,
    firmware_version      TEXT,
    uptime                TEXT,
    consumption           REAL,
    max_consumption       REAL,
    pdu_power             REAL,
    map_location          TEXT,
    error_codes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_readings_miner ON miner_readings(miner_id, scanned_at);
CREATE INDEX IF NOT EXISTS idx_mr_scanned_at ON miner_readings(scanned_at);

CREATE TABLE IF NOT EXISTS miner_logs (
    id            SERIAL PRIMARY KEY,
    collected_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    miner_id      TEXT NOT NULL,
    model         TEXT,
    health_status TEXT,
    log_file      TEXT NOT NULL,
    content       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_logs_miner ON miner_logs(miner_id, collected_at);

CREATE TABLE IF NOT EXISTS miner_restarts (
    id                  SERIAL PRIMARY KEY,
    restarted_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    miner_id            TEXT NOT NULL,
    ip                  TEXT,
    model               TEXT,
    restart_type        TEXT,
    elevated_until      TEXT,
    outcome             TEXT,
    outcome_checked_at  TEXT,
    hashrate_before     REAL,
    hashrate_after      REAL,
    recovery_time_scans INTEGER
);

CREATE INDEX IF NOT EXISTS idx_restarts_miner ON miner_restarts(miner_id, restarted_at);

CREATE TABLE IF NOT EXISTS weather_readings (
    id           SERIAL PRIMARY KEY,
    recorded_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    temp_f       REAL,
    humidity_pct REAL,
    feels_like_f REAL,
    temp_high_f  REAL,
    temp_low_f   REAL,
    humidity_max REAL,
    humidity_min REAL
);

CREATE TABLE IF NOT EXISTS ams_notifications (
    id              SERIAL PRIMARY KEY,
    recorded_at     TIMESTAMP WITH TIME ZONE NOT NULL,
    notification_id INTEGER,
    device_id       TEXT,
    type            TEXT,
    key             TEXT,
    alert_level     TEXT,
    miner_ip        TEXT,
    raw             TEXT
);

CREATE TABLE IF NOT EXISTS action_audit_log (
    id            SERIAL PRIMARY KEY,
    timestamp     TIMESTAMP WITH TIME ZONE NOT NULL,
    date          DATE NOT NULL,
    scan_id       INTEGER,
    miner_id      TEXT NOT NULL,
    ip            TEXT NOT NULL,
    model         TEXT,
    problem       TEXT NOT NULL,
    action_taken  TEXT NOT NULL,
    decision      TEXT NOT NULL,
    approved_by   TEXT,
    slack_user_id TEXT,
    notes         TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_date ON action_audit_log(date);
CREATE INDEX IF NOT EXISTS idx_audit_miner ON action_audit_log(miner_id);

CREATE TABLE IF NOT EXISTS pending_approvals (
    id               SERIAL PRIMARY KEY,
    created_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    scan_id          INTEGER,
    thread_ts        TEXT NOT NULL,
    miner_id         TEXT NOT NULL,
    ip               TEXT NOT NULL,
    model            TEXT,
    action_type      TEXT NOT NULL,
    problem          TEXT,
    pdu_id           INTEGER,
    outlet           INTEGER,
    status           TEXT DEFAULT 'PENDING',
    responded_at     TEXT,
    confidence_score INTEGER,
    confidence_gate  TEXT
);

CREATE INDEX IF NOT EXISTS idx_pending_thread ON pending_approvals(thread_ts, status);

CREATE TABLE IF NOT EXISTS miner_baselines (
    miner_id              TEXT PRIMARY KEY,
    ip                    TEXT,
    model                 TEXT,
    firmware              TEXT,
    learning_start        TIMESTAMP WITH TIME ZONE NOT NULL,
    learning_complete     INTEGER DEFAULT 0,
    baseline_hashrate_ths REAL,
    baseline_power_kw     REAL,
    samples_collected     INTEGER DEFAULT 0,
    hours_observed        REAL DEFAULT 0,
    locked_at             TEXT,
    last_updated          TEXT
);

CREATE TABLE IF NOT EXISTS hvac_readings (
    id              SERIAL PRIMARY KEY,
    recorded_at     TIMESTAMP WITH TIME ZONE NOT NULL,
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
    pump_fault      INTEGER DEFAULT 0,
    system_id       TEXT DEFAULT 'warehouse',
    outside_air_f   REAL,
    container_temp_f REAL
);

CREATE TABLE IF NOT EXISTS llm_analysis (
    id          SERIAL PRIMARY KEY,
    scan_id     INTEGER,
    analyzed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    miner_id    TEXT,
    ip          TEXT,
    prompt      TEXT,
    response    TEXT,
    model_used  TEXT,
    duration_ms INTEGER
);

CREATE TABLE IF NOT EXISTS known_dead_boards (
    id                SERIAL PRIMARY KEY,
    miner_id          TEXT NOT NULL,
    ip                TEXT,
    model             TEXT,
    board_indices     TEXT NOT NULL,
    first_seen        TIMESTAMP WITH TIME ZONE NOT NULL,
    restart_attempted TEXT,
    restart_result    TEXT,
    ticket_created    TEXT,
    resolved_at       TEXT,
    notes             TEXT,
    ticket_noticed_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_dead_boards_miner ON known_dead_boards(miner_id) WHERE resolved_at IS NULL;

-- ============================================
-- DETAILED READING TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS chain_readings (
    id            SERIAL PRIMARY KEY,
    scan_id       INTEGER NOT NULL REFERENCES scans(id),
    scanned_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    miner_id      TEXT NOT NULL,
    ip            TEXT,
    board_index   INTEGER NOT NULL,
    rate_mhs      REAL,
    voltage       REAL,
    freq_mhz      REAL,
    consumption_w REAL,
    hw_errors     INTEGER,
    temp_board    REAL,
    temp_chip     REAL
);

CREATE INDEX IF NOT EXISTS idx_chain_miner ON chain_readings(miner_id, scanned_at);
CREATE INDEX IF NOT EXISTS idx_cr_miner ON chain_readings(miner_id, board_index);

CREATE TABLE IF NOT EXISTS pool_readings (
    id            SERIAL PRIMARY KEY,
    scan_id       INTEGER NOT NULL REFERENCES scans(id),
    scanned_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    miner_id      TEXT NOT NULL,
    ip            TEXT,
    pool_priority INTEGER,
    pool_url      TEXT,
    pool_user     TEXT,
    pool_type     TEXT,
    status        TEXT,
    accepted      INTEGER,
    rejected      INTEGER,
    accepted_diff REAL,
    rejected_diff REAL,
    difficulty    TEXT
);

CREATE INDEX IF NOT EXISTS idx_pool_miner ON pool_readings(miner_id, scanned_at);

CREATE TABLE IF NOT EXISTS chip_readings (
    id          SERIAL PRIMARY KEY,
    scan_id     INTEGER NOT NULL REFERENCES scans(id),
    scanned_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    miner_id    TEXT NOT NULL,
    ip          TEXT,
    board_index INTEGER NOT NULL,
    chip_index  INTEGER NOT NULL,
    freq_mhz    REAL,
    voltage_mv  REAL,
    temp_c      REAL,
    source      TEXT DEFAULT 'direct_api'
);

CREATE INDEX IF NOT EXISTS idx_chip_miner ON chip_readings(miner_id, scanned_at);

CREATE TABLE IF NOT EXISTS miner_state_readings (
    id               SERIAL PRIMARY KEY,
    scan_id          INTEGER NOT NULL REFERENCES scans(id),
    scanned_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    miner_id         TEXT NOT NULL,
    ip               TEXT,
    hashrate_medium  REAL,
    hashrate_low     REAL,
    max_hashrate     REAL,
    max_consumption  REAL,
    max_temp_board   REAL,
    max_temp_chip    REAL,
    temp_chip_low    REAL,
    temp_chip_medium REAL,
    miner_status     INTEGER,
    cooling_mode     INTEGER,
    worker_version   TEXT,
    active_pool_user TEXT
);

CREATE INDEX IF NOT EXISTS idx_state_miner ON miner_state_readings(miner_id, scanned_at);

CREATE TABLE IF NOT EXISTS miner_hardware (
    id               SERIAL PRIMARY KEY,
    miner_id         TEXT NOT NULL,
    ip               TEXT,
    mac              TEXT,
    board_index      INTEGER NOT NULL,
    board_name       TEXT,
    serial_number    TEXT,
    chip_die         TEXT,
    chip_marking     TEXT,
    chip_technology  TEXT,
    pcb_version      TEXT,
    bom_version      TEXT,
    chip_bin         TEXT,
    chip_ft_ver      TEXT,
    ideal_hashrate   INTEGER,
    control_board    TEXT,
    psu_version      TEXT,
    bixminer_version TEXT,
    topol_machine    TEXT,
    device_name      TEXT,
    asic_count       INTEGER,
    bad_chips_count  INTEGER,
    pic_version      TEXT,
    first_seen       TIMESTAMP WITH TIME ZONE NOT NULL,
    last_updated     TIMESTAMP WITH TIME ZONE NOT NULL,
    log_source       TEXT,
    UNIQUE(miner_id, board_index)
);

CREATE TABLE IF NOT EXISTS miner_ams_extended (
    id              SERIAL PRIMARY KEY,
    scan_id         INTEGER NOT NULL REFERENCES scans(id),
    scanned_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    miner_id        TEXT NOT NULL,
    ip              TEXT,
    ams_timestamp   TEXT,
    map_location_id INTEGER,
    map_x           REAL,
    map_y           REAL,
    pdu_counter     REAL,
    stratum_url     TEXT,
    favorite        INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_ams_ext_miner ON miner_ams_extended(miner_id, scanned_at);

CREATE TABLE IF NOT EXISTS log_metrics (
    id            SERIAL PRIMARY KEY,
    miner_id      TEXT NOT NULL,
    ip            TEXT,
    log_timestamp TEXT,
    metric_type   TEXT NOT NULL,
    board_index   INTEGER,
    chip_index    INTEGER,
    value_1       REAL,
    value_2       REAL,
    value_3       REAL,
    value_4       REAL,
    text_value    TEXT,
    log_source    TEXT,
    recorded_at   TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_log_metrics_miner ON log_metrics(miner_id, log_timestamp);
CREATE INDEX IF NOT EXISTS idx_lm_miner_type ON log_metrics(miner_id, metric_type);
CREATE INDEX IF NOT EXISTS idx_lm_recorded ON log_metrics(recorded_at);
CREATE INDEX IF NOT EXISTS idx_lm_type_miner ON log_metrics(metric_type, miner_id);

-- ============================================
-- ALERT LISTENER TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS alert_listener_seen (
    notification_id INTEGER PRIMARY KEY,
    key             TEXT,
    alert_level     TEXT,
    miner_id        TEXT,
    ip              TEXT,
    action_taken    TEXT,
    seen_at         TEXT,
    acted_at        TEXT,
    outcome         TEXT
);

CREATE INDEX IF NOT EXISTS idx_seen_miner ON alert_listener_seen(miner_id);

CREATE TABLE IF NOT EXISTS alert_listener_cooldown (
    miner_id       TEXT PRIMARY KEY,
    last_action    TEXT,
    last_action_at TEXT
);

-- ============================================
-- TRACKING TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS log_collection_failures (
    id                    SERIAL PRIMARY KEY,
    miner_id              TEXT NOT NULL,
    ip                    TEXT,
    model                 TEXT,
    failure_date          DATE NOT NULL,
    failure_reason        TEXT,
    consecutive_failures  INTEGER DEFAULT 1,
    last_successful_log   TEXT,
    created_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_log_failures_miner ON log_collection_failures(miner_id);
CREATE INDEX IF NOT EXISTS idx_log_failures_date ON log_collection_failures(failure_date);

CREATE TABLE IF NOT EXISTS s19jpro_overheat_tracking (
    id                   SERIAL PRIMARY KEY,
    miner_id             TEXT NOT NULL UNIQUE,
    ip                   TEXT,
    first_overheat_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    restart_attempted_at TEXT,
    log_before           TEXT,
    log_after            TEXT,
    restart_helped       INTEGER,  -- 1=yes, 0=no, NULL=pending
    marked_aging_at      TEXT,     -- when we gave up and marked as aging hardware
    notes                TEXT
);

CREATE TABLE IF NOT EXISTS discovery_log (
    id               SERIAL PRIMARY KEY,
    discovery_type   TEXT NOT NULL,
    device_name      TEXT,
    normalized_name  TEXT,
    firmware_version TEXT,
    miner_id         TEXT,
    ip               TEXT,
    hashrate         REAL,
    temp_chip        REAL,
    consumption      REAL,
    board_count      INTEGER,
    chip_count       INTEGER,
    raw_data         TEXT,
    first_seen       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    acknowledged     INTEGER DEFAULT 0,
    notes            TEXT
);

CREATE INDEX IF NOT EXISTS idx_discovery_type_name ON discovery_log(discovery_type, normalized_name);
CREATE INDEX IF NOT EXISTS idx_discovery_ack ON discovery_log(acknowledged);

-- ============================================
-- PARTITIONING (for large tables)
-- ============================================

-- For log_metrics (18M+ rows), we'll partition by recorded_at month
-- This is a template - actual partitioning will be done during migration
-- to avoid data loss

-- ============================================
-- COMMENTS
-- ============================================

COMMENT ON TABLE scans IS 'Each scan cycle of the fleet';
COMMENT ON TABLE miner_readings IS 'Per-miner metrics from each scan';
COMMENT ON TABLE chain_readings IS 'Per-hashboard metrics from each scan';
COMMENT ON TABLE log_metrics IS 'Parsed metrics from miner log files';
COMMENT ON TABLE action_audit_log IS 'Complete history of all remediation actions';
COMMENT ON TABLE hvac_readings IS 'HVAC system readings (warehouse + container)';

