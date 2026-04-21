-- Phase D fix: separate variant bundles from version history.
--
-- D.2/D.3 originally wrote multi-style variant arrays into the
-- existing `cv_versions` / `ps_versions` JSONB columns, but those
-- columns were already in use by the frontend's snapshotDocVersion()
-- to store user-curated history snapshots (shape: {id, html, label,
-- createdAt}).  The two shapes are incompatible, so generation runs
-- were silently wiping a user's saved history.
--
-- Fix: dedicated `cv_variants` / `ps_variants` columns for the
-- style-variant bundles.  History snapshots stay in *_versions.

ALTER TABLE applications
  ADD COLUMN IF NOT EXISTS cv_variants JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS ps_variants JSONB DEFAULT '[]'::jsonb;

COMMENT ON COLUMN applications.cv_variants IS
  'Phase D.2 multi-style CV bundle: [{variant, label, content, locked, generated_at}]. '
  'Distinct from cv_versions (history snapshots).';
COMMENT ON COLUMN applications.ps_variants IS
  'Phase D.3 multi-style personal-statement bundle: [{variant, label, content, locked, generated_at}]. '
  'Distinct from ps_versions (history snapshots).';
