-- PR m1-pr3: Idempotency-Key middleware ledger.
--
-- Records every idempotency-keyed POST/PATCH/DELETE so retries collapse
-- onto a single backend execution. The unique (org_id, key) primary
-- key is the dedupe mechanism; request_hash detects key reuse across
-- semantically different requests (→ 409).
--
-- Service-role-only table — RLS enabled with no policies for anon /
-- authenticated → deny-by-default. Idempotency middleware runs with
-- the service role key.
--
-- Mirror of database/migrations/20260514_idempotency_keys.sql,
-- consolidated under m9-pr33 (single migration root). RLS added in
-- the mirror to satisfy supabase-migrations RLS invariant.

BEGIN;

CREATE TABLE IF NOT EXISTS public.idempotency_keys (
    org_id        TEXT        NOT NULL,
    key           TEXT        NOT NULL,
    method        TEXT        NOT NULL,
    path          TEXT        NOT NULL,
    request_hash  TEXT        NOT NULL,
    status_code   INT,
    response_body BYTEA,
    response_headers JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMPTZ,
    PRIMARY KEY (org_id, key)
);

CREATE INDEX IF NOT EXISTS idx_idempotency_keys_created_at
    ON public.idempotency_keys (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_idempotency_keys_completed_at
    ON public.idempotency_keys (completed_at DESC)
    WHERE completed_at IS NOT NULL;

ALTER TABLE public.idempotency_keys ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS idempotency_keys_service_role_all
    ON public.idempotency_keys;
CREATE POLICY idempotency_keys_service_role_all
    ON public.idempotency_keys
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

COMMENT ON TABLE public.idempotency_keys IS
    'PR m1-pr3: ledger for client-supplied Idempotency-Key headers on POST/PATCH/DELETE. '
    'Rows older than 24h may be evicted by a periodic sweep (PR-6 scheduler).';

COMMIT;
