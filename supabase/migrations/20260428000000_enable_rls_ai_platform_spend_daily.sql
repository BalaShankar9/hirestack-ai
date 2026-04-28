-- S2-F3: enable RLS deny-by-default on ai_platform_spend_daily.
--
-- This table is a platform-wide AI cost counter (one row per day,
-- aggregated globally). Only the backend service role writes to it
-- and only admin endpoints read it. End users must never see or
-- mutate it directly.
--
-- The original 20260420300000_usage_guard_tables.sql migration
-- enabled RLS on its sibling table ai_generation_usage_daily but
-- forgot this one. The S2 RLS audit caught the gap.
--
-- Idempotent — `ENABLE ROW LEVEL SECURITY` is a no-op if already on.

ALTER TABLE public.ai_platform_spend_daily ENABLE ROW LEVEL SECURITY;

NOTIFY pgrst, 'reload schema';
