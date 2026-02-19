-- HireStack AI — Generation Jobs
-- Adds a DB-backed job record for long-running AI pipeline runs so the UI can
-- resume progress after refresh and support cancellation/retry without getting stuck.

CREATE TABLE IF NOT EXISTS public.generation_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  application_id UUID NOT NULL REFERENCES public.applications(id) ON DELETE CASCADE,

  -- Which modules were requested for this run (e.g. {benchmark,gaps,cv})
  requested_modules TEXT[] NOT NULL DEFAULT '{}'::text[],

  -- queued | running | succeeded | failed | cancelled
  status VARCHAR(20) NOT NULL DEFAULT 'queued',

  -- UI-friendly progress fields (0-100)
  progress INTEGER NOT NULL DEFAULT 0,
  phase TEXT,
  message TEXT,

  -- Cancellation flag checked between phases (best-effort)
  cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,

  -- Final response payload (same shape as /api/generate/pipeline response)
  result JSONB,
  error_message TEXT,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.generation_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own generation jobs" ON public.generation_jobs
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Service role full access on generation_jobs" ON public.generation_jobs
  FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_generation_jobs_user_id ON public.generation_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_generation_jobs_application_id ON public.generation_jobs(application_id);
CREATE INDEX IF NOT EXISTS idx_generation_jobs_status ON public.generation_jobs(status);

-- Keep updated_at in sync with the repo's shared trigger function.
DROP TRIGGER IF EXISTS update_generation_jobs_updated_at ON public.generation_jobs;
CREATE TRIGGER update_generation_jobs_updated_at
  BEFORE UPDATE ON public.generation_jobs
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- Realtime support (optional, but keeps local + prod behavior aligned)
ALTER TABLE public.generation_jobs REPLICA IDENTITY FULL;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime'
      AND schemaname = 'public'
      AND tablename = 'generation_jobs'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.generation_jobs;
  END IF;
END
$$;

