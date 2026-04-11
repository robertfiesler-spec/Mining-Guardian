-- =============================================================================
-- MINING INTELLIGENCE CATALOG — V3 ADDITIONS (Exhaustive Gap Audit)
-- =============================================================================
-- Run AFTER intelligence_catalog_schema.sql AND v2_additions.sql
-- =============================================================================
-- This file addresses EVERY gap found across three audit dimensions:
--   1. Codebase data points NOT captured in the intelligence catalog
--   2. Industry-standard mining intelligence data points we were missing
--   3. Bobby's auto-discovery requirement: never skip unknown data points
-- =============================================================================
-- Target: PostgreSQL 16 on ROBS-PC (192.168.188.47:5432)
-- =============================================================================

-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  SECTION A: AUTO-DISCOVERY MECHANISM                                     ║
-- ║  "If a new data point comes up that it has never seen before, it knows   ║
-- ║   to mark it down, register it as a new data point, not skip over it"   ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- A1: Field Registry — canonical list of every known data field across all sources
-- This is the "dictionary" the system checks before deciding if something is new
CREATE TABLE IF NOT EXISTS knowledge.field_registry (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    field_key           TEXT NOT NULL,             -- Canonical key: "miner_readings.hashrate"
    field_source        TEXT NOT NULL,             -- Where it comes from: 'guardian_db', 'container_monitor', 'hvac', 'ams_api', 'bixbit_api', 'miner_log', 'user_input'
    field_category      TEXT NOT NULL,             -- 'thermal', 'electrical', 'performance', 'environmental', 'safety', 'identity', 'pool', 'firmware', 'facility'
    data_type           TEXT NOT NULL,             -- 'numeric', 'text', 'boolean', 'json', 'timestamp'
    unit                TEXT,                      -- 'celsius', 'watts', 'th/s', 'mhz', 'mv', 'psi', 'mpa', 'kwh', '%', etc.
    description         TEXT,                      -- Human-readable description
    typical_min         NUMERIC,                   -- Expected range low
    typical_max         NUMERIC,                   -- Expected range high
    is_alertable        BOOLEAN NOT NULL DEFAULT FALSE,  -- Can this field trigger alerts?
    alert_threshold_low NUMERIC,
    alert_threshold_high NUMERIC,
    catalog_table       TEXT,                      -- Which intelligence catalog table maps to this: 'ops.operational_thresholds', etc.
    catalog_column      TEXT,                      -- Which column in that table
    guardian_db_table    TEXT,                      -- Which guardian.db table stores this operationally
    guardian_db_column   TEXT,                      -- Which column
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    seen_count          BIGINT NOT NULL DEFAULT 1,
    registered_by       TEXT NOT NULL DEFAULT 'system',  -- 'system', 'auto_discovery', 'bobby', 'import'
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (field_key, field_source)
);

COMMENT ON TABLE knowledge.field_registry IS
'Master dictionary of every known data field across all sources. The auto-discovery engine
checks incoming data against this registry. If a field is NOT in here, it gets flagged as
unknown and routed to knowledge.unknown_fields. Bobby''s rule: "NO data point is too small."';

CREATE INDEX idx_field_registry_key ON knowledge.field_registry(field_key);
CREATE INDEX idx_field_registry_source ON knowledge.field_registry(field_source);
CREATE INDEX idx_field_registry_category ON knowledge.field_registry(field_category);
CREATE INDEX idx_field_registry_catalog ON knowledge.field_registry(catalog_table, catalog_column);
CREATE INDEX idx_field_registry_guardian ON knowledge.field_registry(guardian_db_table, guardian_db_column);
CREATE INDEX idx_field_registry_active ON knowledge.field_registry(id) WHERE is_active = TRUE;

CREATE TRIGGER trg_field_registry_updated_at
    BEFORE UPDATE ON knowledge.field_registry
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- A2: Unknown Fields — auto-captured data points the system has never seen before
-- This is the "inbox" for new data. Mining Guardian writes here when it encounters
-- a field that doesn't match anything in field_registry.
CREATE TABLE IF NOT EXISTS knowledge.unknown_fields (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_field_name      TEXT NOT NULL,             -- The original field name as received
    raw_field_value     TEXT,                      -- The first observed value (as text)
    raw_field_type      TEXT,                      -- Detected type: 'number', 'string', 'boolean', 'object', 'array'
    source_system       TEXT NOT NULL,             -- 'ams_api', 'bixbit_api', 'container_monitor', 'miner_log', 'firmware_api', 'direct_api'
    source_endpoint     TEXT,                      -- The specific API endpoint or log file
    source_miner_id     TEXT,                      -- Which miner generated it (if applicable)
    source_ip           TEXT,                      -- Source IP
    source_firmware     TEXT,                      -- Firmware version that produced it
    source_model        TEXT,                      -- Miner model
    parent_object       TEXT,                      -- Parent JSON path if nested: 'devs[0].chains[0]'
    sample_values       JSONB NOT NULL DEFAULT '[]', -- Array of first N observed values for pattern analysis
    occurrence_count    BIGINT NOT NULL DEFAULT 1, -- How many times seen
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Classification workflow
    status              TEXT NOT NULL DEFAULT 'new',  -- 'new', 'under_review', 'classified', 'mapped', 'ignored', 'duplicate'
    classified_as       TEXT,                      -- Once reviewed: field_registry.field_key it maps to
    mapped_to_table     TEXT,                      -- Target intelligence catalog table
    mapped_to_column    TEXT,                      -- Target column (may need ALTER TABLE to create)
    reviewed_by         TEXT,                      -- 'bobby', 'llm_tier1', 'llm_tier2', 'auto'
    reviewed_at         TIMESTAMPTZ,
    review_notes        TEXT,
    -- Auto-classification hints
    llm_suggested_category TEXT,                   -- LLM's best guess: 'thermal', 'electrical', etc.
    llm_suggested_unit  TEXT,                      -- LLM's best guess at unit
    llm_confidence      NUMERIC(4,3),              -- 0.000 to 1.000
    llm_reasoning       TEXT,                      -- Why the LLM thinks this
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE knowledge.unknown_fields IS
'Auto-discovery inbox. When Mining Guardian encounters ANY data field not in field_registry,
it logs it here with sample values. Bobby''s hard requirement: "if a new data point comes up
that it has never seen before, it knows to mark it down, register it as a new data point,
not skip over it." The Tier 1 LLM auto-classifies on first sight. Bobby reviews weekly.';

CREATE INDEX idx_unknown_fields_status ON knowledge.unknown_fields(status);
CREATE INDEX idx_unknown_fields_source ON knowledge.unknown_fields(source_system);
CREATE INDEX idx_unknown_fields_name ON knowledge.unknown_fields(raw_field_name);
CREATE INDEX idx_unknown_fields_miner ON knowledge.unknown_fields(source_miner_id);
CREATE INDEX idx_unknown_fields_new ON knowledge.unknown_fields(id) WHERE status = 'new';
CREATE INDEX idx_unknown_fields_first_seen ON knowledge.unknown_fields(first_seen_at);
CREATE UNIQUE INDEX idx_unknown_fields_unique ON knowledge.unknown_fields(raw_field_name, source_system, parent_object)
    WHERE status NOT IN ('duplicate', 'ignored');

CREATE TRIGGER trg_unknown_fields_updated_at
    BEFORE UPDATE ON knowledge.unknown_fields
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- A3: Raw Ingestion Log — stores EVERY raw API/log response for forensic analysis
-- When something weird happens, Bobby can look at exactly what the system received
CREATE TABLE IF NOT EXISTS knowledge.raw_ingestion_log (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ingestion_source    TEXT NOT NULL,             -- 'ams_api', 'bixbit_api', 'container_monitor', 'hvac_bacnet', 'miner_log', 'weather_api'
    source_endpoint     TEXT,                      -- Specific endpoint or log path
    source_miner_id     TEXT,
    source_ip           TEXT,
    raw_payload         JSONB NOT NULL,            -- Complete raw response — JSONB for queryability
    payload_hash        TEXT NOT NULL,             -- SHA-256 of payload — dedup identical payloads
    payload_size_bytes  INTEGER,
    new_fields_found    INTEGER NOT NULL DEFAULT 0, -- Count of unknown fields found in this payload
    processing_status   TEXT NOT NULL DEFAULT 'processed', -- 'processed', 'error', 'partial'
    processing_error    TEXT,
    processing_time_ms  INTEGER,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Partitioning column — auto-prune after retention period
    retention_tier      TEXT NOT NULL DEFAULT 'standard'  -- 'standard' (90 days), 'flagged' (1 year), 'permanent'
) PARTITION BY RANGE (ingested_at);

COMMENT ON TABLE knowledge.raw_ingestion_log IS
'Complete raw payload archive. Every API response, every log parse. Partitioned by month,
auto-pruned by retention_tier. Standard = 90 days, flagged = 1 year, permanent = forever.
This is the forensic backbone — when something weird happens, we can replay exactly what arrived.';

-- Create initial partitions (12 months forward)
CREATE TABLE knowledge.raw_ingestion_log_2026_q1 PARTITION OF knowledge.raw_ingestion_log
    FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');
CREATE TABLE knowledge.raw_ingestion_log_2026_q2 PARTITION OF knowledge.raw_ingestion_log
    FOR VALUES FROM ('2026-04-01') TO ('2026-07-01');
CREATE TABLE knowledge.raw_ingestion_log_2026_q3 PARTITION OF knowledge.raw_ingestion_log
    FOR VALUES FROM ('2026-07-01') TO ('2026-10-01');
CREATE TABLE knowledge.raw_ingestion_log_2026_q4 PARTITION OF knowledge.raw_ingestion_log
    FOR VALUES FROM ('2026-10-01') TO ('2027-01-01');
CREATE TABLE knowledge.raw_ingestion_log_2027_q1 PARTITION OF knowledge.raw_ingestion_log
    FOR VALUES FROM ('2027-01-01') TO ('2027-04-01');

CREATE INDEX idx_raw_ingestion_source ON knowledge.raw_ingestion_log(ingestion_source, ingested_at);
CREATE INDEX idx_raw_ingestion_miner ON knowledge.raw_ingestion_log(source_miner_id, ingested_at);
CREATE INDEX idx_raw_ingestion_hash ON knowledge.raw_ingestion_log(payload_hash);
CREATE INDEX idx_raw_ingestion_new_fields ON knowledge.raw_ingestion_log(id) WHERE new_fields_found > 0;


-- A4: Field Discovery Audit Trail — tracks the lifecycle of every discovered field
CREATE TABLE IF NOT EXISTS knowledge.field_discovery_log (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    unknown_field_id    UUID REFERENCES knowledge.unknown_fields(id),
    registry_field_id   UUID REFERENCES knowledge.field_registry(id),
    action              TEXT NOT NULL,  -- 'discovered', 'auto_classified', 'bobby_reviewed', 'mapped_to_catalog', 'schema_altered', 'ignored'
    action_by           TEXT NOT NULL,  -- 'auto_discovery_engine', 'llm_tier1', 'llm_tier2', 'bobby'
    action_details      JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE knowledge.field_discovery_log IS
'Audit trail for auto-discovery. Tracks every step from first sighting through classification,
mapping, and schema integration. Answers the question: "When did we first see this field, who
classified it, and where does it live now?"';

CREATE INDEX idx_discovery_log_unknown ON knowledge.field_discovery_log(unknown_field_id);
CREATE INDEX idx_discovery_log_registry ON knowledge.field_discovery_log(registry_field_id);
CREATE INDEX idx_discovery_log_action ON knowledge.field_discovery_log(action, created_at);


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  SECTION B: CONTAINER / FACILITY INFRASTRUCTURE GAPS                    ║
-- ║  Data points found in container_monitor.py and hvac_client.py that      ║
-- ║  have no reference intelligence counterpart in the catalog              ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- B1: Container Hydraulics Reference — what "normal" looks like for BiXBiT containers
CREATE TABLE IF NOT EXISTS facility.container_hydraulics_reference (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    container_model     TEXT NOT NULL,             -- 'BiXBiT 40ft', 'BiXBiT 20ft', etc.
    cooling_solution_id UUID REFERENCES facility.cooling_solutions(id),
    -- Supply side reference
    supply_temp_c_nom   NUMERIC(5,2),              -- Normal supply temperature
    supply_temp_c_min   NUMERIC(5,2),              -- Minimum safe supply temp
    supply_temp_c_max   NUMERIC(5,2),              -- Maximum safe supply temp
    supply_pressure_mpa_nom NUMERIC(6,4),          -- Normal supply pressure
    supply_pressure_mpa_min NUMERIC(6,4),
    supply_pressure_mpa_max NUMERIC(6,4),
    -- Return side reference
    return_temp_c_nom   NUMERIC(5,2),
    return_temp_c_min   NUMERIC(5,2),
    return_temp_c_max   NUMERIC(5,2),
    return_pressure_mpa_nom NUMERIC(6,4),
    return_pressure_mpa_min NUMERIC(6,4),
    return_pressure_mpa_max NUMERIC(6,4),
    -- Delta-T reference (supply→return)
    delta_t_c_nom       NUMERIC(5,2),              -- Normal delta-T
    delta_t_c_min       NUMERIC(5,2),              -- Minimum acceptable
    delta_t_c_max       NUMERIC(5,2),              -- Maximum acceptable (Bobby's 84°C locked rule context)
    -- Filter pressure differential
    filter_before_mpa_nom NUMERIC(6,4),
    filter_after_mpa_nom  NUMERIC(6,4),
    filter_delta_mpa_alarm NUMERIC(6,4),           -- When to change filter
    -- High pressure reference
    high_pressure_mpa_nom NUMERIC(6,4),
    high_pressure_mpa_alarm NUMERIC(6,4),
    -- Flow rate reference
    flow_rate_m3h_nom   NUMERIC(8,3),              -- Normal flow rate
    flow_rate_m3h_min   NUMERIC(8,3),              -- Minimum acceptable
    flow_rate_m3h_max   NUMERIC(8,3),
    -- Conductivity reference (fluid quality)
    conductivity_us_nom NUMERIC(8,2),              -- Normal conductivity µS/cm
    conductivity_us_max NUMERIC(8,2),              -- When fluid replacement needed
    conductivity_us_alarm NUMERIC(8,2),            -- Alert threshold
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

COMMENT ON TABLE facility.container_hydraulics_reference IS
'Reference data for container hydraulic systems — what "normal" supply temp, pressure,
flow rate, conductivity, and delta-T look like. Mapped from container_monitor.py
ContainerHydraulics data class. Used by the LLM to judge whether readings are healthy.';

CREATE INDEX idx_container_hydro_model ON facility.container_hydraulics_reference(container_model);
CREATE INDEX idx_container_hydro_active ON facility.container_hydraulics_reference(id) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_container_hydro_ref_updated_at
    BEFORE UPDATE ON facility.container_hydraulics_reference
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- B2: Container Cooling Equipment Reference
CREATE TABLE IF NOT EXISTS facility.container_cooling_equipment (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    container_model     TEXT NOT NULL,
    cooling_solution_id UUID REFERENCES facility.cooling_solutions(id),
    -- Dry cooler specs
    dry_cooler_model    TEXT,
    dry_cooler_freq_hz_nom NUMERIC(6,2),           -- Normal operating frequency
    dry_cooler_freq_hz_min NUMERIC(6,2),
    dry_cooler_freq_hz_max NUMERIC(6,2),
    dry_cooler_power_kw NUMERIC(6,2),
    -- Fan specs (G21, G22 etc. from BiXBiT)
    fan_count           INTEGER,
    fan_ids             TEXT[],                    -- ['G21', 'G22']
    fan_model           TEXT,
    fan_rpm_nom         INTEGER,
    fan_power_w         NUMERIC(6,2),
    -- Main pump specs (P01)
    main_pump_model     TEXT,
    main_pump_freq_hz_nom NUMERIC(6,2),
    main_pump_freq_hz_min NUMERIC(6,2),
    main_pump_freq_hz_max NUMERIC(6,2),
    main_pump_flow_m3h  NUMERIC(8,3),
    main_pump_power_kw  NUMERIC(6,2),
    -- Filling pump specs (P11)
    filling_pump_model  TEXT,
    filling_pump_flow_lph NUMERIC(8,2),            -- Liters per hour
    -- Power distribution reference
    pmm_count           INTEGER DEFAULT 3,         -- Number of power monitoring modules
    pmm_labels          TEXT[],                    -- ['PMM1', 'PMM2', 'PMM3']
    total_power_capacity_kw NUMERIC(8,2),
    -- PUE reference
    pue_target          NUMERIC(4,3),              -- Target PUE (e.g., 1.05)
    pue_typical         NUMERIC(4,3),              -- Typical observed PUE
    pue_worst_case      NUMERIC(4,3),              -- Worst case observed PUE
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

COMMENT ON TABLE facility.container_cooling_equipment IS
'Reference specs for container-level cooling equipment: dry coolers, circulation fans,
main pumps, filling pumps, power monitoring modules. Maps to container_monitor.py
ContainerCooling data class.';

CREATE INDEX idx_container_cooling_model ON facility.container_cooling_equipment(container_model);
CREATE TRIGGER trg_container_cooling_equip_updated_at
    BEFORE UPDATE ON facility.container_cooling_equipment
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- B3: Container Environment Reference
CREATE TABLE IF NOT EXISTS facility.container_environment_reference (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    container_model     TEXT NOT NULL,
    -- Internal temperature sensors reference
    inside_temp_sensor_count INTEGER,              -- TT21, TT22, etc.
    inside_temp_c_nom   NUMERIC(5,2),
    inside_temp_c_max   NUMERIC(5,2),
    dist_cabinet_temp_c_max NUMERIC(5,2),          -- Distribution cabinet (TT41)
    ctrl_cabinet_temp_c_max NUMERIC(5,2),          -- Control cabinet (TT43)
    -- External conditions reference
    outside_temp_c_min  NUMERIC(5,2),              -- Min operating ambient
    outside_temp_c_max  NUMERIC(5,2),              -- Max operating ambient
    outside_humidity_pct_max NUMERIC(5,2),
    -- Safety thresholds
    tank_level_low_alarm BOOLEAN NOT NULL DEFAULT TRUE,
    leakage_detection_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    smoke_detection_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    emergency_shutdown_temp_c NUMERIC(5,2),
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE facility.container_environment_reference IS
'Reference data for container internal environment: sensor layout, safe temperature
ranges for distribution and control cabinets, safety system enablement.
Maps to container_monitor.py ContainerEnvironment and ContainerSafety data classes.';

CREATE INDEX idx_container_env_model ON facility.container_environment_reference(container_model);
CREATE TRIGGER trg_container_env_ref_updated_at
    BEFORE UPDATE ON facility.container_environment_reference
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- B4: HVAC System Reference — extends facility.hvac_patterns with specific equipment data
ALTER TABLE facility.hvac_patterns
    ADD COLUMN IF NOT EXISTS supply_temp_f_nom NUMERIC(5,2),
    ADD COLUMN IF NOT EXISTS supply_temp_f_min NUMERIC(5,2),
    ADD COLUMN IF NOT EXISTS supply_temp_f_max NUMERIC(5,2),
    ADD COLUMN IF NOT EXISTS return_temp_f_nom NUMERIC(5,2),
    ADD COLUMN IF NOT EXISTS return_temp_f_min NUMERIC(5,2),
    ADD COLUMN IF NOT EXISTS return_temp_f_max NUMERIC(5,2),
    ADD COLUMN IF NOT EXISTS delta_t_f_nom NUMERIC(5,2),
    ADD COLUMN IF NOT EXISTS delta_t_f_min NUMERIC(5,2),
    ADD COLUMN IF NOT EXISTS delta_t_f_max NUMERIC(5,2),
    ADD COLUMN IF NOT EXISTS diff_pressure_psi_nom NUMERIC(6,3),
    ADD COLUMN IF NOT EXISTS diff_pressure_psi_min NUMERIC(6,3),
    ADD COLUMN IF NOT EXISTS diff_pressure_psi_max NUMERIC(6,3),
    -- VFD (Variable Frequency Drive) reference percentages
    ADD COLUMN IF NOT EXISTS cwp1_vfd_pct_nom NUMERIC(5,2),       -- Chilled water pump 1
    ADD COLUMN IF NOT EXISTS cwp2_vfd_pct_nom NUMERIC(5,2),       -- Chilled water pump 2
    ADD COLUMN IF NOT EXISTS ct1_vfd_pct_nom NUMERIC(5,2),        -- Cooling tower fan 1
    ADD COLUMN IF NOT EXISTS ct2_vfd_pct_nom NUMERIC(5,2),        -- Cooling tower fan 2
    ADD COLUMN IF NOT EXISTS ct_fan_pct_nom NUMERIC(5,2),         -- Overall CT fan percentage
    ADD COLUMN IF NOT EXISTS pump_pct_nom NUMERIC(5,2),           -- Overall pump percentage
    -- Cooling tower specs
    ADD COLUMN IF NOT EXISTS cooling_tower_model TEXT,
    ADD COLUMN IF NOT EXISTS cooling_tower_capacity_kw NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS cooling_tower_fan_count INTEGER,
    -- Spray pump reference
    ADD COLUMN IF NOT EXISTS spray_pump_model TEXT,
    ADD COLUMN IF NOT EXISTS spray_pump_flow_gpm NUMERIC(8,2),
    -- Basin reference
    ADD COLUMN IF NOT EXISTS basin_capacity_gal NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS basin_level_low_alarm_gal NUMERIC(10,2),
    -- Known fault patterns
    ADD COLUMN IF NOT EXISTS ct_fault_common_causes JSONB NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS pump_fault_common_causes JSONB NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS tower_vibration_causes JSONB NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS leak_alarm_common_causes JSONB NOT NULL DEFAULT '[]';

COMMENT ON COLUMN facility.hvac_patterns.cwp1_vfd_pct_nom IS
'Nominal VFD percentage for chilled water pump 1. Maps to hvac_client.py cwp1_vfd field.
Bobby monitors this to detect pump degradation.';

COMMENT ON COLUMN facility.hvac_patterns.ct_fault_common_causes IS
'Known causes for cooling tower fan faults. Maps to hvac_client.py ct1_fault/ct2_fault.
Example: [{"cause": "belt slip", "likelihood": "high"}, {"cause": "motor overtemp", "likelihood": "medium"}]';


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  SECTION C: IMMERSION COOLING FLUID INTELLIGENCE                        ║
-- ║  Industry gap — critical for Bobby's liquid-cooled fleet                ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- C1: Immersion Cooling Fluids — comprehensive fluid reference
CREATE TABLE IF NOT EXISTS facility.immersion_fluids (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fluid_name          TEXT NOT NULL,             -- 'Engineered Fluids ElectroCool EC-110'
    brand               TEXT NOT NULL,             -- 'Engineered Fluids', '3M', 'Shell'
    product_line        TEXT,                      -- 'ElectroCool', 'Novec', 'Thermia'
    fluid_type          TEXT NOT NULL,             -- 'mineral_oil', 'synthetic', 'two_phase', 'hydrocarbon', 'silicone'
    -- Physical properties
    dielectric_strength_kv NUMERIC(8,2),           -- kV breakdown voltage
    viscosity_cst_25c   NUMERIC(8,3),              -- Kinematic viscosity at 25°C in centistokes
    viscosity_cst_40c   NUMERIC(8,3),              -- Kinematic viscosity at 40°C
    viscosity_cst_100c  NUMERIC(8,3),              -- Kinematic viscosity at 100°C
    density_kg_m3       NUMERIC(8,3),              -- Density at 25°C
    specific_heat_j_kg_k NUMERIC(8,2),             -- Specific heat capacity
    thermal_conductivity_w_mk NUMERIC(6,4),        -- Thermal conductivity
    pour_point_c        NUMERIC(5,2),              -- Pour point (cold flow limit)
    flash_point_c       NUMERIC(5,2),              -- Flash point
    fire_point_c        NUMERIC(5,2),              -- Fire point
    boiling_point_c     NUMERIC(5,2),              -- Boiling point (critical for two-phase)
    -- Operating parameters
    operating_temp_min_c NUMERIC(5,2),
    operating_temp_max_c NUMERIC(5,2),
    max_chip_temp_c     NUMERIC(5,2),              -- Maximum recommended chip temp in this fluid
    -- Fluid lifecycle
    expected_lifespan_years NUMERIC(4,1),
    color_new           TEXT,                      -- 'clear', 'amber', 'blue'
    color_degraded      TEXT,                      -- What color indicates degradation
    acid_number_max_mg_koh NUMERIC(6,3),           -- Max total acid number before replacement
    water_content_max_ppm NUMERIC(8,2),            -- Max water content
    -- Volume & cost
    volume_per_miner_liters NUMERIC(8,2),          -- Typical volume per miner
    cost_per_liter_usd  NUMERIC(8,2),
    cost_per_gallon_usd NUMERIC(8,2),
    -- Compatibility
    compatible_materials JSONB NOT NULL DEFAULT '[]', -- Materials safe for contact
    incompatible_materials JSONB NOT NULL DEFAULT '[]', -- Materials that degrade in this fluid
    compatible_cooling_ids UUID[],                 -- facility.cooling_solutions IDs
    -- Safety
    sds_url             TEXT,                      -- Safety data sheet URL
    is_food_safe        BOOLEAN,
    is_biodegradable    BOOLEAN,
    ghs_hazard_codes    TEXT[],                    -- GHS hazard classification codes
    disposal_requirements TEXT,
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    verified_by_bobby   BOOLEAN NOT NULL DEFAULT FALSE,
    notes               TEXT,
    search_vector       TSVECTOR,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ
);

COMMENT ON TABLE facility.immersion_fluids IS
'Comprehensive immersion cooling fluid reference. Every property Bobby needs to evaluate,
procure, and maintain cooling fluids for the BiXBiT fleet. Includes dielectric strength,
viscosity curves, thermal properties, fluid lifecycle indicators, and compatibility data.';

CREATE INDEX idx_immersion_fluids_brand ON facility.immersion_fluids(brand);
CREATE INDEX idx_immersion_fluids_type ON facility.immersion_fluids(fluid_type);
CREATE INDEX idx_immersion_fluids_search ON facility.immersion_fluids USING GIN(search_vector);
CREATE INDEX idx_immersion_fluids_active ON facility.immersion_fluids(id) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_immersion_fluids_updated_at
    BEFORE UPDATE ON facility.immersion_fluids
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_immersion_fluids_search_vector
    BEFORE INSERT OR UPDATE ON facility.immersion_fluids
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(search_vector, 'pg_catalog.english', fluid_name, brand, product_line, notes);


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  SECTION D: POWER & ELECTRICITY INTELLIGENCE                            ║
-- ║  Rate structures, demand response, curtailment                          ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- D1: Electricity Rate Structures — utility rate intelligence
CREATE TABLE IF NOT EXISTS facility.electricity_rates (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility_id         UUID REFERENCES facility.facilities(id),
    utility_name        TEXT NOT NULL,             -- 'Oncor', 'TXU Energy', etc.
    rate_plan_name      TEXT NOT NULL,             -- 'Large General Service TOU'
    rate_plan_code      TEXT,                      -- Utility's plan code
    contract_type       TEXT,                      -- 'fixed', 'variable', 'indexed', 'ppa', 'behind_the_meter'
    -- Rate components
    energy_rate_kwh_usd NUMERIC(8,5),              -- $/kWh energy charge
    demand_charge_kw_usd NUMERIC(8,4),             -- $/kW demand charge
    transmission_kwh_usd NUMERIC(8,5),             -- Transmission component
    distribution_kwh_usd NUMERIC(8,5),             -- Distribution component
    ancillary_kwh_usd  NUMERIC(8,5),               -- Ancillary services
    total_all_in_kwh_usd NUMERIC(8,5),             -- Total all-in rate
    -- Time-of-use tiers
    peak_rate_kwh_usd   NUMERIC(8,5),
    peak_hours           TEXT,                     -- 'M-F 2pm-7pm Jun-Sep'
    off_peak_rate_kwh_usd NUMERIC(8,5),
    off_peak_hours       TEXT,
    super_off_peak_rate_kwh_usd NUMERIC(8,5),
    super_off_peak_hours TEXT,                     -- 'Daily 12am-6am'
    -- Contract terms
    contract_start_date DATE,
    contract_end_date   DATE,
    minimum_usage_kw    NUMERIC(8,2),
    penalty_for_under_usage NUMERIC(10,2),
    -- Effective period
    effective_from      DATE NOT NULL,
    effective_to        DATE,
    is_current          BOOLEAN NOT NULL DEFAULT TRUE,
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'high',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE facility.electricity_rates IS
'Complete electricity rate intelligence per facility. Bobby needs this for profitability
modeling, curtailment decisions, and understanding the true cost per TH/s per day.
Tracks all rate components: energy, demand, transmission, distribution, ancillary.';

CREATE INDEX idx_electricity_rates_facility ON facility.electricity_rates(facility_id);
CREATE INDEX idx_electricity_rates_current ON facility.electricity_rates(facility_id) WHERE is_current = TRUE;

CREATE TRIGGER trg_electricity_rates_updated_at
    BEFORE UPDATE ON facility.electricity_rates
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- D2: Demand Response / Curtailment Intelligence
CREATE TABLE IF NOT EXISTS facility.demand_response_programs (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility_id         UUID REFERENCES facility.facilities(id),
    program_name        TEXT NOT NULL,             -- 'ERCOT 4CP', 'ERCOT ERS', 'Direct Load Control'
    program_operator    TEXT NOT NULL,             -- 'ERCOT', 'Oncor', 'TXU'
    program_type        TEXT NOT NULL,             -- '4cp', 'ers', 'demand_response', 'interruptible', 'curtailment'
    -- Program parameters
    notification_lead_time_min INTEGER,            -- Minutes of advance notice
    min_curtailment_mw  NUMERIC(8,3),              -- Minimum load reduction
    max_duration_hours  NUMERIC(6,2),              -- Maximum curtailment duration
    max_events_per_month INTEGER,
    max_events_per_year INTEGER,
    season              TEXT,                      -- 'summer', 'winter', 'year_round'
    eligible_hours      TEXT,                      -- 'M-F 1pm-7pm Jun-Sep'
    -- Financial
    capacity_payment_kw_month_usd NUMERIC(8,4),    -- Monthly capacity payment
    energy_payment_kwh_usd NUMERIC(8,5),           -- Per-kWh payment during curtailment
    penalty_non_compliance_usd NUMERIC(10,2),      -- Penalty for not curtailing
    estimated_annual_revenue_usd NUMERIC(12,2),
    -- Operational
    ramp_down_time_min  INTEGER,                   -- How fast Bobby can ramp down
    ramp_up_time_min    INTEGER,                   -- How fast Bobby can ramp back up
    miners_affected     INTEGER,                   -- How many miners go offline
    hashrate_loss_th    NUMERIC(12,2),             -- TH/s lost during curtailment
    btc_opportunity_cost_per_hour_usd NUMERIC(10,2),
    -- Status
    enrolled            BOOLEAN NOT NULL DEFAULT FALSE,
    enrollment_date     DATE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE facility.demand_response_programs IS
'Demand response and curtailment program intelligence for Bobby''s Fort Worth facility.
ERCOT 4CP is critical — avoiding the 15-minute peak windows can save tens of thousands
in demand charges. Tracks notification time, financials, and operational impact.';

CREATE INDEX idx_dr_programs_facility ON facility.demand_response_programs(facility_id);
CREATE INDEX idx_dr_programs_active ON facility.demand_response_programs(id) WHERE is_active = TRUE;

CREATE TRIGGER trg_dr_programs_updated_at
    BEFORE UPDATE ON facility.demand_response_programs
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- D3: Curtailment Event History — reference intelligence
CREATE TABLE IF NOT EXISTS facility.curtailment_events (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility_id         UUID REFERENCES facility.facilities(id),
    program_id          UUID REFERENCES facility.demand_response_programs(id),
    event_date          DATE NOT NULL,
    event_start         TIMESTAMPTZ NOT NULL,
    event_end           TIMESTAMPTZ,
    duration_minutes    INTEGER,
    -- Grid conditions
    grid_signal         TEXT,                      -- 'ERCOT conservation appeal', 'EEA Level 1', etc.
    real_time_price_mwh NUMERIC(10,2),             -- Real-time LMP at event time
    day_ahead_price_mwh NUMERIC(10,2),
    -- Response
    load_reduced_kw     NUMERIC(8,2),
    miners_curtailed    INTEGER,
    hashrate_lost_th    NUMERIC(12,2),
    -- Financial impact
    curtailment_payment_usd NUMERIC(10,2),
    btc_mining_lost_usd NUMERIC(10,2),
    net_financial_impact_usd NUMERIC(10,2),        -- Payment minus lost mining
    -- Decision
    was_voluntary       BOOLEAN NOT NULL DEFAULT TRUE,
    decision_rationale  TEXT,
    decided_by          TEXT,                      -- 'bobby', 'auto_guardian', 'manual'
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE facility.curtailment_events IS
'Historical curtailment event intelligence. Every time Bobby shuts down miners for
demand response or grid economics. Tracks financial impact: was it profitable to curtail?
Feeds the LLM''s decision engine for future curtailment recommendations.';

CREATE INDEX idx_curtailment_facility ON facility.curtailment_events(facility_id, event_date);
CREATE INDEX idx_curtailment_program ON facility.curtailment_events(program_id);

CREATE TRIGGER trg_curtailment_events_updated_at
    BEFORE UPDATE ON facility.curtailment_events
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  SECTION E: DEPRECIATION / TAX / FINANCIAL INTELLIGENCE                 ║
-- ║  Bobby asked for: "original cost" — extends to full financial lifecycle  ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- E1: Asset Depreciation Schedules — per-model depreciation intelligence
CREATE TABLE IF NOT EXISTS market.depreciation_schedules (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_model_id      UUID REFERENCES hardware.miner_models(id),
    -- Purchase context
    acquisition_cost_usd NUMERIC(12,2),            -- Original purchase price
    acquisition_date    DATE,
    acquisition_method  TEXT,                      -- 'new_purchase', 'used_purchase', 'trade', 'gift'
    vendor_name         TEXT,
    includes_psu        BOOLEAN,
    -- Tax depreciation
    depreciation_method TEXT NOT NULL,              -- 'MACRS_5yr', 'MACRS_7yr', 'straight_line', 'section_179', 'bonus_100pct'
    useful_life_years   NUMERIC(4,1) NOT NULL DEFAULT 5,
    salvage_value_usd   NUMERIC(10,2) NOT NULL DEFAULT 0,
    section_179_eligible BOOLEAN NOT NULL DEFAULT TRUE,
    bonus_depreciation_pct NUMERIC(5,2),           -- 80% for 2024, 60% for 2025, 40% for 2026
    bonus_depreciation_year INTEGER,
    tax_year            INTEGER,
    -- Depreciation amounts (pre-computed per year)
    year1_depreciation_usd NUMERIC(12,2),
    year2_depreciation_usd NUMERIC(12,2),
    year3_depreciation_usd NUMERIC(12,2),
    year4_depreciation_usd NUMERIC(12,2),
    year5_depreciation_usd NUMERIC(12,2),
    accumulated_depreciation_usd NUMERIC(12,2),
    current_book_value_usd NUMERIC(12,2),
    -- Market value tracking
    current_market_value_usd NUMERIC(12,2),
    market_value_date   DATE,
    unrealized_gain_loss_usd NUMERIC(12,2),        -- Market value minus book value
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE market.depreciation_schedules IS
'Asset depreciation intelligence per miner model. Tracks MACRS 5-year, Section 179,
and bonus depreciation schedules. Bobby needs this for tax planning and knowing
when a miner''s book value justifies repair vs. replace decisions.';

CREATE INDEX idx_depreciation_model ON market.depreciation_schedules(miner_model_id);
CREATE INDEX idx_depreciation_year ON market.depreciation_schedules(tax_year);

CREATE TRIGGER trg_depreciation_schedules_updated_at
    BEFORE UPDATE ON market.depreciation_schedules
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- E2: Resale Value Tracking — market depreciation curves
CREATE TABLE IF NOT EXISTS market.resale_value_history (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_model_id      UUID NOT NULL REFERENCES hardware.miner_models(id),
    observation_date    DATE NOT NULL,
    age_days            INTEGER,                   -- Days since model release
    -- Value observations
    avg_resale_usd      NUMERIC(10,2),
    min_resale_usd      NUMERIC(10,2),
    max_resale_usd      NUMERIC(10,2),
    sample_size         INTEGER,
    condition           TEXT NOT NULL DEFAULT 'used_good', -- 'used_excellent', 'used_good', 'used_fair', 'for_parts'
    includes_psu        BOOLEAN,
    -- Context at observation time
    btc_price_usd       NUMERIC(12,2),
    network_difficulty   NUMERIC(20,2),
    hashprice_usd_per_th NUMERIC(8,4),             -- Revenue per TH per day
    -- Depreciation rate
    pct_of_original_msrp NUMERIC(6,2),             -- e.g., 45% of MSRP
    monthly_depreciation_rate NUMERIC(6,4),        -- Monthly % decline
    -- Source
    source_platform     TEXT,                      -- 'eBay', 'Kaboom', 'AsicMarketplace', 'direct'
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'low',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE market.resale_value_history IS
'Tracks actual resale values over time per model. Combined with depreciation_schedules,
Bobby can see: "My S19 Pro is worth $400 on the market but $0 on the books — time to
sell and capture the gain." Feeds repair-vs-replace decision engine.';

CREATE INDEX idx_resale_model_date ON market.resale_value_history(miner_model_id, observation_date);
CREATE INDEX idx_resale_condition ON market.resale_value_history(condition);

CREATE TRIGGER trg_resale_value_updated_at
    BEFORE UPDATE ON market.resale_value_history
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  SECTION F: PER-CHIP DIAGNOSTIC REFERENCE DATA                          ║
-- ║  Hashboard signal chain, diode-mode readings, domain resistance         ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- F1: Chip Diagnostic Reference — expected values per chip model
ALTER TABLE hardware.chips
    ADD COLUMN IF NOT EXISTS diode_mode_reading_v_nom NUMERIC(6,4),    -- Normal diode-mode voltage
    ADD COLUMN IF NOT EXISTS diode_mode_reading_v_min NUMERIC(6,4),
    ADD COLUMN IF NOT EXISTS diode_mode_reading_v_max NUMERIC(6,4),
    ADD COLUMN IF NOT EXISTS domain_resistance_ohm_nom NUMERIC(8,4),   -- Normal domain resistance
    ADD COLUMN IF NOT EXISTS domain_resistance_ohm_min NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS domain_resistance_ohm_max NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS thermal_signature_profile JSONB,          -- Expected thermal gradient pattern
    ADD COLUMN IF NOT EXISTS nonce_error_rate_ppm_nom NUMERIC(8,2),   -- Normal nonce error rate (parts per million)
    ADD COLUMN IF NOT EXISTS max_stable_voltage_mv NUMERIC(6,2),       -- Maximum stable operating voltage
    ADD COLUMN IF NOT EXISTS min_stable_voltage_mv NUMERIC(6,2),       -- Minimum stable operating voltage
    ADD COLUMN IF NOT EXISTS voltage_step_mv NUMERIC(6,2),             -- Granularity of voltage adjustment
    ADD COLUMN IF NOT EXISTS frequency_step_mhz NUMERIC(6,2),         -- Granularity of frequency adjustment
    ADD COLUMN IF NOT EXISTS leakage_current_ua_nom NUMERIC(8,2);     -- Typical leakage current

COMMENT ON COLUMN hardware.chips.diode_mode_reading_v_nom IS
'Expected diode-mode multimeter reading across the chip. Bobby uses this to identify
dead chips during board-level diagnostics. Out-of-range = suspect chip.';


-- F2: Hashboard Signal Chain Reference
CREATE TABLE IF NOT EXISTS hardware.signal_chain_reference (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hashboard_id        UUID NOT NULL REFERENCES hardware.hashboards(id),
    signal_name         TEXT NOT NULL,             -- 'RX', 'TX', 'CLK', 'CHK', 'RST', 'RI', 'RO', 'CI', 'CO', 'BO'
    signal_type         TEXT NOT NULL,             -- 'data', 'clock', 'check', 'reset', 'power_good', 'temperature'
    signal_path         TEXT,                      -- 'control_board → chip_0 → chip_1 → ... → chip_N → return'
    -- Expected values
    voltage_high_v      NUMERIC(6,4),              -- Logic HIGH voltage
    voltage_low_v       NUMERIC(6,4),              -- Logic LOW voltage
    frequency_mhz       NUMERIC(8,3),              -- Expected frequency for clock signals
    duty_cycle_pct      NUMERIC(5,2),              -- Expected duty cycle
    -- Measurement points
    test_point_locations TEXT[],                   -- ['TP1 (near U1)', 'TP2 (near U30)', ...]
    oscilloscope_settings TEXT,                    -- 'Timebase: 1µs/div, Voltage: 1V/div, Trigger: Rising edge'
    -- Failure indicators
    absent_signal_means TEXT,                      -- 'Dead chip at position N' or 'Open trace'
    weak_signal_means   TEXT,                      -- 'Marginal chip' or 'Corroded via'
    noisy_signal_means  TEXT,                      -- 'Decoupling cap failure' or 'Ground loop'
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    verified_by_bobby   BOOLEAN NOT NULL DEFAULT FALSE,
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE hardware.signal_chain_reference IS
'Hashboard signal chain reference data. For each signal (RX, CLK, CHK, etc.), documents
expected voltages, frequencies, test points, and what abnormal readings mean. Bobby uses
this during board-level repair diagnostics. Critical for identifying dead/marginal chips.';

CREATE INDEX idx_signal_chain_board ON hardware.signal_chain_reference(hashboard_id);
CREATE INDEX idx_signal_chain_signal ON hardware.signal_chain_reference(signal_name);

CREATE TRIGGER trg_signal_chain_ref_updated_at
    BEFORE UPDATE ON hardware.signal_chain_reference
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- F3: Test Fixture / Diagnostic Tool Specifications
CREATE TABLE IF NOT EXISTS repair.diagnostic_tools (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tool_name           TEXT NOT NULL,             -- 'Antminer Test Fixture V3', 'BM1397 Test Jig'
    tool_type           TEXT NOT NULL,             -- 'test_fixture', 'multimeter', 'oscilloscope', 'thermal_camera', 'bga_rework', 'hot_air'
    manufacturer        TEXT,
    model_number        TEXT,
    -- Capabilities
    compatible_boards   UUID[],                    -- hashboard IDs this tool works with
    compatible_models   UUID[],                    -- miner_model IDs
    measurements        TEXT[],                    -- ['voltage', 'current', 'resistance', 'continuity', 'frequency']
    accuracy            TEXT,                      -- '±0.5% reading ±2 digits'
    -- Usage
    typical_use_cases   JSONB NOT NULL DEFAULT '[]',
    setup_instructions  TEXT,
    safety_warnings     TEXT,
    -- Cost & sourcing
    purchase_price_usd  NUMERIC(10,2),
    purchase_url        TEXT,
    supplier_name       TEXT,
    -- Bobby's inventory
    bobby_owns          BOOLEAN NOT NULL DEFAULT FALSE,
    bobby_rating        INTEGER CHECK (bobby_rating BETWEEN 1 AND 10),
    bobby_notes         TEXT,
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE repair.diagnostic_tools IS
'Diagnostic tool and test fixture reference. Bobby needs to know which tools work with
which boards, what they cost, and where to buy them. Includes his personal inventory
and ratings.';

CREATE INDEX idx_diag_tools_type ON repair.diagnostic_tools(tool_type);

CREATE TRIGGER trg_diagnostic_tools_updated_at
    BEFORE UPDATE ON repair.diagnostic_tools
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  SECTION G: WEATHER CORRELATION REFERENCE                               ║
-- ║  Maps to guardian.db weather_readings + container_monitor environment    ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- G1: Extend ops.environmental_correlations with weather-specific fields
ALTER TABLE ops.environmental_correlations
    ADD COLUMN IF NOT EXISTS ambient_temp_impact_th_per_c NUMERIC(6,4),  -- TH/s lost per degree C ambient increase
    ADD COLUMN IF NOT EXISTS humidity_impact_th_per_pct NUMERIC(6,4),    -- TH/s impact per % humidity change
    ADD COLUMN IF NOT EXISTS wind_speed_impact TEXT,                     -- Qualitative: 'high winds improve air-cooled, no impact on immersion'
    ADD COLUMN IF NOT EXISTS barometric_pressure_impact TEXT,
    ADD COLUMN IF NOT EXISTS dew_point_impact TEXT,                      -- 'Condensation risk below X°F dew point'
    ADD COLUMN IF NOT EXISTS season_adjustment_factor JSONB,             -- {"summer": 0.95, "winter": 1.02} — hashrate multiplier
    ADD COLUMN IF NOT EXISTS optimal_ambient_temp_c NUMERIC(5,2),       -- Best performance ambient temp
    ADD COLUMN IF NOT EXISTS performance_at_35c_pct NUMERIC(5,2),       -- % of nominal at 35°C ambient
    ADD COLUMN IF NOT EXISTS performance_at_40c_pct NUMERIC(5,2),       -- % of nominal at 40°C ambient
    ADD COLUMN IF NOT EXISTS performance_at_45c_pct NUMERIC(5,2);       -- % of nominal at 45°C ambient

-- G2: Weather Reference Patterns — Fort Worth and other locations
CREATE TABLE IF NOT EXISTS facility.weather_reference (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility_id         UUID REFERENCES facility.facilities(id),
    month               INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    -- Temperature reference
    avg_temp_f          NUMERIC(5,2),
    avg_temp_high_f     NUMERIC(5,2),
    avg_temp_low_f      NUMERIC(5,2),
    record_high_f       NUMERIC(5,2),
    record_low_f        NUMERIC(5,2),
    days_above_100f     INTEGER,
    days_below_32f      INTEGER,
    -- Humidity reference
    avg_humidity_pct    NUMERIC(5,2),
    avg_humidity_max_pct NUMERIC(5,2),
    avg_humidity_min_pct NUMERIC(5,2),
    -- Weather events
    avg_precip_inches   NUMERIC(6,2),
    avg_precip_days     INTEGER,
    avg_snow_inches     NUMERIC(6,2),
    severe_storm_days   INTEGER,
    -- Impact on mining
    expected_hashrate_adjustment_pct NUMERIC(5,2), -- % adjustment from baseline
    expected_pue_adjustment NUMERIC(4,3),          -- PUE adjustment from baseline
    cooling_mode_recommendation TEXT,              -- 'normal', 'eco', 'high_performance'
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (facility_id, month)
);

COMMENT ON TABLE facility.weather_reference IS
'Monthly weather reference data per facility location. Helps the LLM understand seasonal
patterns: "It''s July in Fort Worth, expect 100°F+ days, adjust hashrate expectations
down 3-5%, watch PUE closely." Also useful for planning maintenance windows.';

CREATE INDEX idx_weather_ref_facility ON facility.weather_reference(facility_id);

CREATE TRIGGER trg_weather_ref_updated_at
    BEFORE UPDATE ON facility.weather_reference
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  SECTION H: ADDITIONAL MINER MODEL FIELDS                              ║
-- ║  Bobby's tear sheet + industry standard gaps                            ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- H1: Extend hardware.miner_models with tear-sheet / completeness fields
ALTER TABLE hardware.miner_models
    ADD COLUMN IF NOT EXISTS years_in_production INTEGER,
    ADD COLUMN IF NOT EXISTS production_start_year INTEGER,
    ADD COLUMN IF NOT EXISTS production_end_year INTEGER,
    ADD COLUMN IF NOT EXISTS is_discontinued BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS warranty_months INTEGER,
    ADD COLUMN IF NOT EXISTS warranty_terms TEXT,
    ADD COLUMN IF NOT EXISTS noise_db_typical NUMERIC(5,1),           -- dB(A) at 1 meter
    ADD COLUMN IF NOT EXISTS noise_db_max NUMERIC(5,1),
    ADD COLUMN IF NOT EXISTS operating_altitude_max_m INTEGER,        -- Max altitude in meters
    ADD COLUMN IF NOT EXISTS shipping_weight_kg NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS package_dimensions_mm JSONB,             -- {"length": 600, "width": 400, "height": 300}
    ADD COLUMN IF NOT EXISTS total_chips_per_unit INTEGER,            -- Total ASIC chip count
    ADD COLUMN IF NOT EXISTS rated_voltage_dc_v NUMERIC(6,2),        -- DC voltage to hashboards
    ADD COLUMN IF NOT EXISTS rated_hertz_across_hashboards NUMERIC(8,3), -- Bobby asked: "Hertz across dashboards"
    ADD COLUMN IF NOT EXISTS rated_voltage_across_hashboards NUMERIC(6,3), -- Bobby asked: "Voltage across dashboards"
    ADD COLUMN IF NOT EXISTS ethernet_port_count INTEGER DEFAULT 1,
    ADD COLUMN IF NOT EXISTS usb_port_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS reset_button_type TEXT,                  -- 'physical', 'ip_button', 'paperclip'
    ADD COLUMN IF NOT EXISTS led_indicators JSONB,                    -- [{"color": "green", "meaning": "normal"}, ...]
    ADD COLUMN IF NOT EXISTS power_connector_type TEXT,               -- 'C13', 'C19', 'direct_wire'
    ADD COLUMN IF NOT EXISTS power_connector_count INTEGER,
    ADD COLUMN IF NOT EXISTS hashboard_connector_type TEXT,           -- '2x9 pin', '2x10 pin'
    ADD COLUMN IF NOT EXISTS data_connector_type TEXT,                -- '18-pin', '20-pin ribbon cable'
    ADD COLUMN IF NOT EXISTS fan_connector_type TEXT,                 -- '4-pin PWM', '2-pin DC'
    ADD COLUMN IF NOT EXISTS typical_daily_btc_at_launch NUMERIC(12,8), -- BTC/day when launched
    ADD COLUMN IF NOT EXISTS break_even_days_at_launch INTEGER,       -- Days to ROI at launch price/diff
    ADD COLUMN IF NOT EXISTS roi_btc_price_at_launch NUMERIC(12,2);

COMMENT ON COLUMN hardware.miner_models.rated_hertz_across_hashboards IS
'Bobby asked: "Hertz across dashboards" — the rated chip operating frequency in MHz
as measured at the hashboard level. Different from per-chip frequency_mhz due to
signal chain effects.';


-- H2: Extend hardware.hashboards with additional reference fields
ALTER TABLE hardware.hashboards
    ADD COLUMN IF NOT EXISTS signal_chain_type TEXT,                  -- 'daisy_chain', 'star', 'tree'
    ADD COLUMN IF NOT EXISTS data_connector_pin_count INTEGER,
    ADD COLUMN IF NOT EXISTS power_connector_pin_count INTEGER,
    ADD COLUMN IF NOT EXISTS layer_count INTEGER,                     -- PCB layers (4, 6, 8)
    ADD COLUMN IF NOT EXISTS copper_weight_oz NUMERIC(4,2),          -- Copper weight per layer
    ADD COLUMN IF NOT EXISTS solder_type TEXT,                       -- 'lead_free_SAC305', 'leaded_SN63PB37'
    ADD COLUMN IF NOT EXISTS heatsink_type TEXT,                     -- 'aluminum_finned', 'copper_baseplate', 'none'
    ADD COLUMN IF NOT EXISTS heatsink_attachment TEXT,                -- 'thermal_paste', 'thermal_pad', 'soldered'
    ADD COLUMN IF NOT EXISTS thermal_pad_thickness_mm NUMERIC(4,2),
    ADD COLUMN IF NOT EXISTS domain_count INTEGER,                   -- Number of voltage domains
    ADD COLUMN IF NOT EXISTS chips_per_domain INTEGER,               -- Chips per voltage domain
    ADD COLUMN IF NOT EXISTS buck_converter_model TEXT,               -- Voltage regulator IC model
    ADD COLUMN IF NOT EXISTS buck_converter_count INTEGER,
    ADD COLUMN IF NOT EXISTS weight_g NUMERIC(8,2);                  -- Board weight in grams

COMMENT ON COLUMN hardware.hashboards.domain_count IS
'Number of voltage domains on the hashboard. Each domain has its own buck converter
and voltage rail. Critical for diagnostics: a dead domain means a specific set of chips.';


-- H3: Extend hardware.control_boards with additional reference fields
ALTER TABLE hardware.control_boards
    ADD COLUMN IF NOT EXISTS serial_number_format TEXT,
    ADD COLUMN IF NOT EXISTS os_type TEXT,                           -- 'Linux', 'BusyBox', 'custom'
    ADD COLUMN IF NOT EXISTS os_version TEXT,
    ADD COLUMN IF NOT EXISTS bootloader_type TEXT,                   -- 'U-Boot', 'custom'
    ADD COLUMN IF NOT EXISTS sd_card_slot BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS emmc_size_gb NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS gpio_pin_count INTEGER,
    ADD COLUMN IF NOT EXISTS i2c_bus_count INTEGER,
    ADD COLUMN IF NOT EXISTS spi_bus_count INTEGER,
    ADD COLUMN IF NOT EXISTS fan_header_count INTEGER,
    ADD COLUMN IF NOT EXISTS hashboard_connector_count INTEGER,
    ADD COLUMN IF NOT EXISTS power_input_connector TEXT,
    ADD COLUMN IF NOT EXISTS weight_g NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(10,2);


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  SECTION I: KNOWLEDGE.JSON INTELLIGENCE MAPPING                         ║
-- ║  Maps knowledge.json structure into catalog reference tables             ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- I1: LLM Analysis Reference — maps to llm_analysis table in guardian.db
CREATE TABLE IF NOT EXISTS knowledge.llm_analysis_patterns (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_type       TEXT NOT NULL,             -- 'local_llm', 'claude_weekly', 'daily_deep_dive', 'hvac_correlation'
    pattern_category    TEXT NOT NULL,             -- 'thermal_anomaly', 'hashrate_decline', 'power_anomaly', 'board_failure'
    pattern_description TEXT NOT NULL,
    detection_criteria  JSONB NOT NULL DEFAULT '{}', -- Machine-readable detection rules
    -- Historical accuracy
    total_predictions   INTEGER NOT NULL DEFAULT 0,
    correct_predictions INTEGER NOT NULL DEFAULT 0,
    accuracy_pct        NUMERIC(5,2),
    false_positive_rate NUMERIC(5,2),
    avg_lead_time_hours NUMERIC(8,2),              -- How far in advance detected before event
    -- Action mapping
    recommended_actions JSONB NOT NULL DEFAULT '[]',
    auto_action_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    requires_approval   BOOLEAN NOT NULL DEFAULT TRUE,
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE knowledge.llm_analysis_patterns IS
'Reference intelligence for LLM analysis patterns. Maps to knowledge.json patterns[]
and llm_analysis table in guardian.db. Tracks prediction accuracy over time so the
system can learn which patterns are reliable and which generate false positives.';

CREATE INDEX idx_llm_patterns_type ON knowledge.llm_analysis_patterns(analysis_type);
CREATE INDEX idx_llm_patterns_category ON knowledge.llm_analysis_patterns(pattern_category);

CREATE TRIGGER trg_llm_patterns_updated_at
    BEFORE UPDATE ON knowledge.llm_analysis_patterns
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- I2: Miner Baseline Reference — maps to miner_baselines in guardian.db
CREATE TABLE IF NOT EXISTS ops.miner_baseline_reference (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_model_id      UUID NOT NULL REFERENCES hardware.miner_models(id),
    firmware_id         UUID REFERENCES firmware.firmware_releases(id),
    cooling_type        public.cooling_type NOT NULL DEFAULT 'immersion',
    operational_mode    TEXT NOT NULL DEFAULT 'normal',
    -- Baseline ranges (what "normal" looks like for this config)
    hashrate_th_baseline NUMERIC(10,3),
    hashrate_th_stddev  NUMERIC(8,3),
    hashrate_pct_warning_low NUMERIC(5,2) NOT NULL DEFAULT 85,
    hashrate_pct_critical_low NUMERIC(5,2) NOT NULL DEFAULT 70,
    power_w_baseline    NUMERIC(10,2),
    power_w_stddev      NUMERIC(8,2),
    efficiency_j_th_baseline NUMERIC(6,3),
    chip_temp_c_baseline NUMERIC(5,2),
    chip_temp_c_stddev  NUMERIC(5,2),
    board_temp_c_baseline NUMERIC(5,2),
    hw_error_rate_baseline NUMERIC(8,4),           -- Hardware errors per hour baseline
    -- Calculation metadata
    sample_period_start TIMESTAMPTZ,
    sample_period_end   TIMESTAMPTZ,
    sample_count        INTEGER,
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    verified_by_bobby   BOOLEAN NOT NULL DEFAULT FALSE,
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ops.miner_baseline_reference IS
'Reference baselines for miner performance by model/firmware/cooling combo.
Maps to guardian.db miner_baselines table. Tells the LLM what "normal" hashrate,
power, temp, and efficiency look like for each configuration so deviations
trigger meaningful alerts, not noise.';

CREATE INDEX idx_miner_baseline_model ON ops.miner_baseline_reference(miner_model_id);
CREATE INDEX idx_miner_baseline_combo ON ops.miner_baseline_reference(miner_model_id, firmware_id, cooling_type);

CREATE TRIGGER trg_miner_baseline_ref_updated_at
    BEFORE UPDATE ON ops.miner_baseline_reference
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  SECTION J: MISCELLANEOUS GAPS                                          ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- J1: Extend facility.cooling_solutions with immersion-specific fields
ALTER TABLE facility.cooling_solutions
    ADD COLUMN IF NOT EXISTS fluid_id UUID REFERENCES facility.immersion_fluids(id),
    ADD COLUMN IF NOT EXISTS fluid_change_interval_months INTEGER,
    ADD COLUMN IF NOT EXISTS fluid_test_interval_months INTEGER,
    ADD COLUMN IF NOT EXISTS fluid_cost_per_fill_usd NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS immersion_tank_material TEXT,            -- 'stainless_steel', 'aluminum', 'polypropylene'
    ADD COLUMN IF NOT EXISTS immersion_tank_volume_liters NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS immersion_tank_dimensions_mm JSONB,     -- {"length": 1200, "width": 800, "height": 600}
    ADD COLUMN IF NOT EXISTS max_heat_rejection_kw NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS dry_cooler_model TEXT,
    ADD COLUMN IF NOT EXISTS dry_cooler_capacity_kw NUMERIC(8,2);


-- J2: Extend pool.mining_pools with additional intelligence
ALTER TABLE pool.mining_pools
    ADD COLUMN IF NOT EXISTS payout_method TEXT,                     -- 'on-chain', 'lightning', 'both'
    ADD COLUMN IF NOT EXISTS lightning_enabled BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS supports_hashrate_proof BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS transparency_score NUMERIC(4,2),        -- 0-10 transparency rating
    ADD COLUMN IF NOT EXISTS governance_model TEXT,                  -- 'centralized', 'decentralized', 'dao'
    ADD COLUMN IF NOT EXISTS insurance_fund BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS kyc_required BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS country_restrictions TEXT[];             -- Countries where pool is blocked


-- J3: Extend ops.operational_thresholds with container-monitor-specific thresholds
ALTER TABLE ops.operational_thresholds
    ADD COLUMN IF NOT EXISTS supply_temp_c_warning NUMERIC(5,2),
    ADD COLUMN IF NOT EXISTS supply_temp_c_critical NUMERIC(5,2),
    ADD COLUMN IF NOT EXISTS return_pressure_mpa_warning NUMERIC(6,4),
    ADD COLUMN IF NOT EXISTS return_pressure_mpa_critical NUMERIC(6,4),
    ADD COLUMN IF NOT EXISTS flow_rate_m3h_warning NUMERIC(8,3),
    ADD COLUMN IF NOT EXISTS flow_rate_m3h_critical NUMERIC(8,3),
    ADD COLUMN IF NOT EXISTS conductivity_us_warning NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS conductivity_us_critical NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS pue_warning NUMERIC(4,3),
    ADD COLUMN IF NOT EXISTS pue_critical NUMERIC(4,3),
    ADD COLUMN IF NOT EXISTS container_inside_temp_c_warning NUMERIC(5,2),
    ADD COLUMN IF NOT EXISTS container_inside_temp_c_critical NUMERIC(5,2);

COMMENT ON COLUMN ops.operational_thresholds.supply_temp_c_warning IS
'Warning threshold for container coolant supply temperature. Maps to container_monitor.py
ContainerHydraulics.supply_temp_c alert configuration.';


-- J4: Firmware telemetry completeness — add fields from BixBiT-specific API
ALTER TABLE firmware.firmware_telemetry_fields
    ADD COLUMN IF NOT EXISTS bixbit_field_name TEXT,                  -- BixBiT-specific field name mapping
    ADD COLUMN IF NOT EXISTS ams_field_name TEXT,                     -- AMS-specific field name mapping
    ADD COLUMN IF NOT EXISTS cgminer_field_name TEXT,                 -- CGMiner field name
    ADD COLUMN IF NOT EXISTS is_bixbit_only BOOLEAN NOT NULL DEFAULT FALSE,  -- Only available on BixBiT firmware
    ADD COLUMN IF NOT EXISTS is_immersion_only BOOLEAN NOT NULL DEFAULT FALSE; -- Only relevant for immersion


-- J5: Extend repair.parts with component-level diagnostic reference
ALTER TABLE repair.parts
    ADD COLUMN IF NOT EXISTS test_method TEXT,                        -- How to test this part: 'multimeter_diode_mode', 'resistance_check', etc.
    ADD COLUMN IF NOT EXISTS expected_reading TEXT,                   -- Expected measurement: '0.55V diode mode', '47Ω ±10%'
    ADD COLUMN IF NOT EXISTS failure_reading TEXT,                    -- What a failed part reads: 'OL', '0Ω', '>1MΩ'
    ADD COLUMN IF NOT EXISTS common_failure_mode TEXT,                -- 'short', 'open', 'drift', 'intermittent'
    ADD COLUMN IF NOT EXISTS failure_rate_per_1000h NUMERIC(8,4),    -- Expected failure rate
    ADD COLUMN IF NOT EXISTS is_critical_path BOOLEAN NOT NULL DEFAULT FALSE;  -- Failure kills the board?


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  SECTION K: SEED DATA — Pre-populate field_registry with known fields   ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- Seed the field registry with ALL known guardian.db operational fields
-- This is what the auto-discovery engine checks against

INSERT INTO knowledge.field_registry (field_key, field_source, field_category, data_type, unit, description, guardian_db_table, guardian_db_column, is_alertable)
VALUES
-- miner_readings fields
('miner_readings.hashrate', 'guardian_db', 'performance', 'numeric', 'th/s', 'Current hashrate in TH/s', 'miner_readings', 'hashrate', TRUE),
('miner_readings.max_hashrate', 'guardian_db', 'performance', 'numeric', 'th/s', 'Maximum observed hashrate', 'miner_readings', 'max_hashrate', FALSE),
('miner_readings.hashrate_pct', 'guardian_db', 'performance', 'numeric', '%', 'Hashrate as percentage of nominal', 'miner_readings', 'hashrate_pct', TRUE),
('miner_readings.temp_chip', 'guardian_db', 'thermal', 'numeric', 'celsius', 'Chip temperature', 'miner_readings', 'temp_chip', TRUE),
('miner_readings.temp_board', 'guardian_db', 'thermal', 'numeric', 'celsius', 'Board temperature', 'miner_readings', 'temp_board', TRUE),
('miner_readings.consumption', 'guardian_db', 'electrical', 'numeric', 'watts', 'Power consumption', 'miner_readings', 'consumption', TRUE),
('miner_readings.max_consumption', 'guardian_db', 'electrical', 'numeric', 'watts', 'Maximum power consumption', 'miner_readings', 'max_consumption', FALSE),
('miner_readings.pdu_power', 'guardian_db', 'electrical', 'numeric', 'watts', 'PDU-reported power', 'miner_readings', 'pdu_power', FALSE),
('miner_readings.cooling_mode', 'guardian_db', 'environmental', 'numeric', NULL, 'Cooling mode integer', 'miner_readings', 'cooling_mode', FALSE),
('miner_readings.firmware_version', 'guardian_db', 'firmware', 'text', NULL, 'Current firmware version', 'miner_readings', 'firmware_version', FALSE),
('miner_readings.uptime', 'guardian_db', 'performance', 'text', NULL, 'Miner uptime string', 'miner_readings', 'uptime', FALSE),
('miner_readings.error_codes', 'guardian_db', 'performance', 'text', NULL, 'Active error codes', 'miner_readings', 'error_codes', TRUE),
-- chain_readings fields
('chain_readings.rate_mhs', 'guardian_db', 'performance', 'numeric', 'mh/s', 'Per-board hashrate in MH/s', 'chain_readings', 'rate_mhs', TRUE),
('chain_readings.voltage', 'guardian_db', 'electrical', 'numeric', 'volts', 'Board voltage', 'chain_readings', 'voltage', TRUE),
('chain_readings.freq_mhz', 'guardian_db', 'electrical', 'numeric', 'mhz', 'Board operating frequency', 'chain_readings', 'freq_mhz', FALSE),
('chain_readings.consumption_w', 'guardian_db', 'electrical', 'numeric', 'watts', 'Per-board power consumption', 'chain_readings', 'consumption_w', TRUE),
('chain_readings.hw_errors', 'guardian_db', 'performance', 'numeric', 'count', 'Hardware errors per board', 'chain_readings', 'hw_errors', TRUE),
('chain_readings.temp_board', 'guardian_db', 'thermal', 'numeric', 'celsius', 'Board temperature', 'chain_readings', 'temp_board', TRUE),
('chain_readings.temp_chip', 'guardian_db', 'thermal', 'numeric', 'celsius', 'Chip temperature per board', 'chain_readings', 'temp_chip', TRUE),
-- chip_readings fields
('chip_readings.freq_mhz', 'guardian_db', 'electrical', 'numeric', 'mhz', 'Per-chip frequency', 'chip_readings', 'freq_mhz', FALSE),
('chip_readings.voltage_mv', 'guardian_db', 'electrical', 'numeric', 'mv', 'Per-chip voltage in millivolts', 'chip_readings', 'voltage_mv', TRUE),
('chip_readings.temp_c', 'guardian_db', 'thermal', 'numeric', 'celsius', 'Per-chip temperature', 'chip_readings', 'temp_c', TRUE),
-- pool_readings fields
('pool_readings.accepted', 'guardian_db', 'pool', 'numeric', 'count', 'Accepted shares', 'pool_readings', 'accepted', FALSE),
('pool_readings.rejected', 'guardian_db', 'pool', 'numeric', 'count', 'Rejected shares', 'pool_readings', 'rejected', TRUE),
('pool_readings.difficulty', 'guardian_db', 'pool', 'text', NULL, 'Pool difficulty', 'pool_readings', 'difficulty', FALSE),
-- weather_readings fields
('weather_readings.temp_f', 'guardian_db', 'environmental', 'numeric', 'fahrenheit', 'Outside temperature', 'weather_readings', 'temp_f', FALSE),
('weather_readings.humidity_pct', 'guardian_db', 'environmental', 'numeric', '%', 'Outside humidity', 'weather_readings', 'humidity_pct', FALSE),
('weather_readings.feels_like_f', 'guardian_db', 'environmental', 'numeric', 'fahrenheit', 'Feels-like temperature', 'weather_readings', 'feels_like_f', FALSE),
-- hvac_readings fields
('hvac_readings.supply_temp_f', 'guardian_db', 'environmental', 'numeric', 'fahrenheit', 'HVAC supply temperature', 'hvac_readings', 'supply_temp_f', TRUE),
('hvac_readings.return_temp_f', 'guardian_db', 'environmental', 'numeric', 'fahrenheit', 'HVAC return temperature', 'hvac_readings', 'return_temp_f', TRUE),
('hvac_readings.delta_t_f', 'guardian_db', 'environmental', 'numeric', 'fahrenheit', 'HVAC delta-T', 'hvac_readings', 'delta_t_f', TRUE),
('hvac_readings.diff_pressure', 'guardian_db', 'environmental', 'numeric', 'psi', 'Differential pressure', 'hvac_readings', 'diff_pressure', TRUE),
('hvac_readings.cwp1_vfd_pct', 'guardian_db', 'environmental', 'numeric', '%', 'Chilled water pump 1 VFD percentage', 'hvac_readings', 'cwp1_vfd_pct', FALSE),
('hvac_readings.cwp2_vfd_pct', 'guardian_db', 'environmental', 'numeric', '%', 'Chilled water pump 2 VFD percentage', 'hvac_readings', 'cwp2_vfd_pct', FALSE),
('hvac_readings.ct1_vfd_pct', 'guardian_db', 'environmental', 'numeric', '%', 'Cooling tower fan 1 VFD percentage', 'hvac_readings', 'ct1_vfd_pct', FALSE),
('hvac_readings.ct2_vfd_pct', 'guardian_db', 'environmental', 'numeric', '%', 'Cooling tower fan 2 VFD percentage', 'hvac_readings', 'ct2_vfd_pct', FALSE),
('hvac_readings.ct_fan_pct', 'guardian_db', 'environmental', 'numeric', '%', 'Overall CT fan percentage', 'hvac_readings', 'ct_fan_pct', FALSE),
('hvac_readings.spray_pump_on', 'guardian_db', 'environmental', 'boolean', NULL, 'Spray pump status', 'hvac_readings', 'spray_pump_on', TRUE),
('hvac_readings.leak_alarm', 'guardian_db', 'safety', 'boolean', NULL, 'Leak alarm status', 'hvac_readings', 'leak_alarm', TRUE),
('hvac_readings.tower_vibration', 'guardian_db', 'safety', 'boolean', NULL, 'Tower vibration alarm', 'hvac_readings', 'tower_vibration', TRUE),
('hvac_readings.basin_level_ok', 'guardian_db', 'safety', 'boolean', NULL, 'Basin level status', 'hvac_readings', 'basin_level_ok', TRUE),
('hvac_readings.ct1_fault', 'guardian_db', 'safety', 'boolean', NULL, 'Cooling tower fan 1 fault', 'hvac_readings', 'ct1_fault', TRUE),
('hvac_readings.ct2_fault', 'guardian_db', 'safety', 'boolean', NULL, 'Cooling tower fan 2 fault', 'hvac_readings', 'ct2_fault', TRUE),
('hvac_readings.pump_fault', 'guardian_db', 'safety', 'boolean', NULL, 'Spray pump fault', 'hvac_readings', 'pump_fault', TRUE),
-- container_monitor fields
('container.supply_temp_c', 'container_monitor', 'thermal', 'numeric', 'celsius', 'Container supply temperature', NULL, NULL, TRUE),
('container.supply_pressure_mpa', 'container_monitor', 'environmental', 'numeric', 'mpa', 'Container supply pressure', NULL, NULL, TRUE),
('container.return_temp_c', 'container_monitor', 'thermal', 'numeric', 'celsius', 'Container return temperature', NULL, NULL, TRUE),
('container.return_pressure_mpa', 'container_monitor', 'environmental', 'numeric', 'mpa', 'Container return pressure', NULL, NULL, TRUE),
('container.flow_rate_m3h', 'container_monitor', 'environmental', 'numeric', 'm3/h', 'Container coolant flow rate', NULL, NULL, TRUE),
('container.conductivity_us', 'container_monitor', 'environmental', 'numeric', 'us/cm', 'Coolant conductivity', NULL, NULL, TRUE),
('container.delta_t_c', 'container_monitor', 'thermal', 'numeric', 'celsius', 'Container delta-T', NULL, NULL, TRUE),
('container.dry_cooler_freq_hz', 'container_monitor', 'environmental', 'numeric', 'hz', 'Dry cooler frequency', NULL, NULL, FALSE),
('container.pmm1_kw', 'container_monitor', 'electrical', 'numeric', 'kw', 'Power monitoring module 1', NULL, NULL, FALSE),
('container.pmm2_kw', 'container_monitor', 'electrical', 'numeric', 'kw', 'Power monitoring module 2', NULL, NULL, FALSE),
('container.pmm3_kw', 'container_monitor', 'electrical', 'numeric', 'kw', 'Power monitoring module 3', NULL, NULL, FALSE),
('container.total_kw', 'container_monitor', 'electrical', 'numeric', 'kw', 'Total container power', NULL, NULL, TRUE),
('container.pue', 'container_monitor', 'electrical', 'numeric', 'ratio', 'Power usage effectiveness', NULL, NULL, TRUE),
('container.inside_temp1_c', 'container_monitor', 'thermal', 'numeric', 'celsius', 'Inside temperature sensor 1', NULL, NULL, TRUE),
('container.inside_temp2_c', 'container_monitor', 'thermal', 'numeric', 'celsius', 'Inside temperature sensor 2', NULL, NULL, TRUE),
('container.leakage_detected', 'container_monitor', 'safety', 'boolean', NULL, 'Coolant leakage detected', NULL, NULL, TRUE),
('container.smoke_detected', 'container_monitor', 'safety', 'boolean', NULL, 'Smoke detected', NULL, NULL, TRUE),
('container.tank_level_ok', 'container_monitor', 'safety', 'boolean', NULL, 'Tank level normal', NULL, NULL, TRUE),
-- log_metrics fields
('log_metrics.psu_voltage', 'guardian_db', 'electrical', 'numeric', 'volts', 'PSU voltage from miner logs', 'log_metrics', 'value_1', TRUE),
('log_metrics.chain_event', 'guardian_db', 'performance', 'text', NULL, 'Board attach/detach events', 'log_metrics', 'text_value', TRUE),
('log_metrics.system_health', 'guardian_db', 'performance', 'text', NULL, 'System health metrics from logs', 'log_metrics', 'text_value', FALSE),
-- miner_hardware identity fields
('miner_hardware.serial_number', 'guardian_db', 'identity', 'text', NULL, 'Board serial number', 'miner_hardware', 'serial_number', FALSE),
('miner_hardware.chip_die', 'guardian_db', 'identity', 'text', NULL, 'Chip die identifier', 'miner_hardware', 'chip_die', FALSE),
('miner_hardware.chip_marking', 'guardian_db', 'identity', 'text', NULL, 'Chip marking/bin code', 'miner_hardware', 'chip_marking', FALSE),
('miner_hardware.chip_bin', 'guardian_db', 'identity', 'text', NULL, 'Chip bin designation', 'miner_hardware', 'chip_bin', FALSE),
('miner_hardware.pcb_version', 'guardian_db', 'identity', 'text', NULL, 'PCB revision', 'miner_hardware', 'pcb_version', FALSE),
('miner_hardware.bom_version', 'guardian_db', 'identity', 'text', NULL, 'BOM revision', 'miner_hardware', 'bom_version', FALSE),
('miner_hardware.control_board', 'guardian_db', 'identity', 'text', NULL, 'Control board model', 'miner_hardware', 'control_board', FALSE),
('miner_hardware.psu_version', 'guardian_db', 'identity', 'text', NULL, 'PSU version string', 'miner_hardware', 'psu_version', FALSE),
('miner_hardware.asic_count', 'guardian_db', 'identity', 'numeric', 'count', 'ASIC chip count per board', 'miner_hardware', 'asic_count', FALSE),
('miner_hardware.bad_chips_count', 'guardian_db', 'identity', 'numeric', 'count', 'Number of bad chips detected', 'miner_hardware', 'bad_chips_count', TRUE)
ON CONFLICT (field_key, field_source) DO NOTHING;


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  FINAL: Updated Totals                                                   ║
-- ║  Base: 63 tables, ~1429 columns                                         ║
-- ║  V2:   9 tables, ~113 new columns added                                 ║
-- ║  V3:   14 new tables, ~170+ new columns, auto-discovery mechanism,      ║
-- ║        partitioned raw ingestion log, 75 seed registry entries           ║
-- ║  GRAND TOTAL: ~86 tables, ~1712+ columns, 10 schemas                    ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝
