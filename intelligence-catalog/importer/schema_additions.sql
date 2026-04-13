-- ═══════════════════════════════════════════════════════════════════════════════
-- Intelligence Catalog Importer — Schema Additions
-- Target: PostgreSQL 16 on ROBS-PC (mining-guardian-db)
-- Database: mining_guardian
-- ═══════════════════════════════════════════════════════════════════════════════

-- Track every import job
CREATE TABLE IF NOT EXISTS knowledge.import_jobs (
    import_id SERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    source_path TEXT NOT NULL,
    source_type TEXT NOT NULL,  -- 'file', 'folder', 'archive', 'email', 'bulk_drop'
    total_files INTEGER DEFAULT 0,
    processed_files INTEGER DEFAULT 0,
    skipped_files INTEGER DEFAULT 0,
    failed_files INTEGER DEFAULT 0,
    needs_review INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',  -- 'running', 'completed', 'failed', 'partial'
    notes TEXT,
    metadata JSONB DEFAULT '{}'
);

-- Track every individual file processed
CREATE TABLE IF NOT EXISTS knowledge.imported_files (
    file_id SERIAL PRIMARY KEY,
    import_id INTEGER NOT NULL REFERENCES knowledge.import_jobs(import_id),
    original_filename TEXT NOT NULL,
    original_path TEXT,
    file_size_bytes BIGINT,
    file_type TEXT,  -- 'log', 'csv', 'pdf', 'archive', 'text', 'unknown'
    file_hash TEXT,  -- SHA-256 hash for deduplication
    detected_brand TEXT,
    detected_model TEXT,
    detected_firmware TEXT,
    detected_serial TEXT,
    detected_mac TEXT,
    detection_confidence REAL,
    detection_evidence JSONB DEFAULT '[]',
    catalog_model_id TEXT,  -- UUID string from hardware.miner_models
    processing_status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'processed', 'skipped', 'failed', 'needs_review'
    processing_notes TEXT,
    parsed_data JSONB DEFAULT '{}',
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Diagnostic test results per file
CREATE TABLE IF NOT EXISTS ops.import_diagnostic_results (
    result_id SERIAL PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES knowledge.imported_files(file_id),
    test_id TEXT NOT NULL,
    test_name TEXT NOT NULL,
    category TEXT,  -- 'universal', 'brand_specific', 'model_specific'
    result TEXT NOT NULL,  -- 'PASS', 'WARN', 'FAIL', 'SKIP', 'ERROR'
    severity TEXT,  -- 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    evidence TEXT,
    diagnosis TEXT,
    recommended_action TEXT,
    confidence REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Cross-file patterns discovered
CREATE TABLE IF NOT EXISTS ops.import_patterns (
    pattern_id SERIAL PRIMARY KEY,
    pattern_type TEXT NOT NULL,  -- 'model_defect', 'firmware_regression', 'batch_issue', 'environmental'
    brand TEXT,
    model TEXT,
    fault_type TEXT,
    first_observed TIMESTAMPTZ,
    last_observed TIMESTAMPTZ,
    file_count INTEGER DEFAULT 0,
    miner_count INTEGER DEFAULT 0,
    description TEXT,
    recommended_action TEXT,
    confidence REAL,
    human_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_imported_files_import_id ON knowledge.imported_files(import_id);
CREATE INDEX IF NOT EXISTS idx_imported_files_hash ON knowledge.imported_files(file_hash);
CREATE INDEX IF NOT EXISTS idx_imported_files_brand_model ON knowledge.imported_files(detected_brand, detected_model);
CREATE INDEX IF NOT EXISTS idx_import_diag_file_id ON ops.import_diagnostic_results(file_id);
CREATE INDEX IF NOT EXISTS idx_import_patterns_brand_model ON ops.import_patterns(brand, model);
