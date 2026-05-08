-- ADR-0040 / m7-pr27c (P0-3): consumer-side dedup table for the
-- generation job queue (`hirestack:generation_jobs` Redis Stream).
--
-- Sister table to `consumed_events` (events bus), which keys on
-- `event_id uuid`. Here the key is `msg_id text` because Redis stream
-- IDs are `<ms>-<seq>`, not UUIDs. Each successful handler invocation
-- inserts (consumer, msg_id); a unique-violation on a redelivery means
-- "already processed, ACK + skip".
--
-- Retention: unbounded for now (matches consumed_events policy);
-- pruning sweeper planned in M7-D (Stage-A trailing).

BEGIN;

CREATE TABLE IF NOT EXISTS public.processed_queue_events (
    consumer     text        NOT NULL,
    msg_id       text        NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer, msg_id)
);

CREATE INDEX IF NOT EXISTS processed_queue_events_processed_at_idx
    ON public.processed_queue_events (processed_at);

ALTER TABLE public.processed_queue_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS processed_queue_events_service_role_all
    ON public.processed_queue_events;
CREATE POLICY processed_queue_events_service_role_all
    ON public.processed_queue_events
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

COMMIT;
