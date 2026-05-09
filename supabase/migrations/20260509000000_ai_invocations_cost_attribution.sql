-- ═══════════════════════════════════════════════════════════════════════
--  ai_invocations cost attribution — P1-8 / m12-pr07 · 2026-05-09
--  ---------------------------------------------------------------------
--  Adds the `cost_cents` column to `public.ai_invocations` (the source
--  of truth per blueprint §12.2) and a per-tenant per-hour
--  materialized view `public.org_cost_hourly` for cheap dashboard
--  reads + per-org budget enforcement.
--
--  Refresh strategy: pg_cron runs `REFRESH MATERIALIZED VIEW
--  CONCURRENTLY public.org_cost_hourly` every 60s. Concurrent refresh
--  requires a UNIQUE index on the MV, which we provide on
--  `(tenant_id, hour)`.
--
--  Idempotent. Re-applying is safe.
-- ═══════════════════════════════════════════════════════════════════════

BEGIN;

-- ── 1. cost_cents column on the recorder table ────────────────────────
ALTER TABLE public.ai_invocations
    ADD COLUMN IF NOT EXISTS cost_cents INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN public.ai_invocations.cost_cents IS
    'Estimated USD cost in cents for this LLM call (input+output tokens × model rate). Source of truth for org cost attribution per blueprint §12.2.';

-- Partial index for the hot dashboard query: total cost by tenant in
-- the last N hours. Skips zero-cost rows (failures and breaker_open
-- events) to keep the index narrow.
CREATE INDEX IF NOT EXISTS idx_ai_invocations_tenant_cost_created
    ON public.ai_invocations (tenant_id, created_at DESC)
    INCLUDE (cost_cents)
    WHERE cost_cents > 0;

-- ── 2. Materialized view: per-(tenant, hour) cost roll-up ─────────────
-- We materialise instead of viewing live so dashboard queries do not
-- scan the full ai_invocations table. Refresh cadence = 60s via pg_cron.
DROP MATERIALIZED VIEW IF EXISTS public.org_cost_hourly;
CREATE MATERIALIZED VIEW public.org_cost_hourly AS
SELECT
    tenant_id,
    date_trunc('hour', created_at) AS hour,
    COUNT(*)::BIGINT               AS call_count,
    COALESCE(SUM(cost_cents), 0)::BIGINT  AS total_cost_cents,
    COALESCE(SUM(total_tokens), 0)::BIGINT AS total_tokens,
    COALESCE(SUM(prompt_tokens), 0)::BIGINT AS prompt_tokens,
    COALESCE(SUM(completion_tokens), 0)::BIGINT AS completion_tokens
FROM public.ai_invocations
WHERE tenant_id IS NOT NULL
GROUP BY tenant_id, date_trunc('hour', created_at);

-- UNIQUE index is REQUIRED for REFRESH MATERIALIZED VIEW CONCURRENTLY.
CREATE UNIQUE INDEX IF NOT EXISTS uq_org_cost_hourly_tenant_hour
    ON public.org_cost_hourly (tenant_id, hour);

-- Read pattern: "what did tenant X spend in the last 24h?" — index hour
-- DESC to support cheap LIMIT scans.
CREATE INDEX IF NOT EXISTS idx_org_cost_hourly_hour_desc
    ON public.org_cost_hourly (hour DESC);

COMMENT ON MATERIALIZED VIEW public.org_cost_hourly IS
    'P1-8: per-tenant per-hour cost roll-up of ai_invocations. Refreshed every 60s via pg_cron. Dashboards and per-org $ caps read here, not the base table.';

-- ── 3. Refresh function (single chokepoint) ───────────────────────────
CREATE OR REPLACE FUNCTION public.refresh_org_cost_hourly()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $func$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY public.org_cost_hourly;
EXCEPTION WHEN OTHERS THEN
    -- Concurrent refresh fails on the very first run (empty MV) and
    -- on any race with a competing refresh. Fall back to a non-
    -- concurrent refresh so the schedule self-heals on first invocation.
    REFRESH MATERIALIZED VIEW public.org_cost_hourly;
END;
$func$;

COMMENT ON FUNCTION public.refresh_org_cost_hourly() IS
    'P1-8: refresh org_cost_hourly MV. Concurrent first; falls back to blocking refresh on first run or refresh races.';

-- ── 4. Schedule the refresh via pg_cron (every 60s) ────────────────────
-- pg_cron is already installed by 20260508120000_outbox_partition_rotation.sql.
DO $$
DECLARE
    existing_jobid bigint;
BEGIN
    SELECT jobid INTO existing_jobid
    FROM cron.job
    WHERE jobname = 'org-cost-hourly-refresh';

    IF existing_jobid IS NOT NULL THEN
        PERFORM cron.unschedule(existing_jobid);
    END IF;

    -- '* * * * *' = every minute. pg_cron's minimum granularity.
    PERFORM cron.schedule(
        'org-cost-hourly-refresh',
        '* * * * *',
        $cmd$ SELECT public.refresh_org_cost_hourly(); $cmd$
    );
END $$;

-- ── 5. RLS on the MV ──────────────────────────────────────────────────
-- Materialized views inherit no RLS by default. We rely on application-
-- layer access control (cost service queries with service-role key);
-- the read service NEVER takes a tenant_id from untrusted input — it
-- reads it from the authenticated session.
GRANT SELECT ON public.org_cost_hourly TO service_role;

COMMIT;
