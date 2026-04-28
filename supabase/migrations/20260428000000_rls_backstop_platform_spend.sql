-- S2-F3: Backstop deny-by-default RLS on platform-wide service-role-only tables.
--
-- The S2 RLS audit (docs/audits/S2-data-migrations.md) found 1 of 70
-- tables in supabase/migrations/ without RLS enabled:
--
--   public.ai_platform_spend_daily — singleton-per-day platform cost
--   counter written by backend/app/services/usage_guard.py via the
--   service-role key. End users must never read or write it.
--
-- Without RLS enabled, a misconfigured anon-key request through PostgREST
-- could read or update the platform-wide spend counter, allowing an
-- attacker to either (a) reset the counter to bypass the daily cost
-- circuit-breaker, or (b) artificially trip it as a DoS.
--
-- Fix: enable RLS with no policies. Service-role bypasses RLS, so the
-- backend writer keeps working; anon / authenticated get deny-by-default.
--
-- Idempotent — safe to re-run.

ALTER TABLE public.ai_platform_spend_daily ENABLE ROW LEVEL SECURITY;

NOTIFY pgrst, 'reload schema';
