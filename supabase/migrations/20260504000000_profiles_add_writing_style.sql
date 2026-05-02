-- ════════════════════════════════════════════════════════════════
-- 20260504000000_profiles_add_writing_style.sql
-- V2 — writing-style calibration UX persistence.
--
-- Adds a JSONB column to public.profiles that caches the user's
-- derived writing-style signals (length bucket, tone, preferred
-- keywords) extracted from past pieces they paste into the Career
-- Nexus calibration panel.
--
-- The Drafter agent reads this blob via enriched_context so the
-- next pipeline run mirrors the user's own voice instead of the
-- generic baseline.
--
-- Pure-additive: NOT NULL DEFAULT '{}'::jsonb so existing rows are
-- unaffected and downstream code can read profile["writing_style"]
-- unconditionally.
-- ════════════════════════════════════════════════════════════════

BEGIN;

ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS writing_style jsonb NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.profiles.writing_style IS
  'V2 writing-style calibration: cached signals derived from user-supplied past pieces. Populated by POST /api/profile/{id}/writing-style/calibrate. Read by Drafter at run time.';

COMMIT;
