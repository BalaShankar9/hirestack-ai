-- PR m3-pr10: per-consumer dedup table for Redis Streams consumers.
--
-- Each consumer (e.g. "billing_usage") records every event_id it has
-- successfully processed. PK on (consumer, event_id) means a second
-- INSERT for the same pair raises a unique-violation; the consumer
-- treats that as "already handled, skip + ACK" → at-least-once delivery
-- becomes effectively-once at the handler boundary.
--
-- Cheap to write (UUID + short string), cheap to query (PK lookup).
-- Retention: prune via scheduler later (PR-13+); for now, unbounded.

BEGIN;

CREATE TABLE IF NOT EXISTS public.consumed_events (
    consumer    text        NOT NULL,
    event_id    uuid        NOT NULL,
    consumed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer, event_id)
);

CREATE INDEX IF NOT EXISTS consumed_events_consumed_at_idx
    ON public.consumed_events (consumed_at);

ALTER TABLE public.consumed_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS consumed_events_service_role_all ON public.consumed_events;
CREATE POLICY consumed_events_service_role_all
    ON public.consumed_events
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

COMMIT;
