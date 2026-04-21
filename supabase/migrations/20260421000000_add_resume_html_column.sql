-- Adds the resume_html column to applications so the tailored-resume document
-- (separate from the cv_html short-form CV) can be persisted by the generation
-- job runner.  Mirrors database/migrations/20260418_add_resume_html_column.sql
-- which was never copied into supabase/migrations/, so production was missing
-- the column and the job runner would PGRST204 on every persistence attempt.
--
-- Idempotent — safe to re-run.

ALTER TABLE public.applications
  ADD COLUMN IF NOT EXISTS resume_html TEXT;

NOTIFY pgrst, 'reload schema';
