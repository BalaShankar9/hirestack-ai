-- Add recovery_attempts counter to generation_jobs for restart resilience.
-- When the server restarts mid-generation, jobs are re-queued up to 3 times
-- before being marked permanently failed.
ALTER TABLE public.generation_jobs
  ADD COLUMN IF NOT EXISTS recovery_attempts INTEGER NOT NULL DEFAULT 0;
