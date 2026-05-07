-- PR m3-pr9: Outbox relay support — claim RPC + DLQ marker.
--
-- Adds the SQL surface the relay worker needs:
--   * dead_lettered_at column on events_outbox (DLQ marker; simpler than
--     a side table — events_outbox is partitioned, so the row stays in
--     situ but is filtered out of future drains).
--   * outbox_claim_batch(p_batch_size) — atomic claim using
--     FOR UPDATE SKIP LOCKED so multiple relay replicas can drain in
--     parallel without double-publishing. Increments publish_attempts
--     in the same statement so retries are visible even if XADD never
--     returns.
--   * outbox_mark_published(p_event_id, p_occurred_at) and
--     outbox_record_failure(p_event_id, p_occurred_at, p_error,
--     p_max_attempts) helpers so the relay does not embed
--     publish_attempts arithmetic in Python.

BEGIN;

ALTER TABLE public.events_outbox
    ADD COLUMN IF NOT EXISTS dead_lettered_at timestamptz NULL;

CREATE INDEX IF NOT EXISTS events_outbox_dlq_idx
    ON public.events_outbox (dead_lettered_at)
    WHERE dead_lettered_at IS NOT NULL;

-- Atomic claim. Bumps publish_attempts so an in-flight crash still
-- leaves a paper trail. Caller MUST call outbox_mark_published on
-- success or outbox_record_failure on permanent failure.
CREATE OR REPLACE FUNCTION public.outbox_claim_batch(p_batch_size integer)
RETURNS SETOF public.events_outbox
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH claimed AS (
        SELECT event_id, occurred_at
        FROM public.events_outbox
        WHERE published_at IS NULL
          AND dead_lettered_at IS NULL
        ORDER BY occurred_at
        FOR UPDATE SKIP LOCKED
        LIMIT GREATEST(p_batch_size, 1)
    )
    UPDATE public.events_outbox eo
       SET publish_attempts = eo.publish_attempts + 1
      FROM claimed
     WHERE eo.event_id = claimed.event_id
       AND eo.occurred_at = claimed.occurred_at
    RETURNING eo.*;
END;
$$;

CREATE OR REPLACE FUNCTION public.outbox_mark_published(
    p_event_id uuid,
    p_occurred_at timestamptz
)
RETURNS void
LANGUAGE sql
AS $$
    UPDATE public.events_outbox
       SET published_at = now(),
           last_publish_error = NULL
     WHERE event_id = p_event_id
       AND occurred_at = p_occurred_at;
$$;

CREATE OR REPLACE FUNCTION public.outbox_record_failure(
    p_event_id uuid,
    p_occurred_at timestamptz,
    p_error text,
    p_max_attempts integer
)
RETURNS void
LANGUAGE sql
AS $$
    UPDATE public.events_outbox
       SET last_publish_error = p_error,
           dead_lettered_at = CASE
               WHEN publish_attempts >= GREATEST(p_max_attempts, 1) THEN now()
               ELSE NULL
           END
     WHERE event_id = p_event_id
       AND occurred_at = p_occurred_at;
$$;

-- Service role only; consumers run as service role.
REVOKE ALL ON FUNCTION public.outbox_claim_batch(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.outbox_mark_published(uuid, timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.outbox_record_failure(uuid, timestamptz, text, integer) FROM PUBLIC;

COMMIT;
