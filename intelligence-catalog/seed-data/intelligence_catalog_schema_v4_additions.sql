-- =============================================================================
-- MINING INTELLIGENCE CATALOG — V4 ADDITIONS
-- =============================================================================
-- Run AFTER intelligence_catalog_schema.sql, v2_additions.sql, v3_additions.sql
-- Included by deploy_schema.sql via \ir, after v3 and before staging_schema.sql.
-- =============================================================================
-- W10 (docs/strategy/04_MASTER_EXECUTION_PLAN.md §W10, AMENDMENTS §A09):
-- the dual_writer catalog-intake function propose_data_conflict() dedups on
-- the (conflict_table, conflict_row_id, conflict_field) triple while a
-- conflict is unresolved — so the W11 /intel handler can re-send the same
-- morning finding without piling up duplicate conflict rows.
--
-- propose_data_conflict() does that dedup with an in-function SELECT-then-
-- INSERT check, which is correct on its own. This index makes the same
-- contract DB-ENFORCED: it is a backstop, not the primary mechanism. With it,
-- a future caller that forgets the check (or two callers racing) still cannot
-- create a duplicate unresolved conflict. This mirrors the partial-unique-index
-- pattern already used in staging_schema.sql for the proposal tables.
--
-- Partial (WHERE is_resolved = FALSE) on purpose: once a conflict is resolved,
-- the same triple is allowed to recur — a later disagreement on the same
-- field is a new, legitimate conflict, not a duplicate of the settled one.
--
-- Idempotent (IF NOT EXISTS) — deploy_schema.sql runs on every install.
-- Verified safe against the live catalog DB 2026-05-14: zero pre-existing
-- duplicate unresolved triples, so the unique index builds cleanly.
-- =============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS idx_data_conflicts_unresolved_triple
    ON knowledge.data_conflicts (conflict_table, conflict_row_id, conflict_field)
    WHERE is_resolved = FALSE;

COMMENT ON INDEX knowledge.idx_data_conflicts_unresolved_triple IS
    'W10 — DB-enforced dedup backstop for dual_writer.propose_data_conflict(). '
    'One unresolved conflict per (conflict_table, conflict_row_id, '
    'conflict_field) triple. Partial: resolved conflicts may recur as new rows.';

-- =============================================================================
-- DONE — V4 additions applied
-- =============================================================================
SELECT 'V4 additions complete' AS status;
