-- =============================================================================
-- MINING INTELLIGENCE CATALOG — V2 ADDITIONS (Bobby's Gap Audit)
-- Adds every missing data point Bobby requested, plus fields discovered in the
-- Mining Guardian codebase that the intelligence catalog should capture.
-- =============================================================================
-- Run AFTER intelligence_catalog_schema.sql
-- =============================================================================

-- ============================================================================
-- GAP 1: PSU SERIAL NUMBERS
-- Bobby asked: "PSU serial numbers"
-- Existing: hardware.psu_models captures model specs — no serial tracking.
-- The intelligence catalog is a REFERENCE database, not operational. But Bobby
-- wants to know: "Which PSU serial number patterns are associated with failures?"
-- Solution: Add serial number pattern/format tracking to psu_models, and a
-- NEW TABLE for PSU serial batch intelligence.
-- ============================================================================

ALTER TABLE hardware.psu_models
    ADD COLUMN IF NOT EXISTS serial_number_format TEXT,
    -- Pattern: "PSU serial format: APWxxxx-yyyy-zz where xx=wattage, yyyy=batch, zz=revision"
    ADD COLUMN IF NOT EXISTS serial_prefix_pattern TEXT,
    -- Regex or prefix: "APW12" for APW12 series
    ADD COLUMN IF NOT EXISTS output_voltage_12v_nom NUMERIC(6,3),
    -- Nominal 12V rail output (e.g., 12.05V typical)
    ADD COLUMN IF NOT EXISTS output_voltage_12v_min NUMERIC(6,3),
    -- Minimum 12V rail under load
    ADD COLUMN IF NOT EXISTS output_voltage_12v_max NUMERIC(6,3),
    -- Maximum 12V rail output
    ADD COLUMN IF NOT EXISTS output_voltage_12v_ripple_mv NUMERIC(6,2),
    -- Ripple in mV (spec sheet value)
    ADD COLUMN IF NOT EXISTS output_current_a_max NUMERIC(8,3),
    -- Maximum output current in amps
    ADD COLUMN IF NOT EXISTS output_current_a_nom NUMERIC(8,3),
    -- Nominal/typical current draw
    ADD COLUMN IF NOT EXISTS standby_power_w NUMERIC(6,2),
    -- Standby power consumption
    ADD COLUMN IF NOT EXISTS inrush_current_a NUMERIC(8,3),
    -- Inrush current on power-on
    ADD COLUMN IF NOT EXISTS power_factor NUMERIC(4,3),
    -- Power factor rating (e.g., 0.99)
    ADD COLUMN IF NOT EXISTS protection_features JSONB NOT NULL DEFAULT '[]',
    -- ["OVP", "OCP", "OTP", "SCP", "UVP"] — over-voltage, over-current, etc.
    ADD COLUMN IF NOT EXISTS noise_db_typical NUMERIC(5,1),
    -- Typical noise level in dB(A)
    ADD COLUMN IF NOT EXISTS noise_db_max NUMERIC(5,1),
    -- Maximum noise level in dB(A) under full load
    ADD COLUMN IF NOT EXISTS operating_temp_min_c INTEGER,
    ADD COLUMN IF NOT EXISTS operating_temp_max_c INTEGER,
    ADD COLUMN IF NOT EXISTS original_cost_usd NUMERIC(10,2),
    -- MSRP/retail cost of the PSU alone
    ADD COLUMN IF NOT EXISTS years_in_production INTEGER,
    ADD COLUMN IF NOT EXISTS production_start_year INTEGER,
    ADD COLUMN IF NOT EXISTS production_end_year INTEGER,
    ADD COLUMN IF NOT EXISTS is_discontinued BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN hardware.psu_models.serial_number_format IS
'Describes the serial number encoding pattern. E.g., "APW12-xxxx-yyyy where xxxx=production batch, yyyy=sequential"';
COMMENT ON COLUMN hardware.psu_models.output_voltage_12v_nom IS
'Nominal 12V rail output voltage. Real-world PSU voltage Bobby measures across hashboards.';

-- PSU serial batch intelligence — tracks quality patterns by serial batch
CREATE TABLE IF NOT EXISTS hardware.psu_serial_batches (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    psu_model_id        UUID NOT NULL REFERENCES hardware.psu_models(id) ON DELETE CASCADE,
    batch_prefix        TEXT NOT NULL,           -- Serial number batch prefix e.g., "APW12-2023Q2"
    batch_description   TEXT,                    -- "Q2 2023 production run from Dongguan factory"
    production_date_est DATE,                    -- Estimated production date
    production_facility TEXT,                    -- Factory name/location if known
    -- Quality intelligence
    known_issues        JSONB NOT NULL DEFAULT '[]',
    -- [{"issue": "cap C44 premature failure", "severity": "high", "affected_pct": 5.2}]
    failure_rate_pct    NUMERIC(6,3),            -- Observed failure rate for this batch
    sample_size         INTEGER,                 -- How many units in sample
    quality_rating      TEXT,                    -- 'excellent', 'good', 'fair', 'poor', 'defective_batch'
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'low',
    verified_by_bobby   BOOLEAN NOT NULL DEFAULT FALSE,
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ,
    UNIQUE (psu_model_id, batch_prefix)
);

COMMENT ON TABLE hardware.psu_serial_batches IS
'Tracks quality intelligence per PSU serial number batch. If Bobby sees PSUs with serial
prefix APW12-2023Q2 failing at 3x the rate of APW12-2023Q4, that is captured here.
Links failure patterns to production batches for procurement decisions.';

CREATE INDEX idx_psu_batch_model ON hardware.psu_serial_batches(psu_model_id);
CREATE INDEX idx_psu_batch_prefix ON hardware.psu_serial_batches(batch_prefix);
CREATE INDEX idx_psu_batch_quality ON hardware.psu_serial_batches(quality_rating);
CREATE INDEX idx_psu_batch_issues ON hardware.psu_serial_batches USING GIN(known_issues);
CREATE INDEX idx_psu_batch_active ON hardware.psu_serial_batches(id) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_psu_batch_updated_at
    BEFORE UPDATE ON hardware.psu_serial_batches
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ============================================================================
-- GAP 2: CHIPS USED ON HASHBOARDS — "passports for certain models"
-- Bobby's repo tracks: chip_die, chip_marking, chip_technology, chip_bin,
-- chip_ft_ver, bad_chips_count, asic_count, pic_version
-- These are the "chip passport" fields from EEPROM data.
-- Existing: hardware.chips has model-level specs. Missing: per-board
-- chip identity fields that come from EEPROM.
-- Solution: Add chip passport fields to hardware.hashboards + NEW TABLE
-- for chip bin intelligence.
-- ============================================================================

ALTER TABLE hardware.hashboards
    ADD COLUMN IF NOT EXISTS chip_die_type TEXT,
    -- EEPROM chip_die field: e.g., "BM1362AA"
    ADD COLUMN IF NOT EXISTS chip_marking TEXT,
    -- EEPROM chip_marking field: e.g., "BM1362"
    ADD COLUMN IF NOT EXISTS chip_technology TEXT,
    -- EEPROM chip_technology field: manufacturing tech variant
    ADD COLUMN IF NOT EXISTS chip_ft_ver TEXT,
    -- EEPROM chip_ft_ver (final test version)
    ADD COLUMN IF NOT EXISTS pic_version TEXT,
    -- PIC microcontroller version on the hashboard
    ADD COLUMN IF NOT EXISTS typical_asic_count INTEGER,
    -- Standard number of ASICs per board (e.g., 126 for S19j Pro)
    ADD COLUMN IF NOT EXISTS typical_bad_chip_tolerance INTEGER DEFAULT 0,
    -- How many bad chips before the board is considered degraded
    ADD COLUMN IF NOT EXISTS ideal_hashrate_per_board_th NUMERIC(10,3),
    -- Reference ideal hashrate per board (from EEPROM ideal_hashrate)
    ADD COLUMN IF NOT EXISTS board_serial_format TEXT,
    -- Serial number encoding pattern: "CNXXX-YYYY-ZZZZ"
    ADD COLUMN IF NOT EXISTS board_serial_prefix_pattern TEXT,
    -- For batch identification from serial prefixes
    ADD COLUMN IF NOT EXISTS weight_g INTEGER,
    -- Weight of the hashboard in grams
    ADD COLUMN IF NOT EXISTS layer_count INTEGER,
    -- PCB layer count (4-layer, 6-layer, etc.)
    ADD COLUMN IF NOT EXISTS copper_weight_oz NUMERIC(4,2),
    -- Copper weight in oz/ft² (e.g., 2.0 oz for high-current boards)
    ADD COLUMN IF NOT EXISTS solder_type TEXT;
    -- 'leaded', 'lead_free', 'SAC305', etc.

COMMENT ON COLUMN hardware.hashboards.chip_die_type IS
'From EEPROM passport: chip_die field. E.g., "BM1362AA" — identifies exact die variant.';
COMMENT ON COLUMN hardware.hashboards.chip_ft_ver IS
'From EEPROM passport: chip final test version. Different ft_ver = different quality screening.';


-- Chip bin intelligence — performance data by chip bin designation
CREATE TABLE IF NOT EXISTS hardware.chip_bins (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chip_id             UUID NOT NULL REFERENCES hardware.chips(id) ON DELETE CASCADE,
    bin_designation     TEXT NOT NULL,            -- "O20", "O22", etc.
    -- Performance characteristics of this bin
    hashrate_per_chip_gh_min NUMERIC(10,4),
    hashrate_per_chip_gh_max NUMERIC(10,4),
    hashrate_per_chip_gh_avg NUMERIC(10,4),
    power_per_chip_mw_min NUMERIC(10,4),
    power_per_chip_mw_max NUMERIC(10,4),
    power_per_chip_mw_avg NUMERIC(10,4),
    efficiency_j_th_avg NUMERIC(8,4),
    -- Voltage/frequency characteristics
    optimal_voltage_mv  INTEGER,
    optimal_frequency_mhz INTEGER,
    max_stable_frequency_mhz INTEGER,
    -- Quality grade
    quality_grade       TEXT,                     -- 'premium', 'standard', 'economy', 'salvage'
    yield_pct           NUMERIC(6,3),            -- Approximate yield % for this bin
    -- Observed reliability
    failure_rate_pct    NUMERIC(6,3),            -- Observed failure rate for this bin
    avg_lifespan_hours  INTEGER,                 -- Estimated average lifespan
    -- Bobby's fleet data
    fleet_count         INTEGER,                 -- How many miners Bobby has with this bin
    fleet_avg_hashrate_pct NUMERIC(5,2),         -- Fleet average as % of nominal
    verified_by_bobby   BOOLEAN NOT NULL DEFAULT FALSE,
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'low',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ,
    UNIQUE (chip_id, bin_designation)
);

COMMENT ON TABLE hardware.chip_bins IS
'Quality grades within same chip model. Different bins = different performance tiers.
Bobby tracks chip_bin in operational data (miner_hardware table) and uses it for
cohort analysis. This table stores the reference intelligence per bin designation.
E.g., "O20 bins of BM1362 average 94.2% of nominal hashrate, 2.1% failure rate."';

CREATE INDEX idx_chip_bins_chip ON hardware.chip_bins(chip_id);
CREATE INDEX idx_chip_bins_grade ON hardware.chip_bins(quality_grade);
CREATE INDEX idx_chip_bins_bobby ON hardware.chip_bins(verified_by_bobby) WHERE verified_by_bobby = TRUE;
CREATE INDEX idx_chip_bins_active ON hardware.chip_bins(id) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_chip_bins_updated_at
    BEFORE UPDATE ON hardware.chip_bins
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- Board serial batch intelligence (parallel to PSU serial batches)
CREATE TABLE IF NOT EXISTS hardware.board_serial_batches (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hashboard_id        UUID NOT NULL REFERENCES hardware.hashboards(id) ON DELETE CASCADE,
    batch_prefix        TEXT NOT NULL,            -- First 8 chars of serial number
    batch_description   TEXT,
    production_date_est DATE,
    production_facility TEXT,
    -- Quality intelligence
    known_issues        JSONB NOT NULL DEFAULT '[]',
    failure_rate_pct    NUMERIC(6,3),
    sample_size         INTEGER,
    quality_rating      TEXT,
    -- Performance stats for this batch
    avg_hashrate_pct_of_nominal NUMERIC(5,2),
    avg_hw_error_rate   NUMERIC(8,4),
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'low',
    verified_by_bobby   BOOLEAN NOT NULL DEFAULT FALSE,
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ,
    UNIQUE (hashboard_id, batch_prefix)
);

COMMENT ON TABLE hardware.board_serial_batches IS
'Tracks quality intelligence per hashboard serial number batch prefix.
Bobby groups by SUBSTR(serial_number, 1, 8) in cohort analysis (train_comprehensive.py).
If serial batch CN2023Q2 has 3x the failure rate of CN2024Q1, that lives here.';

CREATE INDEX idx_board_batch_hashboard ON hardware.board_serial_batches(hashboard_id);
CREATE INDEX idx_board_batch_prefix ON hardware.board_serial_batches(batch_prefix);
CREATE INDEX idx_board_batch_quality ON hardware.board_serial_batches(quality_rating);
CREATE INDEX idx_board_batch_active ON hardware.board_serial_batches(id) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_board_batch_updated_at
    BEFORE UPDATE ON hardware.board_serial_batches
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ============================================================================
-- GAP 3: CONTROL BOARD SERIAL NUMBERS AND TYPES
-- Bobby asked: "control board serial numbers and types"
-- Existing: hardware.control_boards has model specs but no serial tracking.
-- Bobby's repo tracks: control_board, bixminer_version, topol_machine, device_name
-- Solution: Add missing fields to control_boards table.
-- ============================================================================

ALTER TABLE hardware.control_boards
    ADD COLUMN IF NOT EXISTS serial_number_format TEXT,
    ADD COLUMN IF NOT EXISTS serial_prefix_pattern TEXT,
    ADD COLUMN IF NOT EXISTS bixminer_compatible_versions TEXT[],
    -- BiXBiT firmware versions known to work on this control board
    ADD COLUMN IF NOT EXISTS topol_machine_type TEXT,
    -- topol_machine field from EEPROM: machine topology identifier
    ADD COLUMN IF NOT EXISTS device_name_pattern TEXT,
    -- device_name field pattern from EEPROM/API
    ADD COLUMN IF NOT EXISTS supported_hashboard_count_max INTEGER,
    -- Max hashboards this control board can manage
    ADD COLUMN IF NOT EXISTS voltage_output_to_boards_v NUMERIC(6,3),
    -- Control voltage output to hashboard signal lines
    ADD COLUMN IF NOT EXISTS pic_versions_supported TEXT[],
    -- PIC microcontroller firmware versions this board supports
    ADD COLUMN IF NOT EXISTS original_cost_usd NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS is_discontinued BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS weight_g INTEGER,
    ADD COLUMN IF NOT EXISTS typical_failure_modes JSONB NOT NULL DEFAULT '[]';

COMMENT ON COLUMN hardware.control_boards.topol_machine_type IS
'From EEPROM: topol_machine field. Identifies machine topology for firmware configuration.';
COMMENT ON COLUMN hardware.control_boards.bixminer_compatible_versions IS
'BiXBiT firmware versions verified to work with this control board model.';


-- ============================================================================
-- GAP 4: VOLTAGE ACROSS HASHBOARDS
-- Bobby asked: "voltage going across dashboards" (hashboards)
-- Existing: hardware.hashboards has board_voltage_v_nom/min/max (spec sheet).
-- Missing: per-chip domain voltage, voltage measurement points, and
-- operational voltage reference data.
-- Solution: Add domain-level voltage fields + NEW measurement points table.
-- ============================================================================

ALTER TABLE hardware.hashboards
    ADD COLUMN IF NOT EXISTS domain_count INTEGER,
    -- Number of voltage domains on the board (e.g., 3 for S19j Pro)
    ADD COLUMN IF NOT EXISTS domain_voltage_v JSONB,
    -- Per-domain nominal voltage: [{"domain": 1, "voltage_v": 14.5, "chips": 42}, ...]
    ADD COLUMN IF NOT EXISTS voltage_regulator_type TEXT,
    -- VRM type: 'buck', 'linear', 'multiphase', etc.
    ADD COLUMN IF NOT EXISTS voltage_regulator_model TEXT,
    -- VRM IC model number
    ADD COLUMN IF NOT EXISTS voltage_measurement_points JSONB NOT NULL DEFAULT '[]';
    -- [{TP": "TP3", "location": "domain1_input", "expected_v": 14.5, "tolerance_pct": 2.0}]

COMMENT ON COLUMN hardware.hashboards.domain_voltage_v IS
'Per-domain nominal voltage mapping. Bobby monitors voltage per board in chain_readings.
This reference data tells you what voltage SHOULD be at each domain.';
COMMENT ON COLUMN hardware.hashboards.voltage_measurement_points IS
'Test point reference for repair techs. E.g., "TP3 should read 14.5V ± 2%"';


-- ============================================================================
-- GAP 5: HERTZ ACROSS HASHBOARDS
-- Bobby asked: "Hertz across dashboards" (frequency per hashboard)
-- Existing: chips table has frequency_mhz_min/max/nom for chips.
-- hashboards has no per-board frequency reference.
-- Solution: Add frequency reference data to hashboards.
-- ============================================================================

ALTER TABLE hardware.hashboards
    ADD COLUMN IF NOT EXISTS freq_mhz_stock NUMERIC(8,2),
    -- Stock frequency per board in MHz
    ADD COLUMN IF NOT EXISTS freq_mhz_min_stable NUMERIC(8,2),
    -- Minimum stable frequency
    ADD COLUMN IF NOT EXISTS freq_mhz_max_stable NUMERIC(8,2),
    -- Maximum stable frequency (without thermal throttling)
    ADD COLUMN IF NOT EXISTS freq_mhz_max_overclock NUMERIC(8,2),
    -- Maximum overclocked frequency (with proper cooling)
    ADD COLUMN IF NOT EXISTS freq_step_mhz NUMERIC(6,2),
    -- Frequency adjustment step size
    ADD COLUMN IF NOT EXISTS freq_voltage_curve JSONB;
    -- [{freq_mhz: 400, voltage_mv: 350}, {freq_mhz: 500, voltage_mv: 380}...]
    -- Frequency-voltage scaling curve for the board

COMMENT ON COLUMN hardware.hashboards.freq_mhz_stock IS
'Stock operating frequency for this hashboard. Bobby tracks freq_mhz per board in chain_readings.
This reference tells you what frequency SHOULD be at stock.';
COMMENT ON COLUMN hardware.hashboards.freq_voltage_curve IS
'Frequency-voltage scaling curve: what voltage is needed at each frequency step.
Critical for autotuning — running too high freq at too low voltage = instability.';


-- ============================================================================
-- GAP 6: TYPICAL FAN SPEEDS
-- Bobby asked: "typical fan speeds"
-- Existing: ops.operational_profiles has fan_speed_pct.
-- ops.operational_thresholds has fan_speed_low_rpm, fan_speed_high_rpm.
-- Missing: per-model fan specifications (model ships with X fans of Y type)
-- Solution: NEW TABLE for miner fan specifications.
-- ============================================================================

CREATE TABLE IF NOT EXISTS hardware.fan_specifications (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_model_id      UUID NOT NULL REFERENCES hardware.miner_models(id) ON DELETE CASCADE,
    -- Fan hardware specs
    fan_count           INTEGER NOT NULL,         -- Total fans in the unit
    fan_size_mm         INTEGER,                  -- Fan diameter in mm (e.g., 120, 140)
    fan_model           TEXT,                     -- Fan model/part number
    fan_manufacturer    TEXT,                     -- Fan manufacturer
    fan_type            TEXT NOT NULL DEFAULT 'axial',
    -- 'axial', 'centrifugal', 'blower', 'none' (immersion/hydro units)
    fan_bearing_type    TEXT,
    -- 'ball_bearing', 'sleeve', 'hydraulic', 'maglev', 'FDB'
    -- RPM specs
    rpm_min             INTEGER,                  -- Minimum RPM (idle/eco)
    rpm_max             INTEGER,                  -- Maximum RPM (full speed)
    rpm_typical_stock   INTEGER,                  -- Typical RPM at stock settings
    rpm_typical_turbo   INTEGER,                  -- Typical RPM in turbo mode
    -- Airflow
    cfm_max             NUMERIC(8,2),             -- Cubic feet per minute max airflow
    static_pressure_mmh2o NUMERIC(6,2),           -- Static pressure
    -- PWM control
    pwm_controlled      BOOLEAN NOT NULL DEFAULT TRUE,
    pwm_min_pct         INTEGER,                  -- Minimum PWM % (often 20-30%)
    pwm_default_pct     INTEGER,                  -- Default PWM % at stock
    -- Noise
    noise_db_idle       NUMERIC(5,1),             -- Noise at idle/minimum speed
    noise_db_stock      NUMERIC(5,1),             -- Noise at stock settings
    noise_db_full       NUMERIC(5,1),             -- Noise at full speed
    noise_db_turbo      NUMERIC(5,1),             -- Noise in turbo mode
    -- Power
    fan_power_w_each    NUMERIC(6,2),             -- Power per fan in watts
    fan_power_w_total   NUMERIC(6,2),             -- Total fan power
    -- Failure characteristics
    typical_lifespan_hours INTEGER,               -- Expected fan lifespan
    common_failure_modes JSONB NOT NULL DEFAULT '[]',
    -- [{"mode": "bearing_wear", "typical_age_months": 18, "symptom": "grinding noise"}]
    replacement_part_id UUID REFERENCES repair.parts(id),
    -- Direct replacement part in repair catalog
    -- Note for liquid-cooled units
    is_fan_applicable   BOOLEAN NOT NULL DEFAULT TRUE,
    -- FALSE for immersion/hydro units that have no intake/exhaust fans
    liquid_cooling_note TEXT,
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    verified_by_bobby   BOOLEAN NOT NULL DEFAULT FALSE,
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ
);

COMMENT ON TABLE hardware.fan_specifications IS
'Fan specifications per miner model. Covers fan count, RPM ranges, noise levels,
airflow specs, PWM control ranges, and failure characteristics.
For liquid-cooled units (S21 Immersion, AH3880 Hydro), is_fan_applicable=FALSE
but the record still exists to document cooling pump noise or absence of fans.
Bobby''s HVAC system monitors fan status via container_monitor/hvac_client.';

CREATE INDEX idx_fan_model ON hardware.fan_specifications(miner_model_id);
CREATE INDEX idx_fan_applicable ON hardware.fan_specifications(is_fan_applicable);
CREATE INDEX idx_fan_bobby ON hardware.fan_specifications(verified_by_bobby) WHERE verified_by_bobby = TRUE;
CREATE INDEX idx_fan_active ON hardware.fan_specifications(id) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_fan_updated_at
    BEFORE UPDATE ON hardware.fan_specifications
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ============================================================================
-- GAP 7: PSU VOLTAGE OUTPUT LEVELS (stock, high-end)
-- Bobby asked: "PSU voltage output, stock output level, high-end output level"
-- Existing: psu_models has output_power_w but no detailed voltage rails.
-- Solution: NEW TABLE for PSU voltage rail specifications.
-- ============================================================================

CREATE TABLE IF NOT EXISTS hardware.psu_voltage_rails (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    psu_model_id        UUID NOT NULL REFERENCES hardware.psu_models(id) ON DELETE CASCADE,
    rail_name           TEXT NOT NULL,             -- "12V_main", "12V_standby", "5V_aux", "3.3V_aux"
    -- Voltage specs
    voltage_nom_v       NUMERIC(8,4) NOT NULL,    -- Nominal voltage (e.g., 12.000)
    voltage_min_v       NUMERIC(8,4),             -- Minimum under load
    voltage_max_v       NUMERIC(8,4),             -- Maximum (no load/light load)
    -- At different load levels
    voltage_at_25pct_load_v NUMERIC(8,4),
    voltage_at_50pct_load_v NUMERIC(8,4),
    voltage_at_75pct_load_v NUMERIC(8,4),
    voltage_at_100pct_load_v NUMERIC(8,4),
    -- Current
    current_max_a       NUMERIC(8,3),             -- Maximum rated current on this rail
    current_typical_a   NUMERIC(8,3),             -- Typical current at normal mining load
    -- Power
    power_max_w         NUMERIC(8,2),             -- Maximum power on this rail
    -- Regulation
    regulation_pct      NUMERIC(5,3),             -- Voltage regulation % (e.g., ±1%)
    ripple_mv_max       NUMERIC(6,2),             -- Maximum ripple in mV
    -- Cross-regulation (how load on other rails affects this one)
    cross_regulation_pct NUMERIC(5,3),
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ,
    UNIQUE (psu_model_id, rail_name)
);

COMMENT ON TABLE hardware.psu_voltage_rails IS
'Detailed voltage rail specifications per PSU model. Bobby monitors PSU voltage
trends via log_metrics (psu_voltage metric type) in the operational DB.
This reference data tells you what the PSU SHOULD output under various loads.
stock output = voltage_at_75pct_load_v typical mining load.
high-end output = voltage_at_100pct_load_v overclocked turbo mode.';

CREATE INDEX idx_psu_rails_model ON hardware.psu_voltage_rails(psu_model_id);
CREATE INDEX idx_psu_rails_name ON hardware.psu_voltage_rails(rail_name);
CREATE INDEX idx_psu_rails_active ON hardware.psu_voltage_rails(id) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_psu_rails_updated_at
    BEFORE UPDATE ON hardware.psu_voltage_rails
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ============================================================================
-- GAP 8: KNOWN PROBLEMS / KNOWN SUCCESSES / COMMON ISSUES / UNCOMMON ISSUES
-- Bobby asked: "known problems, known successes, common issues, uncommon issues"
-- Existing: ops.failure_patterns covers failures. market.war_stories covers narratives.
-- Missing: structured per-model known issues AND successes registry.
-- Solution: NEW TABLE — model-level issue/success registry.
-- ============================================================================

CREATE TABLE IF NOT EXISTS hardware.model_known_issues (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_model_id      UUID NOT NULL REFERENCES hardware.miner_models(id) ON DELETE CASCADE,
    -- Classification
    issue_type          TEXT NOT NULL,
    -- 'problem', 'success', 'quirk', 'limitation', 'advantage', 'tip'
    commonality         TEXT NOT NULL,
    -- 'very_common', 'common', 'uncommon', 'rare', 'isolated', 'universal'
    category            TEXT NOT NULL,
    -- 'thermal', 'hashboard', 'psu', 'control_board', 'fan', 'firmware',
    -- 'network', 'pool', 'electrical', 'physical', 'noise', 'efficiency',
    -- 'reliability', 'compatibility', 'usability'
    severity            public.failure_severity,
    -- Title and description
    title               TEXT NOT NULL,
    description         TEXT NOT NULL,
    -- Affected scope
    affected_hardware   TEXT,                     -- 'all_units', 'batch_X', 'pcb_rev_Y', etc.
    affected_firmware   TEXT,                     -- Firmware versions affected
    affected_cooling    public.cooling_type,      -- Specific cooling type or NULL=all
    -- Resolution/workaround
    workaround          TEXT,
    resolution          TEXT,
    is_resolved         BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_in_firmware TEXT,                    -- Firmware version that fixed it
    resolved_in_hardware TEXT,                    -- Hardware revision that fixed it
    -- Linked failure pattern (if applicable)
    failure_pattern_id  UUID REFERENCES ops.failure_patterns(id),
    -- Impact
    hashrate_impact_pct NUMERIC(6,2),            -- % hashrate impact (negative = loss)
    power_impact_pct    NUMERIC(6,2),
    financial_impact_usd_est NUMERIC(10,2),
    -- Occurrence
    first_reported_date DATE,
    report_count        INTEGER NOT NULL DEFAULT 1,
    -- Bobby's experience
    bobby_experienced   BOOLEAN NOT NULL DEFAULT FALSE,
    bobby_notes         TEXT,
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    search_vector       TSVECTOR,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ
);

COMMENT ON TABLE hardware.model_known_issues IS
'Per-model registry of known problems, successes, common issues, and uncommon issues.
Bobby asked for ALL of these: "known problems, known successes, common issues, uncommon issues."
issue_type distinguishes problems from successes/advantages.
commonality tracks how frequently the issue appears across the user base.
This is the first place Mining Guardian checks when a user asks "What should I know about model X?"';

CREATE INDEX idx_known_issues_model ON hardware.model_known_issues(miner_model_id);
CREATE INDEX idx_known_issues_type ON hardware.model_known_issues(issue_type);
CREATE INDEX idx_known_issues_commonality ON hardware.model_known_issues(commonality);
CREATE INDEX idx_known_issues_category ON hardware.model_known_issues(category);
CREATE INDEX idx_known_issues_bobby ON hardware.model_known_issues(bobby_experienced) WHERE bobby_experienced = TRUE;
CREATE INDEX idx_known_issues_unresolved ON hardware.model_known_issues(is_resolved) WHERE is_resolved = FALSE;
CREATE INDEX idx_known_issues_search ON hardware.model_known_issues USING GIN(search_vector);
CREATE INDEX idx_known_issues_active ON hardware.model_known_issues(id) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_known_issues_updated_at
    BEFORE UPDATE ON hardware.model_known_issues
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_known_issues_search_vector
    BEFORE INSERT OR UPDATE ON hardware.model_known_issues
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        title, description, category, workaround, resolution, bobby_notes
    );


-- ============================================================================
-- GAP 9: GOOD REVIEWS / BAD REVIEWS
-- Bobby asked: "good reviews, bad reviews"
-- Existing: market.user_reviews already captures reviews with multi-dimension ratings,
-- pros/cons, and sentiment. This is ALREADY COVERED.
-- Enhancement: Add aggregate review summary table for fast lookups.
-- ============================================================================

CREATE TABLE IF NOT EXISTS market.review_summaries (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_model_id      UUID NOT NULL REFERENCES hardware.miner_models(id) ON DELETE CASCADE,
    -- Aggregate stats
    total_reviews       INTEGER NOT NULL DEFAULT 0,
    positive_reviews    INTEGER NOT NULL DEFAULT 0,  -- sentiment = very_positive or positive
    negative_reviews    INTEGER NOT NULL DEFAULT 0,  -- sentiment = very_negative or negative
    neutral_reviews     INTEGER NOT NULL DEFAULT 0,
    -- Average ratings
    avg_overall_rating  NUMERIC(4,2),
    avg_build_quality   NUMERIC(4,2),
    avg_performance     NUMERIC(4,2),
    avg_value           NUMERIC(4,2),
    avg_reliability     NUMERIC(4,2),
    avg_support         NUMERIC(4,2),
    avg_noise           NUMERIC(4,2),
    -- Top pros and cons (aggregated from review data)
    top_pros            JSONB NOT NULL DEFAULT '[]',
    -- [{"pro": "stable hashrate", "mention_count": 42}, ...]
    top_cons            JSONB NOT NULL DEFAULT '[]',
    -- [{"con": "runs hot in summer", "mention_count": 28}, ...]
    -- Bobby's verdict
    bobby_verdict       TEXT,
    bobby_recommendation TEXT,                    -- 'buy', 'avoid', 'conditional', 'best_in_class'
    -- Timestamps
    last_calculated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ,
    UNIQUE (miner_model_id)
);

COMMENT ON TABLE market.review_summaries IS
'Pre-computed review aggregates per model. Bobby asked for "good reviews, bad reviews" —
this provides instant access to review sentiment breakdown, top pros/cons, and Bobby''s verdict.
Recalculated periodically from market.user_reviews.';

CREATE INDEX idx_review_sum_model ON market.review_summaries(miner_model_id);
CREATE INDEX idx_review_sum_active ON market.review_summaries(id) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_review_sum_updated_at
    BEFORE UPDATE ON market.review_summaries
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ============================================================================
-- GAP 10: ORIGINAL COST
-- Bobby asked: "original cost"
-- Existing: hardware.miner_models has msrp_usd and msrp_date.
-- market.pricing_history tracks all prices over time.
-- Enhancement: Add more cost detail fields to miner_models.
-- ============================================================================

ALTER TABLE hardware.miner_models
    ADD COLUMN IF NOT EXISTS original_msrp_usd NUMERIC(10,2),
    -- The very first retail price at launch
    ADD COLUMN IF NOT EXISTS original_msrp_date DATE,
    -- Date of original MSRP
    ADD COLUMN IF NOT EXISTS current_new_price_usd NUMERIC(10,2),
    -- Current new-in-box price (updated periodically)
    ADD COLUMN IF NOT EXISTS current_used_price_usd NUMERIC(10,2),
    -- Current typical used price
    ADD COLUMN IF NOT EXISTS price_last_updated DATE,
    -- When current prices were last checked
    ADD COLUMN IF NOT EXISTS cost_per_th_at_launch NUMERIC(10,4),
    -- MSRP / stock_hashrate_th at launch
    ADD COLUMN IF NOT EXISTS roi_days_at_launch INTEGER;
    -- Estimated ROI in days at launch BTC price/difficulty

COMMENT ON COLUMN hardware.miner_models.original_msrp_usd IS
'Bobby asked for "original cost" — this is the launch-day retail price before any market adjustments.';


-- ============================================================================
-- GAP 11: TEAR SHEET / COMPLETE SPEC BREAKDOWN
-- Bobby asked: "breakdown every tear sheet on the miner itself — size, weight,
-- standard output, years in production, etc."
-- Existing: miner_models has dimensions, weight, hashrate, dates.
-- Missing: noise levels, cable requirements, shipping weight,
-- packaging dimensions, warranty info, and lifecycle tracking.
-- Solution: Add comprehensive spec fields to miner_models.
-- ============================================================================

ALTER TABLE hardware.miner_models
    ADD COLUMN IF NOT EXISTS noise_db_stock NUMERIC(5,1),
    -- Noise level in dB(A) at stock settings
    ADD COLUMN IF NOT EXISTS noise_db_turbo NUMERIC(5,1),
    -- Noise level in dB(A) in turbo/overclock mode
    ADD COLUMN IF NOT EXISTS noise_db_eco NUMERIC(5,1),
    -- Noise level in dB(A) in eco mode
    ADD COLUMN IF NOT EXISTS shipping_weight_kg NUMERIC(7,3),
    -- Weight including packaging
    ADD COLUMN IF NOT EXISTS packaging_length_mm NUMERIC(7,2),
    ADD COLUMN IF NOT EXISTS packaging_width_mm NUMERIC(7,2),
    ADD COLUMN IF NOT EXISTS packaging_height_mm NUMERIC(7,2),
    ADD COLUMN IF NOT EXISTS units_per_pallet INTEGER,
    -- How many units fit on a standard pallet
    ADD COLUMN IF NOT EXISTS cable_requirements JSONB NOT NULL DEFAULT '[]',
    -- [{"type": "C19-C20", "count": 2, "gauge_awg": 12, "length_m": 1.5}]
    ADD COLUMN IF NOT EXISTS breaker_size_a INTEGER,
    -- Required circuit breaker amperage
    ADD COLUMN IF NOT EXISTS outlet_type TEXT,
    -- 'NEMA_5-15', 'NEMA_6-20', 'C14', 'C19', etc.
    ADD COLUMN IF NOT EXISTS years_in_production INTEGER,
    -- GENERATED or manually set
    ADD COLUMN IF NOT EXISTS production_batch_count INTEGER,
    -- How many production batches known
    ADD COLUMN IF NOT EXISTS total_units_manufactured_est INTEGER,
    -- Estimated total units produced worldwide
    ADD COLUMN IF NOT EXISTS warranty_months INTEGER,
    -- Standard warranty period
    ADD COLUMN IF NOT EXISTS warranty_notes TEXT,
    -- Warranty fine print, limitations, void conditions
    ADD COLUMN IF NOT EXISTS end_of_support_date DATE,
    -- When manufacturer stops providing firmware/parts
    ADD COLUMN IF NOT EXISTS altitude_max_m INTEGER,
    -- Maximum operating altitude in meters
    ADD COLUMN IF NOT EXISTS storage_temp_min_c INTEGER,
    ADD COLUMN IF NOT EXISTS storage_temp_max_c INTEGER,
    ADD COLUMN IF NOT EXISTS storage_humidity_max_pct INTEGER,
    ADD COLUMN IF NOT EXISTS ingress_protection TEXT,
    -- IP rating: 'IP20', 'IP54', etc.
    ADD COLUMN IF NOT EXISTS compliance_marks JSONB NOT NULL DEFAULT '[]',
    -- ['CE', 'FCC Part 15B', 'RoHS', 'REACH', 'UL Listed']
    ADD COLUMN IF NOT EXISTS datasheet_url TEXT,
    ADD COLUMN IF NOT EXISTS product_page_url TEXT,
    ADD COLUMN IF NOT EXISTS manual_url TEXT,
    ADD COLUMN IF NOT EXISTS quick_start_guide_url TEXT;

COMMENT ON COLUMN hardware.miner_models.noise_db_stock IS
'Bobby asked for full tear sheet breakdown. Noise is critical for site planning.';
COMMENT ON COLUMN hardware.miner_models.years_in_production IS
'Bobby asked for "years in production" — how long this model has been manufactured.';
COMMENT ON COLUMN hardware.miner_models.cable_requirements IS
'Cable/power cord requirements for installation. Critical for facility planning.';


-- ============================================================================
-- GAP 12: CONTROL BOARD SERIAL BATCH INTELLIGENCE
-- Parallel to PSU and hashboard serial batches.
-- ============================================================================

CREATE TABLE IF NOT EXISTS hardware.control_board_serial_batches (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    control_board_id    UUID NOT NULL REFERENCES hardware.control_boards(id) ON DELETE CASCADE,
    batch_prefix        TEXT NOT NULL,
    batch_description   TEXT,
    production_date_est DATE,
    production_facility TEXT,
    known_issues        JSONB NOT NULL DEFAULT '[]',
    failure_rate_pct    NUMERIC(6,3),
    sample_size         INTEGER,
    quality_rating      TEXT,
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'low',
    verified_by_bobby   BOOLEAN NOT NULL DEFAULT FALSE,
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ,
    UNIQUE (control_board_id, batch_prefix)
);

COMMENT ON TABLE hardware.control_board_serial_batches IS
'Serial batch intelligence for control boards. Same pattern as PSU and hashboard batches.';

CREATE INDEX idx_cb_batch_board ON hardware.control_board_serial_batches(control_board_id);
CREATE INDEX idx_cb_batch_prefix ON hardware.control_board_serial_batches(batch_prefix);
CREATE INDEX idx_cb_batch_active ON hardware.control_board_serial_batches(id) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_cb_batch_updated_at
    BEFORE UPDATE ON hardware.control_board_serial_batches
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ============================================================================
-- GAP 13: PIN COUNT / PIN NUMBERS ON CHIPS
-- Bobby asked: "pin numbers"
-- Existing: hardware.chips.pin_count exists (line 512).
-- Missing: pin diagram/mapping data and connector pinout reference.
-- Solution: Add pin mapping details to chips + connector pinout reference.
-- ============================================================================

ALTER TABLE hardware.chips
    ADD COLUMN IF NOT EXISTS pin_map JSONB,
    -- Pin map: {"VDD": [1,2,3], "GND": [4,5,6], "CLK": 7, "NRST": 8, ...}
    ADD COLUMN IF NOT EXISTS pin_pitch_mm NUMERIC(5,3),
    -- Pin pitch (distance between pins) in mm
    ADD COLUMN IF NOT EXISTS ball_count INTEGER,
    -- For BGA packages: total ball count
    ADD COLUMN IF NOT EXISTS thermal_pad_pin TEXT;
    -- Which pin/pad is the thermal pad (for heat dissipation)

-- Connector pinout reference — for all connectors in the mining system
CREATE TABLE IF NOT EXISTS hardware.connector_pinouts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    connector_name      TEXT NOT NULL,             -- "S19j Pro hashboard data connector"
    connector_type      TEXT NOT NULL,             -- "14-pin ribbon", "6-pin power", etc.
    -- Where this connector is found
    miner_model_id      UUID REFERENCES hardware.miner_models(id),
    component_type      TEXT NOT NULL,             -- 'hashboard', 'control_board', 'psu', 'fan'
    -- Pinout
    pin_count           INTEGER NOT NULL,
    pinout_map          JSONB NOT NULL,
    -- {"1": {"signal": "GND", "voltage": "0V"},
    --  "2": {"signal": "CLK_OUT", "voltage": "3.3V"},
    --  "3": {"signal": "VDD_CHAIN", "voltage": "14.5V"}, ...}
    notes               TEXT,
    diagram_url         TEXT,
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'low',
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ
);

COMMENT ON TABLE hardware.connector_pinouts IS
'Pin-by-pin reference for all connectors in mining hardware.
Critical for repair techs probing connector signals with multimeter/oscilloscope.
"Pin 3 on the S19j Pro hashboard data connector should read 14.5V"';

CREATE INDEX idx_pinout_model ON hardware.connector_pinouts(miner_model_id);
CREATE INDEX idx_pinout_component ON hardware.connector_pinouts(component_type);
CREATE INDEX idx_pinout_active ON hardware.connector_pinouts(id) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_pinout_updated_at
    BEFORE UPDATE ON hardware.connector_pinouts
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ============================================================================
-- GAP 14: ADDITIONAL FIELDS FROM MINING GUARDIAN CODEBASE
-- Fields tracked in guardian.db that should have reference intelligence:
-- - bixminer_version (firmware field on control board)
-- - topol_machine (machine topology)
-- - device_name (device identifier)
-- - pic_version (PIC microcontroller firmware)
-- - psu_version (PSU firmware/revision)
-- These are operational fields. Reference data about them goes here.
-- ============================================================================

-- PSU firmware/revision tracking
ALTER TABLE hardware.psu_models
    ADD COLUMN IF NOT EXISTS firmware_version_latest TEXT,
    -- Latest PSU firmware version (some PSUs have updatable firmware)
    ADD COLUMN IF NOT EXISTS firmware_updatable BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS firmware_update_url TEXT,
    ADD COLUMN IF NOT EXISTS hardware_revision TEXT,
    -- "Rev 1.0", "Rev 2.1" — the psu_version field from guardian.db
    ADD COLUMN IF NOT EXISTS hardware_revision_history JSONB NOT NULL DEFAULT '[]';
    -- [{"revision": "1.0", "date": "2022-01", "changes": "initial release"},
    --  {"revision": "2.1", "date": "2023-06", "changes": "improved OCP circuit"}]

COMMENT ON COLUMN hardware.psu_models.hardware_revision IS
'Maps to psu_version field in guardian.db miner_hardware table.';


-- ============================================================================
-- GAP 15: ANYTHING ELSE FOUND — CATCH-ALL REFERENCE FIELDS
-- Bobby said: "and anything else you ever find it needs to have its own data table"
-- From the repo audit, additional data points tracked operationally that need
-- reference intelligence in the catalog.
-- ============================================================================

-- Add to miner_models: operational reference data
ALTER TABLE hardware.miner_models
    ADD COLUMN IF NOT EXISTS typical_break_even_months INTEGER,
    -- Typical break-even period at current difficulty/price
    ADD COLUMN IF NOT EXISTS hash_to_power_ratio NUMERIC(8,4),
    -- TH/s per kW at stock — quick efficiency comparison metric
    ADD COLUMN IF NOT EXISTS operating_voltage_range TEXT,
    -- Human-readable: "200-240V AC" or "100-240V AC (universal)"
    ADD COLUMN IF NOT EXISTS max_altitude_derate_pct NUMERIC(5,2),
    -- Performance derating per 1000m altitude
    ADD COLUMN IF NOT EXISTS ethernet_ports INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS usb_ports INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS sd_card_slot BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS reset_button BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS ip_finder_button BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS led_indicators JSONB NOT NULL DEFAULT '[]',
    -- [{"color": "green", "meaning": "normal"}, {"color": "red", "meaning": "fault"}]
    ADD COLUMN IF NOT EXISTS country_of_manufacture CHAR(2),
    ADD COLUMN IF NOT EXISTS hs_tariff_code TEXT;
    -- Harmonized System tariff code for import/export

COMMENT ON COLUMN hardware.miner_models.hash_to_power_ratio IS
'TH/s per kW — quick metric Bobby can use to compare efficiency across models at a glance.';


-- ============================================================================
-- SUMMARY OF ADDITIONS
-- ============================================================================
-- NEW TABLES (7):
--   1. hardware.psu_serial_batches      — PSU serial number batch quality tracking
--   2. hardware.chip_bins               — Chip bin quality/performance grades
--   3. hardware.board_serial_batches    — Hashboard serial batch quality tracking
--   4. hardware.fan_specifications      — Per-model fan specs, RPM, noise, CFM
--   5. hardware.psu_voltage_rails       — Detailed PSU voltage rail specifications
--   6. hardware.model_known_issues      — Known problems, successes, common/uncommon issues
--   7. hardware.connector_pinouts       — Pin-by-pin connector reference
--   8. hardware.control_board_serial_batches — Control board serial batch tracking
--   9. market.review_summaries          — Pre-computed review aggregates
--
-- ALTERED TABLES (6):
--   1. hardware.psu_models      — +20 columns (serial format, voltage output, noise, cost, etc.)
--   2. hardware.hashboards      — +18 columns (chip passport, freq, voltage, board specs)
--   3. hardware.control_boards  — +12 columns (serial format, bixminer, topol, pic versions)
--   4. hardware.miner_models    — +30 columns (noise, packaging, cables, warranty, lifecycle)
--   5. hardware.chips           — +4 columns (pin map, pitch, thermal pad)
--
-- TOTAL NEW COLUMNS: ~84
-- TOTAL NEW TABLES: 9
-- Updated table count: 63 + 9 = 72
-- ============================================================================
