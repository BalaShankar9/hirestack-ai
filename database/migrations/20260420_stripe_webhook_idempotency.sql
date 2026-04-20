-- W8 follow-up: Stripe webhook event idempotency
--
-- Records every Stripe event we have processed so that retries
-- (Stripe redelivers, network blips, multi-instance races) do not
-- double-grant subscriptions or fire duplicate side effects.
--
-- The unique index on event_id is the actual idempotency mechanism;
-- the table just gives us audit trail + a way to expire old rows.
--
-- Safe to run multiple times.

CREATE TABLE IF NOT EXISTS processed_webhook_events (
    event_id    TEXT PRIMARY KEY,
    event_type  TEXT NOT NULL,
    org_id      TEXT,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_processed_webhook_events_processed_at
    ON processed_webhook_events (processed_at DESC);

-- Optional: cleanup helper. Stripe's redelivery window is < 30 days,
-- so anything older is safe to evict.
COMMENT ON TABLE processed_webhook_events IS
    'Idempotency ledger for Stripe (and future) webhook events. Rows older than 30 days may be deleted.';
