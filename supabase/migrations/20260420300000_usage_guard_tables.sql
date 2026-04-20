-- ═══════════════════════════════════════════════════════════════════════
--  Usage Guard Tables (2026-04-20)
--  ---------------------------------------------------------------------
--  Adds two backstop cost-control surfaces that enforce caps regardless
--  of billing flag state:
--    1. ai_generation_usage_daily — per-user per-day generation counter
--    2. ai_platform_spend_daily   — platform-wide AI cost counter
--
--  These protect against:
--    • Solo users bypassing check_billing_limit (no org → no cap today)
--    • BILLING_ENABLED=false letting every request through
--    • Scripted abuse burning the AI budget in hours
--    • Viral moments exceeding planned monthly spend in a day
--
--  Idempotent: safe to re-apply.
-- ═══════════════════════════════════════════════════════════════════════

-- ── Per-user, per-day generation counter ──────────────────────────────
CREATE TABLE IF NOT EXISTS public.ai_generation_usage_daily (
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
    generation_count INTEGER NOT NULL DEFAULT 0,
    token_total BIGINT NOT NULL DEFAULT 0,
    cost_cents INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, usage_date)
);

CREATE INDEX IF NOT EXISTS idx_ai_gen_usage_date
    ON public.ai_generation_usage_daily(usage_date);

-- ── Platform-wide daily spend counter (singleton per day) ────────────
CREATE TABLE IF NOT EXISTS public.ai_platform_spend_daily (
    spend_date DATE PRIMARY KEY DEFAULT CURRENT_DATE,
    generation_count INTEGER NOT NULL DEFAULT 0,
    token_total BIGINT NOT NULL DEFAULT 0,
    cost_cents INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── RLS: users can only read their own usage rows ────────────────────
ALTER TABLE public.ai_generation_usage_daily ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can read own ai usage" ON public.ai_generation_usage_daily;
CREATE POLICY "Users can read own ai usage"
    ON public.ai_generation_usage_daily
    FOR SELECT
    USING (auth.uid() = user_id);

-- Service role (backend) writes via service key; no user-level insert/update policy
-- needed because RLS is bypassed with the service role key.

COMMENT ON TABLE public.ai_generation_usage_daily IS
    'Backstop per-user daily generation counter. Enforced by usage_guard.py regardless of billing flag.';
COMMENT ON TABLE public.ai_platform_spend_daily IS
    'Platform-wide daily AI-spend circuit breaker. Pauses generation when daily cap exceeded.';
