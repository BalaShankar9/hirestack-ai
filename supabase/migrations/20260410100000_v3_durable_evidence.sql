-- HireStack AI v3 — Durable Workflow Runtime + Evidence Ledger support
-- Adds workflow tracking columns and evidence storage to generation_jobs

-- Workflow runtime columns on generation_jobs
ALTER TABLE public.generation_jobs
  ADD COLUMN IF NOT EXISTS workflow_id TEXT,
  ADD COLUMN IF NOT EXISTS last_heartbeat_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS stage_timeouts JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS evidence_summary JSONB;

-- Evidence ledger storage per job (for audit and resumability)
CREATE TABLE IF NOT EXISTS public.evidence_ledger_items (
  pk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id TEXT NOT NULL,                     -- ev_<hash> content-based ID
  job_id UUID NOT NULL REFERENCES public.generation_jobs(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  tier TEXT NOT NULL CHECK (tier IN ('verbatim', 'derived', 'inferred', 'user_stated')),
  source TEXT NOT NULL CHECK (source IN ('profile', 'jd', 'company', 'tool', 'memory')),
  source_field TEXT NOT NULL DEFAULT '',
  evidence_text TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(job_id, id)
);

ALTER TABLE public.evidence_ledger_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own evidence items" ON public.evidence_ledger_items
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Service role full access on evidence_ledger_items" ON public.evidence_ledger_items
  FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_evidence_ledger_job_id
  ON public.evidence_ledger_items(job_id);
CREATE INDEX IF NOT EXISTS idx_evidence_ledger_user_id
  ON public.evidence_ledger_items(user_id);
CREATE INDEX IF NOT EXISTS idx_evidence_ledger_tier
  ON public.evidence_ledger_items(tier);

-- Citations table: links claims to evidence items
CREATE TABLE IF NOT EXISTS public.claim_citations (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id UUID NOT NULL REFERENCES public.generation_jobs(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  claim_text TEXT NOT NULL,
  evidence_ids TEXT[] NOT NULL DEFAULT '{}',
  classification TEXT NOT NULL DEFAULT '',
  confidence REAL NOT NULL DEFAULT 0,
  tier TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.claim_citations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own citations" ON public.claim_citations
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Service role full access on claim_citations" ON public.claim_citations
  FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_claim_citations_job_id
  ON public.claim_citations(job_id);

-- Add new event types to the event_name values commonly used
COMMENT ON TABLE public.generation_job_events IS
  'Append-only event log. v3 event types: workflow_start, stage_start, '
  'stage_complete, stage_failed, stage_timeout, stage_cancelled, heartbeat, '
  'workflow_complete, workflow_failed, artifact, evidence_populated, citation_created';
