-- HireStack AI — Generation Job Events + Snapshot Fields
-- Persists a detailed append-only event log for long-running generation jobs.

ALTER TABLE public.generation_jobs
  ADD COLUMN IF NOT EXISTS current_agent TEXT,
  ADD COLUMN IF NOT EXISTS completed_steps INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS total_steps INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS active_sources_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS public.generation_job_events (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id UUID NOT NULL REFERENCES public.generation_jobs(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  application_id UUID NOT NULL REFERENCES public.applications(id) ON DELETE CASCADE,
  sequence_no INTEGER NOT NULL,
  event_name TEXT NOT NULL,
  agent_name TEXT,
  stage TEXT,
  status TEXT,
  message TEXT NOT NULL DEFAULT '',
  source TEXT,
  url TEXT,
  latency_ms INTEGER,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(job_id, sequence_no)
);

ALTER TABLE public.generation_job_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own generation job events" ON public.generation_job_events
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Service role full access on generation_job_events" ON public.generation_job_events
  FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_generation_job_events_job_sequence
  ON public.generation_job_events(job_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_generation_job_events_application_id
  ON public.generation_job_events(application_id);
CREATE INDEX IF NOT EXISTS idx_generation_job_events_user_id
  ON public.generation_job_events(user_id);

ALTER TABLE public.generation_job_events REPLICA IDENTITY FULL;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime'
      AND schemaname = 'public'
      AND tablename = 'generation_job_events'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.generation_job_events;
  END IF;
END
$$;
