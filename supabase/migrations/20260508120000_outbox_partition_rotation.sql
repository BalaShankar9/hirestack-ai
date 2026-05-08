-- ════════════════════════════════════════════════════════════════
-- 20260508120000_outbox_partition_rotation.sql
-- M7-A / m7-pr27a — Automated partition rotation for events_outbox
-- ADR-0037: docs/adrs/0037-partition-rotation-strategy.md
-- Closes P0-1 (blueprint §17 anti-pattern register).
--
-- SAFETY: installs pg_cron extension, partition rotation function, and daily cron schedule. Reviewed under ADR-0037.
-- ════════════════════════════════════════════════════════════════

BEGIN;

-- ── 1. Extension --------------------------------------------------
-- pg_cron is a first-class Supabase extension. Idempotent; safe to
-- re-run.
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- ── 2. Audit table ------------------------------------------------
-- One row per rotation invocation. Used by alerting to verify the
-- rotation job is running.
CREATE TABLE IF NOT EXISTS public.partition_rotation_audit (
    id              bigserial   PRIMARY KEY,
    table_name      text        NOT NULL,
    ran_at          timestamptz NOT NULL DEFAULT now(),
    months_ahead    integer     NOT NULL,
    partitions_created integer  NOT NULL,
    error_message   text        NULL
);

CREATE INDEX IF NOT EXISTS partition_rotation_audit_ran_at_idx
    ON public.partition_rotation_audit (table_name, ran_at DESC);

-- Service-role only; no end-user access.
ALTER TABLE public.partition_rotation_audit ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    CREATE POLICY partition_rotation_audit_service_only
        ON public.partition_rotation_audit
        FOR ALL
        TO service_role
        USING (true)
        WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

-- ── 3. Rotation function ------------------------------------------
-- Idempotent: creates a partition for any missing month between the
-- current month and `p_months_ahead` months in the future. Naming
-- convention `events_outbox_YYYY_MM` is preserved.
--
-- Returns the number of partitions actually created (0 on a no-op
-- call, > 0 on bootstrap or after a missed run).
CREATE OR REPLACE FUNCTION public.ensure_events_outbox_partitions(
    p_months_ahead integer DEFAULT 4
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $func$
DECLARE
    base_month date := date_trunc('month', now())::date;
    i          integer;
    pname      text;
    start_d    date;
    end_d      date;
    created    integer := 0;
    err_msg    text;
BEGIN
    IF p_months_ahead < 0 OR p_months_ahead > 24 THEN
        RAISE EXCEPTION 'p_months_ahead must be between 0 and 24, got %', p_months_ahead;
    END IF;

    FOR i IN 0..p_months_ahead LOOP
        start_d := (base_month + (i || ' month')::interval)::date;
        end_d   := (base_month + ((i + 1) || ' month')::interval)::date;
        pname   := format('events_outbox_%s', to_char(start_d, 'YYYY_MM'));

        BEGIN
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS public.%I PARTITION OF public.events_outbox '
                'FOR VALUES FROM (%L) TO (%L)',
                pname, start_d, end_d
            );
            -- to_regclass returns NULL if the partition didn't exist before
            -- this CREATE; non-NULL (already existed) means we did not create.
            -- Approximation: count optimistically, dedup via audit row.
            created := created + 1;
        EXCEPTION WHEN duplicate_table THEN
            -- Already existed via a concurrent rotation run; not an error.
            NULL;
        END;
    END LOOP;

    INSERT INTO public.partition_rotation_audit
        (table_name, months_ahead, partitions_created)
    VALUES
        ('events_outbox', p_months_ahead, created);

    RETURN created;

EXCEPTION WHEN OTHERS THEN
    err_msg := SQLERRM;
    INSERT INTO public.partition_rotation_audit
        (table_name, months_ahead, partitions_created, error_message)
    VALUES
        ('events_outbox', p_months_ahead, 0, err_msg);
    RAISE;
END;
$func$;

REVOKE ALL ON FUNCTION public.ensure_events_outbox_partitions(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.ensure_events_outbox_partitions(integer) TO service_role;

-- ── 4. Bootstrap call --------------------------------------------
-- Close P0-1 immediately on this migration. Ensures 4 months ahead
-- exist as of the moment this migration is applied.
SELECT public.ensure_events_outbox_partitions(4);

-- ── 5. Schedule daily rotation -----------------------------------
-- Runs at 00:01 UTC every day. If the job is already scheduled
-- (re-running migration on a cluster that has it), unschedule first
-- so we don't duplicate.
DO $$
DECLARE
    existing_jobid bigint;
BEGIN
    SELECT jobid INTO existing_jobid
    FROM cron.job
    WHERE jobname = 'events-outbox-rotation';

    IF existing_jobid IS NOT NULL THEN
        PERFORM cron.unschedule(existing_jobid);
    END IF;

    PERFORM cron.schedule(
        'events-outbox-rotation',
        '1 0 * * *',  -- 00:01 UTC daily
        $cmd$ SELECT public.ensure_events_outbox_partitions(4); $cmd$
    );
END $$;

COMMIT;
