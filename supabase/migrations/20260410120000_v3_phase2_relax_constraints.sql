-- HireStack AI v3 Phase 2 — Relax event sequence constraint for parallel pipelines
-- When multiple AgentPipelines run in parallel for the same job (e.g. CV + Cover Letter),
-- each has its own sequence counter. The strict UNIQUE(job_id, sequence_no) prevents
-- concurrent event writes. Replace with a softer ordering using the auto-increment id.

-- Drop old unique constraint
ALTER TABLE public.generation_job_events
  DROP CONSTRAINT IF EXISTS generation_job_events_job_id_sequence_no_key;

-- The primary ordering column is now the auto-incrementing `id`.
-- Keep index on (job_id, sequence_no) for efficient replay/filtering.
CREATE INDEX IF NOT EXISTS idx_generation_job_events_job_seq
  ON public.generation_job_events(job_id, sequence_no);

-- Add resume columns for restart recovery support
-- resume_from_stage: legacy single-pipeline resume marker (TEXT)
-- resume_from_stages: v3.1 per-pipeline resume markers (JSONB: { "cv_generation": "critic", ... })
ALTER TABLE public.generation_jobs
  ADD COLUMN IF NOT EXISTS resume_from_stage TEXT,
  ADD COLUMN IF NOT EXISTS resume_from_stages JSONB,
  ADD COLUMN IF NOT EXISTS recovery_attempts INTEGER NOT NULL DEFAULT 0;
