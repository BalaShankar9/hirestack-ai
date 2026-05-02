-- ════════════════════════════════════════════════════════════════
-- 20260503000000_application_status_taxonomy.sql
-- F1 — extend applications.status taxonomy with career-ops-derived
-- semantics needed for the cadence engine and pattern insights.
--
-- Adds three values: responded, discarded, skip
--   responded  — recruiter replied (no interview scheduled yet);
--                unblocks the 1d/3d follow-up rule
--   discarded  — user closed the application for non-rejection
--                reasons (changed mind, role disappeared, comp too
--                low); semantically distinct from withdrawn
--   skip       — evaluated but never applied (system flagged ghost
--                or score < 4); powers the "self-filtered"
--                classification in pattern insights
--
-- Backwards-compatible: all existing values remain valid forever.
-- No data is rewritten by this migration; service-layer enum +
-- alias map (backend/app/models/application_status.py) handles
-- vocabulary mapping for read paths.
-- ════════════════════════════════════════════════════════════════

BEGIN;

ALTER TABLE public.applications
  DROP CONSTRAINT IF EXISTS chk_applications_status;

ALTER TABLE public.applications
  ADD CONSTRAINT chk_applications_status
  CHECK (status IN (
    'draft',
    'active',
    'submitted',
    'interview',
    'offer',
    'rejected',
    'withdrawn',
    'archived',
    -- F1 additions:
    'responded',
    'discarded',
    'skip'
  ));

COMMENT ON COLUMN public.applications.status IS
  'Application lifecycle status. Canonical values: draft|active|submitted|responded|interview|offer|rejected|discarded|skip|withdrawn|archived. submitted~=applied (legacy label); withdrawn~=discarded (legacy alias). New flows write the new vocab; old data stays valid.';

COMMIT;
