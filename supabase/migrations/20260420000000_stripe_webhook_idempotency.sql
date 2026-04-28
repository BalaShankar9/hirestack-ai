-- Stripe webhook event idempotency (mirrors database/migrations/20260420_stripe_webhook_idempotency.sql).
--
-- This file existed only in database/migrations/ before the S2 audit.
-- supabase db push reads from supabase/migrations/, so production never
-- received this table. backend/app/services/billing.py persists every
-- processed Stripe event_id here as the idempotency mechanism — without
-- the table, retries would double-grant subscriptions or fire duplicate
-- side effects.
--
-- The unique constraint on event_id is the actual idempotency lock; the
-- columns around it provide audit trail and a pruning anchor.
--
-- Idempotent — safe to re-run. Includes a NOTIFY so PostgREST picks up
-- the new table in its in-memory schema cache without a manual reload.

CREATE TABLE IF NOT EXISTS public.processed_webhook_events (
    event_id     TEXT PRIMARY KEY,
    event_type   TEXT NOT NULL,
    org_id       TEXT,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_processed_webhook_events_processed_at
    ON public.processed_webhook_events (processed_at DESC);

COMMENT ON TABLE public.processed_webhook_events IS
    'Idempotency ledger for Stripe (and future) webhook events. Rows older than 30 days may be deleted; Stripe redelivery window is < 30 days.';

-- Service-role-only ledger. End users must never read or write this
-- table; only the backend Stripe webhook handler (via service-role
-- key, which bypasses RLS) touches it. Enable RLS with no policies
-- so anon / authenticated roles get a deny-by-default.
ALTER TABLE public.processed_webhook_events ENABLE ROW LEVEL SECURITY;

NOTIFY pgrst, 'reload schema';
