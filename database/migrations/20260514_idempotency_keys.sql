-- PR m1-pr3: Idempotency-Key middleware ledger.
--
-- Records every idempotency-keyed POST/PATCH/DELETE so retries collapse
-- onto a single backend execution. The unique (org_id, key) primary
-- key is the dedupe mechanism; request_hash detects key reuse across
-- semantically different requests (→ 409).
--
-- Safe to run multiple times.

CREATE TABLE IF NOT EXISTS idempotency_keys (
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
    ON idempotency_keys (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_idempotency_keys_completed_at
    ON idempotency_keys (completed_at DESC)
    WHERE completed_at IS NOT NULL;

COMMENT ON TABLE idempotency_keys IS
    'PR m1-pr3: ledger for client-supplied Idempotency-Key headers on POST/PATCH/DELETE. '
    'Rows older than 24h may be evicted by a periodic sweep (PR-6 scheduler).';
