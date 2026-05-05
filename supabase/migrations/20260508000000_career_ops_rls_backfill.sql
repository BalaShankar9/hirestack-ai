-- HireStack AI — career-ops RLS backfill
--
-- The original career-ops integration migration
-- (20260502000000_career_ops_integration.sql) shipped three tables without
-- RLS. The repository test `test_rls_coverage::test_every_public_table_has_rls_enabled`
-- requires every public table to enable RLS (default deny) plus an explicit
-- policy for any intentional read access. This migration backfills that
-- contract without changing application semantics.
--
--   * archetype_presets    — reference seed data; safe to expose read-only
--                            to anon + authenticated (used by marketing
--                            pages and signed-in dashboards alike).
--   * public_ghost_scans   — anonymized aggregate for the public Ghost
--                            Index; safe public read.
--   * job_scan_history     — internal repost-detection telemetry; service
--                            role only, no public policy (RLS-on with no
--                            policy = deny by default).

-- ── archetype_presets ────────────────────────────────────────────────
ALTER TABLE public.archetype_presets ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "archetype_presets_public_read" ON public.archetype_presets;
CREATE POLICY "archetype_presets_public_read" ON public.archetype_presets
    FOR SELECT USING (true);

-- ── public_ghost_scans ───────────────────────────────────────────────
ALTER TABLE public.public_ghost_scans ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public_ghost_scans_public_read" ON public.public_ghost_scans;
CREATE POLICY "public_ghost_scans_public_read" ON public.public_ghost_scans
    FOR SELECT USING (true);

-- ── job_scan_history ─────────────────────────────────────────────────
-- Service-role only (no SELECT/INSERT/UPDATE policy). RLS-on with zero
-- policies is "deny all" for anon + authenticated; the service role
-- bypasses RLS by design.
ALTER TABLE public.job_scan_history ENABLE ROW LEVEL SECURITY;
