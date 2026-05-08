-- ═══════════════════════════════════════════════════════════════════════
--  ai_invocations — flight recorder for every LLM call (success OR failure)
--  ADR-0034 · PR m7-pr30 · 2026-05-08
--  ---------------------------------------------------------------------
--  One row per terminal LLM call. Forward-only — no backfill from logs.
--  Single non-partitioned table at launch; convert to range-partitioned
--  at Stage B trigger (~50M rows). Writer is best-effort; momentary
--  Postgres unavailability means missed rows by design — the LLM call
--  must never fail because the flight recorder did.
--
--  Schema rules:
--    * Prompt body is NEVER stored. ``prompt_hash`` is sha256-hex.
--    * No FKs to ``users`` / ``organizations`` — high write volume.
--    * Service role writes; tenants read their own rows via RLS.
--
--  Idempotent: safe to re-apply.
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.ai_invocations (
    id                       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                UUID        NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    task_type                TEXT        NULL,
    model                    TEXT        NOT NULL,
    provider                 TEXT        NOT NULL,
    prompt_hash              TEXT        NOT NULL,
    prompt_tokens            INTEGER     NOT NULL DEFAULT 0,
    completion_tokens        INTEGER     NOT NULL DEFAULT 0,
    total_tokens             INTEGER     NOT NULL DEFAULT 0,
    latency_ms               INTEGER     NOT NULL DEFAULT 0,
    outcome                  TEXT        NOT NULL,
    retry_count              INTEGER     NOT NULL DEFAULT 0,
    cascade_position         INTEGER     NOT NULL DEFAULT 0,
    flag_anthropic_enabled   BOOLEAN     NOT NULL DEFAULT FALSE,
    error_class              TEXT        NULL,
    error_message            TEXT        NULL,
    CONSTRAINT ai_invocations_outcome_chk
        CHECK (outcome IN ('success','failure','breaker_open','cascade_failover')),
    CONSTRAINT ai_invocations_provider_chk
        CHECK (provider IN ('gemini','anthropic','unknown'))
);

-- ── Indexes (kept minimal — write volume is high) ─────────────────────
CREATE INDEX IF NOT EXISTS idx_ai_invocations_tenant_created
    ON public.ai_invocations (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_invocations_model_created
    ON public.ai_invocations (model, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_invocations_outcome_created
    ON public.ai_invocations (outcome, created_at DESC)
    WHERE outcome <> 'success';

-- ── RLS ────────────────────────────────────────────────────────────────
ALTER TABLE public.ai_invocations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Tenants can read own invocations" ON public.ai_invocations;
CREATE POLICY "Tenants can read own invocations"
    ON public.ai_invocations
    FOR SELECT
    USING (tenant_id = auth.uid());

-- Service role bypasses RLS via service key; no INSERT policy needed.
-- We deliberately do NOT add an INSERT policy here so anon/authenticated
-- clients cannot poison the audit log directly.

COMMENT ON TABLE public.ai_invocations IS
    'ADR-0034 flight recorder: one row per terminal LLM call (success or failure). Forward-only.';
COMMENT ON COLUMN public.ai_invocations.prompt_hash IS
    'sha256-hex of (system||prompt). Body NEVER stored.';
COMMENT ON COLUMN public.ai_invocations.outcome IS
    'success | failure | breaker_open | cascade_failover';
COMMENT ON COLUMN public.ai_invocations.cascade_position IS
    '0-based index into the resolved cascade. 0 = primary route succeeded; >0 = failover.';
