-- =============================================================================
-- MINING INTELLIGENCE CATALOG — PostgreSQL 16 Schema
-- Part 1: Foundation — Extensions, Enums, Core Infrastructure
-- Owner: Bobby (Rob Fiesler) — Mining Guardian product
-- Created: 2025
-- =============================================================================
-- Design Philosophy: "NO data point is too small or insignificant"
-- Every row tracks its source. Every text field is searchable.
-- Every model name is fuzzy-matchable. 10-year design horizon.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- EXTENSIONS
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";       -- uuid_generate_v4()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";         -- Trigram similarity for fuzzy model name matching
CREATE EXTENSION IF NOT EXISTS "btree_gin";       -- GIN indexes on scalar types
CREATE EXTENSION IF NOT EXISTS "unaccent";        -- Accent-insensitive text search
CREATE EXTENSION IF NOT EXISTS "pgcrypto";        -- gen_random_uuid() alternative
-- Optional: enable PostGIS for geographic queries (repair shop proximity search)
-- Uncomment if PostGIS is installed on your system:
-- CREATE EXTENSION IF NOT EXISTS "postgis";
-- Then repair.repair_shops.location becomes GEOGRAPHY(POINT,4326) and you can use:
--   ST_DWithin(location, ST_MakePoint(-97.4, 32.7)::geography, 500000)  -- 500km radius

-- ---------------------------------------------------------------------------
-- SCHEMAS — logical grouping
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS hardware;    -- Category 1: Miner hardware
CREATE SCHEMA IF NOT EXISTS firmware;   -- Category 2: Firmware
CREATE SCHEMA IF NOT EXISTS ops;        -- Category 3: Operational
CREATE SCHEMA IF NOT EXISTS market;     -- Category 4: Community/Market
CREATE SCHEMA IF NOT EXISTS repair;     -- Category 5: Repair/Service
CREATE SCHEMA IF NOT EXISTS pool;       -- Category 6: Pool/Network
CREATE SCHEMA IF NOT EXISTS facility;   -- Category 7: Facility/Infrastructure
CREATE SCHEMA IF NOT EXISTS regulatory; -- Category 8: Regulatory/Compliance
CREATE SCHEMA IF NOT EXISTS knowledge;  -- Category 9: Knowledge Sources
CREATE SCHEMA IF NOT EXISTS seed;       -- Seed/reference data

-- ---------------------------------------------------------------------------
-- SHARED TRIGGER FUNCTION — updated_at auto-maintenance
-- Applied to every table that has an updated_at column
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.set_updated_at() IS
'Universal updated_at trigger. Attach to every table with DO INSTEAD NOTHING on the old value.';

-- ---------------------------------------------------------------------------
-- ENUM TYPES — controlled vocabularies
-- ---------------------------------------------------------------------------

-- Data source tiers (confidence/trust hierarchy)
CREATE TYPE public.source_tier AS ENUM (
    'tier1_manufacturer',   -- Official manufacturer specs/docs
    'tier2_operational',    -- Bobby's verified operational data
    'tier3_repair_shop',    -- Repair shop empirical data
    'tier4_community',      -- Forum, Reddit, Discord — needs verification
    'tier5_market_external' -- Market APIs, price feeds, external scrapers
);

-- Cooling technology types
CREATE TYPE public.cooling_type AS ENUM (
    'air',               -- Standard air-cooled (fans)
    'immersion',         -- Immersion cooling (mineral oil, engineered fluid)
    'hydro',             -- Hydro/liquid-cooled (water blocks, closed loop)
    'immersion_hydro',   -- Hybrid: immersion + heat exchanger hydro
    'two_phase',         -- Two-phase immersion (3M Novec, etc.)
    'unknown'
);

-- Miner manufacturer brands
CREATE TYPE public.manufacturer_brand AS ENUM (
    'bitmain',
    'microbt',        -- Whatsminer
    'auradine',
    'canaan',
    'jasminer',
    'strongu',
    'ebang',
    'bitfury',
    'iceriver',       -- KAS miners but some BTC
    'goldshell',
    'bitaxe',         -- Open-source SHA-256 miners (OSMU / skot9000) — BM1366/BM1368/BM1370
    'other',
    'unknown'
);

-- Chip/ASIC fabrication process nodes
CREATE TYPE public.process_node AS ENUM (
    '5nm',
    '7nm',
    '10nm',
    '14nm',
    '16nm',
    '28nm',
    '40nm',
    'other',
    'unknown'
);

-- Firmware types/families
CREATE TYPE public.firmware_family AS ENUM (
    'stock_bitmain',      -- OEM Bitmain firmware
    'stock_microbt',      -- OEM MicroBT firmware
    'stock_auradine',     -- OEM Auradine firmware
    'stock_canaan',       -- OEM Canaan firmware
    'bixbit',             -- BiXBiT custom firmware
    'braiins_os',         -- Braiins OS / Braiins OS+
    'vnish',              -- VNish firmware
    'luxos',              -- LuxOS (Luxor)
    'epic',               -- ePIC Blockchain
    'auradine_native',    -- Auradine's own advanced firmware
    'hiveon',             -- Hiveon firmware
    'other',
    'unknown'
);

-- Operational modes
CREATE TYPE public.operational_mode AS ENUM (
    'eco',          -- Low-power, efficiency-optimized
    'normal',       -- Stock/default settings
    'turbo',        -- Overclocked, high performance
    'custom',       -- Manual tuning
    'sleep',        -- Zero or minimal hashing
    'auto',         -- Firmware-managed adaptive mode
    'repair_mode'   -- Diagnostic/recovery mode
);

-- Failure severity levels
CREATE TYPE public.failure_severity AS ENUM (
    'informational', -- Log-worthy but not actionable
    'low',           -- Performance impact, not critical
    'medium',        -- Requires attention within days
    'high',          -- Requires attention within hours
    'critical',      -- Immediate shutdown risk
    'catastrophic'   -- Total loss / unrecoverable
);

-- Repair outcome status
CREATE TYPE public.repair_outcome AS ENUM (
    'success_full',        -- 100% restored to spec
    'success_partial',     -- Functional but below spec
    'success_workaround',  -- Stable with limitations
    'failure_no_fix',      -- Could not be repaired
    'failure_worse',       -- Made condition worse
    'in_progress',         -- Repair ongoing
    'pending_parts',       -- Awaiting parts
    'deferred',            -- Repair postponed
    'scrapped'             -- Unit declared dead
);

-- Data confidence levels
CREATE TYPE public.confidence_level AS ENUM (
    'verified',          -- Cross-verified across multiple sources
    'high',              -- Single high-trust source
    'medium',            -- Single medium-trust source  
    'low',               -- Unverified community claim
    'disputed',          -- Multiple sources disagree
    'deprecated',        -- Superseded by newer data
    'estimated',         -- Calculated/interpolated
    'unknown'
);

-- PSU connector types
CREATE TYPE public.psu_connector_type AS ENUM (
    'pcie_6pin',
    'pcie_8pin',
    'pcie_6plus2pin',
    'molex',
    'server_c14',
    'server_c19',
    'server_c20',
    'proprietary_bitmain',
    'proprietary_auradine',
    'anderson_powerpole',
    'other'
);

-- Stratum protocol versions
CREATE TYPE public.stratum_version AS ENUM (
    'stratum_v1',
    'stratum_v2',
    'stratum_v2_custom',
    'other'
);

-- Regulatory jurisdiction types
CREATE TYPE public.jurisdiction_type AS ENUM (
    'federal_us',
    'state_us',
    'county_us',
    'municipal_us',
    'federal_ca',
    'provincial_ca',
    'eu_regulation',
    'national_other',
    'international'
);

-- Part condition grades
CREATE TYPE public.part_condition AS ENUM (
    'new_oem',          -- New, original equipment
    'new_aftermarket',  -- New, third-party
    'refurbished',      -- Tested/reconditioned
    'pulled_working',   -- Removed from working unit
    'used_untested',    -- Unknown condition
    'for_parts'         -- Partially functional/donor
);

-- Review sentiment
CREATE TYPE public.sentiment AS ENUM (
    'very_positive',
    'positive',
    'neutral',
    'negative',
    'very_negative',
    'mixed'
);

-- Bitcoin network data types
CREATE TYPE public.network_data_type AS ENUM (
    'difficulty_adjustment',
    'block_reward',
    'mempool_fee',
    'hashrate_estimate',
    'price_usd',
    'transaction_count',
    'block_time'
);

-- Conflict resolution strategies
CREATE TYPE public.conflict_resolution AS ENUM (
    'higher_tier_wins',     -- Trust hierarchy decides
    'most_recent_wins',     -- Latest data wins
    'most_citations_wins',  -- Most-cited value wins
    'manual_review',        -- Human must decide
    'weighted_average',     -- Numeric blend of values
    'all_values_stored',    -- Keep all, mark disputed
    'resolved'              -- Resolved, winner recorded
);

-- ---------------------------------------------------------------------------
-- CATEGORY 9 (Foundation): KNOWLEDGE SOURCES — must exist before everything
-- All other tables FK into these
-- ---------------------------------------------------------------------------

-- Master source registry — where did ANY piece of data come from?
CREATE TABLE knowledge.sources (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_key          TEXT NOT NULL UNIQUE,   -- Machine-readable key e.g. 'bitmain_official_site'
    display_name        TEXT NOT NULL,
    tier                public.source_tier NOT NULL,
    source_url          TEXT,                   -- Primary URL for this source
    description         TEXT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    last_verified_at    TIMESTAMPTZ,
    trust_score         NUMERIC(5,4) CHECK (trust_score BETWEEN 0 AND 1),
    -- Trust score: 0.0–1.0, starts at tier default, adjusts from verification history
    trust_score_rationale TEXT,
    contributor_id      UUID,                   -- FK to knowledge.contributors (added later)
    api_endpoint        TEXT,                   -- If data comes from an API
    api_auth_type       TEXT,                   -- 'none', 'apikey', 'oauth2', etc.
    scrape_frequency_hours INTEGER,             -- How often to refresh
    last_fetched_at     TIMESTAMPTZ,
    fetch_error_count   INTEGER NOT NULL DEFAULT 0,
    metadata            JSONB NOT NULL DEFAULT '{}',
    search_vector       TSVECTOR,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE knowledge.sources IS
'Master registry of ALL data sources. Every row in every table must trace back to a source here.
Tier 1 = Manufacturer (highest trust). Tier 5 = Market/external APIs (lowest trust).
trust_score is maintained by the verification pipeline as sources are proven accurate or wrong.';

CREATE INDEX idx_sources_tier ON knowledge.sources(tier);
CREATE INDEX idx_sources_active ON knowledge.sources(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_sources_search ON knowledge.sources USING GIN(search_vector);
CREATE INDEX idx_sources_metadata ON knowledge.sources USING GIN(metadata);

CREATE TRIGGER trg_sources_updated_at
    BEFORE UPDATE ON knowledge.sources
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_sources_search_vector
    BEFORE INSERT OR UPDATE ON knowledge.sources
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english', display_name, description, source_key
    );

-- Contributors — humans or bots that submitted data
CREATE TABLE knowledge.contributors (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    handle          TEXT NOT NULL UNIQUE,       -- Username/identifier
    display_name    TEXT,
    contributor_type TEXT NOT NULL DEFAULT 'community',
    -- 'bobby_operational', 'repair_shop', 'manufacturer', 'researcher', 'community', 'bot'
    trust_score     NUMERIC(5,4) NOT NULL DEFAULT 0.5 CHECK (trust_score BETWEEN 0 AND 1),
    trust_rationale TEXT,
    total_contributions INTEGER NOT NULL DEFAULT 0,
    verified_contributions INTEGER NOT NULL DEFAULT 0,
    refuted_contributions INTEGER NOT NULL DEFAULT 0,
    affiliation     TEXT,          -- Company/shop they represent
    contact_info    JSONB NOT NULL DEFAULT '{}',
    metadata        JSONB NOT NULL DEFAULT '{}',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE knowledge.contributors IS
'Human and bot contributors. Trust score updates automatically as contributions are verified/refuted.
Bobby gets a special contributor record at tier2_operational. Repair shops get tier3 records.';

-- Add FK now that both tables exist
ALTER TABLE knowledge.sources
    ADD CONSTRAINT fk_sources_contributor
    FOREIGN KEY (contributor_id) REFERENCES knowledge.contributors(id);

CREATE TRIGGER trg_contributors_updated_at
    BEFORE UPDATE ON knowledge.contributors
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Source citation — links any row (by table+id) to its source(s)
-- This is the universal attribution mechanism
CREATE TABLE knowledge.citations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id       UUID NOT NULL REFERENCES knowledge.sources(id),
    -- The thing being cited — polymorphic reference
    cited_table     TEXT NOT NULL,   -- e.g. 'hardware.miner_models'
    cited_row_id    UUID NOT NULL,   -- The row's UUID
    cited_field     TEXT,            -- NULL = entire row; otherwise specific field name
    -- What was cited
    excerpt         TEXT,            -- Exact quote or data snippet from source
    source_url      TEXT,            -- Specific page/URL within the source
    citation_date   DATE,            -- When this specific citation was captured
    confidence      public.confidence_level NOT NULL DEFAULT 'medium',
    notes           TEXT,
    contributor_id  UUID REFERENCES knowledge.contributors(id),
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE knowledge.citations IS
'Universal citation table. Any row in any table can be cited here by (cited_table, cited_row_id).
cited_field can narrow to a specific column. This enables per-field source tracking.
Use this to answer: "Where did we get the power consumption spec for the S19j Pro?"';

CREATE INDEX idx_citations_source ON knowledge.citations(source_id);
CREATE INDEX idx_citations_row ON knowledge.citations(cited_table, cited_row_id);
CREATE INDEX idx_citations_field ON knowledge.citations(cited_table, cited_row_id, cited_field)
    WHERE cited_field IS NOT NULL;
CREATE INDEX idx_citations_date ON knowledge.citations(citation_date DESC);
CREATE INDEX idx_citations_contributor ON knowledge.citations(contributor_id);

CREATE TRIGGER trg_citations_updated_at
    BEFORE UPDATE ON knowledge.citations
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Data conflicts — when two sources disagree on a value
CREATE TABLE knowledge.data_conflicts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conflict_table      TEXT NOT NULL,
    conflict_row_id     UUID NOT NULL,
    conflict_field      TEXT NOT NULL,
    -- The competing values
    value_a             JSONB NOT NULL,     -- {"raw": "104", "unit": "TH/s", "source_id": "..."}
    value_b             JSONB NOT NULL,
    source_a_id         UUID NOT NULL REFERENCES knowledge.sources(id),
    source_b_id         UUID NOT NULL REFERENCES knowledge.sources(id),
    -- Resolution
    resolution_strategy public.conflict_resolution NOT NULL DEFAULT 'manual_review',
    resolved_value      JSONB,              -- The winner, if resolved
    resolved_by         UUID REFERENCES knowledge.contributors(id),
    resolved_at         TIMESTAMPTZ,
    resolution_notes    TEXT,
    -- Metadata
    severity            public.failure_severity NOT NULL DEFAULT 'low',
    is_resolved         BOOLEAN NOT NULL DEFAULT FALSE,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE knowledge.data_conflicts IS
'Tracks disagreements between sources on specific field values.
E.g., Bitmain says S19j Pro = 104 TH/s stock, community says 96 TH/s after throttling.
Both values are stored; the conflict tracks which source wins and why.';

CREATE INDEX idx_conflicts_table_row ON knowledge.data_conflicts(conflict_table, conflict_row_id);
CREATE INDEX idx_conflicts_unresolved ON knowledge.data_conflicts(is_resolved)
    WHERE is_resolved = FALSE;

CREATE TRIGGER trg_conflicts_updated_at
    BEFORE UPDATE ON knowledge.data_conflicts
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Data freshness tracking — when was each data point last verified?
CREATE TABLE knowledge.freshness_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tracked_table   TEXT NOT NULL,
    tracked_row_id  UUID NOT NULL,
    tracked_field   TEXT,               -- NULL = whole row
    last_verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_by     UUID REFERENCES knowledge.contributors(id),
    verification_method TEXT,           -- 'api_pull', 'manual_check', 'automated_test', etc.
    next_verify_due TIMESTAMPTZ,        -- When should this be re-verified?
    -- staleness_days was previously a STORED GENERATED column referencing NOW(),
    -- which Postgres rejects (generation expression must be immutable). N6
    -- (2026-04-27) replaced it with a query-time computation; downstream views
    -- and design notes already use EXTRACT(DAY FROM NOW() - last_verified_at)
    -- inline. If a stored column becomes necessary later, populate via trigger.
    is_stale        BOOLEAN NOT NULL DEFAULT FALSE,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE knowledge.freshness_log IS
'Tracks when any data point was last verified. Enables staleness alerts.
Mining Guardian can query: "Which specs have not been verified in 90+ days?"';

CREATE INDEX idx_freshness_row ON knowledge.freshness_log(tracked_table, tracked_row_id);
CREATE INDEX idx_freshness_stale ON knowledge.freshness_log(is_stale, next_verify_due)
    WHERE is_stale = TRUE;
CREATE INDEX idx_freshness_due ON knowledge.freshness_log(next_verify_due ASC)
    WHERE next_verify_due IS NOT NULL;
-- =============================================================================
-- MINING INTELLIGENCE CATALOG — Part 2: Category 1 — Miner Hardware
-- Tables: chips, manufacturers, miner_models, model_aliases, boards, PSUs,
--         control_boards, model_spec_history, model_board_map
-- =============================================================================

-- ---------------------------------------------------------------------------
-- MANUFACTURERS
-- ---------------------------------------------------------------------------
CREATE TABLE hardware.manufacturers (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- N6 (2026-04-27): added UNIQUE on brand. The deploy_schema.sql seed uses
    -- ON CONFLICT (brand) DO NOTHING for idempotency, which requires this
    -- constraint to exist. Brand is also semantically one-row-per-enum-value
    -- (you cannot have two "Bitmain" manufacturers).
    brand               public.manufacturer_brand NOT NULL UNIQUE,
    legal_name          TEXT NOT NULL,
    common_name         TEXT NOT NULL,    -- "Bitmain", "MicroBT", "Auradine"
    country_of_origin   CHAR(2),          -- ISO 3166-1 alpha-2
    headquarters_city   TEXT,
    website_url         TEXT,
    support_url         TEXT,
    support_email       TEXT,
    founded_year        INTEGER,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    -- Reputation metrics (aggregate from market.manufacturer_reputation)
    overall_reputation_score NUMERIC(4,2), -- 0–10
    build_quality_score      NUMERIC(4,2),
    support_quality_score    NUMERIC(4,2),
    warranty_reliability_score NUMERIC(4,2),
    -- Source tracking
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'high',
    metadata            JSONB NOT NULL DEFAULT '{}',
    search_vector       TSVECTOR,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE hardware.manufacturers IS
'Bitcoin mining hardware manufacturers. Reputation scores are aggregated from
market.manufacturer_reputation and updated periodically.';

CREATE INDEX idx_manufacturers_brand ON hardware.manufacturers(brand);
CREATE INDEX idx_manufacturers_active ON hardware.manufacturers(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_manufacturers_search ON hardware.manufacturers USING GIN(search_vector);

CREATE TRIGGER trg_manufacturers_updated_at
    BEFORE UPDATE ON hardware.manufacturers
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_manufacturers_search_vector
    BEFORE INSERT OR UPDATE ON hardware.manufacturers
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english', legal_name, common_name
    );

-- ---------------------------------------------------------------------------
-- CHIPS / ASICs
-- ---------------------------------------------------------------------------
CREATE TABLE hardware.chips (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chip_model          TEXT NOT NULL,       -- "BM1362", "AT7200", "BM1368", "BM1397"
    manufacturer_id     UUID NOT NULL REFERENCES hardware.manufacturers(id),
    -- Process / Physical
    process_node        public.process_node NOT NULL DEFAULT 'unknown',
    die_size_mm2        NUMERIC(8,3),        -- Die area in mm²
    transistor_count_billions NUMERIC(8,3), -- Billions of transistors
    -- Performance (per chip, at reference voltage/frequency)
    hashrate_gh_per_chip NUMERIC(12,4),     -- GH/s per chip at reference settings
    power_mw_per_chip   NUMERIC(10,4),       -- mW per chip at reference settings
    efficiency_j_per_th NUMERIC(8,4),        -- J/TH at reference settings
    -- Electrical
    core_voltage_mv_min  INTEGER,            -- mV minimum
    core_voltage_mv_max  INTEGER,            -- mV maximum
    core_voltage_mv_nom  INTEGER,            -- mV nominal/reference
    frequency_mhz_min    INTEGER,
    frequency_mhz_max    INTEGER,
    frequency_mhz_nom    INTEGER,
    -- Thermal
    tj_max_celsius       INTEGER,            -- Max junction temp
    theta_ja_c_per_w     NUMERIC(6,3),       -- Thermal resistance junction-to-ambient
    -- Package
    package_type         TEXT,               -- 'BGA', 'LGA', etc.
    pin_count            INTEGER,
    -- Algorithm
    algorithm            TEXT NOT NULL DEFAULT 'SHA-256',
    -- Lifecycle
    release_year         INTEGER,
    is_current_gen       BOOLEAN NOT NULL DEFAULT TRUE,
    is_obsolete          BOOLEAN NOT NULL DEFAULT FALSE,
    successor_chip_id    UUID REFERENCES hardware.chips(id),
    predecessor_chip_id  UUID REFERENCES hardware.chips(id),
    -- Notes / raw docs
    datasheet_url        TEXT,
    notes                TEXT,
    -- Source tracking
    primary_source_id    UUID REFERENCES knowledge.sources(id),
    confidence           public.confidence_level NOT NULL DEFAULT 'medium',
    metadata             JSONB NOT NULL DEFAULT '{}',
    search_vector        TSVECTOR,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (chip_model, manufacturer_id)
);

COMMENT ON TABLE hardware.chips IS
'ASIC chip specifications. One row per chip model per manufacturer.
Die size, process node, per-chip hashrate and power, voltage/frequency ranges, and thermal specs.
BM1362 = S19j Pro, BM1368 = S21/S21 EXP, AT7200 = Auradine Teraflux.
Linked to miner_models via hardware.model_board_map → boards → chips.';

CREATE INDEX idx_chips_model ON hardware.chips(chip_model);
CREATE INDEX idx_chips_manufacturer ON hardware.chips(manufacturer_id);
CREATE INDEX idx_chips_process ON hardware.chips(process_node);
CREATE INDEX idx_chips_search ON hardware.chips USING GIN(search_vector);
CREATE INDEX idx_chips_metadata ON hardware.chips USING GIN(metadata);

CREATE TRIGGER trg_chips_updated_at
    BEFORE UPDATE ON hardware.chips
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_chips_search_vector
    BEFORE INSERT OR UPDATE ON hardware.chips
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english', chip_model, package_type, notes, algorithm
    );

-- ---------------------------------------------------------------------------
-- PSU MODELS
-- ---------------------------------------------------------------------------
CREATE TABLE hardware.psu_models (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    manufacturer_id     UUID REFERENCES hardware.manufacturers(id),
    model_name          TEXT NOT NULL,
    -- Electrical ratings
    input_voltage_v_min  NUMERIC(6,2),
    input_voltage_v_max  NUMERIC(6,2),
    input_frequency_hz   TEXT,              -- "50/60Hz"
    output_voltage_12v   BOOLEAN NOT NULL DEFAULT TRUE,
    output_power_w       NUMERIC(8,2),      -- Rated output watts
    output_power_w_peak  NUMERIC(8,2),      -- Peak watts (short-term)
    efficiency_80plus    TEXT,              -- '80Plus Bronze', 'Platinum', 'Titanium', etc.
    -- Efficiency curve data points (load% → efficiency%)
    efficiency_curve     JSONB,             -- [{"load_pct": 20, "eff_pct": 89.5}, ...]
    -- Connectors
    output_connectors    JSONB NOT NULL DEFAULT '[]',
    -- [{"type": "pcie_6pin", "count": 6, "amperage": 12.5}, ...]
    connector_gauge_awg  INTEGER,
    -- Physical
    form_factor          TEXT,              -- '1U', '2U', 'ATX', 'server', 'proprietary'
    width_mm             NUMERIC(7,2),
    height_mm            NUMERIC(7,2),
    depth_mm             NUMERIC(7,2),
    weight_g             INTEGER,
    -- Fan / cooling
    has_fan              BOOLEAN NOT NULL DEFAULT TRUE,
    fan_size_mm          INTEGER,
    fan_count            INTEGER,
    -- Failure characteristics
    mtbf_hours           INTEGER,           -- Mean time between failures (spec sheet)
    known_failure_modes  JSONB NOT NULL DEFAULT '[]',
    -- Source tracking
    primary_source_id    UUID REFERENCES knowledge.sources(id),
    confidence           public.confidence_level NOT NULL DEFAULT 'medium',
    datasheet_url        TEXT,
    notes                TEXT,
    metadata             JSONB NOT NULL DEFAULT '{}',
    search_vector        TSVECTOR,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE hardware.psu_models IS
'PSU/power supply models used with mining hardware. Tracks efficiency curves,
connector types, and known failure modes. Linked to miner_models via the psu_compatibility table.';

CREATE INDEX idx_psu_manufacturer ON hardware.psu_models(manufacturer_id);
CREATE INDEX idx_psu_output_power ON hardware.psu_models(output_power_w);
CREATE INDEX idx_psu_search ON hardware.psu_models USING GIN(search_vector);
CREATE INDEX idx_psu_metadata ON hardware.psu_models USING GIN(metadata);

CREATE TRIGGER trg_psu_updated_at
    BEFORE UPDATE ON hardware.psu_models
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_psu_search_vector
    BEFORE INSERT OR UPDATE ON hardware.psu_models
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english', model_name, form_factor, efficiency_80plus, notes
    );

-- ---------------------------------------------------------------------------
-- CONTROL BOARDS
-- ---------------------------------------------------------------------------
CREATE TABLE hardware.control_boards (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    manufacturer_id      UUID REFERENCES hardware.manufacturers(id),
    model_name           TEXT NOT NULL,
    pcb_revision         TEXT,
    -- CPU / SoC
    cpu_model            TEXT,             -- "Zynq 7020", "S905D3"
    cpu_cores            INTEGER,
    cpu_arch             TEXT,             -- 'arm', 'arm64', 'mips', 'x86'
    ram_mb               INTEGER,
    nand_flash_mb        INTEGER,
    -- Interfaces
    has_ethernet         BOOLEAN NOT NULL DEFAULT TRUE,
    ethernet_speed_mbps  INTEGER,
    has_wifi             BOOLEAN NOT NULL DEFAULT FALSE,
    has_uart             BOOLEAN NOT NULL DEFAULT TRUE,
    has_jtag             BOOLEAN NOT NULL DEFAULT FALSE,
    connector_types      JSONB NOT NULL DEFAULT '[]',  -- Connectors to hashboards
    uart_baud_rate       INTEGER,
    -- Firmware compatibility (detailed in firmware schema)
    default_firmware     TEXT,
    -- Physical
    form_factor          TEXT,
    dimensions_mm        JSONB,            -- {"w": 100, "h": 50, "d": 20}
    -- Known issues
    known_issues         JSONB NOT NULL DEFAULT '[]',
    -- Source tracking
    primary_source_id    UUID REFERENCES knowledge.sources(id),
    confidence           public.confidence_level NOT NULL DEFAULT 'medium',
    notes                TEXT,
    metadata             JSONB NOT NULL DEFAULT '{}',
    search_vector        TSVECTOR,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE hardware.control_boards IS
'Control board (aka controller) models. These are the "brains" — Raspberry Pi-like boards
that manage the hashboards, run the firmware, and expose the API.
Firmware compatibility is tracked in firmware.firmware_compatibility.';

CREATE INDEX idx_cb_manufacturer ON hardware.control_boards(manufacturer_id);
CREATE INDEX idx_cb_search ON hardware.control_boards USING GIN(search_vector);

CREATE TRIGGER trg_cb_updated_at
    BEFORE UPDATE ON hardware.control_boards
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_cb_search_vector
    BEFORE INSERT OR UPDATE ON hardware.control_boards
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english', model_name, pcb_revision, cpu_model, notes
    );

-- ---------------------------------------------------------------------------
-- HASHBOARDS / PCBs
-- ---------------------------------------------------------------------------
CREATE TABLE hardware.hashboards (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    manufacturer_id     UUID NOT NULL REFERENCES hardware.manufacturers(id),
    board_name          TEXT NOT NULL,     -- "S19j Pro Board A", "S21 Hydro PCB v1.2"
    pcb_revision        TEXT,             -- "v1.0", "v1.2", "rev3"
    -- Chip info
    chip_id             UUID REFERENCES hardware.chips(id),
    -- N6 (2026-04-27): relaxed NOT NULL. Some manufacturers (e.g. Auradine)
    -- do not publish chip count per board, and the seed data accordingly
    -- inserts NULL. The schema's own seed (line ~3866) demonstrates this. Keep
    -- column nullable so queries can distinguish "unknown" from "zero".
    chips_per_board     INTEGER,
    chip_layout         TEXT,             -- '3 domains of 8' — textual description
    chip_layout_json    JSONB,            -- Machine-readable domain/row/column layout
    -- Electrical
    board_voltage_v_nom  NUMERIC(6,3),   -- Nominal board input voltage (12V, 14.5V, etc.)
    board_voltage_v_min  NUMERIC(6,3),
    board_voltage_v_max  NUMERIC(6,3),
    board_power_w_nom    NUMERIC(8,2),   -- Nominal power draw
    board_power_w_max    NUMERIC(8,2),
    -- Hash performance (at nominal voltage)
    hashrate_th_nom      NUMERIC(10,4),  -- TH/s per board at nominal
    hashrate_th_max      NUMERIC(10,4),
    -- Thermal
    temp_sensor_count    INTEGER,
    temp_sensor_locations JSONB,         -- [{"id": 1, "location": "left_domain", "type": "thermistor"}]
    max_temp_celsius     INTEGER,
    -- Connectors
    psu_connector_type   public.psu_connector_type,
    psu_connector_count  INTEGER,
    -- Known PCB revision defects (critical design intelligence)
    known_defects        JSONB NOT NULL DEFAULT '[]',
    -- [{"revision": "v1.0", "defect": "cap C142 fails at 65C+", "severity": "high", "workaround": "..."}]
    defect_severity      public.failure_severity,
    -- Dimensions
    length_mm            NUMERIC(7,2),
    width_mm             NUMERIC(7,2),
    -- Source tracking
    primary_source_id    UUID REFERENCES knowledge.sources(id),
    confidence           public.confidence_level NOT NULL DEFAULT 'medium',
    datasheet_url        TEXT,
    notes                TEXT,
    metadata             JSONB NOT NULL DEFAULT '{}',
    search_vector        TSVECTOR,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE hardware.hashboards IS
'Hashboard (PCB) specifications. One row per board model + PCB revision combination.
known_defects JSONB is critical — stores revision-specific failures like bad capacitors,
trace cracks, cold solder joints known to appear at specific revisions.
chips_per_board × chip hashrate = board hashrate (use to sanity-check specs).';

CREATE INDEX idx_hashboards_manufacturer ON hardware.hashboards(manufacturer_id);
CREATE INDEX idx_hashboards_chip ON hardware.hashboards(chip_id);
CREATE INDEX idx_hashboards_revision ON hardware.hashboards(pcb_revision);
CREATE INDEX idx_hashboards_defects ON hardware.hashboards USING GIN(known_defects);
CREATE INDEX idx_hashboards_search ON hardware.hashboards USING GIN(search_vector);
CREATE INDEX idx_hashboards_metadata ON hardware.hashboards USING GIN(metadata);

CREATE TRIGGER trg_hashboards_updated_at
    BEFORE UPDATE ON hardware.hashboards
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_hashboards_search_vector
    BEFORE INSERT OR UPDATE ON hardware.hashboards
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english', board_name, pcb_revision, chip_layout, notes
    );

-- ---------------------------------------------------------------------------
-- MINER MODELS — the core hardware table
-- ---------------------------------------------------------------------------
CREATE TABLE hardware.miner_models (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    manufacturer_id         UUID NOT NULL REFERENCES hardware.manufacturers(id),
    -- Naming
    canonical_name          TEXT NOT NULL,  -- "Antminer S19j Pro" — the ONE true name
    model_number            TEXT,           -- "S19J Pro", "AH3880", "S21 EXP"
    generation              TEXT,           -- "S19 series", "S21 series", "Teraflux"
    parent_model_id         UUID REFERENCES hardware.miner_models(id),  -- S19J Pro+ → parent S19J Pro
    -- Cooling
    cooling_type            public.cooling_type NOT NULL,
    -- Board configuration
    hashboard_count         INTEGER NOT NULL,
    hashboard_id            UUID REFERENCES hardware.hashboards(id),
    -- CRITICAL: hashboard_count is enforced at application layer for known limits
    -- e.g., AH3880 = EXACTLY 2 boards; violation = data quality error
    board_count_is_fixed    BOOLEAN NOT NULL DEFAULT TRUE,
    -- Stock performance (manufacturer specs)
    stock_hashrate_th       NUMERIC(10,3) NOT NULL,   -- TH/s at stock settings
    stock_power_w           NUMERIC(8,2),
    stock_efficiency_j_th   NUMERIC(8,4),             -- Calculated: stock_power_w / stock_hashrate_th
    -- Maximum rated performance
    max_hashrate_th         NUMERIC(10,3),
    max_power_w             NUMERIC(8,2),
    -- Electrical input
    input_voltage_v_min     NUMERIC(6,2),
    input_voltage_v_max     NUMERIC(6,2),
    input_voltage_v_nom     NUMERIC(6,2),
    input_freq_hz           TEXT NOT NULL DEFAULT '50/60Hz',
    input_current_a_max     NUMERIC(7,3),
    -- PSU
    psu_included            BOOLEAN NOT NULL DEFAULT TRUE,
    default_psu_id          UUID REFERENCES hardware.psu_models(id),
    -- Control board
    control_board_id        UUID REFERENCES hardware.control_boards(id),
    -- Operating environment
    ambient_temp_min_c      INTEGER,
    ambient_temp_max_c      INTEGER,
    humidity_min_pct        INTEGER,
    humidity_max_pct        INTEGER,
    -- Physical dimensions
    length_mm               NUMERIC(7,2),
    width_mm                NUMERIC(7,2),
    height_mm               NUMERIC(7,2),
    weight_kg               NUMERIC(7,3),
    -- Networking
    network_interface       TEXT DEFAULT 'Ethernet 1Gbps',
    -- Certifications
    certifications          JSONB NOT NULL DEFAULT '[]',  -- ['CE', 'FCC', 'RoHS']
    -- Algorithm
    algorithm               TEXT NOT NULL DEFAULT 'SHA-256',
    -- Lifecycle
    announced_date          DATE,
    released_date           DATE,
    discontinued_date       DATE,
    is_current_product      BOOLEAN NOT NULL DEFAULT TRUE,
    end_of_life             BOOLEAN NOT NULL DEFAULT FALSE,
    -- Market
    msrp_usd                NUMERIC(10,2),
    msrp_date               DATE,
    -- Source tracking
    -- D-18 P-025 (2026-05-05): seed_miner_models.sql INSERTs omit primary_source_id
    -- (320 rows). Default to the canonical "catalog_research_2026" knowledge.sources
    -- row (a0000000-0000-0000-0000-00000000000e) seeded by deploy_schema.sql so the
    -- NOT NULL constraint passes without per-row column data. Explicit values still
    -- override.
    primary_source_id       UUID NOT NULL DEFAULT 'a0000000-0000-0000-0000-00000000000e'::uuid REFERENCES knowledge.sources(id),
    confidence              public.confidence_level NOT NULL DEFAULT 'high',
    -- Full-text search
    notes                   TEXT,
    search_vector           TSVECTOR,
    -- Extensible
    metadata                JSONB NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (manufacturer_id, canonical_name)
);

COMMENT ON TABLE hardware.miner_models IS
'Core hardware table — one row per canonical miner model.
canonical_name is the authoritative name. All aliases map HERE via hardware.model_aliases.
stock_efficiency_j_th is a generated/computed column kept in sync by trigger.
board_count_is_fixed=TRUE means any repair record claiming a different board count is flagged.
CRITICAL: AH3880 hashboard_count=2 is a hard rule — 2 boards ONLY, no 3-board variants.';

CREATE INDEX idx_miner_manufacturer ON hardware.miner_models(manufacturer_id);
CREATE INDEX idx_miner_cooling ON hardware.miner_models(cooling_type);
CREATE INDEX idx_miner_current ON hardware.miner_models(is_current_product) WHERE is_current_product = TRUE;
CREATE INDEX idx_miner_hashrate ON hardware.miner_models(stock_hashrate_th DESC);
CREATE INDEX idx_miner_board ON hardware.miner_models(hashboard_id);
CREATE INDEX idx_miner_search ON hardware.miner_models USING GIN(search_vector);
CREATE INDEX idx_miner_metadata ON hardware.miner_models USING GIN(metadata);
CREATE INDEX idx_miner_canonical_trgm ON hardware.miner_models USING GIN(canonical_name gin_trgm_ops);
CREATE INDEX idx_miner_model_number_trgm ON hardware.miner_models USING GIN(model_number gin_trgm_ops);

CREATE TRIGGER trg_miner_updated_at
    BEFORE UPDATE ON hardware.miner_models
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_miner_search_vector
    BEFORE INSERT OR UPDATE ON hardware.miner_models
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        canonical_name, model_number, generation, algorithm, notes
    );

-- ---------------------------------------------------------------------------
-- MODEL ALIASES — fuzzy matching support
-- "S19JPro" = "Antminer S19j Pro" = "S19J Pro" = "s19jpro" etc.
-- ---------------------------------------------------------------------------
CREATE TABLE hardware.model_aliases (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_model_id  UUID NOT NULL REFERENCES hardware.miner_models(id) ON DELETE CASCADE,
    alias           TEXT NOT NULL,           -- The alias string (any variant)
    alias_normalized TEXT NOT NULL,           -- Lowercased, no spaces/special chars
    alias_source    TEXT NOT NULL DEFAULT 'unknown',
    -- 'manufacturer_doc', 'forum', 'repair_shop_import', 'bobby_manual', 'auto_generated'
    is_common       BOOLEAN NOT NULL DEFAULT FALSE,  -- Is this a frequently used alias?
    notes           TEXT,
    primary_source_id UUID REFERENCES knowledge.sources(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- N6 (2026-04-27): the original constraint UNIQUE (alias_normalized) was
    -- too strict and broke the schema's own seed data. Two distinct
    -- human-readable aliases ('S21EXP' and 'S21 EXP') legitimately normalize
    -- to the same string ('s21exp') for the same model, and that should not
    -- be rejected. We also do not want different models to claim the same
    -- normalized alias — that would defeat fuzzy matching. The right shape:
    --   * unique (miner_model_id, alias)              — no exact duplicates per model
    --   * separate guard against cross-model collisions on alias_normalized
    --     (a partial unique index where it points to different models)
    -- The cross-model guard is enforced by trigger or by application logic
    -- since SQL alone can't express "unique except within the same group".
    -- For now, the table-level constraint is the per-model uniqueness; the
    -- model_aliases ingestion path in the watchers must check for cross-model
    -- collisions before INSERT.
    UNIQUE (miner_model_id, alias)
);

COMMENT ON TABLE hardware.model_aliases IS
'Fuzzy model name matching table. Every known alias for every miner model.
alias_normalized = lower(alias) with spaces, hyphens, underscores, dots stripped.
Use trigram similarity on alias + alias_normalized to resolve incoming data.
Example: "s19j pro", "s19jpro", "antminers19jpro", "S19J-Pro" → all resolve to same miner_model_id.
Uniqueness: (miner_model_id, alias) — the same human-readable alias cannot be
listed twice for one model, but two human variants that normalize identically
("S21EXP" and "S21 EXP" both → "s21exp") are both valid rows. Cross-model
normalized collisions are checked at ingestion time by the manufacturer
watcher (see PR #16). Auto-generate variants on INSERT to miner_models via
application trigger.';

CREATE INDEX idx_aliases_model ON hardware.model_aliases(miner_model_id);
CREATE INDEX idx_aliases_trgm ON hardware.model_aliases USING GIN(alias gin_trgm_ops);
CREATE INDEX idx_aliases_normalized_trgm ON hardware.model_aliases USING GIN(alias_normalized gin_trgm_ops);
CREATE INDEX idx_aliases_common ON hardware.model_aliases(miner_model_id) WHERE is_common = TRUE;

CREATE TRIGGER trg_aliases_updated_at
    BEFORE UPDATE ON hardware.model_aliases
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- MODEL SPEC HISTORY — versioned specs (specs change over product lifetime)
-- ---------------------------------------------------------------------------
CREATE TABLE hardware.model_spec_history (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_model_id  UUID NOT NULL REFERENCES hardware.miner_models(id) ON DELETE CASCADE,
    spec_version    TEXT NOT NULL,          -- "v1.0", "batch_2023Q1", etc.
    effective_date  DATE NOT NULL,          -- When this spec became effective
    superseded_date DATE,                   -- NULL = currently active
    -- Snapshot of key specs at this version
    hashrate_th     NUMERIC(10,3),
    power_w         NUMERIC(8,2),
    efficiency_j_th NUMERIC(8,4),
    voltage_v_nom   NUMERIC(6,2),
    -- Full spec snapshot (JSONB for any field)
    spec_snapshot   JSONB NOT NULL DEFAULT '{}',
    change_summary  TEXT,                   -- What changed from previous version
    change_reason   TEXT,                   -- Why it changed (batch change, firmware, etc.)
    -- Source
    primary_source_id UUID REFERENCES knowledge.sources(id),
    confidence      public.confidence_level NOT NULL DEFAULT 'medium',
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE hardware.model_spec_history IS
'Versioned spec history for miner models. Bitmain sometimes silently changes specs
between production batches. This table preserves all known spec versions with dates.
spec_snapshot JSONB captures the full spec at that version for any field not in columns.';

CREATE INDEX idx_spec_history_model ON hardware.model_spec_history(miner_model_id);
CREATE INDEX idx_spec_history_date ON hardware.model_spec_history(effective_date DESC);
CREATE INDEX idx_spec_history_active ON hardware.model_spec_history(miner_model_id, superseded_date)
    WHERE superseded_date IS NULL;
CREATE INDEX idx_spec_history_snapshot ON hardware.model_spec_history USING GIN(spec_snapshot);

CREATE TRIGGER trg_spec_history_updated_at
    BEFORE UPDATE ON hardware.model_spec_history
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- PSU COMPATIBILITY — which PSUs work with which miners
-- ---------------------------------------------------------------------------
CREATE TABLE hardware.psu_compatibility (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_model_id  UUID NOT NULL REFERENCES hardware.miner_models(id) ON DELETE CASCADE,
    psu_model_id    UUID NOT NULL REFERENCES hardware.psu_models(id) ON DELETE CASCADE,
    is_oem_included BOOLEAN NOT NULL DEFAULT FALSE,
    compatibility_status TEXT NOT NULL DEFAULT 'compatible',
    -- 'compatible', 'incompatible', 'requires_adapter', 'degraded', 'untested'
    notes           TEXT,
    primary_source_id UUID REFERENCES knowledge.sources(id),
    confidence      public.confidence_level NOT NULL DEFAULT 'medium',
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (miner_model_id, psu_model_id)
);

COMMENT ON TABLE hardware.psu_compatibility IS
'Many-to-many: which PSUs are compatible with which miners.
is_oem_included = TRUE for the PSU bundled in the retail package.
Tracks adapter requirements and incompatibilities.';

CREATE INDEX idx_psu_compat_miner ON hardware.psu_compatibility(miner_model_id);
CREATE INDEX idx_psu_compat_psu ON hardware.psu_compatibility(psu_model_id);

CREATE TRIGGER trg_psu_compat_updated_at
    BEFORE UPDATE ON hardware.psu_compatibility
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- COOLING COMPATIBILITY — which cooling systems work with which miners
-- ---------------------------------------------------------------------------
CREATE TABLE hardware.cooling_compatibility (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_model_id      UUID NOT NULL REFERENCES hardware.miner_models(id) ON DELETE CASCADE,
    cooling_type        public.cooling_type NOT NULL,
    cooling_solution_id UUID,               -- FK to facility.cooling_solutions (cross-schema)
    compatibility_status TEXT NOT NULL DEFAULT 'compatible',
    is_designed_for     BOOLEAN NOT NULL DEFAULT FALSE, -- TRUE = designed for this cooling
    requires_modification BOOLEAN NOT NULL DEFAULT FALSE,
    modification_notes  TEXT,
    -- Performance impact
    hashrate_impact_pct  NUMERIC(6,2),     -- % change vs stock cooling
    power_impact_pct     NUMERIC(6,2),
    thermal_headroom_c   INTEGER,           -- Extra headroom gained vs air cooling
    notes                TEXT,
    primary_source_id    UUID REFERENCES knowledge.sources(id),
    confidence           public.confidence_level NOT NULL DEFAULT 'medium',
    metadata             JSONB NOT NULL DEFAULT '{}',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE hardware.cooling_compatibility IS
'Tracks which cooling types work with each miner model, and what modifications if any.
is_designed_for=TRUE for the OEM cooling (e.g., AH3880 designed for hydro).
hashrate_impact_pct: immersion often enables +50% TH/s via overclocking.';

CREATE INDEX idx_cool_compat_miner ON hardware.cooling_compatibility(miner_model_id);
CREATE INDEX idx_cool_compat_type ON hardware.cooling_compatibility(cooling_type);

CREATE TRIGGER trg_cool_compat_updated_at
    BEFORE UPDATE ON hardware.cooling_compatibility
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
-- =============================================================================
-- MINING INTELLIGENCE CATALOG — Part 3: Category 2 — Firmware
-- Tables: firmware_releases, firmware_api_capabilities, firmware_telemetry_fields,
--         firmware_bugs, firmware_compatibility, firmware_changelog
-- =============================================================================

-- ---------------------------------------------------------------------------
-- FIRMWARE RELEASES
-- ---------------------------------------------------------------------------
CREATE TABLE firmware.firmware_releases (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    firmware_family     public.firmware_family NOT NULL,
    version_string      TEXT NOT NULL,       -- "2024-10-22-legacy", "1.11.0.30", "24.09"
    version_major       INTEGER,
    version_minor       INTEGER,
    version_patch       INTEGER,
    version_build       TEXT,                -- Extra build tag
    display_name        TEXT NOT NULL,       -- Human-readable "BiXBiT 2024-10-22"
    -- Developer
    developer_name      TEXT,               -- "BiXBiT", "Braiins", "Luxor", "Bitmain"
    developer_url       TEXT,
    download_url        TEXT,               -- Direct download if public
    release_notes_url   TEXT,
    -- Dates
    release_date        DATE,
    end_of_support_date DATE,
    is_current_stable   BOOLEAN NOT NULL DEFAULT FALSE,
    is_beta             BOOLEAN NOT NULL DEFAULT FALSE,
    is_deprecated       BOOLEAN NOT NULL DEFAULT FALSE,
    -- Capabilities summary
    supports_autotuning BOOLEAN NOT NULL DEFAULT FALSE,
    supports_eco_mode   BOOLEAN NOT NULL DEFAULT FALSE,
    supports_turbo_mode BOOLEAN NOT NULL DEFAULT FALSE,
    supports_stratum_v2 BOOLEAN NOT NULL DEFAULT FALSE,
    supports_ssl_mining BOOLEAN NOT NULL DEFAULT FALSE,
    supports_api        BOOLEAN NOT NULL DEFAULT TRUE,
    api_version         TEXT,
    supports_ssh        BOOLEAN NOT NULL DEFAULT FALSE,
    supports_web_ui     BOOLEAN NOT NULL DEFAULT TRUE,
    -- Performance modifications possible with this firmware
    max_hashrate_increase_pct NUMERIC(6,2),  -- % above stock possible (e.g., 54% for BiXBiT)
    -- Hash algorithm
    algorithm           TEXT NOT NULL DEFAULT 'SHA-256',
    -- Source tracking
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    search_vector       TSVECTOR,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (firmware_family, version_string)
);

COMMENT ON TABLE firmware.firmware_releases IS
'All known firmware releases across all families. One row per version per family.
BiXBiT firmware can push S19j Pro from 104 TH/s → 160 TH/s (54% increase) and
S21 EXP Hydro from 430 TH/s → 506 TH/s. These are stored in firmware_compatibility.
API capabilities per firmware are in firmware_api_capabilities (one row per endpoint).';

CREATE INDEX idx_fw_family ON firmware.firmware_releases(firmware_family);
CREATE INDEX idx_fw_current ON firmware.firmware_releases(is_current_stable) WHERE is_current_stable = TRUE;
CREATE INDEX idx_fw_version ON firmware.firmware_releases(firmware_family, version_string);
CREATE INDEX idx_fw_search ON firmware.firmware_releases USING GIN(search_vector);
CREATE INDEX idx_fw_metadata ON firmware.firmware_releases USING GIN(metadata);

CREATE TRIGGER trg_fw_updated_at
    BEFORE UPDATE ON firmware.firmware_releases
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- N6 (2026-04-27): firmware_family is an enum; tsvector_update_trigger
-- requires text-typed columns AND does not accept casts in its arg list.
-- Replaced with a custom PL/pgSQL trigger that builds the tsvector explicitly
-- with enum->text coercion. Same indexable result, schema deploys cleanly.
CREATE OR REPLACE FUNCTION firmware.fw_search_vector_trigger()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('pg_catalog.english', coalesce(NEW.firmware_family::text, '')), 'A') ||
        setweight(to_tsvector('pg_catalog.english', coalesce(NEW.version_string, '')), 'A') ||
        setweight(to_tsvector('pg_catalog.english', coalesce(NEW.display_name, '')), 'B') ||
        setweight(to_tsvector('pg_catalog.english', coalesce(NEW.developer_name, '')), 'C') ||
        setweight(to_tsvector('pg_catalog.english', coalesce(NEW.notes, '')), 'D');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_fw_search_vector
    BEFORE INSERT OR UPDATE ON firmware.firmware_releases
    FOR EACH ROW EXECUTE FUNCTION firmware.fw_search_vector_trigger();

-- ---------------------------------------------------------------------------
-- FIRMWARE ↔ HARDWARE COMPATIBILITY MATRIX
-- Which firmware versions run on which hardware?
-- ---------------------------------------------------------------------------
CREATE TABLE firmware.firmware_compatibility (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    firmware_id         UUID NOT NULL REFERENCES firmware.firmware_releases(id) ON DELETE CASCADE,
    miner_model_id      UUID NOT NULL REFERENCES hardware.miner_models(id) ON DELETE CASCADE,
    -- Compatibility status
    is_compatible       BOOLEAN NOT NULL DEFAULT TRUE,
    is_officially_supported BOOLEAN NOT NULL DEFAULT FALSE, -- Vendor endorses this combo
    requires_hardware_mod   BOOLEAN NOT NULL DEFAULT FALSE,
    -- Performance with this firmware on this hardware
    typical_hashrate_th     NUMERIC(10,3),     -- Typical TH/s achieved
    typical_power_w         NUMERIC(8,2),
    max_achievable_th       NUMERIC(10,3),     -- Max TH/s possible with this FW
    max_achievable_w        NUMERIC(8,2),
    efficiency_j_th         NUMERIC(8,4),
    -- Configuration
    install_difficulty      TEXT DEFAULT 'easy',
    -- 'trivial', 'easy', 'moderate', 'hard', 'expert_only'
    install_instructions_url TEXT,
    rollback_possible        BOOLEAN NOT NULL DEFAULT TRUE,
    -- Risk notes
    known_risks              JSONB NOT NULL DEFAULT '[]',
    -- [{"risk": "voids warranty", "severity": "medium"}, ...]
    -- Source
    primary_source_id    UUID REFERENCES knowledge.sources(id),
    confidence           public.confidence_level NOT NULL DEFAULT 'medium',
    verified_by_bobby    BOOLEAN NOT NULL DEFAULT FALSE,  -- Bobby personally verified
    notes                TEXT,
    metadata             JSONB NOT NULL DEFAULT '{}',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (firmware_id, miner_model_id)
);

COMMENT ON TABLE firmware.firmware_compatibility IS
'The firmware × hardware compatibility matrix. Critical for Mining Guardian:
"Can I flash this miner with BiXBiT?" → JOIN this table.
verified_by_bobby=TRUE is a premium flag — Bobby runs the unit and measured actual performance.
max_achievable_th is the real-world ceiling Bobby has observed, not manufacturer claim.';

CREATE INDEX idx_fw_compat_fw ON firmware.firmware_compatibility(firmware_id);
CREATE INDEX idx_fw_compat_model ON firmware.firmware_compatibility(miner_model_id);
CREATE INDEX idx_fw_compat_bobby ON firmware.firmware_compatibility(verified_by_bobby)
    WHERE verified_by_bobby = TRUE;
CREATE INDEX idx_fw_compat_compatible ON firmware.firmware_compatibility(miner_model_id)
    WHERE is_compatible = TRUE;

CREATE TRIGGER trg_fw_compat_updated_at
    BEFORE UPDATE ON firmware.firmware_compatibility
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- FIRMWARE API CAPABILITIES — what does each firmware's API expose?
-- ---------------------------------------------------------------------------
CREATE TABLE firmware.firmware_api_capabilities (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    firmware_id         UUID NOT NULL REFERENCES firmware.firmware_releases(id) ON DELETE CASCADE,
    endpoint_path       TEXT NOT NULL,       -- "/summary", "/stats", "/pools", etc.
    http_method         TEXT NOT NULL DEFAULT 'GET',
    api_type            TEXT NOT NULL DEFAULT 'cgminer_json',
    -- 'cgminer_json', 'rest_json', 'rest_xml', 'websocket', 'grpc', 'proprietary'
    requires_auth       BOOLEAN NOT NULL DEFAULT FALSE,
    auth_type           TEXT,               -- 'basic', 'token', 'none'
    -- What data this endpoint provides
    data_category       TEXT NOT NULL,
    -- 'hashrate', 'temperature', 'power', 'pool', 'errors', 'fan', 'version', 'config', etc.
    response_schema     JSONB,              -- JSON Schema of the response
    sample_response     JSONB,              -- A real example response (anonymized)
    -- Polling recommendations
    recommended_poll_seconds INTEGER,
    is_real_time        BOOLEAN NOT NULL DEFAULT FALSE,
    -- Availability
    available_since_version TEXT,
    deprecated_in_version   TEXT,
    is_available        BOOLEAN NOT NULL DEFAULT TRUE,
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (firmware_id, endpoint_path, http_method)
);

COMMENT ON TABLE firmware.firmware_api_capabilities IS
'Every API endpoint exposed by every firmware version. Mining Guardian uses this to
decide HOW to poll a miner based on what firmware it is running.
response_schema stores a JSON Schema so Guardian can validate API responses.
sample_response stores a real anonymized example for development/testing.';

CREATE INDEX idx_fw_api_firmware ON firmware.firmware_api_capabilities(firmware_id);
CREATE INDEX idx_fw_api_category ON firmware.firmware_api_capabilities(data_category);
CREATE INDEX idx_fw_api_available ON firmware.firmware_api_capabilities(firmware_id)
    WHERE is_available = TRUE;
CREATE INDEX idx_fw_api_schema ON firmware.firmware_api_capabilities USING GIN(response_schema);
CREATE INDEX idx_fw_api_sample ON firmware.firmware_api_capabilities USING GIN(sample_response);

CREATE TRIGGER trg_fw_api_updated_at
    BEFORE UPDATE ON firmware.firmware_api_capabilities
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- FIRMWARE TELEMETRY FIELDS — what telemetry fields does each firmware expose?
-- ---------------------------------------------------------------------------
CREATE TABLE firmware.firmware_telemetry_fields (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    firmware_id         UUID NOT NULL REFERENCES firmware.firmware_releases(id) ON DELETE CASCADE,
    field_name          TEXT NOT NULL,       -- "CHIP_TEMP_MAX", "RT_HASHRATE_5M", etc.
    field_path          TEXT,               -- JSON path if nested: "stats[0].GHS_5s"
    data_type           TEXT NOT NULL,      -- 'float', 'integer', 'string', 'boolean', 'array'
    unit                TEXT,              -- 'celsius', 'GH/s', 'watts', 'V', 'A', 'RPM', '%'
    -- Mapping to canonical Mining Guardian field names
    guardian_canonical_field TEXT,         -- "board0_temp", "total_hashrate", etc.
    -- Valid ranges (for alert thresholds)
    valid_min           NUMERIC,
    valid_max           NUMERIC,
    typical_min         NUMERIC,
    typical_max         NUMERIC,
    alert_threshold_low  NUMERIC,
    alert_threshold_high NUMERIC,
    -- Which API endpoint provides this field
    api_capability_id   UUID REFERENCES firmware.firmware_api_capabilities(id),
    poll_frequency_s    INTEGER,            -- How often this field updates
    is_available        BOOLEAN NOT NULL DEFAULT TRUE,
    is_key_metric       BOOLEAN NOT NULL DEFAULT FALSE,  -- Is this a primary monitoring field?
    notes               TEXT,
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (firmware_id, field_name)
);

COMMENT ON TABLE firmware.firmware_telemetry_fields IS
'Every telemetry field that every firmware version reports. Enables Mining Guardian
to build dynamic parsers: "For this firmware version, field CHIP_TEMP_MAX maps to
guardian_canonical_field=board_max_temp, unit=celsius, alert_high=90."
guardian_canonical_field normalizes across all firmware families.';

CREATE INDEX idx_fw_telem_firmware ON firmware.firmware_telemetry_fields(firmware_id);
CREATE INDEX idx_fw_telem_canonical ON firmware.firmware_telemetry_fields(guardian_canonical_field);
CREATE INDEX idx_fw_telem_key ON firmware.firmware_telemetry_fields(firmware_id)
    WHERE is_key_metric = TRUE;

CREATE TRIGGER trg_fw_telem_updated_at
    BEFORE UPDATE ON firmware.firmware_telemetry_fields
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- FIRMWARE BUGS — known bugs per firmware version
-- ---------------------------------------------------------------------------
CREATE TABLE firmware.firmware_bugs (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    firmware_id         UUID NOT NULL REFERENCES firmware.firmware_releases(id) ON DELETE CASCADE,
    bug_title           TEXT NOT NULL,
    bug_description     TEXT NOT NULL,
    -- Classification
    severity            public.failure_severity NOT NULL DEFAULT 'low',
    bug_category        TEXT NOT NULL,
    -- 'api_reporting', 'performance_loss', 'stability', 'security', 'telemetry_inaccurate',
    --  'pool_disconnect', 'fan_control', 'thermal_management', 'autotuning', 'watchdog'
    affected_feature    TEXT,
    -- Impact
    impacts_hashrate    BOOLEAN NOT NULL DEFAULT FALSE,
    impacts_stability   BOOLEAN NOT NULL DEFAULT FALSE,
    impacts_api         BOOLEAN NOT NULL DEFAULT FALSE,
    impacts_telemetry   BOOLEAN NOT NULL DEFAULT FALSE,
    hashrate_impact_pct NUMERIC(6,2),       -- % hashrate lost due to bug
    -- Resolution
    is_fixed            BOOLEAN NOT NULL DEFAULT FALSE,
    fixed_in_version    TEXT,
    fixed_firmware_id   UUID REFERENCES firmware.firmware_releases(id),
    workaround          TEXT,
    -- Affected hardware (NULL = all hardware running this firmware)
    affected_model_id   UUID REFERENCES hardware.miner_models(id),
    -- Discovery
    discovered_date     DATE,
    reported_by         UUID REFERENCES knowledge.contributors(id),
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    external_bug_id     TEXT,               -- CVE number or vendor bug tracker ID
    reference_urls      JSONB NOT NULL DEFAULT '[]',
    metadata            JSONB NOT NULL DEFAULT '{}',
    search_vector       TSVECTOR,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE firmware.firmware_bugs IS
'Known bugs per firmware version. Critical for Mining Guardian:
"I am seeing random pool disconnects on BiXBiT v2024-10-22 — is this a known bug?"
impacts_telemetry=TRUE is crucial — if a bug makes API data unreliable, Guardian
must know not to trust that telemetry for alerting.';

CREATE INDEX idx_fw_bugs_firmware ON firmware.firmware_bugs(firmware_id);
CREATE INDEX idx_fw_bugs_severity ON firmware.firmware_bugs(severity);
CREATE INDEX idx_fw_bugs_unfixed ON firmware.firmware_bugs(firmware_id)
    WHERE is_fixed = FALSE;
CREATE INDEX idx_fw_bugs_model ON firmware.firmware_bugs(affected_model_id)
    WHERE affected_model_id IS NOT NULL;
CREATE INDEX idx_fw_bugs_search ON firmware.firmware_bugs USING GIN(search_vector);

CREATE TRIGGER trg_fw_bugs_updated_at
    BEFORE UPDATE ON firmware.firmware_bugs
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_fw_bugs_search_vector
    BEFORE INSERT OR UPDATE ON firmware.firmware_bugs
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        bug_title, bug_description, bug_category, affected_feature, workaround
    );

-- ---------------------------------------------------------------------------
-- FIRMWARE CHANGELOG — structured change tracking per version
-- ---------------------------------------------------------------------------
CREATE TABLE firmware.firmware_changelog (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    firmware_id         UUID NOT NULL REFERENCES firmware.firmware_releases(id) ON DELETE CASCADE,
    previous_firmware_id UUID REFERENCES firmware.firmware_releases(id),
    change_type         TEXT NOT NULL,
    -- 'bugfix', 'feature', 'performance', 'security', 'breaking_change', 'api_change'
    change_title        TEXT NOT NULL,
    change_description  TEXT,
    affected_feature    TEXT,
    is_breaking_change  BOOLEAN NOT NULL DEFAULT FALSE,
    migration_notes     TEXT,               -- Required steps to migrate from previous version
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE firmware.firmware_changelog IS
'Structured changelog entries per firmware version transition.
is_breaking_change=TRUE triggers a review before Mining Guardian auto-updates any fleet units.';

CREATE INDEX idx_fw_changelog_firmware ON firmware.firmware_changelog(firmware_id);
CREATE INDEX idx_fw_changelog_breaking ON firmware.firmware_changelog(firmware_id)
    WHERE is_breaking_change = TRUE;

CREATE TRIGGER trg_fw_changelog_updated_at
    BEFORE UPDATE ON firmware.firmware_changelog
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- FIRMWARE AUTOTUNING PROFILES — profiles within firmware (eco/turbo/custom)
-- ---------------------------------------------------------------------------
CREATE TABLE firmware.firmware_autotuning_profiles (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    firmware_id         UUID NOT NULL REFERENCES firmware.firmware_releases(id) ON DELETE CASCADE,
    miner_model_id      UUID NOT NULL REFERENCES hardware.miner_models(id) ON DELETE CASCADE,
    profile_name        TEXT NOT NULL,      -- "Eco", "Turbo", "Normal", "BiXBiT_Max"
    operational_mode    public.operational_mode NOT NULL,
    -- Target performance
    target_hashrate_th  NUMERIC(10,3),
    target_power_w      NUMERIC(8,2),
    target_efficiency_j_th NUMERIC(8,4),
    -- Actual measured performance
    measured_hashrate_th NUMERIC(10,3),
    measured_power_w     NUMERIC(8,2),
    measured_efficiency_j_th NUMERIC(8,4),
    -- Hardware settings
    core_voltage_mv     INTEGER,
    frequency_mhz       INTEGER,
    -- Environmental requirements
    ambient_temp_max_c  INTEGER,            -- Max ambient for this profile
    coolant_temp_max_c  INTEGER,            -- For liquid cooling
    -- Bobby's verification
    verified_by_bobby   BOOLEAN NOT NULL DEFAULT FALSE,
    verification_date   DATE,
    verification_notes  TEXT,
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (firmware_id, miner_model_id, profile_name)
);

COMMENT ON TABLE firmware.firmware_autotuning_profiles IS
'Specific autotuning profiles per firmware per hardware model. This captures
"Auradine Teraflux AH3880: Eco mode = 300 TH/s, Turbo mode = 600 TH/s" and
"S21 EXP Hydro on BiXBiT: up to 506 TH/s achievable."
measured_* fields are Bobby-verified actuals vs target_* which are spec/marketing claims.';

CREATE INDEX idx_fw_profiles_firmware ON firmware.firmware_autotuning_profiles(firmware_id);
CREATE INDEX idx_fw_profiles_model ON firmware.firmware_autotuning_profiles(miner_model_id);
CREATE INDEX idx_fw_profiles_bobby ON firmware.firmware_autotuning_profiles(verified_by_bobby)
    WHERE verified_by_bobby = TRUE;

CREATE TRIGGER trg_fw_profiles_updated_at
    BEFORE UPDATE ON firmware.firmware_autotuning_profiles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
-- =============================================================================
-- MINING INTELLIGENCE CATALOG — Part 4: Category 3 — Operational Intelligence
-- Tables: failure_patterns, failure_symptoms, operational_thresholds,
--         environmental_correlations, operational_profiles, alert_rules
-- =============================================================================

-- ---------------------------------------------------------------------------
-- FAILURE PATTERNS — the root cause knowledge base
-- ---------------------------------------------------------------------------
CREATE TABLE ops.failure_patterns (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pattern_name        TEXT NOT NULL,      -- Short name "Dead hashboard", "Fan failure"
    pattern_code        TEXT UNIQUE,        -- Machine code "HP-DEAD-BOARD-001"
    description         TEXT NOT NULL,
    -- Classification
    failure_category    TEXT NOT NULL,
    -- 'hashboard', 'psu', 'control_board', 'fan', 'thermal', 'network',
    --  'firmware', 'pool', 'electrical', 'physical_damage', 'chip_level'
    severity            public.failure_severity NOT NULL,
    -- Scope
    is_model_specific   BOOLEAN NOT NULL DEFAULT FALSE,
    primary_model_id    UUID REFERENCES hardware.miner_models(id),
    -- Can also affect specific chips, boards, firmware
    affected_chip_id    UUID REFERENCES hardware.chips(id),
    affected_hashboard_id UUID REFERENCES hardware.hashboards(id),
    affected_firmware_id  UUID REFERENCES firmware.firmware_releases(id),
    -- Root cause analysis
    root_cause          TEXT NOT NULL,
    root_cause_category TEXT NOT NULL,
    -- 'design_flaw', 'manufacturing_defect', 'wear_degradation', 'overheating',
    --  'power_event', 'firmware_bug', 'user_error', 'environmental', 'unknown'
    -- Incidence
    estimated_occurrence_rate NUMERIC(6,4), -- Rate: 0.001 = 0.1% of units affected
    occurrence_rate_source    TEXT,
    -- Typical timeline
    typical_age_at_failure_days INTEGER,
    early_failure       BOOLEAN NOT NULL DEFAULT FALSE,  -- Infant mortality pattern
    -- Success rates for fixes
    repair_success_rate  NUMERIC(5,4),      -- 0.0 – 1.0
    repair_success_source TEXT,
    -- Confidence
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    verified_by_bobby   BOOLEAN NOT NULL DEFAULT FALSE,
    -- Full-text
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    search_vector       TSVECTOR,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ops.failure_patterns IS
'The failure knowledge base — root causes, categories, and incidence rates.
Mining Guardian uses this for: "I see X symptoms → likely failure pattern Y → try repair Z."
Pattern codes (HP-DEAD-BOARD-001) enable fast lookup without full-text search.
repair_success_rate is aggregated from repair.repair_records periodically.';

CREATE INDEX idx_fp_category ON ops.failure_patterns(failure_category);
CREATE INDEX idx_fp_severity ON ops.failure_patterns(severity);
CREATE INDEX idx_fp_model ON ops.failure_patterns(primary_model_id)
    WHERE primary_model_id IS NOT NULL;
CREATE INDEX idx_fp_bobby ON ops.failure_patterns(verified_by_bobby)
    WHERE verified_by_bobby = TRUE;
CREATE INDEX idx_fp_search ON ops.failure_patterns USING GIN(search_vector);
CREATE INDEX idx_fp_metadata ON ops.failure_patterns USING GIN(metadata);

CREATE TRIGGER trg_fp_updated_at
    BEFORE UPDATE ON ops.failure_patterns
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_fp_search_vector
    BEFORE INSERT OR UPDATE ON ops.failure_patterns
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        pattern_name, description, failure_category, root_cause, notes
    );

-- ---------------------------------------------------------------------------
-- FAILURE SYMPTOMS — observable indicators linked to failure patterns
-- One pattern can have many symptoms; one symptom can indicate many patterns
-- ---------------------------------------------------------------------------
CREATE TABLE ops.failure_symptoms (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symptom_code    TEXT UNIQUE,             -- "SYM-BOARD-MISSING-001"
    symptom_name    TEXT NOT NULL,
    description     TEXT NOT NULL,
    -- How is this symptom observed?
    detection_method TEXT NOT NULL,
    -- 'api_data', 'visual_inspection', 'temperature_reading', 'hashrate_drop',
    --  'error_log', 'pool_dashboard', 'power_meter', 'smell', 'sound', 'physical'
    -- API-specific detection
    api_field       TEXT,                   -- Which telemetry field shows this symptom
    api_threshold_operator TEXT,            -- '>', '<', '=', '!=', 'contains'
    api_threshold_value    TEXT,            -- The threshold value
    -- Severity hint
    typical_severity public.failure_severity,
    urgency_hours   INTEGER,                -- How many hours before this needs addressing
    -- Search
    search_vector   TSVECTOR,
    metadata        JSONB NOT NULL DEFAULT '{}',
    primary_source_id UUID REFERENCES knowledge.sources(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ops.failure_symptoms IS
'Observable symptoms — what you SEE or MEASURE when something is wrong.
Detection methods include API telemetry, visual inspection, sound (fan rattle),
smell (capacitor burn), hashrate drops, error codes, etc.
Linked to failure_patterns via ops.symptom_pattern_map (M2M).';

CREATE INDEX idx_symptoms_method ON ops.failure_symptoms(detection_method);
CREATE INDEX idx_symptoms_api ON ops.failure_symptoms(api_field)
    WHERE api_field IS NOT NULL;
CREATE INDEX idx_symptoms_search ON ops.failure_symptoms USING GIN(search_vector);

CREATE TRIGGER trg_symptoms_updated_at
    BEFORE UPDATE ON ops.failure_symptoms
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_symptoms_search_vector
    BEFORE INSERT OR UPDATE ON ops.failure_symptoms
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        symptom_name, description, detection_method
    );

-- ---------------------------------------------------------------------------
-- SYMPTOM ↔ PATTERN MAPPING (M2M with probability weighting)
-- ---------------------------------------------------------------------------
CREATE TABLE ops.symptom_pattern_map (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symptom_id          UUID NOT NULL REFERENCES ops.failure_symptoms(id) ON DELETE CASCADE,
    pattern_id          UUID NOT NULL REFERENCES ops.failure_patterns(id) ON DELETE CASCADE,
    -- Bayesian-style: if you see this symptom, how likely is this pattern?
    probability         NUMERIC(5,4) NOT NULL DEFAULT 0.5 CHECK (probability BETWEEN 0 AND 1),
    -- 0.9 = 90% chance this pattern when this symptom is seen
    is_pathognomonic    BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE = symptom ONLY occurs with this pattern
    symptom_is_required BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE = pattern always shows this symptom
    -- Compound: other symptoms that increase/decrease probability together
    modifying_symptoms  JSONB NOT NULL DEFAULT '[]',
    -- [{"symptom_id": "...", "probability_multiplier": 1.5, "description": "..."}]
    notes               TEXT,
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (symptom_id, pattern_id)
);

COMMENT ON TABLE ops.symptom_pattern_map IS
'Probabilistic mapping between symptoms and failure patterns.
Mining Guardian uses this for differential diagnosis:
"Seeing high temp + low hashrate on one board → 0.7 probability dead hashboard,
0.3 probability thermal paste failure." Higher probability patterns shown first.';

CREATE INDEX idx_spm_symptom ON ops.symptom_pattern_map(symptom_id);
CREATE INDEX idx_spm_pattern ON ops.symptom_pattern_map(pattern_id);
CREATE INDEX idx_spm_probability ON ops.symptom_pattern_map(probability DESC);

CREATE TRIGGER trg_spm_updated_at
    BEFORE UPDATE ON ops.symptom_pattern_map
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- OPERATIONAL THRESHOLDS — per model, per firmware, per cooling type
-- ---------------------------------------------------------------------------
CREATE TABLE ops.operational_thresholds (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Scope — can be global, model-specific, firmware-specific, or combo
    miner_model_id      UUID REFERENCES hardware.miner_models(id),  -- NULL = all models
    firmware_id         UUID REFERENCES firmware.firmware_releases(id),  -- NULL = all firmware
    cooling_type        public.cooling_type,    -- NULL = all cooling types
    operational_mode    public.operational_mode, -- NULL = all modes
    threshold_name      TEXT NOT NULL,          -- "Max chip temp air cooling"
    -- Temperature thresholds (Celsius)
    chip_temp_warning_c  INTEGER,
    chip_temp_critical_c INTEGER,
    chip_temp_shutdown_c INTEGER,
    board_temp_warning_c INTEGER,
    board_temp_critical_c INTEGER,
    coolant_temp_warning_c INTEGER,     -- For liquid cooling
    coolant_temp_critical_c INTEGER,
    ambient_temp_warning_c INTEGER,
    ambient_temp_max_c  INTEGER,
    -- Hashrate thresholds (% of expected)
    hashrate_low_warning_pct  NUMERIC(5,2),  -- e.g., 95% = warn if >5% below expected
    hashrate_low_critical_pct NUMERIC(5,2),  -- e.g., 80% = critical if >20% below
    hashrate_variance_max_pct NUMERIC(5,2),  -- Max acceptable variance between boards
    -- Power thresholds
    power_high_warning_w  NUMERIC(8,2),
    power_high_critical_w NUMERIC(8,2),
    power_low_warning_w   NUMERIC(8,2),      -- Unexpected low power may mean dead board
    -- Voltage thresholds (input)
    voltage_low_warning_v  NUMERIC(6,3),
    voltage_low_critical_v NUMERIC(6,3),
    voltage_high_warning_v NUMERIC(6,3),
    voltage_high_critical_v NUMERIC(6,3),
    -- Fan speed (RPM)
    fan_speed_low_rpm   INTEGER,
    fan_speed_high_rpm  INTEGER,
    -- Uptime / connectivity
    max_pool_reject_rate_pct NUMERIC(5,2),   -- Alert if reject rate exceeds this
    max_api_timeout_s   INTEGER,
    -- Valid date range for this threshold set
    effective_from      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_to        TIMESTAMPTZ,          -- NULL = still current
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    verified_by_bobby   BOOLEAN NOT NULL DEFAULT FALSE,
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    search_vector       TSVECTOR,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ops.operational_thresholds IS
'Threshold definitions for every alert-worthy metric, scoped by model/firmware/cooling.
Mining Guardian looks up the most specific applicable threshold (most constraints).
For example: S19j Pro + BiXBiT + immersion has DIFFERENT thermal limits than
S19j Pro + stock + air. Effective_from/to allows historical threshold versioning.';

CREATE INDEX idx_thresh_model ON ops.operational_thresholds(miner_model_id)
    WHERE miner_model_id IS NOT NULL;
CREATE INDEX idx_thresh_firmware ON ops.operational_thresholds(firmware_id)
    WHERE firmware_id IS NOT NULL;
CREATE INDEX idx_thresh_cooling ON ops.operational_thresholds(cooling_type)
    WHERE cooling_type IS NOT NULL;
CREATE INDEX idx_thresh_current ON ops.operational_thresholds(effective_to)
    WHERE effective_to IS NULL;
CREATE INDEX idx_thresh_search ON ops.operational_thresholds USING GIN(search_vector);

CREATE TRIGGER trg_thresh_updated_at
    BEFORE UPDATE ON ops.operational_thresholds
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_thresh_search_vector
    BEFORE INSERT OR UPDATE ON ops.operational_thresholds
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english', threshold_name, notes
    );

-- ---------------------------------------------------------------------------
-- ENVIRONMENTAL CORRELATIONS — how environment affects performance
-- ---------------------------------------------------------------------------
CREATE TABLE ops.environmental_correlations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_model_id      UUID REFERENCES hardware.miner_models(id),  -- NULL = all
    cooling_type        public.cooling_type,
    correlation_type    TEXT NOT NULL,
    -- 'ambient_temp_vs_hashrate', 'ambient_temp_vs_power', 'humidity_vs_failures',
    --  'altitude_vs_performance', 'coolant_temp_vs_efficiency', 'hvac_setpoint_vs_output'
    -- The correlation (could be linear, polynomial, lookup table)
    correlation_function TEXT NOT NULL DEFAULT 'linear',
    -- 'linear', 'polynomial', 'lookup_table', 'exponential', 'empirical'
    -- Linear: y = slope * x + intercept
    slope               NUMERIC(12,6),
    intercept           NUMERIC(12,6),
    -- Polynomial coefficients [a0, a1, a2, ...] for a0 + a1*x + a2*x^2 + ...
    polynomial_coefficients JSONB,
    -- Lookup table: [{x: 20, y: 0.98}, {x: 25, y: 1.0}, {x: 30, y: 1.04}]
    lookup_table        JSONB,
    -- Variable definitions
    independent_var     TEXT NOT NULL,      -- e.g., "ambient_temp_celsius"
    independent_unit    TEXT,
    dependent_var       TEXT NOT NULL,      -- e.g., "hashrate_pct_of_nominal"
    dependent_unit      TEXT,
    -- Valid range for the correlation
    x_min               NUMERIC,
    x_max               NUMERIC,
    r_squared           NUMERIC(6,4),       -- Goodness of fit
    sample_count        INTEGER,            -- Number of data points this is based on
    -- Bobby's measured data
    measured_data_points JSONB,             -- Raw measurement pairs [{"x": 25.3, "y": 0.994}, ...]
    verified_by_bobby   BOOLEAN NOT NULL DEFAULT FALSE,
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'low',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ops.environmental_correlations IS
'Quantified relationships between environmental conditions and performance.
Example: "S19j Pro immersion: for every 1°C coolant temp above 30°C, hashrate drops 0.8%."
Bobby can log actual measured data points (measured_data_points JSONB) and the regression
parameters are calculated and stored. Mining Guardian uses these for predictive alerts.';

CREATE INDEX idx_env_model ON ops.environmental_correlations(miner_model_id)
    WHERE miner_model_id IS NOT NULL;
CREATE INDEX idx_env_cooling ON ops.environmental_correlations(cooling_type);
CREATE INDEX idx_env_type ON ops.environmental_correlations(correlation_type);
CREATE INDEX idx_env_bobby ON ops.environmental_correlations(verified_by_bobby)
    WHERE verified_by_bobby = TRUE;
CREATE INDEX idx_env_lookup ON ops.environmental_correlations USING GIN(lookup_table)
    WHERE lookup_table IS NOT NULL;

CREATE TRIGGER trg_env_updated_at
    BEFORE UPDATE ON ops.environmental_correlations
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- OPERATIONAL PROFILES — complete operating parameter sets per mode/model/firmware
-- ---------------------------------------------------------------------------
CREATE TABLE ops.operational_profiles (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_name        TEXT NOT NULL,
    miner_model_id      UUID NOT NULL REFERENCES hardware.miner_models(id),
    firmware_id         UUID REFERENCES firmware.firmware_releases(id),
    cooling_type        public.cooling_type NOT NULL,
    operational_mode    public.operational_mode NOT NULL,
    -- Performance targets
    target_hashrate_th  NUMERIC(10,3),
    target_power_w      NUMERIC(8,2),
    target_efficiency_j_th NUMERIC(8,4),
    -- Hardware settings
    core_voltage_mv     INTEGER,
    frequency_mhz       INTEGER,
    fan_speed_pct       INTEGER,            -- Target fan speed %
    -- Thermal targets
    target_chip_temp_c  INTEGER,
    target_coolant_temp_c INTEGER,
    -- Economic metrics (at time of profile creation)
    bitcoin_price_usd   NUMERIC(12,2),
    electricity_cost_kwh NUMERIC(8,4),
    estimated_daily_btc NUMERIC(18,8),
    estimated_daily_usd NUMERIC(10,2),
    estimated_daily_cost_usd NUMERIC(10,2),
    estimated_daily_profit_usd NUMERIC(10,2),
    -- Use conditions
    recommended_ambient_max_c INTEGER,
    recommended_coolant_max_c INTEGER,
    -- Bobby's usage
    is_bobby_active_profile BOOLEAN NOT NULL DEFAULT FALSE,
    bobby_notes         TEXT,
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    verified_by_bobby   BOOLEAN NOT NULL DEFAULT FALSE,
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ops.operational_profiles IS
'Complete operating configurations for each miner model + firmware + cooling type combo.
Each profile is a named configuration (Eco, Turbo, BiXBiT_Max) with full parameter set.
Economic metrics are snapshotted at profile creation time for historical comparison.
is_bobby_active_profile=TRUE = what Bobby is running right now on his fleet.';

CREATE INDEX idx_opprofile_model ON ops.operational_profiles(miner_model_id);
CREATE INDEX idx_opprofile_firmware ON ops.operational_profiles(firmware_id);
CREATE INDEX idx_opprofile_mode ON ops.operational_profiles(operational_mode);
CREATE INDEX idx_opprofile_bobby ON ops.operational_profiles(is_bobby_active_profile)
    WHERE is_bobby_active_profile = TRUE;

CREATE TRIGGER trg_opprofile_updated_at
    BEFORE UPDATE ON ops.operational_profiles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- ALERT RULES — parameterized alert definitions for Mining Guardian
-- ---------------------------------------------------------------------------
CREATE TABLE ops.alert_rules (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rule_name           TEXT NOT NULL,
    rule_code           TEXT UNIQUE,        -- "ALERT-TEMP-CHIP-HIGH-001"
    description         TEXT,
    -- Scope
    miner_model_id      UUID REFERENCES hardware.miner_models(id),  -- NULL = all
    firmware_id         UUID REFERENCES firmware.firmware_releases(id), -- NULL = all
    cooling_type        public.cooling_type,  -- NULL = all
    -- Condition
    metric_field        TEXT NOT NULL,      -- guardian_canonical_field name
    operator            TEXT NOT NULL,      -- '>', '<', '>=', '<=', '=', '!=', 'contains', 'not_null'
    threshold_value     TEXT NOT NULL,      -- The value to compare against
    threshold_unit      TEXT,
    -- Timing
    evaluation_window_s INTEGER NOT NULL DEFAULT 60,  -- Evaluate over this window
    min_duration_s      INTEGER NOT NULL DEFAULT 0,   -- Must persist for this long
    -- Alert
    severity            public.failure_severity NOT NULL DEFAULT 'medium',
    alert_title         TEXT NOT NULL,
    alert_body_template TEXT,              -- Template with {miner_id}, {value}, etc.
    -- Related failure patterns
    related_pattern_id  UUID REFERENCES ops.failure_patterns(id),
    -- Actions
    suggested_actions   JSONB NOT NULL DEFAULT '[]',
    auto_actions        JSONB NOT NULL DEFAULT '[]',  -- Actions Guardian can take automatically
    -- Meta
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ops.alert_rules IS
'Parameterized alert rule definitions. Mining Guardian evaluates these rules against
live telemetry and fires alerts when conditions are met.
related_pattern_id links an alert to the failure pattern it likely indicates.
auto_actions can contain safe automated responses (restart pool, reduce frequency, etc.).';

CREATE INDEX idx_alert_model ON ops.alert_rules(miner_model_id)
    WHERE miner_model_id IS NOT NULL;
CREATE INDEX idx_alert_active ON ops.alert_rules(is_active)
    WHERE is_active = TRUE;
CREATE INDEX idx_alert_severity ON ops.alert_rules(severity);
CREATE INDEX idx_alert_pattern ON ops.alert_rules(related_pattern_id)
    WHERE related_pattern_id IS NOT NULL;

CREATE TRIGGER trg_alert_updated_at
    BEFORE UPDATE ON ops.alert_rules
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- KNOWN NETWORK ERROR CODES (moved here from pool schema for cross-reference)
-- Errors that appear in miner API logs / telemetry
-- ---------------------------------------------------------------------------
CREATE TABLE ops.miner_error_codes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    error_code      TEXT NOT NULL,          -- "PLL_LOCK_FAILED", "E23", "CHIP_TEMP_HIGH"
    error_source    TEXT NOT NULL,          -- 'firmware_bitmain', 'firmware_bixbit', 'cgminer', etc.
    display_message TEXT,
    -- Classification
    severity        public.failure_severity NOT NULL DEFAULT 'medium',
    error_category  TEXT NOT NULL,
    -- 'thermal', 'hashboard', 'psu', 'network', 'pool', 'firmware', 'chip', 'fan', 'other'
    related_pattern_id UUID REFERENCES ops.failure_patterns(id),
    -- Affected scope
    miner_model_id  UUID REFERENCES hardware.miner_models(id),  -- NULL = all
    firmware_id     UUID REFERENCES firmware.firmware_releases(id), -- NULL = all
    -- Resolution
    resolution_steps JSONB NOT NULL DEFAULT '[]',
    is_transient    BOOLEAN NOT NULL DEFAULT FALSE, -- TRUE = often resolves itself
    -- Source
    primary_source_id UUID REFERENCES knowledge.sources(id),
    confidence      public.confidence_level NOT NULL DEFAULT 'medium',
    notes           TEXT,
    search_vector   TSVECTOR,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (error_code, error_source)
);

COMMENT ON TABLE ops.miner_error_codes IS
'Error codes reported by miners (firmware-specific codes and generic ones).
Mining Guardian maps raw error codes from API responses to this table to show
human-readable descriptions and suggested fixes.';

CREATE INDEX idx_errcodes_source ON ops.miner_error_codes(error_source);
CREATE INDEX idx_errcodes_pattern ON ops.miner_error_codes(related_pattern_id)
    WHERE related_pattern_id IS NOT NULL;
CREATE INDEX idx_errcodes_search ON ops.miner_error_codes USING GIN(search_vector);

CREATE TRIGGER trg_errcodes_updated_at
    BEFORE UPDATE ON ops.miner_error_codes
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_errcodes_search_vector
    BEFORE INSERT OR UPDATE ON ops.miner_error_codes
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        error_code, display_message, error_category, notes
    );
-- =============================================================================
-- MINING INTELLIGENCE CATALOG — Part 5: Category 4 — Community/Market
-- Tables: user_reviews, pricing_history, manufacturer_reputation,
--         forum_posts, teardown_reports, war_stories
-- =============================================================================

-- ---------------------------------------------------------------------------
-- USER REVIEWS
-- ---------------------------------------------------------------------------
CREATE TABLE market.user_reviews (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_model_id      UUID NOT NULL REFERENCES hardware.miner_models(id),
    reviewer_id         UUID REFERENCES knowledge.contributors(id),
    reviewer_handle     TEXT,               -- Cached alias if contributor not registered
    -- Ratings (1–10 scale for precision)
    overall_rating      NUMERIC(3,1) CHECK (overall_rating BETWEEN 1 AND 10),
    build_quality_rating NUMERIC(3,1) CHECK (build_quality_rating BETWEEN 1 AND 10),
    performance_rating  NUMERIC(3,1) CHECK (performance_rating BETWEEN 1 AND 10),
    value_rating        NUMERIC(3,1) CHECK (value_rating BETWEEN 1 AND 10),
    reliability_rating  NUMERIC(3,1) CHECK (reliability_rating BETWEEN 1 AND 10),
    support_rating      NUMERIC(3,1) CHECK (support_rating BETWEEN 1 AND 10),
    noise_rating        NUMERIC(3,1) CHECK (noise_rating BETWEEN 1 AND 10),
    -- Review content
    title               TEXT,
    body                TEXT,
    pros                JSONB NOT NULL DEFAULT '[]',    -- ["quiet", "stable hashrate"]
    cons                JSONB NOT NULL DEFAULT '[]',    -- ["hot at 35C ambient", "PSU noisy"]
    sentiment           public.sentiment,
    -- Context
    review_date         DATE,
    purchase_date       DATE,
    cooling_type_used   public.cooling_type,
    firmware_used       TEXT,
    hashrate_achieved_th NUMERIC(10,3),
    -- External source
    source_platform     TEXT,               -- 'reddit', 'telegram', 'discord', 'asicminervalue', etc.
    source_url          TEXT,
    -- Verification
    is_verified_purchase BOOLEAN NOT NULL DEFAULT FALSE,
    is_bobby_review      BOOLEAN NOT NULL DEFAULT FALSE,
    -- Quality signals
    helpful_votes        INTEGER NOT NULL DEFAULT 0,
    unhelpful_votes      INTEGER NOT NULL DEFAULT 0,
    is_spam              BOOLEAN NOT NULL DEFAULT FALSE,
    -- Source
    primary_source_id    UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence           public.confidence_level NOT NULL DEFAULT 'low',
    search_vector        TSVECTOR,
    metadata             JSONB NOT NULL DEFAULT '{}',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE market.user_reviews IS
'User reviews and ratings for miner models. Aggregated ratings feed back to
hardware.miner_models via periodic rollup. is_bobby_review=TRUE reviews get
higher weight as tier2 operational data.';

CREATE INDEX idx_reviews_model ON market.user_reviews(miner_model_id);
CREATE INDEX idx_reviews_rating ON market.user_reviews(miner_model_id, overall_rating DESC);
CREATE INDEX idx_reviews_platform ON market.user_reviews(source_platform);
CREATE INDEX idx_reviews_bobby ON market.user_reviews(is_bobby_review)
    WHERE is_bobby_review = TRUE;
CREATE INDEX idx_reviews_search ON market.user_reviews USING GIN(search_vector);
CREATE INDEX idx_reviews_pros ON market.user_reviews USING GIN(pros);
CREATE INDEX idx_reviews_cons ON market.user_reviews USING GIN(cons);

CREATE TRIGGER trg_reviews_updated_at
    BEFORE UPDATE ON market.user_reviews
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_reviews_search_vector
    BEFORE INSERT OR UPDATE ON market.user_reviews
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        title, body, reviewer_handle, firmware_used
    );

-- ---------------------------------------------------------------------------
-- PRICING HISTORY — price over time, new vs used, by source
-- ---------------------------------------------------------------------------
CREATE TABLE market.pricing_history (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_model_id      UUID NOT NULL REFERENCES hardware.miner_models(id),
    -- Price data
    price_usd           NUMERIC(12,2) NOT NULL,
    currency            CHAR(3) NOT NULL DEFAULT 'USD',
    -- Condition
    condition           public.part_condition NOT NULL DEFAULT 'new_oem',
    -- Context
    price_date          DATE NOT NULL,
    price_timestamp     TIMESTAMPTZ,        -- When exactly this price was captured
    -- Where was this price?
    market_type         TEXT NOT NULL,      -- 'manufacturer', 'secondary', 'auction', 'spot'
    vendor_name         TEXT,
    vendor_url          TEXT,
    listing_url         TEXT,
    -- Sale context
    quantity_available  INTEGER,
    is_bulk_price       BOOLEAN NOT NULL DEFAULT FALSE,
    bulk_quantity       INTEGER,
    includes_psu        BOOLEAN NOT NULL DEFAULT TRUE,
    includes_warranty   BOOLEAN NOT NULL DEFAULT FALSE,
    warranty_months     INTEGER,
    -- Derived
    price_per_th        NUMERIC(10,4),      -- Calculated: price_usd / model's TH/s
    -- Location / shipping
    ships_from_country  CHAR(2),
    -- Bitcoin price at time (for BTC-denominated analysis)
    btc_price_at_time   NUMERIC(12,2),
    price_in_btc        NUMERIC(18,8),
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE market.pricing_history IS
'Full pricing history for all miner models. price_per_th is critical for ROI analysis.
Tracks new, used, bulk, and auction prices. Includes BTC-denominated price for
historical purchasing power analysis. Enables: "What did S19j Pro cost in Q3 2022?"';

CREATE INDEX idx_pricing_model ON market.pricing_history(miner_model_id);
CREATE INDEX idx_pricing_date ON market.pricing_history(price_date DESC);
CREATE INDEX idx_pricing_model_date ON market.pricing_history(miner_model_id, price_date DESC);
CREATE INDEX idx_pricing_condition ON market.pricing_history(miner_model_id, condition);
CREATE INDEX idx_pricing_per_th ON market.pricing_history(price_per_th);

CREATE TRIGGER trg_pricing_updated_at
    BEFORE UPDATE ON market.pricing_history
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- MANUFACTURER REPUTATION — scored reputation data by dimension
-- ---------------------------------------------------------------------------
CREATE TABLE market.manufacturer_reputation (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    manufacturer_id         UUID NOT NULL REFERENCES hardware.manufacturers(id),
    -- Score dimensions (0.0–10.0)
    score_dimension         TEXT NOT NULL,
    -- 'build_quality', 'support_quality', 'spec_accuracy', 'delivery_reliability',
    --  'warranty_honor', 'firmware_quality', 'documentation_quality', 'overall'
    score_value             NUMERIC(4,2) NOT NULL CHECK (score_value BETWEEN 0 AND 10),
    score_basis             INTEGER,        -- How many data points (reviews/incidents)
    -- Time context
    score_period_start      DATE,
    score_period_end        DATE,
    -- Source
    source_platform         TEXT,           -- Where this rep data came from
    primary_source_id       UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence              public.confidence_level NOT NULL DEFAULT 'low',
    notes                   TEXT,
    metadata                JSONB NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE market.manufacturer_reputation IS
'Multi-dimensional reputation scores per manufacturer per time period.
Aggregated from reviews, forum sentiment, and support incident outcomes.
These feed back to hardware.manufacturers.overall_reputation_score etc. via rollup.';

CREATE INDEX idx_mfr_rep_manufacturer ON market.manufacturer_reputation(manufacturer_id);
CREATE INDEX idx_mfr_rep_dimension ON market.manufacturer_reputation(score_dimension);
CREATE INDEX idx_mfr_rep_period ON market.manufacturer_reputation(score_period_end DESC);

CREATE TRIGGER trg_mfr_rep_updated_at
    BEFORE UPDATE ON market.manufacturer_reputation
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- FORUM POSTS — tagged discussions from Reddit, Telegram, Discord, etc.
-- ---------------------------------------------------------------------------
CREATE TABLE market.forum_posts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Content
    title               TEXT,
    body                TEXT NOT NULL,
    url                 TEXT,
    -- Source
    platform            TEXT NOT NULL,      -- 'reddit', 'telegram', 'discord', 'braiins_forum', etc.
    platform_post_id    TEXT,               -- Original ID on the platform
    subreddit_channel   TEXT,               -- r/BitcoinMining, #antminer-support, etc.
    author_handle       TEXT,
    post_date           TIMESTAMPTZ,
    -- Tags (which models, failure types, firmware, etc.)
    tagged_model_ids    UUID[] NOT NULL DEFAULT '{}',
    tagged_failure_patterns TEXT[] NOT NULL DEFAULT '{}',   -- pattern_codes
    tagged_firmware     TEXT[] NOT NULL DEFAULT '{}',
    topic_tags          TEXT[] NOT NULL DEFAULT '{}',       -- Free-form tags
    -- Sentiment
    sentiment           public.sentiment,
    -- Community signals
    upvotes             INTEGER,
    downvotes           INTEGER,
    comment_count       INTEGER,
    -- Knowledge extraction
    key_insights        JSONB NOT NULL DEFAULT '[]',
    -- [{"insight": "...", "category": "failure_mode", "confidence": "medium"}]
    contains_repair_data BOOLEAN NOT NULL DEFAULT FALSE,
    contains_spec_data  BOOLEAN NOT NULL DEFAULT FALSE,
    has_been_processed  BOOLEAN NOT NULL DEFAULT FALSE,     -- Has an LLM/human extracted insights?
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'low',
    search_vector       TSVECTOR,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE market.forum_posts IS
'Forum, Reddit, Discord, and Telegram posts relevant to mining hardware intelligence.
tagged_model_ids and tagged_failure_patterns are arrays for multi-model/multi-topic posts.
key_insights JSONB captures extracted actionable intelligence.
has_been_processed=FALSE means this post is in the queue for insight extraction.';

CREATE INDEX idx_forum_platform ON market.forum_posts(platform);
CREATE INDEX idx_forum_date ON market.forum_posts(post_date DESC);
CREATE INDEX idx_forum_models ON market.forum_posts USING GIN(tagged_model_ids);
CREATE INDEX idx_forum_tags ON market.forum_posts USING GIN(topic_tags);
CREATE INDEX idx_forum_patterns ON market.forum_posts USING GIN(tagged_failure_patterns);
CREATE INDEX idx_forum_unprocessed ON market.forum_posts(has_been_processed)
    WHERE has_been_processed = FALSE;
CREATE INDEX idx_forum_repair ON market.forum_posts(contains_repair_data)
    WHERE contains_repair_data = TRUE;
CREATE INDEX idx_forum_insights ON market.forum_posts USING GIN(key_insights);
CREATE INDEX idx_forum_search ON market.forum_posts USING GIN(search_vector);

CREATE TRIGGER trg_forum_updated_at
    BEFORE UPDATE ON market.forum_posts
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_forum_search_vector
    BEFORE INSERT OR UPDATE ON market.forum_posts
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        title, body, platform, author_handle
    );

-- ---------------------------------------------------------------------------
-- TEARDOWN REPORTS — detailed hardware teardown analysis
-- ---------------------------------------------------------------------------
CREATE TABLE market.teardown_reports (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_model_id      UUID NOT NULL REFERENCES hardware.miner_models(id),
    -- Report details
    title               TEXT NOT NULL,
    author_name         TEXT,
    author_id           UUID REFERENCES knowledge.contributors(id),
    teardown_date       DATE,
    publish_url         TEXT,
    -- Content
    summary             TEXT,
    findings            TEXT,
    -- Structured findings
    component_inventory JSONB NOT NULL DEFAULT '[]',
    -- [{"component": "PSU caps", "brand": "TEAPO", "grade": "commercial", "concern": "high_temp"}]
    build_quality_notes TEXT,
    design_observations TEXT,
    failure_risk_notes  TEXT,
    -- Ratings from teardown
    build_quality_score NUMERIC(4,2),       -- 0–10
    repairability_score NUMERIC(4,2),       -- 0–10
    component_quality_score NUMERIC(4,2),
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    search_vector       TSVECTOR,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE market.teardown_reports IS
'Hardware teardown and analysis reports. Captures component inventories (PSU cap brands,
thermal paste quality, PCB trace widths, etc.) which often predict long-term failure modes.
Teardown-identified cheap capacitors → failure pattern → alert rule.';

CREATE INDEX idx_teardown_model ON market.teardown_reports(miner_model_id);
CREATE INDEX idx_teardown_date ON market.teardown_reports(teardown_date DESC);
CREATE INDEX idx_teardown_inventory ON market.teardown_reports USING GIN(component_inventory);
CREATE INDEX idx_teardown_search ON market.teardown_reports USING GIN(search_vector);

CREATE TRIGGER trg_teardown_updated_at
    BEFORE UPDATE ON market.teardown_reports
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_teardown_search_vector
    BEFORE INSERT OR UPDATE ON market.teardown_reports
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        title, summary, findings, build_quality_notes, design_observations, failure_risk_notes
    );

-- ---------------------------------------------------------------------------
-- WAR STORIES — operational lessons learned (narrative knowledge)
-- ---------------------------------------------------------------------------
CREATE TABLE market.war_stories (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title               TEXT NOT NULL,
    narrative           TEXT NOT NULL,      -- Full story in plain text
    -- Context
    author_id           UUID REFERENCES knowledge.contributors(id),
    author_handle       TEXT,
    event_date          DATE,
    facility_type       TEXT,               -- 'home', 'colocation', 'industrial', 'container'
    cooling_type        public.cooling_type,
    fleet_size          INTEGER,            -- Approximate fleet size at time of event
    -- What was involved
    tagged_model_ids    UUID[] NOT NULL DEFAULT '{}',
    tagged_failure_patterns TEXT[] NOT NULL DEFAULT '{}',
    topic_tags          TEXT[] NOT NULL DEFAULT '{}',
    -- Outcome
    outcome_summary     TEXT,
    financial_impact_usd NUMERIC(12,2),     -- Estimated cost/loss
    downtime_hours       NUMERIC(8,2),
    lesson_learned      TEXT NOT NULL,      -- The key takeaway (required)
    preventable         BOOLEAN,            -- Could this have been prevented?
    prevention_method   TEXT,
    -- Is this Bobby's story?
    is_bobby_story      BOOLEAN NOT NULL DEFAULT FALSE,
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'low',
    search_vector       TSVECTOR,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE market.war_stories IS
'Operational war stories — narrative accounts of incidents, failures, and lessons learned.
The lesson_learned field is required: every story must have a takeaway.
is_bobby_story=TRUE entries are tier2 confidence. These inform failure pattern creation.
Mining Guardian can surface relevant war stories when a miner shows suspicious symptoms.';

CREATE INDEX idx_wstories_models ON market.war_stories USING GIN(tagged_model_ids);
CREATE INDEX idx_wstories_tags ON market.war_stories USING GIN(topic_tags);
CREATE INDEX idx_wstories_patterns ON market.war_stories USING GIN(tagged_failure_patterns);
CREATE INDEX idx_wstories_bobby ON market.war_stories(is_bobby_story)
    WHERE is_bobby_story = TRUE;
CREATE INDEX idx_wstories_date ON market.war_stories(event_date DESC NULLS LAST);
CREATE INDEX idx_wstories_search ON market.war_stories USING GIN(search_vector);

CREATE TRIGGER trg_wstories_updated_at
    BEFORE UPDATE ON market.war_stories
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_wstories_search_vector
    BEFORE INSERT OR UPDATE ON market.war_stories
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        title, narrative, outcome_summary, lesson_learned, prevention_method
    );

-- ---------------------------------------------------------------------------
-- AVAILABILITY TRACKING — current-market availability per model
-- ---------------------------------------------------------------------------
CREATE TABLE market.market_availability (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_model_id      UUID NOT NULL REFERENCES hardware.miner_models(id),
    check_date          DATE NOT NULL,
    -- Supply signals
    new_units_available BOOLEAN,
    used_units_available BOOLEAN,
    -- Lead times
    new_lead_time_weeks INTEGER,
    used_lead_time_days INTEGER,
    -- Spot market
    spot_price_usd_low  NUMERIC(12,2),
    spot_price_usd_high NUMERIC(12,2),
    spot_price_usd_avg  NUMERIC(12,2),
    sample_listings     INTEGER,            -- How many listings sampled
    -- Overall market sentiment for this model
    supply_sentiment    TEXT,               -- 'scarce', 'normal', 'oversupply', 'unknown'
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'low',
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_avail_model ON market.market_availability(miner_model_id);
CREATE INDEX idx_avail_date ON market.market_availability(check_date DESC);
CREATE INDEX idx_avail_model_date ON market.market_availability(miner_model_id, check_date DESC);

CREATE TRIGGER trg_avail_updated_at
    BEFORE UPDATE ON market.market_availability
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
-- =============================================================================
-- MINING INTELLIGENCE CATALOG — Part 6: Category 5 — Repair/Service
-- Tables: repair_procedures, repair_steps, parts, part_suppliers,
--         repair_shops, repair_records (flexible JSONB ingestion),
--         repair_statistics
-- =============================================================================

-- ---------------------------------------------------------------------------
-- PARTS DATABASE
-- ---------------------------------------------------------------------------
CREATE TABLE repair.parts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    part_number         TEXT,               -- Manufacturer part number
    part_number_alt     TEXT[] NOT NULL DEFAULT '{}',  -- Alternative/cross-reference PNs
    name                TEXT NOT NULL,
    description         TEXT,
    -- Classification
    part_category       TEXT NOT NULL,
    -- 'chip_asic', 'capacitor', 'inductor', 'mosfet', 'resistor', 'connector',
    --  'thermal_pad', 'thermal_paste', 'fan', 'pcb_blank', 'cable', 'psu_component',
    --  'control_board_component', 'complete_hashboard', 'complete_psu', 'complete_control_board',
    --  'enclosure', 'mounting_hardware', 'fuse', 'diode', 'transformer', 'other'
    -- Physical / Electrical specs
    specs               JSONB NOT NULL DEFAULT '{}',
    -- For capacitor: {"capacitance_uf": 470, "voltage_v": 16, "esr_ohm": 0.05, "package": "SMD_1210"}
    -- For chip: {"chip_model": "BM1362", "hash_rate": "5.8GH"}
    package_type        TEXT,               -- 'SMD_0402', 'SMD_1210', 'THT', 'BGA', 'QFN', etc.
    -- Manufacturer
    manufacturer_name   TEXT,
    datasheet_url       TEXT,
    -- Compatibility
    compatible_model_ids UUID[] NOT NULL DEFAULT '{}',
    compatible_board_ids UUID[] NOT NULL DEFAULT '{}',
    -- Replacement chain
    replaces_part_id    UUID REFERENCES repair.parts(id),  -- Drop-in replacement for
    replaced_by_part_id UUID REFERENCES repair.parts(id),  -- Better part available
    is_obsolete         BOOLEAN NOT NULL DEFAULT FALSE,
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    search_vector       TSVECTOR,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE repair.parts IS
'Component-level parts database. Stores everything from individual SMD capacitors
to complete replacement hashboards. specs JSONB captures component-specific data.
compatible_model_ids and compatible_board_ids are arrays for multi-model parts.
replaces_part_id enables upgrade chains: "replace cap C142 with this improved cap."';

CREATE INDEX idx_parts_category ON repair.parts(part_category);
CREATE INDEX idx_parts_number ON repair.parts(part_number);
CREATE INDEX idx_parts_alt_numbers ON repair.parts USING GIN(part_number_alt);
CREATE INDEX idx_parts_models ON repair.parts USING GIN(compatible_model_ids);
CREATE INDEX idx_parts_boards ON repair.parts USING GIN(compatible_board_ids);
CREATE INDEX idx_parts_specs ON repair.parts USING GIN(specs);
CREATE INDEX idx_parts_search ON repair.parts USING GIN(search_vector);

CREATE TRIGGER trg_parts_updated_at
    BEFORE UPDATE ON repair.parts
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_parts_search_vector
    BEFORE INSERT OR UPDATE ON repair.parts
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        part_number, name, description, part_category, package_type, manufacturer_name
    );

-- ---------------------------------------------------------------------------
-- PART SUPPLIERS — where to source parts
-- ---------------------------------------------------------------------------
CREATE TABLE repair.part_suppliers (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    supplier_name       TEXT NOT NULL,
    supplier_type       TEXT NOT NULL DEFAULT 'online',
    -- 'online', 'local_electronics', 'manufacturer_direct', 'distributor', 'repair_shop', 'ebay'
    website_url         TEXT,
    -- Geographic
    country             CHAR(2),
    ships_to_countries  CHAR(2)[] NOT NULL DEFAULT '{}',
    -- Contact
    email               TEXT,
    phone               TEXT,
    -- Reputation
    reputation_score    NUMERIC(4,2),       -- 0–10
    review_count        INTEGER,
    ships_fast          BOOLEAN,
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_suppliers_type ON repair.part_suppliers(supplier_type);
CREATE INDEX idx_suppliers_country ON repair.part_suppliers(country);

CREATE TRIGGER trg_suppliers_updated_at
    BEFORE UPDATE ON repair.part_suppliers
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- PART AVAILABILITY — current stock and pricing per supplier
-- ---------------------------------------------------------------------------
CREATE TABLE repair.part_availability (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    part_id         UUID NOT NULL REFERENCES repair.parts(id) ON DELETE CASCADE,
    supplier_id     UUID NOT NULL REFERENCES repair.part_suppliers(id) ON DELETE CASCADE,
    condition       public.part_condition NOT NULL DEFAULT 'new_oem',
    check_date      DATE NOT NULL,
    in_stock        BOOLEAN NOT NULL DEFAULT FALSE,
    qty_available   INTEGER,
    price_usd       NUMERIC(10,4),
    moq             INTEGER NOT NULL DEFAULT 1,  -- Minimum order quantity
    lead_time_days  INTEGER,
    listing_url     TEXT,
    -- Source
    primary_source_id UUID REFERENCES knowledge.sources(id),
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_part_avail_part ON repair.part_availability(part_id);
CREATE INDEX idx_part_avail_supplier ON repair.part_availability(supplier_id);
CREATE INDEX idx_part_avail_instock ON repair.part_availability(part_id)
    WHERE in_stock = TRUE;
CREATE INDEX idx_part_avail_date ON repair.part_availability(check_date DESC);

CREATE TRIGGER trg_part_avail_updated_at
    BEFORE UPDATE ON repair.part_availability
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- REPAIR PROCEDURES — documented step-by-step repair guides
-- ---------------------------------------------------------------------------
CREATE TABLE repair.repair_procedures (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    procedure_name      TEXT NOT NULL,
    procedure_code      TEXT UNIQUE,        -- "PROC-S19JP-HASHBOARD-DEADCHIP-001"
    -- Applicability
    miner_model_id      UUID REFERENCES hardware.miner_models(id),  -- NULL = universal
    hashboard_id        UUID REFERENCES hardware.hashboards(id),
    failure_pattern_id  UUID REFERENCES ops.failure_patterns(id),
    -- Difficulty
    skill_level         TEXT NOT NULL DEFAULT 'intermediate',
    -- 'beginner', 'intermediate', 'advanced', 'expert', 'professional_only'
    estimated_time_minutes INTEGER,
    requires_rework_station BOOLEAN NOT NULL DEFAULT FALSE,
    requires_multimeter  BOOLEAN NOT NULL DEFAULT FALSE,
    requires_oscilloscope BOOLEAN NOT NULL DEFAULT FALSE,
    requires_hot_air     BOOLEAN NOT NULL DEFAULT FALSE,
    requires_bga_machine BOOLEAN NOT NULL DEFAULT FALSE,
    -- Tools list
    required_tools      JSONB NOT NULL DEFAULT '[]',
    -- [{"tool": "soldering iron", "spec": "65W, adjustable temp"}, ...]
    -- Parts required
    required_parts      JSONB NOT NULL DEFAULT '[]',
    -- [{"part_id": "...", "quantity": 2, "notes": "C142 replacement cap"}, ...]
    -- Safety
    safety_warnings     JSONB NOT NULL DEFAULT '[]',
    ppe_required        JSONB NOT NULL DEFAULT '[]',
    -- Success metrics
    expected_success_rate NUMERIC(5,4),     -- Historical success rate
    success_criteria    TEXT,               -- How to know repair succeeded
    -- Content
    overview            TEXT,
    prerequisites       TEXT,
    notes               TEXT,
    video_url           TEXT,               -- YouTube or similar tutorial
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    verified_by_bobby   BOOLEAN NOT NULL DEFAULT FALSE,
    search_vector       TSVECTOR,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE repair.repair_procedures IS
'Step-by-step repair procedure catalog. Each procedure links to a failure pattern.
required_tools and required_parts are JSONB arrays to support arbitrary tools.
expected_success_rate is updated from actual repair_records outcomes.
video_url enables Mining Guardian to surface tutorial videos during repair workflow.';

CREATE INDEX idx_proc_model ON repair.repair_procedures(miner_model_id)
    WHERE miner_model_id IS NOT NULL;
CREATE INDEX idx_proc_failure ON repair.repair_procedures(failure_pattern_id);
CREATE INDEX idx_proc_skill ON repair.repair_procedures(skill_level);
CREATE INDEX idx_proc_parts ON repair.repair_procedures USING GIN(required_parts);
CREATE INDEX idx_proc_search ON repair.repair_procedures USING GIN(search_vector);

CREATE TRIGGER trg_proc_updated_at
    BEFORE UPDATE ON repair.repair_procedures
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_proc_search_vector
    BEFORE INSERT OR UPDATE ON repair.repair_procedures
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        procedure_name, overview, prerequisites, notes, success_criteria
    );

-- ---------------------------------------------------------------------------
-- REPAIR STEPS — ordered steps within a procedure
-- ---------------------------------------------------------------------------
CREATE TABLE repair.repair_steps (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    procedure_id        UUID NOT NULL REFERENCES repair.repair_procedures(id) ON DELETE CASCADE,
    step_number         INTEGER NOT NULL,
    step_title          TEXT NOT NULL,
    instructions        TEXT NOT NULL,      -- Full human-readable instructions
    -- Conditional execution
    is_conditional      BOOLEAN NOT NULL DEFAULT FALSE,
    condition_description TEXT,             -- "Only if chip reads 0 ohms at test point TP3"
    -- Visual aids
    image_urls          JSONB NOT NULL DEFAULT '[]',    -- Images for this step
    video_timestamp_s   INTEGER,            -- Timestamp in procedure video
    -- Measurement checkpoints
    checkpoint_type     TEXT,
    -- 'voltage_measurement', 'resistance_measurement', 'visual_inspection',
    --  'functional_test', 'thermal_test', 'none'
    checkpoint_spec     TEXT,               -- "Should read 0.4V ± 0.05V at TP3"
    -- Parts used in this step
    step_parts          JSONB NOT NULL DEFAULT '[]',
    -- Warnings
    warnings            JSONB NOT NULL DEFAULT '[]',
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (procedure_id, step_number)
);

CREATE INDEX idx_steps_procedure ON repair.repair_steps(procedure_id, step_number);

CREATE TRIGGER trg_steps_updated_at
    BEFORE UPDATE ON repair.repair_steps
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- REPAIR SHOPS DIRECTORY
-- ---------------------------------------------------------------------------
CREATE TABLE repair.repair_shops (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shop_name           TEXT NOT NULL,
    -- Location
    address_line1       TEXT,
    address_line2       TEXT,
    city                TEXT,
    state_province      TEXT,
    postal_code         TEXT,
    country             CHAR(2),
    -- Contact
    website_url         TEXT,
    email               TEXT,
    phone               TEXT,
    -- Geographic coordinates for proximity search
    location            POINT,             -- (longitude, latitude) — use with PostGIS or manual distance
    -- Capabilities
    specializes_in      UUID[] NOT NULL DEFAULT '{}',  -- miner_model_ids they specialize in
    capabilities        JSONB NOT NULL DEFAULT '[]',
    -- ["hashboard_repair", "chip_reballing", "bga_rework", "psu_repair", "control_board_repair"]
    has_rework_station  BOOLEAN NOT NULL DEFAULT FALSE,
    has_bga_machine     BOOLEAN NOT NULL DEFAULT FALSE,
    has_xray            BOOLEAN NOT NULL DEFAULT FALSE,    -- X-ray for BGA inspection
    -- Service terms
    accepts_mail_in     BOOLEAN NOT NULL DEFAULT TRUE,
    turnaround_days_min INTEGER,
    turnaround_days_max INTEGER,
    warranty_days       INTEGER,            -- Repair warranty
    -- Pricing
    diagnostic_fee_usd  NUMERIC(8,2),
    typical_hourly_rate_usd NUMERIC(8,2),
    no_fix_no_fee       BOOLEAN NOT NULL DEFAULT FALSE,
    -- Reputation
    reputation_score    NUMERIC(4,2),       -- 0–10, aggregated
    total_reviews        INTEGER NOT NULL DEFAULT 0,
    -- Business
    years_in_business   INTEGER,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'low',
    notes               TEXT,
    search_vector       TSVECTOR,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE repair.repair_shops IS
'Directory of Bitcoin miner repair shops. Mining Guardian uses this to recommend
shops when a repair is beyond on-site capability. specializes_in stores miner_model_ids
for fast filtering: "Who can repair my AH3880?" 
The 1M+ repair record ingestion pipeline generates records in repair.repair_records,
and shops are the submitters (linked via contributor_id).';

CREATE INDEX idx_shops_active ON repair.repair_shops(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_shops_country ON repair.repair_shops(country);
CREATE INDEX idx_shops_specializes ON repair.repair_shops USING GIN(specializes_in);
CREATE INDEX idx_shops_caps ON repair.repair_shops USING GIN(capabilities);
CREATE INDEX idx_shops_search ON repair.repair_shops USING GIN(search_vector);

CREATE TRIGGER trg_shops_updated_at
    BEFORE UPDATE ON repair.repair_shops
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_shops_search_vector
    BEFORE INSERT OR UPDATE ON repair.repair_shops
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        shop_name, city, state_province, country, notes
    );

-- ---------------------------------------------------------------------------
-- REPAIR RECORDS — 1M+ record-capable flexible ingestion table
-- This is the highest-volume table. JSONB for any shop-specific data format.
-- ---------------------------------------------------------------------------
CREATE TABLE repair.repair_records (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Submitter/shop
    shop_id             UUID REFERENCES repair.repair_shops(id),
    submitter_id        UUID REFERENCES knowledge.contributors(id),
    -- Hardware
    miner_model_id      UUID REFERENCES hardware.miner_models(id),
    model_name_raw      TEXT,               -- Raw model name from shop (before normalization)
    serial_number       TEXT,               -- May be NULL for anonymized records
    manufacture_date    DATE,
    -- Failure
    failure_pattern_id  UUID REFERENCES ops.failure_patterns(id),
    failure_category    TEXT,
    symptom_description TEXT,               -- Free-text symptom from technician
    symptom_codes       TEXT[] NOT NULL DEFAULT '{}',  -- Structured symptom codes
    -- Diagnosis
    diagnosed_root_cause TEXT,
    diagnosis_method    TEXT,
    -- Repair
    procedure_id        UUID REFERENCES repair.repair_procedures(id),
    repair_description  TEXT,               -- Free-text repair notes
    -- Parts used
    parts_replaced      JSONB NOT NULL DEFAULT '[]',
    -- [{"part_id": "...", "part_number_raw": "...", "qty": 2, "unit_cost_usd": 0.50}]
    -- Outcome
    outcome             public.repair_outcome NOT NULL DEFAULT 'in_progress',
    outcome_notes       TEXT,
    -- Timing
    received_date       DATE,
    diagnosed_date      DATE,
    repaired_date       DATE,
    returned_date       DATE,
    total_labor_minutes INTEGER,
    -- Costs
    parts_cost_usd      NUMERIC(10,2),
    labor_cost_usd      NUMERIC(10,2),
    total_cost_usd      NUMERIC(10,2),
    -- Context
    cooling_type        public.cooling_type,
    firmware_at_failure TEXT,
    ambient_temp_c      NUMERIC(5,1),
    unit_age_days       INTEGER,            -- Estimated age at failure
    hours_since_last_restart INTEGER,
    -- Performance at time of failure (from API data if available)
    hashrate_at_failure_th NUMERIC(10,3),
    temp_at_failure_c   INTEGER,
    -- Raw shop data (CRITICAL: flexible ingestion for diverse shop formats)
    raw_shop_data       JSONB NOT NULL DEFAULT '{}',
    -- This field absorbs ANY shop-specific fields not mapped above.
    -- Shop CSV imports dump unmapped columns here. Nothing is discarded.
    -- Import metadata
    import_batch_id     TEXT,               -- Which import run created this
    import_source_file  TEXT,               -- Original filename
    is_normalized       BOOLEAN NOT NULL DEFAULT FALSE,  -- Has been mapped to canonical fields
    normalization_notes TEXT,
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE repair.repair_records IS
'The 1M+ record flexible repair ingestion table.
DESIGN PRINCIPLE: raw_shop_data JSONB is a catch-all. Every field from a shop CSV
that cannot be mapped to a column goes here. NOTHING is discarded.
import_batch_id enables rolling back a bad import. is_normalized=FALSE = in normalization queue.
model_name_raw + the alias system normalizes miner_model_id after import.
Partitioning by created_at (RANGE) is recommended once records exceed 500K.
PARTITION BY RANGE (created_at) can be added on migration.';

CREATE INDEX idx_rr_shop ON repair.repair_records(shop_id);
CREATE INDEX idx_rr_model ON repair.repair_records(miner_model_id);
CREATE INDEX idx_rr_pattern ON repair.repair_records(failure_pattern_id);
CREATE INDEX idx_rr_outcome ON repair.repair_records(outcome);
CREATE INDEX idx_rr_received ON repair.repair_records(received_date DESC);
CREATE INDEX idx_rr_batch ON repair.repair_records(import_batch_id)
    WHERE import_batch_id IS NOT NULL;
CREATE INDEX idx_rr_unnormalized ON repair.repair_records(is_normalized)
    WHERE is_normalized = FALSE;
CREATE INDEX idx_rr_raw_data ON repair.repair_records USING GIN(raw_shop_data);
CREATE INDEX idx_rr_parts ON repair.repair_records USING GIN(parts_replaced);
CREATE INDEX idx_rr_symptoms ON repair.repair_records USING GIN(symptom_codes);
CREATE INDEX idx_rr_model_raw ON repair.repair_records USING GIN(model_name_raw gin_trgm_ops);

CREATE TRIGGER trg_rr_updated_at
    BEFORE UPDATE ON repair.repair_records
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- REPAIR STATISTICS — rolled-up failure/repair statistics per model
-- Pre-computed for fast queries. Refreshed periodically.
-- ---------------------------------------------------------------------------
CREATE TABLE repair.repair_statistics (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Scope
    miner_model_id      UUID REFERENCES hardware.miner_models(id),   -- NULL = all models
    failure_pattern_id  UUID REFERENCES ops.failure_patterns(id),    -- NULL = all failures
    shop_id             UUID REFERENCES repair.repair_shops(id),     -- NULL = all shops
    cooling_type        public.cooling_type,    -- NULL = all cooling types
    stat_period_start   DATE NOT NULL,
    stat_period_end     DATE NOT NULL,
    -- Volume
    total_records       INTEGER NOT NULL DEFAULT 0,
    -- Failure rates
    failure_rate_pct    NUMERIC(8,4),           -- Failures per unit-month (or similar)
    failure_rate_basis  TEXT,                   -- Explanation of rate calculation
    -- Outcomes
    success_rate_full   NUMERIC(5,4),           -- Fraction with outcome=success_full
    success_rate_any    NUMERIC(5,4),           -- Any positive outcome
    scrapped_rate       NUMERIC(5,4),
    -- Timing (MTTR — mean time to repair)
    avg_repair_days     NUMERIC(7,2),
    median_repair_days  NUMERIC(7,2),
    p90_repair_days     NUMERIC(7,2),
    -- Costs
    avg_parts_cost_usd  NUMERIC(10,2),
    avg_labor_cost_usd  NUMERIC(10,2),
    avg_total_cost_usd  NUMERIC(10,2),
    median_total_cost_usd NUMERIC(10,2),
    -- Age at failure
    avg_age_at_failure_days INTEGER,
    median_age_at_failure_days INTEGER,
    -- Most common root causes
    top_failure_patterns JSONB NOT NULL DEFAULT '[]',
    -- [{"pattern_id": "...", "pattern_name": "...", "count": 142, "pct": 0.31}]
    -- Compute metadata
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_record_count INTEGER NOT NULL DEFAULT 0,
    is_current          BOOLEAN NOT NULL DEFAULT TRUE,
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE repair.repair_statistics IS
'Pre-computed repair statistics for fast Fleet Intelligence queries.
Refreshed by a periodic job that aggregates from repair_records.
Scoped by model, failure pattern, shop, cooling type, and time period.
top_failure_patterns JSONB gives quick access to the most common root causes.';

CREATE INDEX idx_rstat_model ON repair.repair_statistics(miner_model_id)
    WHERE miner_model_id IS NOT NULL;
CREATE INDEX idx_rstat_pattern ON repair.repair_statistics(failure_pattern_id)
    WHERE failure_pattern_id IS NOT NULL;
CREATE INDEX idx_rstat_current ON repair.repair_statistics(is_current)
    WHERE is_current = TRUE;
CREATE INDEX idx_rstat_period ON repair.repair_statistics(stat_period_end DESC);
CREATE INDEX idx_rstat_top_patterns ON repair.repair_statistics USING GIN(top_failure_patterns);

CREATE TRIGGER trg_rstat_updated_at
    BEFORE UPDATE ON repair.repair_statistics
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- REPAIR RECORD REVIEWS — quality/reputation of repair shops from repair outcomes
-- ---------------------------------------------------------------------------
CREATE TABLE repair.shop_reviews (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shop_id             UUID NOT NULL REFERENCES repair.repair_shops(id) ON DELETE CASCADE,
    repair_record_id    UUID REFERENCES repair.repair_records(id),
    reviewer_id         UUID REFERENCES knowledge.contributors(id),
    reviewer_handle     TEXT,
    review_date         DATE,
    -- Ratings
    overall_rating      NUMERIC(3,1) CHECK (overall_rating BETWEEN 1 AND 10),
    quality_rating      NUMERIC(3,1) CHECK (quality_rating BETWEEN 1 AND 10),
    speed_rating        NUMERIC(3,1) CHECK (speed_rating BETWEEN 1 AND 10),
    price_rating        NUMERIC(3,1) CHECK (price_rating BETWEEN 1 AND 10),
    communication_rating NUMERIC(3,1) CHECK (communication_rating BETWEEN 1 AND 10),
    -- Content
    review_text         TEXT,
    source_platform     TEXT,
    source_url          TEXT,
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'low',
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_shop_reviews_shop ON repair.shop_reviews(shop_id);
CREATE INDEX idx_shop_reviews_rating ON repair.shop_reviews(shop_id, overall_rating DESC);

CREATE TRIGGER trg_shop_reviews_updated_at
    BEFORE UPDATE ON repair.shop_reviews
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
-- =============================================================================
-- MINING INTELLIGENCE CATALOG — Part 7: Category 6 — Pool/Network
-- Tables: mining_pools, pool_endpoints, stratum_configurations,
--         pool_reliability_history, bitcoin_network_snapshots
-- =============================================================================

-- ---------------------------------------------------------------------------
-- MINING POOLS DIRECTORY
-- ---------------------------------------------------------------------------
CREATE TABLE pool.mining_pools (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pool_name           TEXT NOT NULL,
    operator_name       TEXT,
    -- URLs
    website_url         TEXT,
    status_page_url     TEXT,
    api_url             TEXT,
    documentation_url   TEXT,
    -- Fee structure
    fee_model           TEXT NOT NULL DEFAULT 'pplns',
    -- 'pplns', 'pps', 'pps_plus', 'fpps', 'prop', 'solo', 'p2pool', 'ocean'
    fee_pct             NUMERIC(6,4),       -- Standard fee %
    fee_structure_detail TEXT,              -- "FPPS: 2% on block reward + transaction fees"
    minimum_payout_btc  NUMERIC(18,8),
    payout_frequency    TEXT,               -- 'daily', 'per_block', 'threshold', 'manual'
    -- Features
    supports_stratum_v1 BOOLEAN NOT NULL DEFAULT TRUE,
    supports_stratum_v2 BOOLEAN NOT NULL DEFAULT FALSE,
    supports_ssl        BOOLEAN NOT NULL DEFAULT FALSE,
    has_solo_mode       BOOLEAN NOT NULL DEFAULT FALSE,
    has_merged_mining   BOOLEAN NOT NULL DEFAULT FALSE,
    requires_account    BOOLEAN NOT NULL DEFAULT TRUE,
    anonymous_mining    BOOLEAN NOT NULL DEFAULT FALSE,
    -- Geographic distribution
    server_locations    JSONB NOT NULL DEFAULT '[]',
    -- [{"region": "North America", "city": "Dallas", "url": "us-east.pool.com:3333"}]
    -- Performance (aggregated from pool_reliability_history)
    avg_luck_90d        NUMERIC(6,4),       -- Lucky or unlucky pool? >1.0 = lucky
    avg_uptime_pct_90d  NUMERIC(6,4),
    avg_latency_ms      NUMERIC(8,2),
    reject_rate_pct_avg NUMERIC(6,4),
    -- Estimated hashrate share
    estimated_hashrate_eh NUMERIC(12,4),    -- EH/s estimated
    estimated_pool_share_pct NUMERIC(6,4),  -- % of Bitcoin network hashrate
    -- Status
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    is_bobby_using      BOOLEAN NOT NULL DEFAULT FALSE,
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    search_vector       TSVECTOR,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE pool.mining_pools IS
'Bitcoin mining pool directory. is_bobby_using=TRUE pools get higher freshness requirements.
avg_luck_90d is a rolling window metric: >1.0 means pool found more blocks than expected.
fee_model and fee_pct enable ROI calculations per pool.';

CREATE INDEX idx_pools_active ON pool.mining_pools(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_pools_fee ON pool.mining_pools(fee_pct);
CREATE INDEX idx_pools_bobby ON pool.mining_pools(is_bobby_using) WHERE is_bobby_using = TRUE;
CREATE INDEX idx_pools_search ON pool.mining_pools USING GIN(search_vector);
CREATE INDEX idx_pools_servers ON pool.mining_pools USING GIN(server_locations);

CREATE TRIGGER trg_pools_updated_at
    BEFORE UPDATE ON pool.mining_pools
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_pools_search_vector
    BEFORE INSERT OR UPDATE ON pool.mining_pools
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        pool_name, operator_name, fee_model, notes
    );

-- ---------------------------------------------------------------------------
-- POOL ENDPOINTS — specific stratum/API endpoint records
-- ---------------------------------------------------------------------------
CREATE TABLE pool.pool_endpoints (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pool_id             UUID NOT NULL REFERENCES pool.mining_pools(id) ON DELETE CASCADE,
    endpoint_type       TEXT NOT NULL DEFAULT 'stratum',
    -- 'stratum', 'stratum_ssl', 'stratum_v2', 'api', 'monitoring'
    hostname            TEXT NOT NULL,
    port                INTEGER NOT NULL,
    region              TEXT,               -- 'us-east', 'eu-west', 'asia-pacific', etc.
    is_primary          BOOLEAN NOT NULL DEFAULT FALSE,
    is_ssl              BOOLEAN NOT NULL DEFAULT FALSE,
    -- Performance (rolling averages)
    avg_latency_ms      NUMERIC(8,2),
    uptime_pct_30d      NUMERIC(6,4),
    last_checked_at     TIMESTAMPTZ,
    last_check_status   TEXT,               -- 'online', 'offline', 'degraded', 'unknown'
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (pool_id, hostname, port)
);

CREATE INDEX idx_endpoints_pool ON pool.pool_endpoints(pool_id);
CREATE INDEX idx_endpoints_primary ON pool.pool_endpoints(pool_id)
    WHERE is_primary = TRUE;
CREATE INDEX idx_endpoints_online ON pool.pool_endpoints(last_check_status)
    WHERE last_check_status = 'online';

CREATE TRIGGER trg_endpoints_updated_at
    BEFORE UPDATE ON pool.pool_endpoints
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- STRATUM CONFIGURATIONS — per pool per firmware configuration recipes
-- ---------------------------------------------------------------------------
CREATE TABLE pool.stratum_configurations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pool_id             UUID NOT NULL REFERENCES pool.mining_pools(id) ON DELETE CASCADE,
    firmware_id         UUID REFERENCES firmware.firmware_releases(id),  -- NULL = all firmware
    miner_model_id      UUID REFERENCES hardware.miner_models(id),       -- NULL = all models
    config_name         TEXT NOT NULL,      -- "Foundation Pool FPPS BiXBiT Config"
    -- Connection
    primary_endpoint_id UUID REFERENCES pool.pool_endpoints(id),
    fallback_endpoint_id UUID REFERENCES pool.pool_endpoints(id),
    stratum_version     public.stratum_version NOT NULL DEFAULT 'stratum_v1',
    -- Authentication
    worker_format       TEXT,               -- "{wallet_address}.{worker_name}"
    password_required   BOOLEAN NOT NULL DEFAULT FALSE,
    password_value      TEXT DEFAULT 'x',  -- Typically 'x' or '123'
    -- Configuration parameters
    worker_difficulty   INTEGER,            -- Var-diff target (0 = pool-managed)
    max_reconnect_attempts INTEGER,
    reconnect_delay_s   INTEGER,
    -- Full config as JSONB (for firmware-specific config blocks)
    full_config_json    JSONB,             -- Complete JSON config for firmware API
    -- Quality
    verified_working    BOOLEAN NOT NULL DEFAULT FALSE,
    verified_by         UUID REFERENCES knowledge.contributors(id),
    last_verified_at    TIMESTAMPTZ,
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE pool.stratum_configurations IS
'Complete stratum configuration recipes. Mining Guardian can generate the exact
pool config block to push to a miner based on (pool, firmware, model).
full_config_json stores the ready-to-push configuration payload.';

CREATE INDEX idx_stratcfg_pool ON pool.stratum_configurations(pool_id);
CREATE INDEX idx_stratcfg_firmware ON pool.stratum_configurations(firmware_id);
CREATE INDEX idx_stratcfg_model ON pool.stratum_configurations(miner_model_id);
CREATE INDEX idx_stratcfg_verified ON pool.stratum_configurations(verified_working)
    WHERE verified_working = TRUE;
CREATE INDEX idx_stratcfg_config ON pool.stratum_configurations USING GIN(full_config_json);

CREATE TRIGGER trg_stratcfg_updated_at
    BEFORE UPDATE ON pool.stratum_configurations
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- POOL RELIABILITY HISTORY — time-series uptime, luck, reject rates
-- ---------------------------------------------------------------------------
CREATE TABLE pool.pool_reliability_history (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pool_id             UUID NOT NULL REFERENCES pool.mining_pools(id) ON DELETE CASCADE,
    endpoint_id         UUID REFERENCES pool.pool_endpoints(id),
    -- Time window
    period_start        TIMESTAMPTZ NOT NULL,
    period_end          TIMESTAMPTZ NOT NULL,
    period_type         TEXT NOT NULL DEFAULT 'hourly',  -- 'hourly', 'daily', 'weekly'
    -- Metrics
    uptime_pct          NUMERIC(6,4),
    blocks_found        INTEGER,
    expected_blocks     NUMERIC(8,4),
    luck                NUMERIC(8,4),       -- blocks_found / expected_blocks
    avg_latency_ms      NUMERIC(8,2),
    max_latency_ms      NUMERIC(8,2),
    reject_rate_pct     NUMERIC(6,4),
    stale_rate_pct      NUMERIC(6,4),
    incident_count      INTEGER NOT NULL DEFAULT 0,
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (pool_id, period_start, period_type)
);

COMMENT ON TABLE pool.pool_reliability_history IS
'Time-series reliability data for pools. Enables rolling window calculations for
avg_luck_90d and avg_uptime_pct_90d in pool.mining_pools.
luck > 1.0 = pool found more blocks than expected (lucky); < 1.0 = unlucky.';

CREATE INDEX idx_pool_rel_pool ON pool.pool_reliability_history(pool_id);
CREATE INDEX idx_pool_rel_period ON pool.pool_reliability_history(pool_id, period_start DESC);
CREATE INDEX idx_pool_rel_type ON pool.pool_reliability_history(period_type);

CREATE TRIGGER trg_pool_rel_updated_at
    BEFORE UPDATE ON pool.pool_reliability_history
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- POOL INCIDENTS — outages and degradation events
-- ---------------------------------------------------------------------------
CREATE TABLE pool.pool_incidents (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pool_id             UUID NOT NULL REFERENCES pool.mining_pools(id) ON DELETE CASCADE,
    incident_type       TEXT NOT NULL,      -- 'outage', 'degraded', 'slow_blocks', 'ddos', 'maintenance'
    severity            public.failure_severity NOT NULL DEFAULT 'medium',
    started_at          TIMESTAMPTZ NOT NULL,
    ended_at            TIMESTAMPTZ,
    duration_minutes    INTEGER,
    description         TEXT,
    impact_summary      TEXT,
    estimated_hashrate_loss_pct NUMERIC(6,4),
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    source_url          TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pool_incidents_pool ON pool.pool_incidents(pool_id);
CREATE INDEX idx_pool_incidents_start ON pool.pool_incidents(started_at DESC);
CREATE INDEX idx_pool_incidents_active ON pool.pool_incidents(pool_id)
    WHERE ended_at IS NULL;

CREATE TRIGGER trg_pool_incidents_updated_at
    BEFORE UPDATE ON pool.pool_incidents
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- BITCOIN NETWORK SNAPSHOTS — difficulty, reward, price, hashrate
-- ---------------------------------------------------------------------------
CREATE TABLE pool.bitcoin_network_snapshots (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    snapshot_at         TIMESTAMPTZ NOT NULL,
    data_type           public.network_data_type NOT NULL,
    -- Block data
    block_height        INTEGER,
    block_time_avg_s    NUMERIC(8,2),       -- Average block time in seconds
    -- Difficulty
    difficulty          NUMERIC(30,2),
    difficulty_change_pct NUMERIC(8,4),     -- % change at last adjustment
    next_adjustment_blocks INTEGER,          -- Blocks until next difficulty adjustment
    next_adjustment_est_pct NUMERIC(8,4),   -- Estimated next adjustment %
    -- Hashrate estimates
    network_hashrate_eh NUMERIC(16,4),      -- EH/s
    -- Rewards
    block_subsidy_btc   NUMERIC(18,8),
    avg_fees_per_block_btc NUMERIC(18,8),
    total_block_reward_btc NUMERIC(18,8),
    -- Price
    btc_price_usd       NUMERIC(14,2),
    btc_price_source    TEXT,               -- 'coinbase', 'bitstamp', 'kraken', etc.
    -- Mempool
    mempool_size_mb     NUMERIC(10,3),
    mempool_tx_count    INTEGER,
    -- Economics (calculated)
    revenue_per_th_day_usd NUMERIC(10,6),   -- At current diff/price: $/TH/day
    breakeven_electricity_kwh_usd NUMERIC(10,6), -- At what elec price does mining break even?
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE pool.bitcoin_network_snapshots IS
'Time-series Bitcoin network fundamentals. revenue_per_th_day_usd is the most
important field for fleet economics: multiply by fleet TH/s for gross revenue.
Sampled at various frequencies (block by block or hourly for fees/price).';

CREATE INDEX idx_btc_snaps_at ON pool.bitcoin_network_snapshots(snapshot_at DESC);
CREATE INDEX idx_btc_snaps_type ON pool.bitcoin_network_snapshots(data_type);
CREATE INDEX idx_btc_snaps_height ON pool.bitcoin_network_snapshots(block_height DESC)
    WHERE block_height IS NOT NULL;

-- Pool stratum error codes
CREATE TABLE pool.stratum_error_codes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    error_code      INTEGER,                -- Stratum v1 error codes are integers
    error_code_str  TEXT,                   -- Stratum v2 errors are strings
    error_name      TEXT NOT NULL,
    description     TEXT,
    stratum_version public.stratum_version NOT NULL DEFAULT 'stratum_v1',
    -- Is this recoverable?
    is_transient    BOOLEAN NOT NULL DEFAULT FALSE,
    suggested_action TEXT,
    -- Source
    primary_source_id UUID REFERENCES knowledge.sources(id),
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_stratum_errs_code ON pool.stratum_error_codes(error_code);
CREATE INDEX idx_stratum_errs_version ON pool.stratum_error_codes(stratum_version);

CREATE TRIGGER trg_stratum_errs_updated_at
    BEFORE UPDATE ON pool.stratum_error_codes
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
-- =============================================================================
-- MINING INTELLIGENCE CATALOG — Part 8: Categories 7 & 8
-- Facility/Infrastructure + Regulatory/Compliance
-- =============================================================================

-- ===========================================================================
-- CATEGORY 7: FACILITY/INFRASTRUCTURE
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- COOLING SOLUTIONS — immersion tanks, hydro loops, air cooling units
-- ---------------------------------------------------------------------------
CREATE TABLE facility.cooling_solutions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    solution_name       TEXT NOT NULL,
    manufacturer_name   TEXT,
    model_number        TEXT,
    cooling_type        public.cooling_type NOT NULL,
    -- Capacity
    max_miners_capacity INTEGER,            -- Max miners this solution handles
    max_power_kw        NUMERIC(10,3),      -- Max total kW heat load
    -- Fluid / medium
    fluid_type          TEXT,               -- 'mineral_oil', 'dielectric_fluid', 'propylene_glycol',
                                            --  'water', 'engineered_fluid_3m', 'air', 'refrigerant'
    fluid_brand         TEXT,               -- "BitCool BC-888", "Shell Diala S4"
    fluid_volume_liters NUMERIC(10,2),
    -- Performance
    max_coolant_inlet_temp_c  INTEGER,
    min_coolant_inlet_temp_c  INTEGER,
    target_coolant_outlet_temp_c INTEGER,
    -- Compatibility
    compatible_model_ids UUID[] NOT NULL DEFAULT '{}',
    -- Physical
    dimensions_mm       JSONB,
    weight_kg           NUMERIC(8,2),
    -- Installation
    requires_secondary_cooling BOOLEAN NOT NULL DEFAULT FALSE,
    secondary_cooling_type TEXT,
    installation_notes  TEXT,
    -- Cost
    msrp_usd            NUMERIC(12,2),
    operating_cost_kw_day_usd NUMERIC(8,4),
    -- Vendor
    vendor_name         TEXT,
    vendor_url          TEXT,
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    search_vector       TSVECTOR,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add FK from hardware.cooling_compatibility (created earlier)
ALTER TABLE hardware.cooling_compatibility
    ADD CONSTRAINT fk_cooling_compat_solution
    FOREIGN KEY (cooling_solution_id) REFERENCES facility.cooling_solutions(id);

COMMENT ON TABLE facility.cooling_solutions IS
'Cooling solution hardware catalog. BiXBiT USA Fort Worth uses immersion and hydro cooling.
compatible_model_ids tracks which miners fit this solution.
max_power_kw is the thermal load limit — critical for facility planning.';

CREATE INDEX idx_cool_sol_type ON facility.cooling_solutions(cooling_type);
CREATE INDEX idx_cool_sol_models ON facility.cooling_solutions USING GIN(compatible_model_ids);
CREATE INDEX idx_cool_sol_search ON facility.cooling_solutions USING GIN(search_vector);

CREATE TRIGGER trg_cool_sol_updated_at
    BEFORE UPDATE ON facility.cooling_solutions
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- N6 (2026-04-27): cooling_type is an enum. Same fix as fw_search_vector —
-- replace tsvector_update_trigger with a custom PL/pgSQL trigger that does
-- the enum->text coercion explicitly.
CREATE OR REPLACE FUNCTION facility.cool_sol_search_vector_trigger()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('pg_catalog.english', coalesce(NEW.solution_name, '')), 'A') ||
        setweight(to_tsvector('pg_catalog.english', coalesce(NEW.manufacturer_name, '')), 'B') ||
        setweight(to_tsvector('pg_catalog.english', coalesce(NEW.cooling_type::text, '')), 'B') ||
        setweight(to_tsvector('pg_catalog.english', coalesce(NEW.fluid_type, '')), 'C') ||
        setweight(to_tsvector('pg_catalog.english', coalesce(NEW.notes, '')), 'D');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cool_sol_search_vector
    BEFORE INSERT OR UPDATE ON facility.cooling_solutions
    FOR EACH ROW EXECUTE FUNCTION facility.cool_sol_search_vector_trigger();

-- ---------------------------------------------------------------------------
-- POWER DISTRIBUTION UNITS
-- ---------------------------------------------------------------------------
CREATE TABLE facility.power_distribution_units (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    manufacturer_name   TEXT,
    model_name          TEXT NOT NULL,
    pdu_type            TEXT NOT NULL DEFAULT 'basic',
    -- 'basic', 'metered', 'switched', 'smart', 'managed'
    -- Input
    input_voltage_v     NUMERIC(6,2),
    input_phase         TEXT NOT NULL DEFAULT 'single',  -- 'single', 'three'
    input_amperage      NUMERIC(7,2),
    input_connector     TEXT,               -- 'NEMA 5-15', 'NEMA 6-20', 'L6-30', etc.
    -- Output
    outlet_count        INTEGER,
    outlet_types        JSONB NOT NULL DEFAULT '[]',
    -- [{"type": "C13", "count": 12, "amps": 16}, {"type": "C19", "count": 4, "amps": 32}]
    total_output_kw     NUMERIC(8,3),
    -- Monitoring
    has_per_outlet_metering   BOOLEAN NOT NULL DEFAULT FALSE,
    has_remote_switching      BOOLEAN NOT NULL DEFAULT FALSE,
    has_ip_management         BOOLEAN NOT NULL DEFAULT FALSE,
    api_type            TEXT,               -- 'snmp', 'rest', 'modbus', 'none'
    -- Dimensions
    rack_units          INTEGER,            -- 1U, 2U, etc.
    -- Source
    primary_source_id   UUID REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pdu_type ON facility.power_distribution_units(pdu_type);

CREATE TRIGGER trg_pdu_updated_at
    BEFORE UPDATE ON facility.power_distribution_units
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- FACILITIES — physical locations / data centers
-- ---------------------------------------------------------------------------
CREATE TABLE facility.facilities (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility_name       TEXT NOT NULL,
    -- e.g., "BiXBiT USA Fort Worth" or "ROBS-PC Dev Lab" or "UGREEN NAS July 2026"
    facility_type       TEXT NOT NULL DEFAULT 'colocation',
    -- 'home', 'colocation', 'industrial', 'container', 'warehouse', 'data_center'
    -- Location
    address_line1       TEXT,
    city                TEXT,
    state_province      TEXT,
    country             CHAR(2),
    -- Power
    total_power_capacity_kw  NUMERIC(10,3),
    current_power_usage_kw   NUMERIC(10,3),
    power_rate_kwh_usd       NUMERIC(8,4),
    power_contract_type      TEXT,          -- 'fixed', 'variable', 'demand_response'
    power_contract_expires   DATE,
    -- Cooling
    primary_cooling_type     public.cooling_type,
    cooling_capacity_kw      NUMERIC(10,3),
    -- Environment
    ambient_temp_typical_c   INTEGER,
    ambient_humidity_typical_pct INTEGER,
    -- Security
    has_24_7_monitoring      BOOLEAN NOT NULL DEFAULT FALSE,
    has_biometric_access     BOOLEAN NOT NULL DEFAULT FALSE,
    -- Bobby's facilities
    is_bobby_facility        BOOLEAN NOT NULL DEFAULT FALSE,
    fleet_size               INTEGER,       -- Number of miners currently here
    -- Source
    primary_source_id        UUID NOT NULL REFERENCES knowledge.sources(id),
    notes                    TEXT,
    metadata                 JSONB NOT NULL DEFAULT '{}',
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE facility.facilities IS
'Physical facilities where miners operate. Bobby current facility:
BiXBiT USA Fort Worth TX — 58 liquid-cooled miners. Future NAS migration July 2026.';

CREATE INDEX idx_facilities_bobby ON facility.facilities(is_bobby_facility)
    WHERE is_bobby_facility = TRUE;
CREATE INDEX idx_facilities_country ON facility.facilities(country);

CREATE TRIGGER trg_facilities_updated_at
    BEFORE UPDATE ON facility.facilities
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- HVAC INTEGRATION PATTERNS
-- ---------------------------------------------------------------------------
CREATE TABLE facility.hvac_patterns (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pattern_name        TEXT NOT NULL,
    description         TEXT,
    cooling_type        public.cooling_type,    -- Compatible cooling type
    -- What works with what
    works_with_miners   UUID[] NOT NULL DEFAULT '{}',  -- miner_model_ids
    works_with_cooling  UUID[] NOT NULL DEFAULT '{}',  -- cooling_solution_ids
    -- Performance data
    efficiency_cop      NUMERIC(6,3),       -- Coefficient of performance
    ambient_temp_range  JSONB,              -- {"min_c": 10, "max_c": 45}
    humidity_range      JSONB,
    -- Known issues
    known_issues        JSONB NOT NULL DEFAULT '[]',
    recommended_setpoints JSONB,
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'low',
    verified_by_bobby   BOOLEAN NOT NULL DEFAULT FALSE,
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_hvac_cooling ON facility.hvac_patterns(cooling_type);
CREATE INDEX idx_hvac_miners ON facility.hvac_patterns USING GIN(works_with_miners);
CREATE INDEX idx_hvac_bobby ON facility.hvac_patterns(verified_by_bobby)
    WHERE verified_by_bobby = TRUE;

CREATE TRIGGER trg_hvac_updated_at
    BEFORE UPDATE ON facility.hvac_patterns
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- RACK/POSITION LAYOUTS — physical slot tracking
-- ---------------------------------------------------------------------------
CREATE TABLE facility.rack_positions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility_id         UUID NOT NULL REFERENCES facility.facilities(id),
    rack_id             TEXT NOT NULL,          -- "RACK-A1", "TANK-01"
    position_in_rack    INTEGER,                -- Slot number or position
    position_label      TEXT,                   -- "A1-Slot-3"
    cooling_zone        TEXT,                   -- HVAC zone this position is in
    pdu_id              UUID REFERENCES facility.power_distribution_units(id),
    pdu_outlet          TEXT,                   -- Which outlet on the PDU
    network_switch      TEXT,
    network_port        TEXT,
    -- Currently installed miner (from operational guardian.db — this is intelligence only)
    current_model_id    UUID REFERENCES hardware.miner_models(id),
    -- Position notes
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (facility_id, rack_id, position_in_rack)
);

COMMENT ON TABLE facility.rack_positions IS
'Physical rack/tank position map. Links infrastructure to installed hardware models.
The actual live miner data (IP, serial, current status) lives in guardian.db operational DB.
This table stores the INTELLIGENCE layer: which model type is in each slot, for pattern analysis.';

CREATE INDEX idx_rack_facility ON facility.rack_positions(facility_id);
CREATE INDEX idx_rack_model ON facility.rack_positions(current_model_id)
    WHERE current_model_id IS NOT NULL;

CREATE TRIGGER trg_rack_updated_at
    BEFORE UPDATE ON facility.rack_positions
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ===========================================================================
-- CATEGORY 8: REGULATORY/COMPLIANCE
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- REGULATORY FRAMEWORKS — laws, regs, and rules by jurisdiction
-- ---------------------------------------------------------------------------
CREATE TABLE regulatory.frameworks (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    framework_name      TEXT NOT NULL,
    jurisdiction        TEXT NOT NULL,          -- "Texas, USA", "EU", "Federal US"
    jurisdiction_type   public.jurisdiction_type NOT NULL,
    -- Category
    reg_category        TEXT NOT NULL,
    -- 'zoning', 'noise', 'electrical', 'environmental', 'tax', 'securities', 
    --  'import_export', 'data_privacy', 'energy', 'building_permit', 'insurance'
    -- Effective
    effective_date      DATE,
    expiration_date     DATE,
    is_current          BOOLEAN NOT NULL DEFAULT TRUE,
    -- Requirements
    summary             TEXT NOT NULL,
    key_requirements    JSONB NOT NULL DEFAULT '[]',
    -- [{"requirement": "Noise < 55dB at property line", "threshold": "55dB", "time": "nighttime"}]
    compliance_steps    JSONB NOT NULL DEFAULT '[]',
    penalties_for_violation TEXT,
    -- Links
    official_source_url TEXT,
    -- Applicability to Bobby's fleet
    applies_to_facility_ids UUID[] NOT NULL DEFAULT '{}',
    -- Source
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    last_verified_date  DATE,
    notes               TEXT,
    search_vector       TSVECTOR,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE regulatory.frameworks IS
'Regulatory and compliance frameworks by jurisdiction. Covers noise ordinances,
electrical permits, environmental rules, tax treatment, and import/export.
applies_to_facility_ids links regulations to Bobby''s specific facilities.';

CREATE INDEX idx_reg_jurisdiction ON regulatory.frameworks(jurisdiction);
CREATE INDEX idx_reg_category ON regulatory.frameworks(reg_category);
CREATE INDEX idx_reg_current ON regulatory.frameworks(is_current) WHERE is_current = TRUE;
CREATE INDEX idx_reg_facilities ON regulatory.frameworks USING GIN(applies_to_facility_ids);
CREATE INDEX idx_reg_search ON regulatory.frameworks USING GIN(search_vector);

CREATE TRIGGER trg_reg_updated_at
    BEFORE UPDATE ON regulatory.frameworks
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_reg_search_vector
    BEFORE INSERT OR UPDATE ON regulatory.frameworks
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        framework_name, jurisdiction, reg_category, summary, notes
    );

-- ---------------------------------------------------------------------------
-- TAX TREATMENT — depreciation schedules, deductions, mining income rules
-- ---------------------------------------------------------------------------
CREATE TABLE regulatory.tax_treatment (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    jurisdiction        TEXT NOT NULL,
    tax_year            INTEGER,                -- NULL = ongoing/multi-year
    -- Category
    tax_category        TEXT NOT NULL,
    -- 'hardware_depreciation', 'mining_income', 'electricity_deduction',
    --  'facility_expense', 'capital_gains', 'self_employment', 'bitcoin_as_property'
    -- Treatment details
    treatment_summary   TEXT NOT NULL,
    depreciation_method TEXT,                  -- 'MACRS', 'straight_line', 'bonus', 'section_179'
    depreciation_years  INTEGER,
    depreciation_pct_year1 NUMERIC(6,4),       -- Year 1 depreciation %
    bonus_depreciation_eligible BOOLEAN,
    -- Documentation required
    required_forms      JSONB NOT NULL DEFAULT '[]',    -- ["Form 4562", "Schedule C"]
    documentation_requirements TEXT,
    -- Source
    official_source_url TEXT,
    irs_publication_ref TEXT,
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    last_verified_date  DATE,
    notes               TEXT,
    search_vector       TSVECTOR,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE regulatory.tax_treatment IS
'US and international tax treatment for mining hardware and operations.
Hardware depreciation (MACRS 5-year, Section 179, bonus depreciation) is tracked here.
Mining income recognition rules and electricity deductibility are key topics for Bobby.';

CREATE INDEX idx_tax_jurisdiction ON regulatory.tax_treatment(jurisdiction);
CREATE INDEX idx_tax_category ON regulatory.tax_treatment(tax_category);
CREATE INDEX idx_tax_year ON regulatory.tax_treatment(tax_year DESC);
CREATE INDEX idx_tax_search ON regulatory.tax_treatment USING GIN(search_vector);

CREATE TRIGGER trg_tax_updated_at
    BEFORE UPDATE ON regulatory.tax_treatment
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_tax_search_vector
    BEFORE INSERT OR UPDATE ON regulatory.tax_treatment
    FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(
        search_vector, 'pg_catalog.english',
        jurisdiction, tax_category, treatment_summary, notes
    );

-- ---------------------------------------------------------------------------
-- IMPORT/EXPORT — tariffs, restrictions, compliance requirements
-- ---------------------------------------------------------------------------
CREATE TABLE regulatory.import_export_rules (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rule_type           TEXT NOT NULL DEFAULT 'import',  -- 'import', 'export', 'both'
    origin_country      CHAR(2),                -- ISO 3166-1 alpha-2
    destination_country CHAR(2),
    -- Affected goods
    hs_code             TEXT,                   -- Harmonized System tariff code
    goods_description   TEXT NOT NULL,
    affected_model_ids  UUID[] NOT NULL DEFAULT '{}',
    -- Current tariff / duty
    duty_rate_pct       NUMERIC(8,4),
    special_duty_pct    NUMERIC(8,4),           -- Section 301, anti-dumping, etc.
    duty_basis          TEXT,                   -- 'ad_valorem', 'specific', 'compound'
    -- Restrictions
    is_restricted       BOOLEAN NOT NULL DEFAULT FALSE,
    restriction_type    TEXT,                   -- 'banned', 'license_required', 'quota'
    license_required    BOOLEAN NOT NULL DEFAULT FALSE,
    license_type        TEXT,
    -- Compliance
    documentation_required JSONB NOT NULL DEFAULT '[]',
    customs_value_method TEXT,
    -- Dates
    effective_date      DATE,
    expiration_date     DATE,
    is_current          BOOLEAN NOT NULL DEFAULT TRUE,
    -- Source
    official_source_url TEXT,
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE regulatory.import_export_rules IS
'Import/export tariff and restriction data. Critical for fleet expansion purchases.
Bitmain miners from China face Section 301 tariffs. Tracking hs_code enables
rapid lookup of current duty rates when evaluating purchase decisions.';

CREATE INDEX idx_ie_origin ON regulatory.import_export_rules(origin_country);
CREATE INDEX idx_ie_dest ON regulatory.import_export_rules(destination_country);
CREATE INDEX idx_ie_models ON regulatory.import_export_rules USING GIN(affected_model_ids);
CREATE INDEX idx_ie_current ON regulatory.import_export_rules(is_current) WHERE is_current = TRUE;

CREATE TRIGGER trg_ie_updated_at
    BEFORE UPDATE ON regulatory.import_export_rules
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- INSURANCE REQUIREMENTS
-- ---------------------------------------------------------------------------
CREATE TABLE regulatory.insurance_requirements (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    jurisdiction        TEXT NOT NULL,
    facility_type       TEXT,               -- 'home', 'commercial', 'industrial', etc.
    requirement_type    TEXT NOT NULL,
    -- 'general_liability', 'property', 'business_interruption', 'workers_comp',
    --  'equipment_breakdown', 'cyber', 'professional_liability'
    summary             TEXT NOT NULL,
    minimum_coverage_usd NUMERIC(14,2),
    notes               TEXT,
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'low',
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_insurance_jurisdiction ON regulatory.insurance_requirements(jurisdiction);
CREATE INDEX idx_insurance_type ON regulatory.insurance_requirements(requirement_type);

CREATE TRIGGER trg_insurance_updated_at
    BEFORE UPDATE ON regulatory.insurance_requirements
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- NOISE / ENVIRONMENTAL REGULATIONS
-- ---------------------------------------------------------------------------
CREATE TABLE regulatory.environmental_regs (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    jurisdiction        TEXT NOT NULL,
    regulation_name     TEXT NOT NULL,
    -- Noise
    noise_limit_db_day  NUMERIC(6,2),
    noise_limit_db_night NUMERIC(6,2),
    noise_measurement_point TEXT,           -- 'property_line', '50_feet', 'nearest_residence'
    -- Heat / thermal
    heat_discharge_limit_kw NUMERIC(10,3),
    coolant_disposal_restrictions TEXT,
    -- Emissions
    air_emission_restrictions TEXT,
    -- Enforcement
    enforcing_agency    TEXT,
    penalty_per_violation_usd NUMERIC(10,2),
    permit_required     BOOLEAN NOT NULL DEFAULT FALSE,
    permit_type         TEXT,
    -- Source
    official_source_url TEXT,
    primary_source_id   UUID NOT NULL REFERENCES knowledge.sources(id),
    confidence          public.confidence_level NOT NULL DEFAULT 'medium',
    notes               TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_envregs_jurisdiction ON regulatory.environmental_regs(jurisdiction);

CREATE TRIGGER trg_envregs_updated_at
    BEFORE UPDATE ON regulatory.environmental_regs
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
-- =============================================================================
-- MINING INTELLIGENCE CATALOG — Part 9: Seed Data
-- Bobby's Fleet Models, Core Sources, Contributors, Chips, Firmware
-- =============================================================================
-- All UUIDs are deterministic for referential integrity in seed data.
-- Use gen_random_uuid() or hard-code stable UUIDs here.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- SEED: CONTRIBUTORS
-- ---------------------------------------------------------------------------
INSERT INTO knowledge.contributors (id, handle, display_name, contributor_type, trust_score,
    trust_rationale, affiliation, is_active)
VALUES
    ('00000000-0000-0000-0000-000000000001',
     'bobby_fiesler',
     'Bobby (Rob Fiesler)',
     'bobby_operational',
     0.95,
     'Fleet owner and operator with 58 liquid-cooled miners. Direct operational experience. Mining Guardian product owner.',
     'Mining Guardian / BiXBiT USA Fort Worth TX',
     TRUE),
    ('00000000-0000-0000-0000-000000000002',
     'bitmain_official',
     'Bitmain Technologies Official',
     'manufacturer',
     0.88,
     'Manufacturer specifications. Generally accurate but occasionally conservative or silent on thermal throttling behaviors.',
     'Bitmain Technologies Ltd.',
     TRUE),
    ('00000000-0000-0000-0000-000000000003',
     'auradine_official',
     'Auradine Official',
     'manufacturer',
     0.90,
     'Manufacturer of Teraflux line. New company, strong engineering team, specs verified by Bobby.',
     'Auradine Inc.',
     TRUE),
    ('00000000-0000-0000-0000-000000000004',
     'bixbit_team',
     'BiXBiT Firmware Team',
     'manufacturer',
     0.92,
     'Custom firmware developer. Performance specs verified by Bobby operationally.',
     'BiXBiT',
     TRUE);

-- ---------------------------------------------------------------------------
-- SEED: SOURCES
-- ---------------------------------------------------------------------------
INSERT INTO knowledge.sources (id, source_key, display_name, tier, source_url, description,
    trust_score, contributor_id, is_active)
VALUES
    ('10000000-0000-0000-0000-000000000001',
     'bitmain_official_site',
     'Bitmain Official Website',
     'tier1_manufacturer',
     'https://www.bitmain.com',
     'Official Bitmain product pages, datasheets, and specifications.',
     0.88,
     '00000000-0000-0000-0000-000000000002',
     TRUE),
    ('10000000-0000-0000-0000-000000000002',
     'auradine_official_site',
     'Auradine Official Website',
     'tier1_manufacturer',
     'https://www.auradine.com',
     'Official Auradine product pages for Teraflux line.',
     0.90,
     '00000000-0000-0000-0000-000000000003',
     TRUE),
    ('10000000-0000-0000-0000-000000000003',
     'bixbit_official',
     'BiXBiT Official Documentation',
     'tier1_manufacturer',
     'https://bixbit.io',
     'BiXBiT custom firmware documentation, release notes, and supported hardware.',
     0.92,
     '00000000-0000-0000-0000-000000000004',
     TRUE),
    ('10000000-0000-0000-0000-000000000004',
     'bobby_operational_data',
     'Bobby Fiesler Operational Data',
     'tier2_operational',
     NULL,
     'Direct measurements and observations from Bobby''s 58-unit fleet at BiXBiT USA Fort Worth TX.',
     0.95,
     '00000000-0000-0000-0000-000000000001',
     TRUE),
    ('10000000-0000-0000-0000-000000000005',
     'braiins_official',
     'Braiins Official Documentation',
     'tier1_manufacturer',
     'https://braiins.com',
     'Braiins OS, Braiins OS+, and Braiins Pool documentation.',
     0.87,
     NULL,
     TRUE),
    ('10000000-0000-0000-0000-000000000006',
     'vnish_official',
     'VNish Official Documentation',
     'tier1_manufacturer',
     'https://vnish.net',
     'VNish custom firmware documentation and release notes.',
     0.82,
     NULL,
     TRUE),
    ('10000000-0000-0000-0000-000000000007',
     'asicminervalue',
     'ASIC Miner Value',
     'tier5_market_external',
     'https://www.asicminervalue.com',
     'Mining profitability calculator and hardware database. Market pricing data.',
     0.65,
     NULL,
     TRUE),
    ('10000000-0000-0000-0000-000000000008',
     'reddit_bitcoinmining',
     'Reddit r/BitcoinMining',
     'tier4_community',
     'https://www.reddit.com/r/BitcoinMining/',
     'Community discussion on Bitcoin mining hardware, operations, and troubleshooting.',
     0.45,
     NULL,
     TRUE),
    ('10000000-0000-0000-0000-000000000009',
     'schema_design_initial',
     'Mining Intelligence Catalog — Initial Schema Design',
     'tier2_operational',
     NULL,
     'Internal: Initial seed data loaded during schema creation.',
     0.90,
     '00000000-0000-0000-0000-000000000001',
     TRUE);

-- ---------------------------------------------------------------------------
-- SEED: MANUFACTURERS
-- ---------------------------------------------------------------------------
INSERT INTO hardware.manufacturers (id, brand, legal_name, common_name, country_of_origin,
    headquarters_city, website_url, is_active, primary_source_id, confidence)
VALUES
    ('20000000-0000-0000-0000-000000000001',
     'bitmain',
     'Bitmain Technologies Holding Company',
     'Bitmain',
     'CN',
     'Beijing',
     'https://www.bitmain.com',
     TRUE,
     '10000000-0000-0000-0000-000000000001',
     'verified'),
    ('20000000-0000-0000-0000-000000000002',
     'auradine',
     'Auradine, Inc.',
     'Auradine',
     'US',
     'San Jose',
     'https://www.auradine.com',
     TRUE,
     '10000000-0000-0000-0000-000000000002',
     'verified'),
    ('20000000-0000-0000-0000-000000000003',
     'microbt',
     'MicroBT Electronics Technology Co., Ltd.',
     'MicroBT / Whatsminer',
     'CN',
     'Shenzhen',
     'https://www.microbt.com',
     TRUE,
     '10000000-0000-0000-0000-000000000009',
     'high');

-- ---------------------------------------------------------------------------
-- SEED: CHIPS (Bobby's fleet chips)
-- ---------------------------------------------------------------------------
INSERT INTO hardware.chips (id, chip_model, manufacturer_id, process_node,
    hashrate_gh_per_chip, power_mw_per_chip, efficiency_j_per_th,
    core_voltage_mv_nom, frequency_mhz_nom, algorithm, release_year,
    is_current_gen, primary_source_id, confidence, notes)
VALUES
    -- BM1362: S19j Pro chip
    ('30000000-0000-0000-0000-000000000001',
     'BM1362',
     '20000000-0000-0000-0000-000000000001',
     '5nm',
     5800.0,          -- ~5.8 GH/s per chip
     800.0,           -- ~800mW per chip at nominal
     0.138,           -- ~138 J/TH
     310,             -- ~310mV nominal core voltage
     490,             -- ~490 MHz nominal
     'SHA-256',
     2021,
     FALSE,           -- Superseded by BM1368
     '10000000-0000-0000-0000-000000000001',
     'medium',
     'Used in Antminer S19j Pro (126 chips per board × 3 boards). '
     'Process node is 5nm. Capable of significant overclock in immersion cooling.'),

    -- BM1368: S21 / S21 EXP chip
    ('30000000-0000-0000-0000-000000000002',
     'BM1368',
     '20000000-0000-0000-0000-000000000001',
     '5nm',
     9500.0,          -- ~9.5 GH/s per chip (estimated)
     1100.0,
     0.116,
     350,
     600,
     'SHA-256',
     2023,
     TRUE,
     '10000000-0000-0000-0000-000000000001',
     'medium',
     'Used in Antminer S21 EXP Hydro and S21 Immersion. Higher performance successor to BM1362. '
     'Higher efficiency enables >500 TH/s with BiXBiT firmware.'),

    -- AT7200: Auradine Teraflux
    ('30000000-0000-0000-0000-000000000003',
     'AT7200',
     '20000000-0000-0000-0000-000000000002',
     '5nm',
     NULL,            -- Auradine does not publish per-chip specs publicly
     NULL,
     NULL,
     NULL,
     NULL,
     'SHA-256',
     2023,
     TRUE,
     '10000000-0000-0000-0000-000000000002',
     'medium',
     'Used in Auradine Teraflux AH3880. Hydro-native design. '
     'Eco mode 300 TH/s, Turbo mode 600 TH/s across 2 hashboards.'),

    -- BM1397: Older S17/S19 reference chip
    ('30000000-0000-0000-0000-000000000004',
     'BM1397',
     '20000000-0000-0000-0000-000000000001',
     '7nm',
     3700.0,
     650.0,
     0.176,
     385,
     450,
     'SHA-256',
     2020,
     FALSE,
     '10000000-0000-0000-0000-000000000001',
     'medium',
     'Used in Antminer S17 and early S19 units. 7nm TSMC. Reference chip for repair training.');

-- ---------------------------------------------------------------------------
-- SEED: HASHBOARDS (Bobby's fleet boards)
-- ---------------------------------------------------------------------------
INSERT INTO hardware.hashboards (id, manufacturer_id, board_name, pcb_revision,
    chip_id, chips_per_board, board_power_w_nom, hashrate_th_nom, hashrate_th_max,
    temp_sensor_count, max_temp_celsius, primary_source_id, confidence, notes)
VALUES
    -- S19j Pro hashboard
    ('40000000-0000-0000-0000-000000000001',
     '20000000-0000-0000-0000-000000000001',
     'Antminer S19j Pro Hashboard',
     'v1.0',
     '30000000-0000-0000-0000-000000000001',   -- BM1362
     126,             -- 126 chips per board
     1155.0,          -- ~1155W per board (3×1155=3465W ≈ 3500W stock)
     34.7,            -- ~34.7 TH/s per board (3×34.7≈104 TH/s)
     55.0,            -- Can do ~55 TH/s per board in immersion overclocked
     3,               -- 3 temp sensors per board
     90,
     '10000000-0000-0000-0000-000000000001',
     'medium',
     'Standard S19j Pro hashboard. 126× BM1362 chips. 3 boards per unit = 104 TH/s stock.'),

    -- S21 EXP Hydro hashboard
    ('40000000-0000-0000-0000-000000000002',
     '20000000-0000-0000-0000-000000000001',
     'Antminer S21 EXP Hydro Hashboard',
     'v1.0',
     '30000000-0000-0000-0000-000000000002',   -- BM1368
     180,             -- Estimated chip count
     2550.0,          -- ~2550W per board (3×2550≈7650W ≈ 5765W stock — see note)
     143.3,           -- ~143.3 TH/s per board (3×143.3≈430 TH/s stock)
     170.0,           -- ~170 TH/s per board max (BiXBiT: 3×170≈506 TH/s)
     4,
     95,
     '10000000-0000-0000-0000-000000000001',
     'medium',
     'S21 EXP Hydro hashboard. 3 boards per unit = 430 TH/s stock. BiXBiT → 506 TH/s.'),

    -- S21 Immersion hashboard
    ('40000000-0000-0000-0000-000000000003',
     '20000000-0000-0000-0000-000000000001',
     'Antminer S21 Immersion Hashboard',
     'v1.0',
     '30000000-0000-0000-0000-000000000002',   -- BM1368
     144,
     1540.0,          -- ~1540W per board (3 boards × 1540 ≈ 4620W ≈ stock power)
     69.3,            -- ~69.3 TH/s per board (3×69.3≈208 TH/s)
     120.0,           -- ~120 TH/s per board (3×120≈360 TH/s max)
     3,
     90,
     '10000000-0000-0000-0000-000000000001',
     'medium',
     'S21 Immersion variant hashboard. 3 boards = 208 TH/s stock, max 360 TH/s.'),

    -- Auradine AH3880 hashboard
    ('40000000-0000-0000-0000-000000000004',
     '20000000-0000-0000-0000-000000000002',
     'Auradine Teraflux AH3880 Hashboard',
     'v1.0',
     '30000000-0000-0000-0000-000000000003',   -- AT7200
     NULL,            -- Auradine does not publish chip count
     NULL,
     150.0,           -- ~150 TH/s per board × 2 = 300 TH/s eco; 300 TH/s × 2 = 600 TH/s turbo
     300.0,
     4,
     85,              -- Hydro cooling enables lower operating temps
     '10000000-0000-0000-0000-000000000002',
     'medium',
     'AH3880 hashboard. CRITICAL: AH3880 uses EXACTLY 2 boards — NOT 3. '
     'Any record claiming 3 boards is an error. Hydro-native design.');

-- ---------------------------------------------------------------------------
-- SEED: MINER MODELS (Bobby's fleet — 4 models)
-- ---------------------------------------------------------------------------
INSERT INTO hardware.miner_models (id, manufacturer_id, canonical_name, model_number,
    generation, cooling_type, hashboard_count, hashboard_id, board_count_is_fixed,
    stock_hashrate_th, stock_power_w, stock_efficiency_j_th, max_hashrate_th, max_power_w,
    input_voltage_v_nom, algorithm, released_date, is_current_product,
    primary_source_id, confidence, notes)
VALUES
    -- Antminer S19j Pro
    ('50000000-0000-0000-0000-000000000001',
     '20000000-0000-0000-0000-000000000001',
     'Antminer S19j Pro',
     'S19J Pro',
     'S19 series',
     'immersion',
     3,
     '40000000-0000-0000-0000-000000000001',
     TRUE,
     104.0,
     3068.0,          -- Bitmain spec: 3068W ±5%
     29.5,            -- 3068/104 ≈ 29.5 J/TH
     160.0,           -- BiXBiT max
     5500.0,          -- Estimated at max TH/s
     220.0,
     'SHA-256',
     '2021-07-01',
     FALSE,           -- Superseded by S21 series
     '10000000-0000-0000-0000-000000000001',
     'verified',
     'Bobby''s fleet includes S19j Pro units. Immersion cooled. '
     'BiXBiT firmware enables up to 160 TH/s (54% above stock 104 TH/s). '
     '3 boards × 126 BM1362 chips. CANNOT have any other board count.'),

    -- Auradine Teraflux AH3880
    ('50000000-0000-0000-0000-000000000002',
     '20000000-0000-0000-0000-000000000002',
     'Auradine Teraflux AH3880',
     'AH3880',
     'Teraflux',
     'hydro',
     2,               -- CRITICAL: EXACTLY 2 BOARDS. THIS IS A HARD RULE.
     '40000000-0000-0000-0000-000000000004',
     TRUE,            -- board_count_is_fixed = TRUE: 2 boards, no exceptions
     300.0,           -- Eco mode = 300 TH/s
     1800.0,          -- Eco mode power (estimated; Auradine does not publish)
     6.0,             -- 1800/300 = 6 J/TH (eco mode)
     600.0,           -- Turbo mode = 600 TH/s
     5500.0,          -- Turbo power (estimated)
     48.0,            -- Hydro-native high voltage
     'SHA-256',
     '2023-01-01',
     TRUE,
     '10000000-0000-0000-0000-000000000002',
     'verified',
     'CRITICAL DESIGN RULE: AH3880 has EXACTLY 2 hashboards. Any record stating 3 boards '
     'is wrong. Hydro-cooled only. AT7200 chip. Eco: 300 TH/s, Turbo: 600 TH/s. '
     'Bobby runs these at BiXBiT USA Fort Worth in hydro cooling loop.'),

    -- Antminer S21 EXP Hydro
    ('50000000-0000-0000-0000-000000000003',
     '20000000-0000-0000-0000-000000000001',
     'Antminer S21 EXP Hydro',
     'S21 EXP',
     'S21 series',
     'hydro',
     3,
     '40000000-0000-0000-0000-000000000002',
     TRUE,
     430.0,           -- Stock: 430 TH/s
     5765.0,          -- Bitmain spec: 5765W ±5%
     13.4,            -- 5765/430 ≈ 13.4 J/TH (very efficient)
     506.0,           -- BiXBiT max
     7500.0,          -- Estimated
     48.0,
     'SHA-256',
     '2024-01-01',
     TRUE,
     '10000000-0000-0000-0000-000000000001',
     'verified',
     'Hydro-cooled S21 EXP. 3 boards × BM1368 chips. Stock 430 TH/s. '
     'BiXBiT firmware enables up to 506 TH/s (18% above stock). '
     'Part of Bobby''s current fleet at BiXBiT USA Fort Worth.'),

    -- Antminer S21 Immersion
    ('50000000-0000-0000-0000-000000000004',
     '20000000-0000-0000-0000-000000000001',
     'Antminer S21 Immersion',
     'S21 Immersion',
     'S21 series',
     'immersion',
     3,
     '40000000-0000-0000-0000-000000000003',
     TRUE,
     208.0,           -- Stock: 208 TH/s
     3500.0,          -- Estimated stock power
     16.8,            -- 3500/208 ≈ 16.8 J/TH
     360.0,           -- Max (with tuning)
     6000.0,          -- Estimated
     220.0,
     'SHA-256',
     '2023-07-01',
     TRUE,
     '10000000-0000-0000-0000-000000000001',
     'verified',
     'Immersion-cooled S21 variant. 3 boards × BM1368 chips. Stock 208 TH/s, max 360 TH/s. '
     'Part of Bobby''s fleet at BiXBiT USA Fort Worth.');

-- ---------------------------------------------------------------------------
-- SEED: MODEL ALIASES (critical for fuzzy matching and 1M+ repair record ingestion)
-- ---------------------------------------------------------------------------
INSERT INTO hardware.model_aliases (miner_model_id, alias, alias_normalized, alias_source, is_common)
VALUES
    -- S19j Pro aliases
    ('50000000-0000-0000-0000-000000000001', 'Antminer S19j Pro',    'antminers19jpro',    'manufacturer_doc', TRUE),
    ('50000000-0000-0000-0000-000000000001', 'S19j Pro',             's19jpro',            'manufacturer_doc', TRUE),
    ('50000000-0000-0000-0000-000000000001', 'S19J Pro',             's19jpro',            'manufacturer_doc', FALSE),
    ('50000000-0000-0000-0000-000000000001', 'S19JPro',              's19jpro',            'forum',            TRUE),
    ('50000000-0000-0000-0000-000000000001', 'S19-J-Pro',            's19jpro',            'forum',            FALSE),
    ('50000000-0000-0000-0000-000000000001', 's19j pro',             's19jpro',            'repair_shop_import',TRUE),
    ('50000000-0000-0000-0000-000000000001', 'S19 J Pro',            's19jpro',            'forum',            FALSE),
    ('50000000-0000-0000-0000-000000000001', 'Antminer S19J Pro 104TH','antminers19jpro104th','listing',       FALSE),
    ('50000000-0000-0000-0000-000000000001', 'BM S19J Pro',          'bms19jpro',          'repair_shop_import',FALSE),
    ('50000000-0000-0000-0000-000000000001', 's19j-pro',             's19jpro',            'repair_shop_import',FALSE),
    -- AH3880 aliases
    ('50000000-0000-0000-0000-000000000002', 'Auradine Teraflux AH3880','auraterafluxah3880','manufacturer_doc',TRUE),
    ('50000000-0000-0000-0000-000000000002', 'AH3880',               'ah3880',             'manufacturer_doc', TRUE),
    ('50000000-0000-0000-0000-000000000002', 'Auradine AH3880',      'auradineah3880',     'manufacturer_doc', TRUE),
    ('50000000-0000-0000-0000-000000000002', 'Teraflux AH3880',      'terafluxah3880',     'forum',            FALSE),
    ('50000000-0000-0000-0000-000000000002', 'AH 3880',              'ah3880',             'forum',            FALSE),
    ('50000000-0000-0000-0000-000000000002', 'auradine ah3880',      'auradineah3880',     'repair_shop_import',FALSE),
    -- S21 EXP Hydro aliases
    ('50000000-0000-0000-0000-000000000003', 'Antminer S21 EXP Hydro','antminers21exphydro','manufacturer_doc',TRUE),
    ('50000000-0000-0000-0000-000000000003', 'S21 EXP Hydro',        's21exphydro',        'manufacturer_doc', TRUE),
    ('50000000-0000-0000-0000-000000000003', 'S21EXP',               's21exp',             'forum',            TRUE),
    ('50000000-0000-0000-0000-000000000003', 'S21 EXP',              's21exp',             'manufacturer_doc', TRUE),
    ('50000000-0000-0000-0000-000000000003', 'S21EXPHydro',          's21exphydro',        'forum',            FALSE),
    ('50000000-0000-0000-0000-000000000003', 's21 exp hydro',        's21exphydro',        'repair_shop_import',FALSE),
    ('50000000-0000-0000-0000-000000000003', 'Antminer S21 EXP 430TH','antminers21exp430th','listing',         FALSE),
    -- S21 Immersion aliases
    ('50000000-0000-0000-0000-000000000004', 'Antminer S21 Immersion','antminers21immersion','manufacturer_doc',TRUE),
    ('50000000-0000-0000-0000-000000000004', 'S21 Immersion',        's21immersion',       'manufacturer_doc', TRUE),
    ('50000000-0000-0000-0000-000000000004', 'S21Imm',               's21imm',             'forum',            TRUE),
    ('50000000-0000-0000-0000-000000000004', 's21 imm',              's21imm',             'repair_shop_import',FALSE),
    ('50000000-0000-0000-0000-000000000004', 'S21-Immersion',        's21immersion',       'forum',            FALSE),
    ('50000000-0000-0000-0000-000000000004', 'Antminer S21 208TH',   'antminers21208th',   'listing',          FALSE);

-- ---------------------------------------------------------------------------
-- SEED: FIRMWARE RELEASES (key versions for Bobby's fleet)
-- ---------------------------------------------------------------------------
INSERT INTO firmware.firmware_releases (id, firmware_family, version_string, display_name,
    developer_name, developer_url, is_current_stable, supports_autotuning, supports_eco_mode,
    supports_turbo_mode, supports_ssl_mining, max_hashrate_increase_pct,
    primary_source_id, confidence, notes)
VALUES
    -- BiXBiT
    ('60000000-0000-0000-0000-000000000001',
     'bixbit',
     '2024-10-22-legacy',
     'BiXBiT 2024-10-22 (Legacy)',
     'BiXBiT',
     'https://bixbit.io',
     FALSE,
     TRUE, TRUE, TRUE, TRUE,
     54.0,   -- Up to 54% above stock on S19j Pro
     '10000000-0000-0000-0000-000000000003',
     'verified',
     'BiXBiT firmware version running on Bobby''s S19j Pro units. Enables 160 TH/s from 104 TH/s.'),
    ('60000000-0000-0000-0000-000000000002',
     'bixbit',
     '2025-latest',
     'BiXBiT Latest (2025)',
     'BiXBiT',
     'https://bixbit.io',
     TRUE,
     TRUE, TRUE, TRUE, TRUE,
     18.0,   -- 18% above stock on S21 EXP (430→506 TH/s)
     '10000000-0000-0000-0000-000000000003',
     'verified',
     'Current BiXBiT firmware. Supports S21 EXP Hydro → 506 TH/s.'),
    -- Stock Bitmain
    ('60000000-0000-0000-0000-000000000003',
     'stock_bitmain',
     'stock_s19j_pro',
     'Bitmain S19j Pro Stock Firmware',
     'Bitmain',
     'https://www.bitmain.com',
     FALSE,
     FALSE, FALSE, FALSE, FALSE,
     0.0,
     '10000000-0000-0000-0000-000000000001',
     'high',
     'Stock Bitmain firmware for S19j Pro. 104 TH/s stock.'),
    ('60000000-0000-0000-0000-000000000004',
     'stock_bitmain',
     'stock_s21_exp',
     'Bitmain S21 EXP Stock Firmware',
     'Bitmain',
     'https://www.bitmain.com',
     TRUE,
     FALSE, FALSE, FALSE, FALSE,
     0.0,
     '10000000-0000-0000-0000-000000000001',
     'high',
     'Stock Bitmain firmware for S21 EXP Hydro and S21 Immersion. 430 / 208 TH/s.'),
    -- Auradine native
    ('60000000-0000-0000-0000-000000000005',
     'auradine_native',
     'auradine_latest',
     'Auradine Native Firmware (Latest)',
     'Auradine',
     'https://www.auradine.com',
     TRUE,
     TRUE, TRUE, TRUE, TRUE,
     0.0,
     '10000000-0000-0000-0000-000000000002',
     'verified',
     'Auradine''s native firmware for AH3880. Eco 300 TH/s / Turbo 600 TH/s.'),
    -- Braiins OS+
    ('60000000-0000-0000-0000-000000000006',
     'braiins_os',
     'bos_24_09',
     'Braiins OS+ 24.09',
     'Braiins',
     'https://braiins.com',
     TRUE,
     TRUE, TRUE, TRUE, TRUE,
     10.0,
     '10000000-0000-0000-0000-000000000005',
     'high',
     'Braiins OS+ version 24.09. Autotuning firmware for Bitmain S-series.');

-- ---------------------------------------------------------------------------
-- SEED: FIRMWARE ↔ HARDWARE COMPATIBILITY (Bobby's fleet combos)
-- ---------------------------------------------------------------------------
INSERT INTO firmware.firmware_compatibility (firmware_id, miner_model_id,
    is_compatible, is_officially_supported, typical_hashrate_th, max_achievable_th,
    verified_by_bobby, primary_source_id, confidence, notes)
VALUES
    -- BiXBiT on S19j Pro (verified by Bobby!)
    ('60000000-0000-0000-0000-000000000001',
     '50000000-0000-0000-0000-000000000001',
     TRUE, FALSE, 140.0, 160.0, TRUE,
     '10000000-0000-0000-0000-000000000004',
     'verified',
     'Bobby verified: BiXBiT on S19j Pro achieves 140–160 TH/s immersion. '
     'Typical daily average ~145 TH/s. Max observed 160 TH/s at low coolant temp.'),
    -- BiXBiT on S21 EXP Hydro (verified by Bobby!)
    ('60000000-0000-0000-0000-000000000002',
     '50000000-0000-0000-0000-000000000003',
     TRUE, FALSE, 480.0, 506.0, TRUE,
     '10000000-0000-0000-0000-000000000004',
     'verified',
     'Bobby verified: BiXBiT on S21 EXP Hydro achieves up to 506 TH/s. '
     'Typical operation ~470-490 TH/s.'),
    -- Auradine native on AH3880 (the only supported firmware)
    ('60000000-0000-0000-0000-000000000005',
     '50000000-0000-0000-0000-000000000002',
     TRUE, TRUE, 300.0, 600.0, TRUE,
     '10000000-0000-0000-0000-000000000004',
     'verified',
     'Auradine native firmware is the ONLY firmware for AH3880. '
     'Eco: 300 TH/s, Turbo: 600 TH/s. Bobby verified both modes.'),
    -- Stock Bitmain on S19j Pro
    ('60000000-0000-0000-0000-000000000003',
     '50000000-0000-0000-0000-000000000001',
     TRUE, TRUE, 104.0, 104.0, FALSE,
     '10000000-0000-0000-0000-000000000001',
     'verified',
     'Stock firmware, stock performance: 104 TH/s.'),
    -- Stock Bitmain on S21 EXP Hydro
    ('60000000-0000-0000-0000-000000000004',
     '50000000-0000-0000-0000-000000000003',
     TRUE, TRUE, 430.0, 430.0, FALSE,
     '10000000-0000-0000-0000-000000000001',
     'verified',
     'Stock firmware on S21 EXP Hydro: 430 TH/s.'),
    -- Stock Bitmain on S21 Immersion
    ('60000000-0000-0000-0000-000000000004',
     '50000000-0000-0000-0000-000000000004',
     TRUE, TRUE, 208.0, 360.0, FALSE,
     '10000000-0000-0000-0000-000000000001',
     'verified',
     'Stock firmware on S21 Immersion: 208 TH/s. Max with tuning: 360 TH/s.');

-- ---------------------------------------------------------------------------
-- SEED: AUTOTUNING PROFILES (Bobby's fleet operational modes)
-- ---------------------------------------------------------------------------
INSERT INTO firmware.firmware_autotuning_profiles (firmware_id, miner_model_id,
    profile_name, operational_mode, target_hashrate_th, measured_hashrate_th,
    verified_by_bobby, verification_date, primary_source_id, confidence, notes)
VALUES
    -- S19j Pro: BiXBiT Eco
    ('60000000-0000-0000-0000-000000000001',
     '50000000-0000-0000-0000-000000000001',
     'BiXBiT Eco', 'eco', 120.0, 118.0, TRUE, '2024-01-01',
     '10000000-0000-0000-0000-000000000004', 'verified',
     'S19j Pro BiXBiT eco mode: ~118-120 TH/s at reduced power.'),
    -- S19j Pro: BiXBiT Turbo/Max
    ('60000000-0000-0000-0000-000000000001',
     '50000000-0000-0000-0000-000000000001',
     'BiXBiT Max', 'turbo', 160.0, 155.0, TRUE, '2024-01-01',
     '10000000-0000-0000-0000-000000000004', 'verified',
     'S19j Pro BiXBiT max: up to 160 TH/s observed at low coolant temps.'),
    -- AH3880: Eco
    ('60000000-0000-0000-0000-000000000005',
     '50000000-0000-0000-0000-000000000002',
     'Auradine Eco', 'eco', 300.0, 300.0, TRUE, '2024-01-01',
     '10000000-0000-0000-0000-000000000004', 'verified',
     'AH3880 eco mode: 300 TH/s across 2 boards.'),
    -- AH3880: Turbo
    ('60000000-0000-0000-0000-000000000005',
     '50000000-0000-0000-0000-000000000002',
     'Auradine Turbo', 'turbo', 600.0, 590.0, TRUE, '2024-01-01',
     '10000000-0000-0000-0000-000000000004', 'verified',
     'AH3880 turbo mode: 600 TH/s spec. Bobby observes ~580-600 TH/s in practice.'),
    -- S21 EXP Hydro: BiXBiT Max
    ('60000000-0000-0000-0000-000000000002',
     '50000000-0000-0000-0000-000000000003',
     'BiXBiT S21 Max', 'turbo', 506.0, 490.0, TRUE, '2024-06-01',
     '10000000-0000-0000-0000-000000000004', 'verified',
     'S21 EXP Hydro BiXBiT max: up to 506 TH/s. Typical ~470-490 TH/s.'),
    -- S21 EXP Hydro: Stock
    ('60000000-0000-0000-0000-000000000004',
     '50000000-0000-0000-0000-000000000003',
     'S21 EXP Stock', 'normal', 430.0, 430.0, FALSE, NULL,
     '10000000-0000-0000-0000-000000000001', 'verified',
     'S21 EXP Hydro stock: 430 TH/s.'),
    -- S21 Immersion: Stock
    ('60000000-0000-0000-0000-000000000004',
     '50000000-0000-0000-0000-000000000004',
     'S21 Imm Stock', 'normal', 208.0, 208.0, FALSE, NULL,
     '10000000-0000-0000-0000-000000000001', 'verified',
     'S21 Immersion stock: 208 TH/s.'),
    -- S21 Immersion: Max tuned
    ('60000000-0000-0000-0000-000000000004',
     '50000000-0000-0000-0000-000000000004',
     'S21 Imm Max Tuned', 'turbo', 360.0, NULL, FALSE, NULL,
     '10000000-0000-0000-0000-000000000001', 'medium',
     'S21 Immersion max achievable with tuning: 360 TH/s (not Bobby-verified yet).');

-- ---------------------------------------------------------------------------
-- SEED: FACILITY (Bobby's current facility)
-- ---------------------------------------------------------------------------
INSERT INTO facility.facilities (id, facility_name, facility_type,
    city, state_province, country,
    primary_cooling_type, is_bobby_facility, fleet_size,
    primary_source_id, notes)
VALUES
    ('70000000-0000-0000-0000-000000000001',
     'BiXBiT USA Fort Worth',
     'colocation',
     'Fort Worth', 'TX', 'US',
     'hydro',
     TRUE,
     58,
     '10000000-0000-0000-0000-000000000004',
     'Bobby''s primary facility. 58 liquid-cooled miners (mix of immersion and hydro). '
     'Operated by BiXBiT USA. Anticipated migration to UGREEN NAS environment July 2026.');

-- ---------------------------------------------------------------------------
-- SEED: OPERATIONAL THRESHOLDS (Key limits for Bobby's fleet)
-- ---------------------------------------------------------------------------
INSERT INTO ops.operational_thresholds (miner_model_id, cooling_type, operational_mode,
    threshold_name, chip_temp_warning_c, chip_temp_critical_c, chip_temp_shutdown_c,
    hashrate_low_warning_pct, hashrate_low_critical_pct, power_high_warning_w,
    coolant_temp_warning_c, coolant_temp_critical_c,
    verified_by_bobby, primary_source_id, confidence, notes)
VALUES
    -- S19j Pro Immersion
    ('50000000-0000-0000-0000-000000000001', 'immersion', NULL,
     'S19j Pro Immersion Thresholds',
     75, 85, 95,
     90.0, 75.0, 6000.0,
     35, 45,
     TRUE, '10000000-0000-0000-0000-000000000004', 'verified',
     'Bobby-verified thresholds for S19j Pro in immersion cooling with BiXBiT.'),
    -- AH3880 Hydro
    ('50000000-0000-0000-0000-000000000002', 'hydro', NULL,
     'AH3880 Hydro Thresholds',
     70, 80, 90,
     90.0, 75.0, 6500.0,
     30, 40,
     TRUE, '10000000-0000-0000-0000-000000000004', 'verified',
     'Bobby-verified thresholds for AH3880 in hydro cooling.'),
    -- S21 EXP Hydro
    ('50000000-0000-0000-0000-000000000003', 'hydro', NULL,
     'S21 EXP Hydro Thresholds',
     75, 85, 95,
     90.0, 75.0, 8500.0,
     32, 42,
     TRUE, '10000000-0000-0000-0000-000000000004', 'verified',
     'Bobby-verified thresholds for S21 EXP Hydro with BiXBiT firmware.'),
    -- S21 Immersion
    ('50000000-0000-0000-0000-000000000004', 'immersion', NULL,
     'S21 Immersion Thresholds',
     75, 85, 95,
     90.0, 75.0, 7000.0,
     35, 45,
     FALSE, '10000000-0000-0000-0000-000000000001', 'medium',
     'Manufacturer-based thresholds for S21 Immersion. Not yet Bobby-verified.');

-- ---------------------------------------------------------------------------
-- SEED: MINING POOLS (Key pools Bobby would use)
-- ---------------------------------------------------------------------------
INSERT INTO pool.mining_pools (id, pool_name, fee_model, fee_pct, supports_stratum_v1,
    supports_stratum_v2, supports_ssl, minimum_payout_btc, is_active,
    primary_source_id, confidence, notes)
VALUES
    ('80000000-0000-0000-0000-000000000001',
     'Foundry USA Pool',
     'fpps',
     0.0,             -- Foundry charges 0% but earns from TX fees FPPS share
     TRUE, FALSE, TRUE, 0.001,
     TRUE,
     '10000000-0000-0000-0000-000000000009',
     'high',
     'Largest US-based pool. FPPS model. 0% fee but TX fee structure.'),
    ('80000000-0000-0000-0000-000000000002',
     'AntPool',
     'pps_plus',
     0.0150,
     TRUE, FALSE, TRUE, 0.001,
     TRUE,
     '10000000-0000-0000-0000-000000000001',
     'high',
     'Bitmain-operated pool. 1.5% PPS+.'),
    ('80000000-0000-0000-0000-000000000003',
     'Braiins Pool',
     'pps_plus',
     0.0,
     TRUE, TRUE, TRUE, 0.0001,
     TRUE,
     '10000000-0000-0000-0000-000000000005',
     'high',
     'Formerly Slush Pool. 0% fee for Braiins OS users. Supports Stratum V2.'),
    ('80000000-0000-0000-0000-000000000004',
     'Ocean.xyz',
     'ocean',
     0.02,
     TRUE, FALSE, TRUE, 0.001,
     TRUE,
     '10000000-0000-0000-0000-000000000009',
     'high',
     'Ocean (formerly OCEAN) — full block reward transparency, no custodial payout.'),
    ('80000000-0000-0000-0000-000000000005',
     'Luxor Pool',
     'fpps',
     0.005,
     TRUE, FALSE, TRUE, 0.001,
     TRUE,
     '10000000-0000-0000-0000-000000000009',
     'high',
     'Luxor USA-based pool. 0.5% FPPS. Also offers hashrate marketplace (hashrate.com).');

-- ---------------------------------------------------------------------------
-- SEED: DATA INTEGRITY CONSTRAINT NOTES
-- (Stored as a war story for reference)
-- ---------------------------------------------------------------------------
INSERT INTO market.war_stories (title, narrative, is_bobby_story,
    tagged_model_ids, lesson_learned, preventable, prevention_method,
    primary_source_id, confidence)
VALUES
    ('AH3880 Board Count Rule — Design Constraint',
     'The Auradine Teraflux AH3880 is a hydro-native miner designed with EXACTLY 2 hashboards. '
     'Unlike Bitmain S-series miners which typically use 3 boards, the AH3880 architecture '
     'uses 2 high-capacity boards. Any repair record, inventory scan, or telemetry data '
     'claiming 3 boards in an AH3880 is definitionally an error — either a data entry '
     'mistake, a mislabeled unit, or a mislabeled model. '
     'The Mining Guardian application should treat miner_model_id=AH3880 with board_count≠2 '
     'as an immediate data quality alert requiring human review.',
     TRUE,
     ARRAY['50000000-0000-0000-0000-000000000002'::UUID],
     'AH3880 = 2 boards. Always. Any deviation is a data error. '
     'Enforce this constraint at ingestion time in application code.',
     TRUE,
     'Validate board_count=2 for all AH3880 records during ingestion. '
     'Flag and quarantine records with wrong board count for manual review.',
     '10000000-0000-0000-0000-000000000004',
     'verified');

-- =============================================================================
-- SOFT DELETES — deleted_at column on all tables
-- V2 Prompt requirement: preserve history, never hard-delete
-- Query convention: WHERE deleted_at IS NULL for active records
-- =============================================================================

ALTER TABLE knowledge.sources ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE knowledge.contributors ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE knowledge.citations ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE knowledge.data_conflicts ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE knowledge.freshness_log ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE hardware.manufacturers ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE hardware.chips ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE hardware.psu_models ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE hardware.control_boards ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE hardware.hashboards ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE hardware.miner_models ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE hardware.model_aliases ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE hardware.model_spec_history ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE hardware.psu_compatibility ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE hardware.cooling_compatibility ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE firmware.firmware_releases ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE firmware.firmware_compatibility ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE firmware.firmware_api_capabilities ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE firmware.firmware_telemetry_fields ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE firmware.firmware_bugs ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE firmware.firmware_changelog ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE firmware.firmware_autotuning_profiles ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE ops.failure_patterns ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE ops.failure_symptoms ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE ops.symptom_pattern_map ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE ops.operational_thresholds ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE ops.environmental_correlations ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE ops.operational_profiles ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE ops.alert_rules ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE ops.miner_error_codes ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE market.user_reviews ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE market.pricing_history ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE market.manufacturer_reputation ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE market.forum_posts ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE market.teardown_reports ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE market.war_stories ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE market.market_availability ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE repair.parts ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE repair.part_suppliers ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE repair.part_availability ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE repair.repair_procedures ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE repair.repair_steps ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE repair.repair_shops ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE repair.repair_records ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE repair.repair_statistics ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE repair.shop_reviews ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE pool.mining_pools ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE pool.pool_endpoints ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE pool.stratum_configurations ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE pool.pool_reliability_history ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE pool.pool_incidents ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE pool.bitcoin_network_snapshots ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE pool.stratum_error_codes ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE facility.cooling_solutions ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE facility.power_distribution_units ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE facility.facilities ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE facility.hvac_patterns ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE facility.rack_positions ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE regulatory.frameworks ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE regulatory.tax_treatment ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE regulatory.import_export_rules ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE regulatory.insurance_requirements ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE regulatory.environmental_regs ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

-- Partial indexes: only index active (non-deleted) rows for common queries
-- These speed up WHERE deleted_at IS NULL without bloating the index with dead rows
CREATE INDEX IF NOT EXISTS idx_hardware_miner_models_active ON hardware.miner_models(id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_hardware_model_aliases_active ON hardware.model_aliases(id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_ops_failure_patterns_active ON ops.failure_patterns(id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_ops_operational_thresholds_active ON ops.operational_thresholds(id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_firmware_firmware_releases_active ON firmware.firmware_releases(id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_repair_repair_records_active ON repair.repair_records(id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_repair_repair_shops_active ON repair.repair_shops(id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_market_pricing_history_active ON market.pricing_history(id) WHERE deleted_at IS NULL;

-- End of soft delete additions
