-- intelligence-catalog/seed-data/sample_rows_for_api_coverage_2026-04-27.sql
-- ---------------------------------------------------------------------------
-- PR #23 — minimum-viable seed rows so every catalog API query type returns
-- ≥1 row (cutover gate row 5 / ROADMAP §Wed PM).
--
-- These are intentionally small, well-attributed sample rows. They get a
-- stable provenance handle (`metadata->>'seed_pr' = 'pr23'`) so post-Mac-
-- Mini cleanup can target them precisely if real data overrides them.
--
-- All inserts are idempotent via WHERE NOT EXISTS guards on natural keys.
-- Re-running this file is safe.
-- ---------------------------------------------------------------------------

-- Reusable references used across multiple inserts ---------------------------
-- Use bobby_operational (tier2_operational) as the source for everything in
-- this file so it shows up next to PR #22 feedback-loop rows under one
-- audit handle.
DO $$
DECLARE
    v_source_id     uuid := 'a0000000-0000-0000-0000-00000000000f';
    v_model_s19     uuid;
    v_model_m50     uuid;
    v_firmware_id   uuid;
BEGIN
    SELECT id INTO v_model_s19
    FROM hardware.miner_models
    WHERE canonical_name ILIKE '%S19j Pro%'
    ORDER BY length(canonical_name) ASC
    LIMIT 1;

    SELECT id INTO v_model_m50
    FROM hardware.miner_models
    WHERE canonical_name ILIKE '%M50%'
    ORDER BY length(canonical_name) ASC
    LIMIT 1;

    SELECT id INTO v_firmware_id FROM firmware.firmware_releases LIMIT 1;

    -- ─────────────────────────────────────────────────────────────────────
    -- hardware.psu_models
    -- ─────────────────────────────────────────────────────────────────────
    INSERT INTO hardware.psu_models (model_name, manufacturer_id, metadata)
    SELECT 'APW12 (Bitmain)', NULL, jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM hardware.psu_models WHERE model_name='APW12 (Bitmain)');
    INSERT INTO hardware.psu_models (model_name, manufacturer_id, metadata)
    SELECT 'APW171 (Bitmain)', NULL, jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM hardware.psu_models WHERE model_name='APW171 (Bitmain)');

    -- ─────────────────────────────────────────────────────────────────────
    -- ops.failure_patterns
    -- ─────────────────────────────────────────────────────────────────────
    INSERT INTO ops.failure_patterns (
        pattern_name, pattern_code, description,
        failure_category, severity, is_model_specific,
        root_cause, root_cause_category,
        primary_source_id, confidence, metadata
    )
    SELECT 'High board temperature', 'SEED_FP_THERMAL', 'Hashboard temperature exceeds safe envelope (>85C inlet).',
           'thermal', 'high', false,
           'Insufficient airflow or ambient temperature too high', 'thermal',
           v_source_id, 'high', jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM ops.failure_patterns WHERE pattern_code='SEED_FP_THERMAL');

    INSERT INTO ops.failure_patterns (
        pattern_name, pattern_code, description,
        failure_category, severity, is_model_specific,
        root_cause, root_cause_category,
        primary_source_id, confidence, metadata
    )
    SELECT 'Underperformance vs baseline', 'SEED_FP_UNDERPERF', 'Sustained hashrate ≥10% below model baseline.',
           'performance', 'medium', false,
           'Asic degradation or thermal throttling', 'performance',
           v_source_id, 'medium', jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM ops.failure_patterns WHERE pattern_code='SEED_FP_UNDERPERF');

    -- ─────────────────────────────────────────────────────────────────────
    -- ops.failure_symptoms
    -- ─────────────────────────────────────────────────────────────────────
    INSERT INTO ops.failure_symptoms (symptom_name, description, detection_method, metadata)
    SELECT 'OVERHEAT', 'Inlet or outlet temp exceeds safe range', 'temp sensor reading', jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM ops.failure_symptoms WHERE symptom_name='OVERHEAT');
    INSERT INTO ops.failure_symptoms (symptom_name, description, detection_method, metadata)
    SELECT 'OFFLINE', 'Miner unreachable on management network', 'ICMP / API ping', jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM ops.failure_symptoms WHERE symptom_name='OFFLINE');
    INSERT INTO ops.failure_symptoms (symptom_name, description, detection_method, metadata)
    SELECT 'LOW_HASHRATE', 'Hashrate below baseline by >10% sustained', 'rolling-average comparison', jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM ops.failure_symptoms WHERE symptom_name='LOW_HASHRATE');

    -- ─────────────────────────────────────────────────────────────────────
    -- ops.miner_error_codes
    -- ─────────────────────────────────────────────────────────────────────
    INSERT INTO ops.miner_error_codes (error_code, error_source, error_category, metadata)
    SELECT 'TEMP_OVER', 'antminer', 'thermal', jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM ops.miner_error_codes WHERE error_code='TEMP_OVER' AND error_source='antminer');
    INSERT INTO ops.miner_error_codes (error_code, error_source, error_category, metadata)
    SELECT 'CHAIN_LOST', 'antminer', 'hardware', jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM ops.miner_error_codes WHERE error_code='CHAIN_LOST' AND error_source='antminer');
    INSERT INTO ops.miner_error_codes (error_code, error_source, error_category, metadata)
    SELECT 'HW_ERR_HIGH', 'whatsminer', 'hardware', jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM ops.miner_error_codes WHERE error_code='HW_ERR_HIGH' AND error_source='whatsminer');

    -- ─────────────────────────────────────────────────────────────────────
    -- hardware.model_known_issues
    -- ─────────────────────────────────────────────────────────────────────
    IF v_model_s19 IS NOT NULL THEN
        INSERT INTO hardware.model_known_issues (
            miner_model_id, issue_type, commonality, category,
            title, description,
            primary_source_id, confidence, metadata
        )
        SELECT v_model_s19, 'reliability', 'occasional', 'reliability',
               'PSU fan bearing wear', 'After ~18 months of continuous operation the APW12 fan can begin to fail. Symptom: PSU temp rising, fan speed maxed.',
               v_source_id, 'high', jsonb_build_object('seed_pr', 'pr23')
        WHERE NOT EXISTS (
            SELECT 1 FROM hardware.model_known_issues
            WHERE miner_model_id=v_model_s19 AND title='PSU fan bearing wear'
        );
    END IF;

    -- ─────────────────────────────────────────────────────────────────────
    -- firmware.firmware_bugs
    -- ─────────────────────────────────────────────────────────────────────
    IF v_firmware_id IS NOT NULL THEN
        INSERT INTO firmware.firmware_bugs (firmware_id, bug_title, bug_description, bug_category, metadata)
        SELECT v_firmware_id, 'Hashrate ramp-up regression', 'After firmware boot, hashrate takes ~30 min longer than prior firmware to reach baseline.', 'performance', jsonb_build_object('seed_pr', 'pr23')
        WHERE NOT EXISTS (
            SELECT 1 FROM firmware.firmware_bugs
            WHERE firmware_id=v_firmware_id AND bug_title='Hashrate ramp-up regression'
        );
    END IF;

    -- ─────────────────────────────────────────────────────────────────────
    -- ops.miner_baseline_reference
    -- ─────────────────────────────────────────────────────────────────────
    IF v_model_s19 IS NOT NULL THEN
        INSERT INTO ops.miner_baseline_reference (miner_model_id, metadata)
        SELECT v_model_s19, jsonb_build_object('seed_pr', 'pr23',
            'baseline_hashrate_th', 100, 'baseline_power_w', 3250)
        WHERE NOT EXISTS (
            SELECT 1 FROM ops.miner_baseline_reference WHERE miner_model_id=v_model_s19
        );
    END IF;

    -- ─────────────────────────────────────────────────────────────────────
    -- ops.operational_profiles
    -- ─────────────────────────────────────────────────────────────────────
    IF v_model_s19 IS NOT NULL THEN
        INSERT INTO ops.operational_profiles (
            profile_name, miner_model_id, cooling_type, operational_mode,
            primary_source_id, metadata
        )
        SELECT 'S19j Pro · normal · air', v_model_s19, 'air', 'normal',
               v_source_id, jsonb_build_object('seed_pr', 'pr23')
        WHERE NOT EXISTS (
            SELECT 1 FROM ops.operational_profiles
            WHERE profile_name='S19j Pro · normal · air'
        );
    END IF;

    -- ─────────────────────────────────────────────────────────────────────
    -- ops.environmental_correlations
    -- ─────────────────────────────────────────────────────────────────────
    INSERT INTO ops.environmental_correlations (
        correlation_type, independent_var, dependent_var,
        primary_source_id, metadata
    )
    SELECT 'thermal_efficiency', 'inlet_temp_c', 'efficiency_j_per_th',
           v_source_id,
           jsonb_build_object('seed_pr', 'pr23',
                              'note', '+1C inlet ≈ +0.05 J/TH efficiency penalty')
    WHERE NOT EXISTS (
        SELECT 1 FROM ops.environmental_correlations
        WHERE correlation_type='thermal_efficiency'
          AND independent_var='inlet_temp_c'
          AND dependent_var='efficiency_j_per_th'
    );

    -- ─────────────────────────────────────────────────────────────────────
    -- repair.repair_procedures
    -- ─────────────────────────────────────────────────────────────────────
    INSERT INTO repair.repair_procedures (procedure_name, primary_source_id, metadata)
    SELECT 'Replace hashboard (3-board chassis)',
           v_source_id,
           jsonb_build_object('seed_pr', 'pr23',
                              'tools', ARRAY['phillips #2', 'thermal paste', 'antistatic mat'])
    WHERE NOT EXISTS (SELECT 1 FROM repair.repair_procedures WHERE procedure_name='Replace hashboard (3-board chassis)');
    INSERT INTO repair.repair_procedures (procedure_name, primary_source_id, metadata)
    SELECT 'Reseat hashboard data ribbon',
           v_source_id,
           jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM repair.repair_procedures WHERE procedure_name='Reseat hashboard data ribbon');

    -- ─────────────────────────────────────────────────────────────────────
    -- repair.diagnostic_tools
    -- ─────────────────────────────────────────────────────────────────────
    INSERT INTO repair.diagnostic_tools (tool_name, tool_type, metadata)
    SELECT 'IR thermal camera', 'thermal', jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM repair.diagnostic_tools WHERE tool_name='IR thermal camera');
    INSERT INTO repair.diagnostic_tools (tool_name, tool_type, metadata)
    SELECT 'Multimeter', 'electrical', jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM repair.diagnostic_tools WHERE tool_name='Multimeter');
    INSERT INTO repair.diagnostic_tools (tool_name, tool_type, metadata)
    SELECT 'PSU bench tester', 'electrical', jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM repair.diagnostic_tools WHERE tool_name='PSU bench tester');

    -- ─────────────────────────────────────────────────────────────────────
    -- repair.parts
    -- ─────────────────────────────────────────────────────────────────────
    INSERT INTO repair.parts (name, part_category, metadata)
    SELECT 'Hashboard fan 12025', 'fan', jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM repair.parts WHERE name='Hashboard fan 12025');
    INSERT INTO repair.parts (name, part_category, metadata)
    SELECT 'PSU APW12 replacement', 'psu', jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM repair.parts WHERE name='PSU APW12 replacement');
    INSERT INTO repair.parts (name, part_category, metadata)
    SELECT 'Thermal paste tube', 'consumable', jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM repair.parts WHERE name='Thermal paste tube');

    -- ─────────────────────────────────────────────────────────────────────
    -- facility.cooling_solutions
    -- ─────────────────────────────────────────────────────────────────────
    INSERT INTO facility.cooling_solutions (solution_name, cooling_type, primary_source_id, metadata)
    SELECT 'Air-cooled container · evaporative pad', 'air', v_source_id, jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM facility.cooling_solutions WHERE solution_name='Air-cooled container · evaporative pad');
    INSERT INTO facility.cooling_solutions (solution_name, cooling_type, primary_source_id, metadata)
    SELECT 'Hydro single-phase immersion', 'hydro', v_source_id, jsonb_build_object('seed_pr', 'pr23')
    WHERE NOT EXISTS (SELECT 1 FROM facility.cooling_solutions WHERE solution_name='Hydro single-phase immersion');

    -- ─────────────────────────────────────────────────────────────────────
    -- facility.container_environment_reference
    -- ─────────────────────────────────────────────────────────────────────
    INSERT INTO facility.container_environment_reference (container_model, metadata)
    SELECT '20ft air-cooled mining container', jsonb_build_object('seed_pr', 'pr23',
        'safe_inlet_max_c', 35, 'safe_humidity_max_pct', 80)
    WHERE NOT EXISTS (SELECT 1 FROM facility.container_environment_reference WHERE container_model='20ft air-cooled mining container');

END $$;
