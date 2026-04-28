-- migrations/003_c5_notify_triggers.sql
-- D-14 PR 4a — C5 NOTIFY triggers (operational → catalog event-driven feedback)
--
-- Per D-14 sub-lock 3: every write to the three operational tables that feed
-- the C5 feedback loop must fire a Postgres NOTIFY so the feedback_loop_daemon
-- can react within ~100ms instead of waiting on a cron.
--
--   public.action_audit_log  → NOTIFY catalog_feedback
--   public.miner_restarts    → NOTIFY catalog_feedback
--   public.llm_analysis      → NOTIFY catalog_feedback
--
-- The daemon listens on channel `catalog_feedback`, debounces a burst of
-- notifications inside a short window (~100ms) and then invokes the
-- existing intelligence-catalog/db/feedback_loop.run_full_feedback_loop().
--
-- Design notes
-- ------------
-- 1. Idempotent: CREATE OR REPLACE on the function, DROP TRIGGER IF EXISTS
--    before each CREATE TRIGGER. Re-running this migration is safe.
-- 2. The payload is a tiny JSON blob — the daemon does not parse table-row
--    contents from it. We only need (table, op, id) so the daemon can log a
--    coherent debounce summary; the actual aggregation runs at SQL level
--    inside run_full_feedback_loop().
-- 3. Postgres NOTIFY payload limit is 8000 bytes; our payload is < 100 bytes,
--    so we never truncate. We deliberately do NOT include row data — that
--    would couple the catalog daemon to operational schemas.
-- 4. The function is SECURITY INVOKER (default) — it runs with the privileges
--    of whoever did the INSERT/UPDATE. pg_notify itself requires no special
--    grant.
-- 5. AFTER INSERT OR UPDATE only — DELETE on these audit tables is not
--    expected (operational tables are append-mostly). If a future cleanup job
--    deletes rows we do not want to re-aggregate against the catalog.
-- 6. PER ROW — feedback aggregations are keyed on row-level state. STATEMENT
--    triggers would lose visibility into multi-row INSERT batches.

BEGIN;

-- ──────────────────────────────────────────────────────────────────────
-- Notify function
-- ──────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.notify_catalog_feedback()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    payload TEXT;
BEGIN
    payload := json_build_object(
        'table', TG_TABLE_NAME,
        'op',    TG_OP,
        'id',    COALESCE(NEW.id, 0)
    )::text;

    PERFORM pg_notify('catalog_feedback', payload);
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.notify_catalog_feedback() IS
  'D-14 PR 4a — emits NOTIFY catalog_feedback on writes to the three C5 operational tables.';

-- ──────────────────────────────────────────────────────────────────────
-- Triggers on the three operational tables
-- ──────────────────────────────────────────────────────────────────────

-- action_audit_log
DROP TRIGGER IF EXISTS trg_notify_catalog_feedback_audit ON public.action_audit_log;
CREATE TRIGGER trg_notify_catalog_feedback_audit
    AFTER INSERT OR UPDATE ON public.action_audit_log
    FOR EACH ROW
    EXECUTE FUNCTION public.notify_catalog_feedback();

-- miner_restarts
DROP TRIGGER IF EXISTS trg_notify_catalog_feedback_restarts ON public.miner_restarts;
CREATE TRIGGER trg_notify_catalog_feedback_restarts
    AFTER INSERT OR UPDATE ON public.miner_restarts
    FOR EACH ROW
    EXECUTE FUNCTION public.notify_catalog_feedback();

-- llm_analysis
DROP TRIGGER IF EXISTS trg_notify_catalog_feedback_llm ON public.llm_analysis;
CREATE TRIGGER trg_notify_catalog_feedback_llm
    AFTER INSERT OR UPDATE ON public.llm_analysis
    FOR EACH ROW
    EXECUTE FUNCTION public.notify_catalog_feedback();

COMMIT;
