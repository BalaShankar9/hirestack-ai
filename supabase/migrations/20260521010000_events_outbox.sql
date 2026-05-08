-- ════════════════════════════════════════════════════════════════
-- 20260521010000_events_outbox.sql
-- M3 PR-8 — Transactional outbox for the event bus.
--
-- Captures domain events in the same transaction as the business
-- write that produced them. A separate relay process (PR-9) drains
-- the table and publishes to Redis Streams.
--
-- Partitioned by RANGE on occurred_at (monthly) so we can cheaply
-- drop old partitions once events are fully published and retained
-- past the audit window.
--
-- Idempotent: every CREATE uses IF NOT EXISTS; partition creation
-- is wrapped in DO blocks that swallow duplicate_table.
-- ════════════════════════════════════════════════════════════════

BEGIN;

-- Parent partitioned table -------------------------------------------------
CREATE TABLE IF NOT EXISTS public.events_outbox (
    event_id          uuid        NOT NULL DEFAULT gen_random_uuid(),
    event_type        text        NOT NULL,
    event_version     integer     NOT NULL,
    org_id            uuid        NOT NULL,
    occurred_at       timestamptz NOT NULL DEFAULT now(),
    idempotency_key   text        NULL,
    payload           jsonb       NOT NULL,
    -- Relay bookkeeping (written by PR-9; declared here so the schema
    -- is stable from day one and the relay can land additively).
    published_at      timestamptz NULL,
    publish_attempts  integer     NOT NULL DEFAULT 0,
    last_publish_error text       NULL,
    PRIMARY KEY (event_id, occurred_at)
) PARTITION BY RANGE (occurred_at);

-- Per-tenant idempotency: same (org, key) MUST collapse to one row when key
-- is provided. Null idempotency_key means "fire and forget" — multiple rows
-- allowed.
CREATE UNIQUE INDEX IF NOT EXISTS events_outbox_org_idem_uniq
    ON public.events_outbox (org_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- Drain index for the relay: unpublished rows in occurred order.
CREATE INDEX IF NOT EXISTS events_outbox_unpublished_idx
    ON public.events_outbox (occurred_at)
    WHERE published_at IS NULL;

-- Type/lookup index for filtered relays / debugging.
CREATE INDEX IF NOT EXISTS events_outbox_type_idx
    ON public.events_outbox (event_type, occurred_at);

-- Per-org analytics index.
CREATE INDEX IF NOT EXISTS events_outbox_org_idx
    ON public.events_outbox (org_id, occurred_at);

-- Initial partitions: current month and the next two. Operators (or a
-- maintenance job) must roll new partitions forward each month.
DO $$
DECLARE
    base date := date_trunc('month', now())::date;
    i    int;
    pname text;
    start_d date;
    end_d   date;
BEGIN
    FOR i IN 0..2 LOOP
        start_d := (base + (i || ' month')::interval)::date;
        end_d   := (base + ((i + 1) || ' month')::interval)::date;
        pname   := format('events_outbox_%s', to_char(start_d, 'YYYY_MM'));
        BEGIN
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS public.%I PARTITION OF public.events_outbox '
                'FOR VALUES FROM (%L) TO (%L)',
                pname, start_d, end_d
            );
        EXCEPTION WHEN duplicate_table THEN
            -- already exists, safe to ignore
            NULL;
        END;
    END LOOP;
END $$;

-- RLS: outbox is service-role only. App writers go through the service
-- client; no end-user policy needed.
ALTER TABLE public.events_outbox ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    CREATE POLICY events_outbox_service_only
        ON public.events_outbox
        FOR ALL
        TO service_role
        USING (true)
        WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

COMMIT;
