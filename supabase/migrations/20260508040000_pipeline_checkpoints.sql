-- Pipeline checkpoints for per-stage Temporal activity resume (ADR-0036, m8-pr32).
--
-- SAFETY: indexes created without CONCURRENTLY are safe here because the table
-- is brand new in this same migration (zero rows, zero locks of consequence).
-- ADR-0036 documents the rollout. CONCURRENTLY is required only for indexes
-- on already-populated tables.
--
-- Each row records one (job_id, stage) execution. The Temporal per-stage
-- workflow reads this table at the start of each activity to skip stages
-- already marked complete. Worker crash mid-pipeline => next attempt sees
-- the checkpoint, skips done stages, and resumes from the first
-- non-complete stage.
--
-- Stage names match runtime PHASE_SLO_MS keys: recon, atlas, cipher, quill,
-- forge, sentinel, nova. The `persist` runtime phase is folded into `nova`
-- for checkpointing (it has no independent skip-if-done semantics).
--
-- output_summary is JSONB capped at ~4KB by application policy so Temporal
-- activity history (which carries activity results) stays bounded. This is
-- enforced by CheckpointStore in app code, NOT by a CHECK constraint
-- (CHECK on JSONB length would fire even on legitimate writes during
-- migration).

CREATE TABLE IF NOT EXISTS public.pipeline_checkpoints (
  job_id          uuid        NOT NULL,
  stage           text        NOT NULL,
  status          text        NOT NULL,
  started_at      timestamptz NOT NULL DEFAULT now(),
  completed_at    timestamptz,
  attempt_count   integer     NOT NULL DEFAULT 1,
  output_summary  jsonb,
  error_class     text,
  PRIMARY KEY (job_id, stage),
  CONSTRAINT pipeline_checkpoints_status_chk
    CHECK (status IN ('running', 'complete', 'failed')),
  CONSTRAINT pipeline_checkpoints_attempt_chk
    CHECK (attempt_count >= 1)
);

-- Lookups are always (job_id, stage) PK reads or full-job scans.
CREATE INDEX IF NOT EXISTS pipeline_checkpoints_job_id_idx
  ON public.pipeline_checkpoints (job_id);

-- Diagnostic index on partial: surface failed checkpoints quickly.
CREATE INDEX IF NOT EXISTS pipeline_checkpoints_failed_idx
  ON public.pipeline_checkpoints (job_id, stage)
  WHERE status = 'failed';

ALTER TABLE public.pipeline_checkpoints ENABLE ROW LEVEL SECURITY;

-- Service role bypasses RLS. No INSERT/UPDATE policy for anon/authenticated
-- (deliberately blocks tampering). SELECT gated on job ownership.
DROP POLICY IF EXISTS pipeline_checkpoints_select_owner ON public.pipeline_checkpoints;
CREATE POLICY pipeline_checkpoints_select_owner
  ON public.pipeline_checkpoints
  FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1
      FROM public.generation_jobs gj
      WHERE gj.id = pipeline_checkpoints.job_id
        AND gj.user_id = auth.uid()
    )
  );

COMMENT ON TABLE public.pipeline_checkpoints IS
  'Per-stage Temporal activity checkpoints. ADR-0036, m8-pr32. Reads on job-stage skip if status=complete; otherwise the per-stage activity runs and writes back. Service role only writes.';
